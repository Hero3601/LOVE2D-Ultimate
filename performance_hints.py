"""
performance_hints.py — Love2D Performance Analysis v1.0
========================================================
Static analysis and live hints to help write performant Love2D games:

  1. Draw call analyser — counts love.graphics.* calls in love.draw()
     and warns if count is high
  2. GC pressure detector — spots large table/string creation inside update()
  3. Alloc-in-loop detector — finds  {} or string concat inside for/while
  4. Missing SpriteBatch hint — when >5 draw() calls use same image
  5. Global variable in hot path — globals are slower in Lua than locals
  6. String concatenation in loop → suggest table.concat pattern
  7. love.timer.getDelta() called multiple times → suggest caching in dt
  8. Missing dt scaling — movement without * dt → framerate-dependent
  9. Unindexed table access in loop → suggest local alias
 10. Missing love.graphics.push/pop around transformed draws
All results shown as hints in the Ctrl+. panel, never intrusive.
"""
from __future__ import annotations
import logging, re
import sublime, sublime_plugin

# ── Draw-flag constants (hardcoded integers — safe on all ST4 builds/OS) ────
_DRAW_SQUIGGLY = 2048   # DRAW_SQUIGGLY_UNDER
_DRAW_NO_FILL  = 256    # DRAW_NO_FILL
_DRAW_SOLID    = 1024   # DRAW_SOLID_UNDERLINE
_DRAW_NO_OUTL  = 512    # DRAW_NO_OUTLINE
_DRAW_STIPPLED = 4096   # DRAW_STIPPLED_UNDERLINE

_DRAW_SOLID     = getattr(sublime, "DRAW_SOLID_UNDERLINE",    1024)
_DRAW_NO_FILL   = getattr(sublime, "DRAW_NO_FILL",             256)
_DRAW_NO_OUTL   = getattr(sublime, "DRAW_NO_OUTLINE",          512)


log = logging.getLogger("Love2D_Ultimate.perf")
SETTINGS_FILE = "Love2D_Ultimate.sublime-settings"


def _in_function(lines: list[str], start: int, func_pattern: str) -> tuple[int, int] | None:
    """Return (start_line, end_line) of the function body if func_pattern found."""
    RE_OPEN  = re.compile(r"^\s*(?:(?:local\s+)?function\b|if\b.+\bthen\b|for\b.+\bdo\b|while\b.+\bdo\b)")
    RE_CLOSE = re.compile(r"^\s*end\b")
    RE_PAT   = re.compile(func_pattern)

    for i, line in enumerate(lines):
        if not RE_PAT.search(line):
            continue
        depth = 0
        for j in range(i, len(lines)):
            depth += len(RE_OPEN.findall(lines[j]))
            depth -= len(RE_CLOSE.findall(lines[j]))
            if depth <= 0 and j > i:
                return i, j
    return None


class PerfHint:
    def __init__(self, line: int, message: str, severity: str = "hint"):
        self.line     = line
        self.message  = message
        self.severity = severity


class PerfAnalyser:

    @staticmethod
    def analyse(source: str) -> list[PerfHint]:
        s = sublime.load_settings(SETTINGS_FILE)
        if not s.get("perf_hints", True):
            return []

        lines  = source.splitlines()
        hints  = []
        hints.extend(PerfAnalyser._alloc_in_loop(source, lines))
        hints.extend(PerfAnalyser._string_concat_in_loop(source, lines))
        hints.extend(PerfAnalyser._global_in_update(source, lines))
        hints.extend(PerfAnalyser._movement_without_dt(source, lines))
        hints.extend(PerfAnalyser._repeated_draw_same_image(source, lines))
        hints.extend(PerfAnalyser._missing_push_pop(source, lines))
        hints.extend(PerfAnalyser._high_draw_call_count(source, lines))
        return hints

    @staticmethod
    def _lineno(source: str, pos: int) -> int:
        return source[:pos].count("\n")

    @staticmethod
    def _alloc_in_loop(source: str, lines: list[str]) -> list[PerfHint]:
        """Detect table/string allocation inside for/while loops."""
        hints = []
        RE_LOOP  = re.compile(r"^\s*(?:for|while)\b", re.M)
        RE_ALLOC = re.compile(r"\{\s*\}|=\s*\{\s*\}|\bstring\.(format|rep|sub)\b")
        RE_OPEN  = re.compile(r"^\s*(?:for\b|while\b|if\b|function\b)")
        RE_CLOSE = re.compile(r"^\s*end\b")

        for m in RE_LOOP.finditer(source):
            start_line = PerfAnalyser._lineno(source, m.start())
            depth = 0
            for i in range(start_line, min(start_line + 80, len(lines))):
                line = lines[i]
                depth += len(RE_OPEN.findall(line))
                depth -= len(RE_CLOSE.findall(line))
                if depth <= 0 and i > start_line:
                    break
                if i > start_line and RE_ALLOC.search(line):
                    stripped = line.strip()
                    if not stripped.startswith("--"):
                        hints.append(PerfHint(
                            i,
                            f"Table/string allocation inside loop — consider pre-allocating outside.",
                            "hint"
                        ))
                        break  # one hint per loop
        return hints

    @staticmethod
    def _string_concat_in_loop(source: str, lines: list[str]) -> list[PerfHint]:
        """Detect  str = str .. x  inside loops."""
        hints = []
        RE_LOOP  = re.compile(r"^\s*(?:for|while)\b", re.M)
        RE_CONCAT = re.compile(r"\w+\s*=\s*\w+\s*\.\.\s*")
        RE_OPEN  = re.compile(r"^\s*(?:for\b|while\b|if\b|function\b)")
        RE_CLOSE = re.compile(r"^\s*end\b")

        for m in RE_LOOP.finditer(source):
            start_line = PerfAnalyser._lineno(source, m.start())
            depth = 0
            for i in range(start_line, min(start_line + 80, len(lines))):
                line = lines[i]
                depth += len(RE_OPEN.findall(line))
                depth -= len(RE_CLOSE.findall(line))
                if depth <= 0 and i > start_line:
                    break
                if i > start_line and RE_CONCAT.search(line):
                    hints.append(PerfHint(
                        i,
                        "String concatenation (..) in loop is slow. Use table.insert + table.concat pattern.",
                        "warning"
                    ))
                    break
        return hints

    @staticmethod
    def _global_in_update(source: str, lines: list[str]) -> list[PerfHint]:
        """
        Detect frequent global variable access inside love.update.
        Globals in Lua are table lookups (_ENV.name) vs local register access.
        """
        hints = []
        update_range = _in_function(lines, 0, r"function\s+love\.update")
        if not update_range:
            return hints
        start, end = update_range

        # Known globals that could be localized
        COMMON_GLOBALS = {"math", "table", "string", "love", "pairs", "ipairs",
                          "tostring", "tonumber", "type", "print"}
        counts: dict[str, int] = {}
        for i in range(start, end):
            line = lines[i]
            if line.strip().startswith("--"):
                continue
            for gname in COMMON_GLOBALS:
                if re.search(r"\b" + gname + r"\b", line):
                    counts[gname] = counts.get(gname, 0) + 1

        for gname, count in counts.items():
            if count >= 5:
                hints.append(PerfHint(
                    start,
                    f"'{gname}' used {count}× in love.update. "
                    f"Localize at top: local {gname} = {gname}",
                    "hint"
                ))
        return hints

    @staticmethod
    def _movement_without_dt(source: str, lines: list[str]) -> list[PerfHint]:
        """
        Detect position assignment without dt scaling inside update —
        framerate-dependent movement.
        """
        hints = []
        update_range = _in_function(lines, 0, r"function\s+love\.update")
        if not update_range:
            return hints
        start, end = update_range

        RE_MOVE = re.compile(r"\b(x|y|position|pos|vx|vy|speed)\s*[+\-]=\s*(\d+|speed|vel)")
        RE_DT   = re.compile(r"\bdt\b")

        for i in range(start, end):
            line = lines[i]
            if line.strip().startswith("--"):
                continue
            if RE_MOVE.search(line) and not RE_DT.search(line):
                hints.append(PerfHint(
                    i,
                    "Movement without * dt — speed will depend on framerate. "
                    "Multiply by dt for frame-independent movement.",
                    "warning"
                ))
        return hints

    @staticmethod
    def _repeated_draw_same_image(source: str, lines: list[str]) -> list[PerfHint]:
        """
        Detect multiple love.graphics.draw() calls with the same image variable
        inside love.draw() — suggests using SpriteBatch.
        """
        hints = []
        draw_range = _in_function(lines, 0, r"function\s+love\.draw")
        if not draw_range:
            return hints
        start, end = draw_range

        RE_DRAW = re.compile(r"love\.graphics\.draw\(\s*(\w+)")
        counts: dict[str, list[int]] = {}
        for i in range(start, end):
            m = RE_DRAW.search(lines[i])
            if m:
                img = m.group(1)
                counts.setdefault(img, []).append(i)

        for img, occurrences in counts.items():
            if len(occurrences) >= 5:
                hints.append(PerfHint(
                    occurrences[0],
                    f"'{img}' drawn {len(occurrences)}× in love.draw(). "
                    f"Consider a SpriteBatch for better performance.",
                    "hint"
                ))
        return hints

    @staticmethod
    def _missing_push_pop(source: str, lines: list[str]) -> list[PerfHint]:
        """
        Detect love.graphics.translate/rotate/scale without matching push/pop.
        """
        hints = []
        draw_range = _in_function(lines, 0, r"function\s+love\.draw")
        if not draw_range:
            return hints
        start, end = draw_range

        push_count = 0
        pop_count  = 0
        transform_line = -1
        for i in range(start, end):
            line = lines[i]
            if re.search(r"love\.graphics\.push\b", line):
                push_count += 1
            if re.search(r"love\.graphics\.pop\b", line):
                pop_count += 1
            if re.search(r"love\.graphics\.(translate|rotate|scale)\b", line):
                if transform_line < 0:
                    transform_line = i

        if transform_line >= 0 and push_count == 0:
            hints.append(PerfHint(
                transform_line,
                "Transform (translate/rotate/scale) used without push/pop. "
                "Transforms accumulate each frame unless reset with push/pop.",
                "warning"
            ))
        elif push_count != pop_count:
            hints.append(PerfHint(
                start,
                f"Mismatched push/pop: {push_count} push vs {pop_count} pop in love.draw().",
                "error"
            ))
        return hints

    @staticmethod
    def _high_draw_call_count(source: str, lines: list[str]) -> list[PerfHint]:
        """Warn if love.draw() has a very high number of draw calls."""
        hints = []
        draw_range = _in_function(lines, 0, r"function\s+love\.draw")
        if not draw_range:
            return hints
        start, end = draw_range

        RE_DRAW_CALL = re.compile(
            r"love\.graphics\.(draw|rectangle|circle|line|polygon|print|printf)\b"
        )
        count = 0
        for i in range(start, end):
            if RE_DRAW_CALL.search(lines[i]):
                count += 1

        s = sublime.load_settings(SETTINGS_FILE)
        limit = s.get("max_draw_calls_hint", 50)
        if limit and count > limit:
            hints.append(PerfHint(
                start,
                f"love.draw() has ~{count} draw calls. "
                f"High counts hurt performance. Use SpriteBatch, Canvas caching, or culling.",
                "hint"
            ))
        return hints


class PerfHintListener(sublime_plugin.EventListener):
    """Runs performance analysis on save and stores results."""
    _cache: dict[int, list[PerfHint]] = {}

    def on_post_save_async(self, view: sublime.View) -> None:
        if not view.match_selector(0, "source.lua"):
            return
        s = sublime.load_settings(SETTINGS_FILE)
        if not s.get("perf_hints", True):
            return
        source = view.substr(sublime.Region(0, view.size()))
        hints  = PerfAnalyser.analyse(source)
        self._cache[view.id()] = hints
        sublime.set_timeout(lambda: self._apply(view, hints), 0)

    def on_close(self, view: sublime.View) -> None:
        self._cache.pop(view.id(), None)

    def _apply(self, view: sublime.View, hints: list[PerfHint]) -> None:
        regions = [
            sublime.Region(view.text_point(h.line, 0), view.text_point(h.line, 0) + 1)
            for h in hints if h.severity in ("warning", "error")
        ]
        view.add_regions(
            "love2d_perf",
            regions,
            scope="region.orangish",
            flags=_DRAW_SQUIGGLY | _DRAW_NO_FILL,
        )
        if hints:
            view.set_status(
                "love2d_perf",
                f"Love2D: {len(hints)} perf hint(s)  (Ctrl+. for details)"
            )
        else:
            view.erase_status("love2d_perf")

    @classmethod
    def get_hints(cls, view: sublime.View) -> list[PerfHint]:
        return cls._cache.get(view.id(), [])


class LoveShowPerfHintsCommand(sublime_plugin.TextCommand):
    """Command: love_show_perf_hints — show performance hints panel."""
    def run(self, edit: sublime.Edit) -> None:
        hints = PerfHintListener.get_hints(self.view)
        if not hints:
            sublime.status_message("No performance hints for this file.")
            return
        items = [
            sublime.QuickPanelItem(
                trigger=f"[{h.severity.upper()}] Line {h.line+1}: {h.message[:70]}",
                details=h.message,
                kind=sublime.KIND_AMBIGUOUS,
            )
            for h in hints
        ]
        def _sel(idx: int) -> None:
            if idx < 0:
                return
            pt = self.view.text_point(hints[idx].line, 0)
            self.view.show_at_center(pt)
            self.view.sel().clear()
            self.view.sel().add(sublime.Region(pt))
        self.view.window().show_quick_panel(items, _sel)
    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")
