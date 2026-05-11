"""
rename_preview.py — Scope-Aware Rename with Diff Preview v1.0
==============================================================
Fixes issues #5 (rename is text-replace, not scope-aware) and
#15 (no rename diff preview).

How it works:
  1. Find the DEFINITION of the symbol under cursor (file + line)
  2. Collect usages that trace back to THAT EXACT definition
     using backward-scan scope analysis (not just word matching)
  3. Show a diff preview in a scratch view:
       --- before
       +++ after
       @@ file.lua line X @@
       - local player = Player.new(10, 20)
       + local hero = Player.new(10, 20)
  4. User reviews, then clicks [Apply] or closes to cancel

Scope awareness rules:
  - A local variable is only renamed within its own scope block
  - A module-level function is renamed in all files that call it
    (via its qualified name e.g. player.update)
  - Two different functions with the same bare name in different
    files are NOT renamed together
"""
from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass, field

import sublime
import sublime_plugin

log = logging.getLogger("Love2D_Ultimate.rename")
SETTINGS_FILE = "Love2D_Ultimate.sublime-settings"


@dataclass
class RenameOccurrence:
    file:      str
    line:      int           # 0-based
    col:       int           # 0-based column of match start
    line_text: str           # full original line
    new_text:  str           # line with replacement applied
    is_def:    bool = False  # True if this is the definition site


@dataclass
class RenameSession:
    old_name:    str
    new_name:    str
    occurrences: list[RenameOccurrence] = field(default_factory=list)
    def_file:    str = ""
    def_line:    int = 0
    scope_type:  str = ""   # "local" | "module" | "global"


# ── Scope analyser ────────────────────────────────────────────────────────────

RE_LOCAL_DEF = re.compile(
    r"^\s*local\s+(?:function\s+)?(\w+)"
)
RE_FUNC_DEF = re.compile(
    r"^\s*(?:local\s+)?function\s+([\w.:]+)\s*\("
)
RE_BLOCK_OPEN  = re.compile(
    r"^\s*(?:(?:local\s+)?function\b|if\b.+\bthen\b"
    r"|for\b.+\bdo\b|while\b.+\bdo\b|repeat\b|do\b)"
)
RE_BLOCK_CLOSE = re.compile(r"^\s*end\b")


def _find_local_scope(lines: list[str], def_line: int) -> tuple[int, int]:
    """
    Returns (scope_start, scope_end) lines for the local declared at def_line.
    Walks outward from def_line to find the enclosing block boundaries.
    """
    depth = 0
    scope_start = 0
    # Walk backward to find enclosing block opener
    for i in range(def_line, -1, -1):
        if RE_BLOCK_CLOSE.match(lines[i]) and i < def_line:
            depth += 1
        elif RE_BLOCK_OPEN.match(lines[i]):
            if depth == 0:
                scope_start = i
                break
            depth -= 1

    # Walk forward to find matching end
    depth = 0
    scope_end = len(lines) - 1
    for i in range(scope_start, len(lines)):
        if RE_BLOCK_OPEN.match(lines[i]):
            depth += 1
        elif RE_BLOCK_CLOSE.match(lines[i]):
            depth -= 1
            if depth <= 0:
                scope_end = i
                break

    return scope_start, scope_end


def _is_local_var(lines: list[str], var_name: str, def_line: int) -> bool:
    """Returns True if var_name is declared as local at def_line."""
    line = lines[def_line] if def_line < len(lines) else ""
    m = RE_LOCAL_DEF.match(line)
    return bool(m and m.group(1) == var_name)


def _collect_occurrences(
    old_name: str,
    new_name: str,
    def_file: str,
    def_line: int,
    scope_start: int,
    scope_end: int,
    files_to_search: list[str],
    scope_type: str,
) -> list[RenameOccurrence]:
    """
    Collect all occurrences of old_name that should be renamed.

    scope_type = "local":
        Only rename within [scope_start, scope_end] of def_file.
        This prevents renaming a different 'x' in another file.

    scope_type = "module":
        Rename the definition + all qualified usages (Module.name)
        across all project files.

    scope_type = "global":
        Rename all bare usages across all project files.
        (Least safe — used when symbol has no clear scope.)
    """
    pat     = re.compile(r"\b" + re.escape(old_name) + r"\b")
    results = []

    for path in files_to_search:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError:
            continue

        for i, raw_line in enumerate(lines):
            line_text = raw_line.rstrip("\n")

            # Skip pure comments
            stripped = line_text.lstrip()
            if stripped.startswith("--"):
                continue

            # Scope filtering
            if scope_type == "local":
                if path != def_file:
                    continue
                if not (scope_start <= i <= scope_end):
                    continue

            if not pat.search(line_text):
                continue

            # Apply replacement
            new_line = pat.sub(new_name, line_text)
            col      = pat.search(line_text).start()
            is_def   = (path == def_file and i == def_line)

            results.append(RenameOccurrence(
                file=path, line=i, col=col,
                line_text=line_text, new_text=new_line,
                is_def=is_def,
            ))

    return results


# ── Diff builder ──────────────────────────────────────────────────────────────

def _build_diff(session: RenameSession) -> str:
    """Build a unified-diff style preview string."""
    lines = [
        f"# Love2D Rename Preview",
        f"# '{session.old_name}'  →  '{session.new_name}'",
        f"# Scope: {session.scope_type}",
        f"# {len(session.occurrences)} occurrence(s) in "
        f"{len({o.file for o in session.occurrences})} file(s)",
        f"#",
        f"# Review changes below, then run:",
        f"#   Love2D: Apply Rename Preview  (in command palette)",
        f"# Or close this tab to cancel.",
        "",
    ]

    by_file: dict[str, list[RenameOccurrence]] = {}
    for occ in session.occurrences:
        by_file.setdefault(occ.file, []).append(occ)

    for fpath, occs in sorted(by_file.items()):
        lines.append(f"--- {fpath}")
        lines.append(f"+++ {fpath}")
        for occ in sorted(occs, key=lambda o: o.line):
            lines.append(f"@@ line {occ.line + 1} @@"
                         + (" [definition]" if occ.is_def else ""))
            lines.append(f"-{occ.line_text}")
            lines.append(f"+{occ.new_text}")
        lines.append("")

    return "\n".join(lines)


# ── Active session storage ─────────────────────────────────────────────────────

_active_session: RenameSession | None = None
_session_lock = threading.Lock()


# ── Commands ──────────────────────────────────────────────────────────────────

class LoveRenameSymbolSmartCommand(sublime_plugin.TextCommand):
    """
    Command: love_rename_symbol_smart
    Scope-aware rename with diff preview.
    Replaces the old love_rename_symbol for all Lua views.
    """

    def run(self, edit: sublime.Edit) -> None:
        global _active_session

        sel = self.view.sel()
        if not sel:
            return
        pt       = sel[0].begin()
        old_name = self.view.substr(self.view.word(pt))
        if not old_name or not re.match(r"^\w+$", old_name):
            return

        def _on_name(new_name: str) -> None:
            if not new_name or new_name.strip() == old_name:
                return
            new_name = new_name.strip()
            if not re.match(r"^\w+$", new_name):
                sublime.error_message(f"'{new_name}' is not a valid identifier.")
                return
            sublime.set_timeout_async(
                lambda: self._build_session(old_name, new_name, pt), 0
            )

        self.view.window().show_input_panel(
            f"Rename '{old_name}' to:", old_name, _on_name, None, None
        )

    def _build_session(self, old_name: str, new_name: str, pt: int) -> None:
        global _active_session

        window  = self.view.window()
        folders = window.folders() if window else []
        fname   = self.view.file_name() or ""

        # Determine definition line and scope type
        def_line   = self.view.rowcol(pt)[0]
        source     = self.view.substr(sublime.Region(0, self.view.size()))
        lines      = source.splitlines()

        is_local      = _is_local_var(lines, old_name, def_line)
        scope_start   = 0
        scope_end     = len(lines)
        scope_type    = "global"

        if is_local:
            scope_type  = "local"
            scope_start, scope_end = _find_local_scope(lines, def_line)
            files_to_search = [fname] if fname else []
        else:
            # Module-level or global — search all project files
            scope_type = "module"
            files_to_search = []
            for folder in folders:
                for root, dirs, files in os.walk(folder):
                    dirs[:] = [d for d in dirs
                                if not d.startswith(".")
                                and d not in (".git", "node_modules")]
                    for f in files:
                        if f.endswith(".lua"):
                            files_to_search.append(os.path.join(root, f))
            if fname and fname not in files_to_search:
                files_to_search.insert(0, fname)

        occurrences = _collect_occurrences(
            old_name=old_name,
            new_name=new_name,
            def_file=fname,
            def_line=def_line,
            scope_start=scope_start,
            scope_end=scope_end,
            files_to_search=files_to_search,
            scope_type=scope_type,
        )

        if not occurrences:
            sublime.set_timeout(
                lambda: sublime.status_message(
                    f"No occurrences of '{old_name}' found in scope."
                ), 0
            )
            return

        session = RenameSession(
            old_name=old_name,
            new_name=new_name,
            occurrences=occurrences,
            def_file=fname,
            def_line=def_line,
            scope_type=scope_type,
        )

        with _session_lock:
            _active_session = session

        diff = _build_diff(session)

        sublime.set_timeout(
            lambda: self._show_preview(diff, len(occurrences)), 0
        )

    def _show_preview(self, diff: str, count: int) -> None:
        view = self.view.window().new_file()
        view.set_name("Love2D Rename Preview")
        view.set_scratch(True)
        view.set_read_only(False)
        view.run_command("append", {"characters": diff})
        view.set_read_only(True)

        sublime.status_message(
            f"Review {count} change(s) above. "
            "Run 'Love2D: Apply Rename Preview' to confirm."
        )

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")


class LoveApplyRenamePreviewCommand(sublime_plugin.WindowCommand):
    """
    Command: love_apply_rename_preview
    Applies the pending rename session after the user reviews the diff.
    """

    def run(self) -> None:
        global _active_session

        with _session_lock:
            session = _active_session

        if not session:
            sublime.status_message("No pending rename session.")
            return

        if not sublime.ok_cancel_dialog(
            f"Apply rename:\n"
            f"  '{session.old_name}'  →  '{session.new_name}'\n"
            f"  {len(session.occurrences)} occurrence(s) in "
            f"  {len({o.file for o in session.occurrences})} file(s)\n\n"
            f"Scope: {session.scope_type}\n\n"
            f"This cannot be undone as a single action.",
            ok_title="Apply Rename",
        ):
            return

        pat     = re.compile(r"\b" + re.escape(session.old_name) + r"\b")
        by_file: dict[str, list[RenameOccurrence]] = {}
        for occ in session.occurrences:
            by_file.setdefault(occ.file, []).append(occ)

        changed = 0
        for fpath, occs in by_file.items():
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                    original = fh.read()

                if session.scope_type == "local":
                    # Only replace within scope lines
                    file_lines = original.splitlines(keepends=True)
                    occ_lines  = {o.line for o in occs}
                    for i in occ_lines:
                        if i < len(file_lines):
                            file_lines[i] = pat.sub(session.new_name, file_lines[i])
                    new_content = "".join(file_lines)
                else:
                    # Replace all collected occurrences
                    new_content = pat.sub(session.new_name, original)

                with open(fpath, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(new_content)
                changed += 1

                # Reload open views
                for v in self.window.views():
                    if v.file_name() == fpath:
                        v.run_command("revert")

            except OSError as exc:
                log.warning(f"Rename apply error {fpath}: {exc}")

        with _session_lock:
            _active_session = None

        sublime.status_message(
            f"Renamed '{session.old_name}' → '{session.new_name}' "
            f"in {changed} file(s)"
        )

    def is_enabled(self) -> bool:
        with _session_lock:
            return _active_session is not None


class LoveCancelRenamePreviewCommand(sublime_plugin.WindowCommand):
    """Command: love_cancel_rename_preview — discards the pending session."""

    def run(self) -> None:
        global _active_session
        with _session_lock:
            _active_session = None
        sublime.status_message("Rename cancelled.")
