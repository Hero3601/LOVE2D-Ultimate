"""
smart_typing.py — Smart Typing Helpers v1.0
=============================================
Features:
  1. Auto-close:  (  [  {  "  '   →  inserts matching closer and positions cursor
  2. Auto-skip:   typing ) ] } " ' when already there → moves cursor over it
  3. Smart enter: pressing Enter inside  {}  or  ()  adds indented line + closer
  4. Auto-indent: after  then  do  repeat  function  → auto-indent next line
  5. Matching pair highlight: when cursor is on a bracket, highlight its pair
  6. Smart backspace: deletes both chars of an empty pair  ()  →  <nothing>
  7. String interpolation helper: inside strings, wraps selection in quotes
  8. Auto-add 'end' suggestion: when user types 'function ... ' and hits enter,
     offers to add matching 'end' as a completion item
"""
from __future__ import annotations

import logging
import re
import sublime

# ── Draw-flag constants (hardcoded integers — safe on all ST4 builds/OS) ────
_DRAW_SQUIGGLY = 2048   # DRAW_SQUIGGLY_UNDER
_DRAW_NO_FILL  = 256    # DRAW_NO_FILL
_DRAW_SOLID    = 1024   # DRAW_SOLID_UNDERLINE
_DRAW_NO_OUTL  = 512    # DRAW_NO_OUTLINE
_DRAW_STIPPLED = 4096   # DRAW_STIPPLED_UNDERLINE

import sublime_plugin
_DRAW_SOLID     = getattr(sublime, "DRAW_SOLID_UNDERLINE",    1024)
_DRAW_NO_FILL   = getattr(sublime, "DRAW_NO_FILL",             256)
_DRAW_NO_OUTL   = getattr(sublime, "DRAW_NO_OUTLINE",          512)


log = logging.getLogger("Love2D_Ultimate.smarttyping")
SETTINGS_FILE = "Love2D_Ultimate.sublime-settings"

PAIRS = {
    "(": ")",
    "[": "]",
    "{": "}",
    '"': '"',
    "'": "'",
}
CLOSERS    = set(PAIRS.values())
OPENERS    = set(PAIRS.keys())
STR_QUOTES = ('"', "'")


def _smart_typing_enabled() -> bool:
    return bool(sublime.load_settings(SETTINGS_FILE).get("smart_typing", True))


class LoveSmartTypingCommand(sublime_plugin.TextCommand):
    """
    Command: love_smart_typing
    Called from keybindings for  ( [ { " '  keys.
    Inserts the opener and its closer, positioning cursor between them.
    Skips if the next char is already the closer (avoids double-closing).
    """

    def run(self, edit: sublime.Edit, char: str) -> None:
        if not _smart_typing_enabled():
            self.view.run_command("insert", {"characters": char})
            return

        closer = PAIRS.get(char, "")
        view   = self.view

        new_sels = []
        for sel in reversed(list(view.sel())):
            if not sel.empty():
                # Wrap selection in the pair
                selected = view.substr(sel)
                view.replace(edit, sel, f"{char}{selected}{closer}")
                # Position after the inserted closer
                new_pt = sel.begin() + len(selected) + 2
                new_sels.append(sublime.Region(sel.begin() + 1,
                                               sel.begin() + 1 + len(selected)))
                continue

            pt = sel.begin()

            # If next char is already the closer, just move over it
            next_char = view.substr(sublime.Region(pt, pt + 1))
            if next_char == closer and char in STR_QUOTES:
                new_sels.append(sublime.Region(pt + 1))
                continue

            # Special: don't auto-close if next char is a word char
            if next_char.isalnum() or next_char == "_":
                view.insert(edit, pt, char)
                new_sels.append(sublime.Region(pt + 1))
                continue

            # Insert opener + closer, position cursor between them
            view.insert(edit, pt, f"{char}{closer}")
            new_sels.append(sublime.Region(pt + 1))

        if new_sels:
            view.sel().clear()
            for r in new_sels:
                view.sel().add(r)

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")


class LoveSmartBackspaceCommand(sublime_plugin.TextCommand):
    """
    Command: love_smart_backspace
    If cursor is between an empty pair  ()  []  {}  ""  ''
    delete both chars. Otherwise normal backspace.
    """

    def run(self, edit: sublime.Edit) -> None:
        view = self.view
        if not _smart_typing_enabled():
            view.run_command("left_delete")
            return

        deleted_pair = False
        for sel in reversed(list(view.sel())):
            if not sel.empty():
                continue
            pt        = sel.begin()
            prev_char = view.substr(sublime.Region(pt - 1, pt)) if pt > 0 else ""
            next_char = view.substr(sublime.Region(pt, pt + 1))
            if prev_char in PAIRS and PAIRS[prev_char] == next_char:
                view.erase(edit, sublime.Region(pt - 1, pt + 1))
                deleted_pair = True

        if not deleted_pair:
            view.run_command("left_delete")

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")


class LoveSmartSkipCloserCommand(sublime_plugin.TextCommand):
    """
    Command: love_smart_skip_closer
    When cursor is on  )  ]  }  and user types that char, skip over it.
    Bound to ) ] } keys.
    """

    def run(self, edit: sublime.Edit, char: str) -> None:
        view = self.view
        if not _smart_typing_enabled():
            view.run_command("insert", {"characters": char})
            return

        skipped = False
        for sel in reversed(list(view.sel())):
            if sel.empty():
                pt        = sel.begin()
                next_char = view.substr(sublime.Region(pt, pt + 1))
                if next_char == char:
                    view.sel().subtract(sel)
                    view.sel().add(sublime.Region(pt + 1))
                    skipped = True
                    continue
            view.run_command("insert", {"characters": char})

        if not skipped:
            view.run_command("insert", {"characters": char})

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")


class LoveSmartEnterCommand(sublime_plugin.TextCommand):
    """
    Command: love_smart_enter
    Smart newline handling:
      - Between  {  and  }  on same line: adds indented inner line + closer on next
      - After lines ending in  then  do  repeat  function ...: auto-indents
      - Otherwise: normal Enter
    """

    _BLOCK_OPENERS = re.compile(
        r"""(\bthen\b|\bdo\b|\brepeat\b|function\s*\(|function\s+\w+|=\s*function)""",
        re.IGNORECASE,
    )

    def run(self, edit: sublime.Edit) -> None:
        view = self.view
        if not _smart_typing_enabled():
            view.run_command("insert", {"characters": "\n"})
            return

        sel = view.sel()
        if not sel:
            view.run_command("insert", {"characters": "\n"})
            return

        pt          = sel[0].begin()
        line_region = view.line(pt)
        line_text   = view.substr(line_region)
        stripped    = line_text.strip()

        # Detect indentation of current line
        indent = len(line_text) - len(line_text.lstrip())
        tab_str = "\t" if view.settings().get("translate_tabs_to_spaces", False) is False else \
                  " " * view.settings().get("tab_size", 4)

        # Case: cursor between { and }
        prev_char = view.substr(sublime.Region(pt - 1, pt)) if pt > 0 else ""
        next_char = view.substr(sublime.Region(pt, pt + 1))
        if prev_char == "{" and next_char == "}":
            inner = f"\n{line_text[:indent]}{tab_str}\n{line_text[:indent]}"
            view.replace(edit, sublime.Region(pt, pt), inner)
            # Position cursor on the inner line
            new_pt = pt + len(f"\n{line_text[:indent]}{tab_str}")
            view.sel().clear()
            view.sel().add(sublime.Region(new_pt))
            return

        # Case: line ends with a block opener → indent next line
        if self._BLOCK_OPENERS.search(stripped) and not stripped.startswith("--"):
            new_indent = line_text[:indent] + tab_str
            view.insert(edit, pt, f"\n{new_indent}")
            return

        # Default
        view.run_command("insert", {"characters": "\n"})

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")


class SmartPairHighlighter(sublime_plugin.ViewEventListener):
    """
    Highlights the matching bracket/paren when cursor sits on one.
    Uses ST4's add_regions with a subtle underline.
    """

    @classmethod
    def is_applicable(cls, s: sublime.Settings) -> bool:
        return bool(sublime.load_settings(SETTINGS_FILE).get("smart_typing", True))

    def on_selection_modified_async(self) -> None:
        view = self.view
        if not view.match_selector(0, "source.lua"):
            return

        view.erase_regions("love2d_pair_match")

        sel = view.sel()
        if not sel or not sel[0].empty():
            return

        pt   = sel[0].begin()
        char = view.substr(sublime.Region(pt, pt + 1))

        OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}"}
        CLOSE_TO_OPEN = {v: k for k, v in OPEN_TO_CLOSE.items()}

        matched_pt = None

        if char in OPEN_TO_CLOSE:
            closer  = OPEN_TO_CLOSE[char]
            depth   = 0
            pos     = pt
            end     = view.size()
            while pos < end:
                c = view.substr(sublime.Region(pos, pos + 1))
                if c == char:
                    depth += 1
                elif c == closer:
                    depth -= 1
                    if depth == 0:
                        matched_pt = pos
                        break
                pos += 1

        elif char in CLOSE_TO_OPEN:
            opener  = CLOSE_TO_OPEN[char]
            depth   = 0
            pos     = pt
            while pos >= 0:
                c = view.substr(sublime.Region(pos, pos + 1))
                if c == char:
                    depth += 1
                elif c == opener:
                    depth -= 1
                    if depth == 0:
                        matched_pt = pos
                        break
                pos -= 1

        if matched_pt is not None:
            regions = [
                sublime.Region(pt, pt + 1),
                sublime.Region(matched_pt, matched_pt + 1),
            ]
            view.add_regions(
                "love2d_pair_match",
                regions,
                scope="region.bluish",
                flags=_DRAW_NO_FILL | _DRAW_NO_OUTL
                    | _DRAW_SOLID,
            )
