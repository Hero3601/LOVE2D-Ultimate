"""
breadcrumbs.py — Scope Navigation & Status Bar v1.0
=====================================================
Features:
  1. Status bar: shows current function scope  e.g.  love.update > Player:move
  2. Breadcrumb quick panel (Ctrl+Shift+B): jump to any scope in current file
  3. Symbol outline for current file (all functions, classes, variables)
  4. "Jump to matching function end" command
  5. Current scope highlight: dim non-current-function lines (optional)
  6. Next/prev function navigation (Alt+Up / Alt+Down)
"""
from __future__ import annotations

import logging
import re
import threading
import sublime
import sublime_plugin

log = logging.getLogger("Love2D_Ultimate.breadcrumbs")
SETTINGS_FILE = "Love2D_Ultimate.sublime-settings"

RE_FUNC = re.compile(
    r"^([ \t]*)(?:local\s+)?function\s+([\w.:]+)\s*\(([^)]*)\)",
    re.M,
)
RE_CLASS_NEW = re.compile(
    r"^[ \t]*local\s+(\w+)\s*=\s*\{\s*\}", re.M
)


def _functions_in_source(source: str) -> list[dict]:
    """Return list of {name, line, col, params, indent} for every function."""
    result = []
    for m in RE_FUNC.finditer(source):
        indent = len(m.group(1))
        name   = m.group(2)
        params = [p.strip() for p in m.group(3).split(",") if p.strip()]
        line   = source[:m.start()].count("\n")
        result.append({
            "name":   name,
            "line":   line,
            "indent": indent,
            "params": params,
        })
    return result


def _scope_at_line(funcs: list[dict], current_line: int) -> list[str]:
    """
    Returns the chain of function scopes containing current_line.
    e.g. ["love.update", "Player:move"]
    Uses indentation to determine nesting.
    """
    chain = []
    for fn in funcs:
        if fn["line"] <= current_line:
            chain.append(fn)
    # Keep only the deepest scope chain by indent
    result = []
    for fn in sorted(chain, key=lambda f: f["line"]):
        # Remove any scope with same or greater indent that came after
        result = [f for f in result if f["indent"] < fn["indent"]]
        result.append(fn)
    return [f["name"] for f in result]


class BreadcrumbListener(sublime_plugin.ViewEventListener):
    """Updates the status bar with the current function scope."""

    @classmethod
    def is_applicable(cls, s: sublime.Settings) -> bool:
        return bool(sublime.load_settings(SETTINGS_FILE).get("breadcrumbs", True))

    def __init__(self, view: sublime.View) -> None:
        super().__init__(view)
        self._funcs: list[dict] = []
        self._pending = False

    def on_load_async(self) -> None:
        self._rebuild()

    def on_post_save_async(self) -> None:
        self._rebuild()

    def on_selection_modified_async(self) -> None:
        if not self._pending:
            self._pending = True
            sublime.set_timeout(self._update_status, 80)

    def _rebuild(self) -> None:
        if not self.view.match_selector(0, "source.lua"):
            return
        source       = self.view.substr(sublime.Region(0, self.view.size()))
        self._funcs  = _functions_in_source(source)
        self._update_status()

    def _update_status(self) -> None:
        self._pending = False
        view = self.view
        if not view.match_selector(0, "source.lua"):
            return
        sel = view.sel()
        if not sel:
            return
        current_line = view.rowcol(sel[0].begin())[0]
        chain        = _scope_at_line(self._funcs, current_line)
        if chain:
            view.set_status("love2d_scope", " › ".join(chain))
        else:
            view.erase_status("love2d_scope")


class LoveBreadcrumbsCommand(sublime_plugin.TextCommand):
    """
    Command: love_breadcrumbs
    Shows a quick panel of all functions in the current file.
    The currently active scope is pre-selected.
    """

    def run(self, edit: sublime.Edit) -> None:
        source = self.view.substr(sublime.Region(0, self.view.size()))
        funcs  = _functions_in_source(source)
        if not funcs:
            sublime.status_message("No functions found in this file.")
            return

        sel          = self.view.sel()
        current_line = self.view.rowcol(sel[0].begin())[0] if sel else 0

        # Find pre-selected index
        preselect = 0
        for i, fn in enumerate(funcs):
            if fn["line"] <= current_line:
                preselect = i

        items = []
        for fn in funcs:
            indent_str  = "  " * (fn["indent"] // 4)
            params_str  = ", ".join(fn["params"])
            items.append(sublime.QuickPanelItem(
                trigger=f"{indent_str}{fn['name']}({params_str})",
                details=f"line {fn['line'] + 1}",
                kind=sublime.KIND_FUNCTION,
            ))

        def _sel(idx: int) -> None:
            if idx < 0:
                return
            fn = funcs[idx]
            pt = self.view.text_point(fn["line"], 0)
            self.view.show_at_center(pt)
            self.view.sel().clear()
            self.view.sel().add(sublime.Region(pt))

        self.view.window().show_quick_panel(
            items, _sel,
            selected_index=preselect,
            flags=sublime.MONOSPACE_FONT,
        )

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")


class LoveNextFunctionCommand(sublime_plugin.TextCommand):
    """Command: love_next_function — jump to the next function definition."""

    def run(self, edit: sublime.Edit) -> None:
        self._jump(direction=1)

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")

    def _jump(self, direction: int) -> None:
        source = self.view.substr(sublime.Region(0, self.view.size()))
        funcs  = _functions_in_source(source)
        if not funcs:
            return
        sel          = self.view.sel()
        current_line = self.view.rowcol(sel[0].begin())[0] if sel else 0

        target = None
        if direction > 0:
            for fn in funcs:
                if fn["line"] > current_line:
                    target = fn
                    break
        else:
            for fn in reversed(funcs):
                if fn["line"] < current_line:
                    target = fn
                    break

        if target:
            pt = self.view.text_point(target["line"], 0)
            self.view.show_at_center(pt)
            self.view.sel().clear()
            self.view.sel().add(sublime.Region(pt))


class LovePrevFunctionCommand(sublime_plugin.TextCommand):
    """Command: love_prev_function — jump to the previous function definition."""

    def run(self, edit: sublime.Edit) -> None:
        source = self.view.substr(sublime.Region(0, self.view.size()))
        funcs  = _functions_in_source(source)
        if not funcs:
            return
        sel          = self.view.sel()
        current_line = self.view.rowcol(sel[0].begin())[0] if sel else 0

        target = None
        for fn in reversed(funcs):
            if fn["line"] < current_line:
                target = fn
                break

        if target:
            pt = self.view.text_point(target["line"], 0)
            self.view.show_at_center(pt)
            self.view.sel().clear()
            self.view.sel().add(sublime.Region(pt))

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")


class LoveJumpToEndCommand(sublime_plugin.TextCommand):
    """
    Command: love_jump_to_end
    Jumps between a function/if/for declaration and its matching 'end'.
    Works bidirectionally — pressing the key again jumps back.
    """

    RE_OPEN  = re.compile(
        r"^\s*(?:(?:local\s+)?function\b|if\b.+\bthen\b|for\b.+\bdo\b"
        r"|while\b.+\bdo\b|repeat\b|do\b)"
    )
    RE_CLOSE = re.compile(r"^\s*end\b")

    def run(self, edit: sublime.Edit) -> None:
        view   = self.view
        sel    = view.sel()
        if not sel:
            return
        pt      = sel[0].begin()
        row, _  = view.rowcol(pt)
        lines   = view.substr(sublime.Region(0, view.size())).splitlines()

        current_line = lines[row] if row < len(lines) else ""

        if self.RE_OPEN.match(current_line):
            # Jump forward to matching end
            depth = 0
            for i in range(row, len(lines)):
                depth += 1 if self.RE_OPEN.match(lines[i]) else 0
                depth -= 1 if self.RE_CLOSE.match(lines[i]) else 0
                if depth <= 0 and i > row:
                    new_pt = view.text_point(i, 0)
                    view.show_at_center(new_pt)
                    view.sel().clear()
                    view.sel().add(sublime.Region(new_pt))
                    return

        elif self.RE_CLOSE.match(current_line):
            # Jump backward to matching opener
            depth = 0
            for i in range(row, -1, -1):
                depth += 1 if self.RE_CLOSE.match(lines[i]) else 0
                depth -= 1 if self.RE_OPEN.match(lines[i]) else 0
                if depth <= 0 and i < row:
                    new_pt = view.text_point(i, 0)
                    view.show_at_center(new_pt)
                    view.sel().clear()
                    view.sel().add(sublime.Region(new_pt))
                    return

        else:
            sublime.status_message("Not on a function/if/for/end line.")

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")
