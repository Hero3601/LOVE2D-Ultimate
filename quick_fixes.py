"""
quick_fixes.py — Smart Diagnostics (v1.1)
=========================================
Design philosophy:
  - NOTHING fires while you type. Zero on_modified interference.
  - Full analysis runs only on save (debounced 600ms after save).
  - Errors (bracket mismatch, extra/missing end) → red squiggly underline only.
    No LAYOUT_BELOW phantoms that push your code down while you work.
  - Warnings (typos) → status bar summary only. No inline noise.
  - Ctrl+. opens a quick panel listing everything with one-click fixes.
  - All regions + phantoms are cleared when the file is fixed and re-saved.
"""
from __future__ import annotations
import logging, re, threading
from dataclasses import dataclass, field
import sublime, sublime_plugin

# ── Draw-flag constants (hardcoded integers — safe on all ST4 builds/OS) ────
_DRAW_SQUIGGLY = 2048   # DRAW_SQUIGGLY_UNDER
_DRAW_NO_FILL  = 256    # DRAW_NO_FILL
_DRAW_SOLID    = 1024   # DRAW_SOLID_UNDERLINE
_DRAW_NO_OUTL  = 512    # DRAW_NO_OUTLINE
_DRAW_STIPPLED = 4096   # DRAW_STIPPLED_UNDERLINE


log = logging.getLogger("Love2D_Ultimate.quickfix")
SETTINGS_FILE = "Love2D_Ultimate.sublime-settings"

# ── Typo dictionaries ─────────────────────────────────────────────────────────
LOVE_TYPOS = {
    "love.grphics":   "love.graphics",
    "love.graphcis":  "love.graphics",
    "love.grpahics":  "love.graphics",
    "love.keyborad":  "love.keyboard",
    "love.filesytem": "love.filesystem",
    "love.filesystm": "love.filesystem",
    "love.audo":      "love.audio",
    "love.auido":     "love.audio",
    "love.physiscs":  "love.physics",
    "love.phyics":    "love.physics",
    "love.matth":     "love.math",
    "love.windwo":    "love.window",
    "love.wndow":     "love.window",
    "love.moues":     "love.mouse",
}
LUA_TYPOS = {
    "funciton": "function",
    "functoin": "function",
    "fucntion":  "function",
    "retrun":   "return",
    "retrn":    "return",
    "lcaol":    "local",
    "lcoal":    "local",
    "thne":     "then",
    "tehn":     "then",
    "elsief":   "elseif",
    "treu":     "true",
    "fasle":    "false",
    "ture":     "true",
    "flase":    "false",
}
ALL_TYPOS = {**LOVE_TYPOS, **LUA_TYPOS}

RE_BLOCK_OPEN = re.compile(
    r"^\s*(?:(?:local\s+)?function\b|if\b.+\bthen\b|for\b.+\bdo\b"
    r"|while\b.+\bdo\b|repeat\b|do\b)",
    re.MULTILINE,
)
RE_BLOCK_CLOSE = re.compile(r"^\s*end\b", re.MULTILINE)
RE_UNTIL       = re.compile(r"^\s*until\b", re.MULTILINE)


@dataclass
class Diagnostic:
    kind:        str
    message:     str
    line:        int
    col:         int
    end_col:     int
    severity:    str = "warning"   # "error" | "warning" | "info"
    fix_command: str = ""
    fix_args:    dict = field(default_factory=dict)


class LuaAnalyser:

    @staticmethod
    def analyse(source: str) -> list[Diagnostic]:
        lines = source.splitlines()
        s     = sublime.load_settings(SETTINGS_FILE)
        diags: list[Diagnostic] = []
        if s.get("qf_check_typos", True):
            diags.extend(LuaAnalyser._typos(lines))
        if s.get("qf_check_blocks", True):
            diags.extend(LuaAnalyser._block_balance(lines))
        if s.get("qf_check_brackets", True):
            diags.extend(LuaAnalyser._brackets(lines))
        return diags

    @staticmethod
    def _typos(lines: list[str]) -> list[Diagnostic]:
        diags = []
        for i, line in enumerate(lines):
            if line.strip().startswith("--"):
                continue
            for typo, correct in ALL_TYPOS.items():
                idx = line.lower().find(typo)
                if idx != -1:
                    diags.append(Diagnostic(
                        kind="typo",
                        message=f"Typo: '{typo}' — did you mean '{correct}'?",
                        line=i, col=idx, end_col=idx + len(typo),
                        severity="warning",
                        fix_command="love_fix_typo",
                        fix_args={"line": i, "col": idx,
                                  "typo": typo, "correct": correct},
                    ))
        return diags

    @staticmethod
    def _block_balance(lines: list[str]) -> list[Diagnostic]:
        depth = 0
        last_open = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("--"):
                continue
            depth += len(RE_BLOCK_OPEN.findall(line))
            depth -= len(RE_BLOCK_CLOSE.findall(line))
            depth -= len(RE_UNTIL.findall(line))
            if depth > 0:
                last_open = i
        if depth > 0:
            return [Diagnostic(
                kind="missing_end",
                message=f"Missing 'end' — {depth} block(s) unclosed.",
                line=last_open, col=0, end_col=0,
                severity="error",
                fix_command="love_fix_missing_end",
                fix_args={"count": depth},
            )]
        if depth < 0:
            return [Diagnostic(
                kind="extra_end",
                message=f"Extra 'end' — {-depth} too many.",
                line=len(lines) - 1, col=0, end_col=0,
                severity="error",
            )]
        return []

    @staticmethod
    def _brackets(lines: list[str]) -> list[Diagnostic]:
        """
        Fix #13: Skip multi-line strings [[ ]] and [=[ ]=],
        single-line strings, and comments before checking brackets.
        This eliminates all false positives from string content.
        """
        source = "\n".join(lines)
        n      = len(source)
        skip: set = set()  # character positions to ignore

        i = 0
        while i < n:
            c = source[i]

            # Long bracket strings and comments: [[ [=[ [==[ and --[[ --[=[
            is_comment = (c == "-" and i+1 < n and source[i+1] == "-")
            bracket_start = i+2 if is_comment else i
            if (c == "[" or is_comment) and bracket_start < n and source[bracket_start] == "[":
                level = 0
                j = bracket_start + 1
                while j < n and source[j] == "=":
                    level += 1
                    j += 1
                if j < n and source[j] == "[":
                    close = "]" + "=" * level + "]"
                    end_idx = source.find(close, j + 1)
                    if end_idx >= 0:
                        end_idx += len(close)
                        for k in range(i, end_idx):
                            skip.add(k)
                        i = end_idx
                        continue

            # Line comments  -- (non-block)
            if c == "-" and i+1 < n and source[i+1] == "-":
                end_idx = source.find("\n", i)
                end_idx = end_idx if end_idx >= 0 else n
                for k in range(i, end_idx):
                    skip.add(k)
                i = end_idx
                continue

            # Short strings  " or '
            if c in ('"', "'"):
                q = c
                k = i + 1
                while k < n:
                    if source[k] == "\\" and k+1 < n:
                        k += 2
                        continue
                    if source[k] == q:
                        for m in range(i, k+1):
                            skip.add(m)
                        i = k + 1
                        break
                    k += 1
                else:
                    i += 1
                continue

            i += 1

        # Scan for unmatched brackets, skipping noise positions
        stacks = {"(": [], "[": [], "{": []}
        pairs  = {")": "(", "]": "[", "}": "{"}
        diags  = []
        pos    = 0
        for row, line in enumerate(lines):
            for col, ch in enumerate(line):
                if pos not in skip:
                    if ch in stacks:
                        stacks[ch].append((row, col))
                    elif ch in pairs:
                        opener = pairs[ch]
                        if stacks[opener]:
                            stacks[opener].pop()
                        else:
                            diags.append(Diagnostic(
                                kind="bracket",
                                message=f"Unmatched closing '{ch}'",
                                line=row, col=col, end_col=col+1,
                                severity="error",
                            ))
                pos += 1
            pos += 1  # newline char

        for opener, stack in stacks.items():
            for (row, col) in stack:
                diags.append(Diagnostic(
                    kind="bracket",
                    message=f"Unmatched opening '{opener}'",
                    line=row, col=col, end_col=col+1,
                    severity="error",
                ))
        return diags[:8]



class QuickFixEngine:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "QuickFixEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        self._cache: dict[int, list[Diagnostic]] = {}   # vid → diags

    def run_on_save(self, view: sublime.View) -> None:
        """
        Called after every save.  Runs the full analysis and applies
        ONLY squiggly underlines (no LAYOUT_BELOW phantoms).
        Warnings go to the status bar summary only.
        """
        s = sublime.load_settings(SETTINGS_FILE)
        if not s.get("quick_fixes_enabled", True):
            self.clear_view(view)
            return

        source = view.substr(sublime.Region(0, view.size()))
        diags  = LuaAnalyser.analyse(source)
        self._cache[view.id()] = diags
        self._apply(view, diags)

    def clear_view(self, view: sublime.View) -> None:
        self._cache.pop(view.id(), None)
        view.erase_regions("love2d_errors")
        view.erase_regions("love2d_warnings")
        view.erase_status("love2d_diag")

    def show_panel(self, view: sublime.View) -> None:
        """Called by Ctrl+. — shows quick panel with all diagnostics."""
        diags = self._cache.get(view.id(), [])
        if not diags:
            sublime.status_message("Love2D: no issues found in this file.")
            return

        items = []
        for d in diags:
            icon = "ERR" if d.severity == "error" else "warn"
            items.append(sublime.QuickPanelItem(
                trigger=f"[{icon}] Line {d.line+1}: {d.message}",
                details="[Fix available]" if d.fix_command else "No auto-fix",
                kind=sublime.KIND_AMBIGUOUS,
            ))

        def _sel(idx: int) -> None:
            if idx < 0:
                return
            d  = diags[idx]
            pt = view.text_point(d.line, max(d.col, 0))
            view.show_at_center(pt)
            view.sel().clear()
            view.sel().add(sublime.Region(pt))
            if d.fix_command:
                view.run_command(d.fix_command, d.fix_args)

        view.window().show_quick_panel(items, _sel)

    def _apply(self, view: sublime.View, diags: list[Diagnostic]) -> None:
        """
        Apply ONLY squiggly underlines — no phantoms that push code down.
        Errors: red squiggly.  Warnings: yellow squiggly.
        Status bar shows the summary.
        """
        errors   = [d for d in diags if d.severity == "error"]
        warnings = [d for d in diags if d.severity == "warning"]

        def _region(d: Diagnostic) -> sublime.Region:
            a = view.text_point(d.line, max(d.col, 0))
            b = view.text_point(d.line, max(d.end_col, d.col + 1))
            return sublime.Region(a, b)

        view.add_regions(
            "love2d_errors",
            [_region(d) for d in errors],
            scope="region.redish",
            flags=_DRAW_SQUIGGLY | _DRAW_NO_FILL,
        )
        view.add_regions(
            "love2d_warnings",
            [_region(d) for d in warnings],
            scope="region.yellowish",
            flags=_DRAW_SQUIGGLY | _DRAW_NO_FILL,
        )

        # Compact status bar summary — not intrusive
        e = len(errors)
        w = len(warnings)
        if e or w:
            parts = []
            if e:
                parts.append(f"{e} error{'s' if e>1 else ''}")
            if w:
                parts.append(f"{w} warning{'s' if w>1 else ''}")
            view.set_status("love2d_diag", f"Love2D: {', '.join(parts)}  (Ctrl+. for fixes)")
        else:
            view.erase_status("love2d_diag")


# ─────────────────────────────────────────────────────────────────────────────
# Fix Commands
# ─────────────────────────────────────────────────────────────────────────────

class LoveFixTypoCommand(sublime_plugin.TextCommand):
    def run(self, edit: sublime.Edit, line: int = 0, col: int = 0,
            typo: str = "", correct: str = "") -> None:
        pt     = self.view.text_point(line, col)
        region = sublime.Region(pt, pt + len(typo))
        if self.view.substr(region).lower() == typo:
            self.view.replace(edit, region, correct)
            sublime.status_message(f"Fixed: '{typo}' -> '{correct}'")


class LoveFixMissingEndCommand(sublime_plugin.TextCommand):
    def run(self, edit: sublime.Edit, count: int = 1) -> None:
        eof    = self.view.size()
        suffix = "\n" + "\n".join(["end"] * count) + "\n"
        self.view.insert(edit, eof, suffix)
        sublime.status_message(f"Inserted {count} 'end'")


class LoveFixAddLocalCommand(sublime_plugin.TextCommand):
    def run(self, edit: sublime.Edit, line: int = 0) -> None:
        pt       = self.view.text_point(line, 0)
        region   = self.view.line(pt)
        text     = self.view.substr(region)
        stripped = text.lstrip()
        indent   = text[: len(text) - len(stripped)]
        self.view.replace(edit, region, f"{indent}local {stripped}")
        sublime.status_message("Added 'local'")


class LoveShowQuickFixesCommand(sublime_plugin.TextCommand):
    """Command bound to Ctrl+. — delegates to QuickFixEngine.show_panel()"""
    def run(self, edit: sublime.Edit) -> None:
        from Love2D_Ultimate.quick_fixes import QuickFixEngine
        QuickFixEngine.instance().show_panel(self.view)
    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")
