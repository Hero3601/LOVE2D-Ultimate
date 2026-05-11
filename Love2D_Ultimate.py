"""
Love2D Ultimate — Main Plugin v1.2
====================================
Critical fixes:
  - NEW CTX_DOT context: fires when user types  identifier.  or  identifier:
    Works with EMPTY prefix (dot just typed, nothing after it yet).
    Checks both simple-module vars (local x = require(...)) AND OOP classes.
  - Auto-trigger: completions appear immediately when you type  .  or  :
    without needing Ctrl+Space.
  - LOVE syntax package unblocked: INHIBIT flags only for contexts we own.
  - No on_modified diagnostics — nothing fires while you type.
"""
from __future__ import annotations
import logging, os, re, threading
import sublime, sublime_plugin

_indexer = _require_resolver = _oop_completion = _quick_fixes = None
log = logging.getLogger("Love2D_Ultimate")
log.setLevel(logging.DEBUG)

PLUGIN_NAME   = "Love2D_Ultimate"
SETTINGS_FILE = f"{PLUGIN_NAME}.sublime-settings"
LUA_SCOPE     = "source.lua"
STATUS_KEY    = "love2d_status"
INDEX_DEBOUNCE_MS = 600

# Context types
CTX_REQUIRE = "require"   # inside require("...")
CTX_SELF    = "self"      # self. or self:
CTX_DOT     = "dot"       # identifier. or identifier:  (module OR class)
CTX_GENERAL = "general"   # general prefix — don't inhibit LOVE syntax

# Regex for context detection
_RE_REQUIRE_OPEN = re.compile(r"""require\s*\(\s*['"][^'"]*$""")
_RE_SELF         = re.compile(r"""\bself[.:](\w*)$""")
# Matches   word.suffix   or   word:suffix   at end of line
# group(1) = identifier before dot/colon
# group(2) = what's been typed after dot (may be empty)
_RE_DOT_ACCESS   = re.compile(r"""\b(\w+)([.:])(\w*)$""")  # group 2 = separator

# Lua/Love built-in globals that the LOVE syntax package handles —
# we never claim ownership of these in CTX_DOT
_LOVE_BUILTINS = {
    "love", "math", "table", "string", "io", "os", "coroutine",
    "package", "debug", "bit", "jit", "ffi", "utf8",
    "pairs", "ipairs", "print", "type", "tostring", "tonumber",
    "setmetatable", "getmetatable", "rawget", "rawset",
}


def plugin_loaded():
    global _indexer, _require_resolver, _oop_completion, _quick_fixes

    h = _SublimeConsoleHandler()
    h.setFormatter(logging.Formatter("[%(name)s] %(levelname)s: %(message)s"))
    logging.getLogger("Love2D_Ultimate").addHandler(h)
    log.info(f"{PLUGIN_NAME} loading ...")

    from Love2D_Ultimate.symbol_indexer   import SymbolIndexer
    from Love2D_Ultimate.require_resolver import RequireResolver
    from Love2D_Ultimate.oop_completion   import OopCompletionEngine
    from Love2D_Ultimate.quick_fixes      import QuickFixEngine
    from Love2D_Ultimate.auto_installer   import DependencyChecker

    _indexer          = SymbolIndexer.instance()
    _require_resolver = RequireResolver.instance()
    _oop_completion   = OopCompletionEngine.instance()
    _quick_fixes      = QuickFixEngine.instance()

    sublime.set_timeout_async(_bootstrap_async, 300)
    log.info(f"{PLUGIN_NAME} loaded.")


def plugin_unloaded():
    if _indexer:
        _indexer.shutdown()
    log.info(f"{PLUGIN_NAME} unloaded.")


def _bootstrap_async():
    try:
        from Love2D_Ultimate.lsp_config import ensure_lsp_configured
        ensure_lsp_configured()
    except Exception as exc:
        log.warning(f"LSP skipped: {exc}")
    for w in sublime.windows():
        if _indexer:
            _indexer.index_window(w)
    sublime.set_timeout_async(_check_legacy_packages, 1500)
    # Auto-installer: check for missing deps and prompt user
    try:
        from Love2D_Ultimate.auto_installer import DependencyChecker
        for w in sublime.windows():
            DependencyChecker.instance().run_startup_check(w)
            break
    except Exception as exc:
        log.debug(f"Auto-installer skipped: {exc}")


def _check_legacy_packages():
    conflicts = [
        p for p in ("Lovely2d", "sublime_love", "luaLove", "LuaLove", "LOVELY2D")
        if os.path.isdir(os.path.join(sublime.packages_path(), p))
    ]
    if conflicts:
        sublime.message_dialog(
            f"Love2D Ultimate: legacy package(s) found: {', '.join(conflicts)}.\n"
            "Run 'Love2D: Migrate from Legacy Packages' to disable them."
        )


def settings():
    return sublime.load_settings(SETTINGS_FILE)


def is_lua_view(view):
    return bool(view and view.match_selector(0, LUA_SCOPE))


def get_word_at(view, point):
    return view.substr(view.word(point))


def get_line_to_cursor(view, point):
    lr = view.line(point)
    return view.substr(sublime.Region(lr.a, point))


class _SublimeConsoleHandler(logging.Handler):
    def emit(self, record):
        try:
            print(self.format(record))
        except Exception:
            pass


def _classify_context(view, pt, line):
    """
    Returns (context_type, identifier, separator).

    separator is "." or ":" — the character the user typed.
    This is critical: module.  must only show dot members,
                     module:  must only show colon methods.

    CTX_REQUIRE — cursor inside require("...")
    CTX_SELF    — line ends with  self.xxx  or  self:xxx
    CTX_DOT     — line ends with  word.xxx  or  word:xxx
                  for a require()'d var or known OOP class we own.
    CTX_GENERAL — everything else, don't inhibit LOVE syntax.
    """
    # 1. require("...")
    if _RE_REQUIRE_OPEN.search(line):
        return CTX_REQUIRE, "", ""

    # 2. self. / self:
    ms = _RE_SELF.search(line)
    if ms:
        # Detect which separator self used
        sep = ":" if ":" in line[ms.start():ms.end()] else "."
        return CTX_SELF, "self", sep

    # 3. word. / word:  — group(1)=identifier, group(2)=separator, group(3)=prefix
    m = _RE_DOT_ACCESS.search(line)
    if m:
        identifier = m.group(1)
        separator  = m.group(2)   # "." or ":"

        # Never claim Lua/Love built-ins — let LOVE syntax handle these
        if identifier in _LOVE_BUILTINS:
            return CTX_GENERAL, "", ""

        # Check if it's a require()'d variable in this view
        if _is_require_var(view, identifier):
            return CTX_DOT, identifier, separator

        # Check if it's a known user-defined OOP class
        if _oop_completion and _oop_completion.is_known_class(view, identifier):
            return CTX_DOT, identifier, separator

        # Check if it's an INSTANCE of a class (p = Player.new() or player:new())
        # _resolve_var_class returns the class/module name if found.
        # This is what makes  p.  and  p:  work after  p = player:new()
        if _indexer and _indexer._resolve_var_class(view, identifier):
            return CTX_DOT, identifier, separator

    return CTX_GENERAL, "", ""


def _is_require_var(view, var_name: str) -> bool:
    """
    Returns True if  [local] var_name = require(...)  exists anywhere
    in the current view's source.
    Matches BOTH:
        local ultimate = require("modules/ultimate")
        ultimate = require("modules/ultimate")
    """
    source = view.substr(sublime.Region(0, view.size()))
    pat = re.compile(
        r"""(?:local\s+)?""" + re.escape(var_name) +
        r"""\s*=\s*require\s*\(\s*['"][^'"]+['"]\s*\)"""
    )
    return bool(pat.search(source))


# ─────────────────────────────────────────────────────────────────────────────
class Love2DEventListener(sublime_plugin.EventListener):

    _save_timers = {}

    def on_load_async(self, view):
        if not is_lua_view(view):
            return
        self._index_view(view)
        self._refresh_status(view)

    def on_activated_async(self, view):
        if is_lua_view(view):
            self._refresh_status(view)

    def on_post_save_async(self, view):
        if not is_lua_view(view):
            return
        vid = view.id()
        t = self._save_timers.pop(vid, None)
        if t:
            t.cancel()

        def _do():
            self._index_view(view)
            if _quick_fixes:
                _quick_fixes.run_on_save(view)
            self._refresh_status(view)

        t2 = threading.Timer(
            INDEX_DEBOUNCE_MS / 1000,
            lambda: sublime.set_timeout_async(_do, 0)
        )
        self._save_timers[vid] = t2
        t2.start()

    def on_modified_async(self, view):
        """
        Auto-trigger completions when user types  .  or  :
        after a known require()'d variable or OOP class.
        This is what makes the dropdown appear WITHOUT pressing Ctrl+Space.
        Only fires for the specific dot/colon after known identifiers —
        never for general typing — so it doesn't hurt performance.
        """
        if not is_lua_view(view):
            return

        sel = view.sel()
        if not sel:
            return
        pt = sel[0].begin()
        if pt < 1:
            return

        # Check the character that was just typed
        last_char = view.substr(sublime.Region(pt - 1, pt))
        if last_char not in (".", ":"):
            return

        # Get the identifier before the dot/colon
        # We need the word immediately before pt-1
        word_region = view.word(pt - 2) if pt >= 2 else None
        if not word_region:
            return
        identifier = view.substr(word_region).strip()
        if not identifier or not identifier.isidentifier():
            return

        # Only auto-trigger if this identifier is something we know about:
        # a require()'d variable OR a known OOP class.
        # Never fire for love, math, table, string (handled by LOVE syntax).
        if identifier in _LOVE_BUILTINS:
            return

        should_trigger = False

        # 'self' is ALWAYS a valid trigger inside any Lua class method.
        # It's never assigned via require() or .new() so the normal checks
        # all fail — but we always have completions for self. and self:
        if identifier == "self":
            should_trigger = True
        elif _is_require_var(view, identifier):
            should_trigger = True
        elif _oop_completion and _oop_completion.is_known_class(view, identifier):
            should_trigger = True
        elif _indexer and _indexer._resolve_var_class(view, identifier):
            # Instance variable:  p = player:new()  or  p = Player.new()
            should_trigger = True

        if should_trigger:
            sublime.set_timeout(lambda: view.run_command("auto_complete"), 0)

    def on_close(self, view):
        vid = view.id()
        t = self._save_timers.pop(vid, None)
        if t:
            t.cancel()
        if _quick_fixes:
            _quick_fixes.clear_view(view)

    def on_new_window_async(self, window):
        if _indexer:
            _indexer.index_window(window)

    # ── COMPLETIONS — the heart of the package ────────────────────────────────

    def on_query_completions(self, view, prefix, locations):
        if not is_lua_view(view) or not locations:
            return None

        pt   = locations[0]
        line = get_line_to_cursor(view, pt)

        ctx, identifier, separator = _classify_context(view, pt, line)

        # ── require("...") ────────────────────────────────────────────────────
        if ctx == CTX_REQUIRE:
            items = []
            try:
                if _require_resolver:
                    items = _require_resolver.completions_for(view, pt, line)
            except Exception as exc:
                log.debug(f"require completions: {exc}")
            if items:
                return sublime.CompletionList(
                    items,
                    flags=sublime.INHIBIT_WORD_COMPLETIONS
                        | sublime.INHIBIT_EXPLICIT_COMPLETIONS,
                )
            return None

        # ── self. / self: ─────────────────────────────────────────────────────
        # separator tells us which side of self the user typed.
        # self:  → colon methods only (exclude dot functions/fields)
        # self.  → dot functions + fields only (exclude colon methods)
        if ctx == CTX_SELF:
            items = []
            try:
                if _oop_completion:
                    items = _oop_completion.completions_for(
                        view, pt, line, prefix,
                        colon_only=(separator == ":"),
                        dot_only=(separator == "."),
                    )
            except Exception as exc:
                log.debug(f"self completions: {exc}")
            # Always return with INHIBIT — we own self context completely.
            # Empty list = blank dropdown (no junk leaks through).
            return sublime.CompletionList(
                items,
                flags=sublime.INHIBIT_WORD_COMPLETIONS
                    | sublime.INHIBIT_EXPLICIT_COMPLETIONS,
            )

        # ── identifier. or identifier: ────────────────────────────────────────
        # ALWAYS inhibit here — we own this context.
        # Pass separator so module_member_completions filters correctly:
        #   player.  → only dot functions + fields
        #   player:  → only colon methods
        # If no members match, returns [] which gives a blank dropdown.
        # That is CORRECT — no junk from All Autocomplete should ever appear
        # after a known module variable.
        if ctx == CTX_DOT:
            items = []
            try:
                if _indexer:
                    items = _indexer.module_member_completions(
                        view, identifier, prefix, separator
                    )
                # Fallback to OOP engine if indexer returns nothing
                if not items and _oop_completion:
                    items = _oop_completion.completions_for(
                        view, pt, line, prefix,
                        colon_only=(separator == ":"),
                        dot_only=(separator == "."),
                    )
            except Exception as exc:
                log.debug(f"dot '{identifier}{separator}': {exc}")

            return sublime.CompletionList(
                items,
                flags=sublime.INHIBIT_WORD_COMPLETIONS
                    | sublime.INHIBIT_EXPLICIT_COMPLETIONS,
            )

        # ── general: add our symbols, never inhibit LOVE syntax ───────────────
        if not prefix or len(prefix) < 2:
            return None

        items = []
        try:
            if _indexer:
                items = _indexer.completions_for(view, pt, line, prefix)
        except Exception as exc:
            log.debug(f"general completions: {exc}")

        if not items:
            return None

        seen = set()
        deduped = []
        for item in items:
            k = item.trigger if hasattr(item, "trigger") else str(item)
            if k not in seen:
                seen.add(k)
                deduped.append(item)

        return sublime.CompletionList(deduped, flags=0)

    # ── Hover ─────────────────────────────────────────────────────────────────

    def on_hover(self, view, point, hover_zone):
        if not is_lua_view(view):
            return
        if hover_zone != sublime.HOVER_TEXT:
            return
        if not settings().get("hover_docs_enabled", True):
            return
        sublime.set_timeout_async(lambda: self._do_hover(view, point), 0)

    def _do_hover(self, view, point):
        word = get_word_at(view, point)
        if not word or len(word) < 2:
            return
        html = None
        if _indexer:
            html = _indexer.hover_html_for(view, point, word)
        if not html and _oop_completion:
            html = _oop_completion.hover_html_for(view, point, word)
        if html:
            view.show_popup(
                html,
                flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
                location=point,
                max_width=700, max_height=320,
            )

    def _index_view(self, view):
        if not view.file_name():
            return
        source = view.substr(sublime.Region(0, view.size()))
        if _indexer:
            _indexer.index_file(view.file_name(), source)
        if _oop_completion:
            _oop_completion.index_file(view.file_name(), source)
        # Inject auto_complete_triggers so ST4 shows completions on . and :
        # without requiring Ctrl+Space. Merges with any existing triggers.
        self._ensure_auto_complete_triggers(view)

    def _ensure_auto_complete_triggers(self, view):
        """
        Tell ST4 to auto-show completions when . or : is typed in Lua files.
        This is a view-level setting — safe to call on every load/save.
        """
        existing = view.settings().get("auto_complete_triggers") or []
        lua_trigger = {"selector": "source.lua", "characters": ".:"}
        # Only add if not already present
        for t in existing:
            if t.get("selector") == "source.lua" and "." in t.get("characters", ""):
                return  # already set
        existing.append(lua_trigger)
        view.settings().set("auto_complete_triggers", existing)

    def _refresh_status(self, view):
        if _indexer:
            view.set_status(STATUS_KEY, f"Love2D: {_indexer.symbol_count()} symbols")
        else:
            view.set_status(STATUS_KEY, "Love2D: ready")


# ─────────────────────────────────────────────────────────────────────────────
class Love2DPhantomManager(sublime_plugin.ViewEventListener):
    @classmethod
    def is_applicable(cls, s):
        return bool(sublime.load_settings(SETTINGS_FILE).get("inline_type_hints", False))

    def __init__(self, view):
        super().__init__(view)
        self._ps      = sublime.PhantomSet(view, "love2d_type_hints")
        self._pending = False

    def on_post_save_async(self):
        if not self._pending:
            self._pending = True
            sublime.set_timeout_async(self._update, 400)

    def _update(self):
        self._pending = False
        if not is_lua_view(self.view) or not _indexer:
            return
        try:
            self._ps.update(_indexer.type_hint_phantoms(self.view))
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

class LoveRequireStripLuaCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if _require_resolver:
            _require_resolver.strip_all_in_view(self.view, edit)
    def is_enabled(self):
        return is_lua_view(self.view)


class LoveGotoDefinitionCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if not _indexer: return
        sel = self.view.sel()
        if sel:
            _indexer.goto_definition(
                self.view.window(), self.view,
                get_word_at(self.view, sel[0].begin()), sel[0].begin()
            )
    def is_enabled(self):
        return is_lua_view(self.view)


class LoveFindUsagesCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if not _indexer: return
        sel = self.view.sel()
        if not sel: return
        word = get_word_at(self.view, sel[0].begin())
        results = _indexer.find_usages(self.view, word)
        if not results:
            sublime.status_message(f"No usages found for '{word}'")
            return
        self.view.window().run_command(
            "love_show_usages_panel", {"usages": results, "symbol": word}
        )
    def is_enabled(self):
        return is_lua_view(self.view)


class LoveShowUsagesPanelCommand(sublime_plugin.WindowCommand):
    def run(self, usages, symbol):
        items = [
            sublime.QuickPanelItem(
                trigger=f"{os.path.basename(u.get('file','?'))}:{u.get('line',0)+1}",
                details=u.get("snippet","").strip()[:80],
                annotation=symbol, kind=sublime.KIND_NAVIGATION,
            )
            for u in usages
        ]
        def _sel(idx):
            if idx < 0: return
            u = usages[idx]
            f = u.get("file")
            if f:
                self.window.open_file(f"{f}:{u.get('line',0)+1}:1", sublime.ENCODED_POSITION)
        self.window.show_quick_panel(items, _sel, flags=sublime.MONOSPACE_FONT)


class LoveSymbolPickerCommand(sublime_plugin.WindowCommand):
    """
    Fix #14: Symbol picker supports scoped search syntax:
      (empty)         → all symbols, MRU sorted
      upd             → symbols starting with "upd" anywhere
      @player         → symbols only from files named "player"
      @player:upd     → symbols from player file starting with "upd"
      @:upd           → symbols starting with "upd" from all files

    Type the filter directly in the quick panel input.
    """
    def run(self, scope_filter: str = "") -> None:
        self._show(scope_filter)

    def _show(self, scope_filter: str = "") -> None:
        if not _indexer:
            return
        syms = _indexer.all_symbols_for_window(self.window, scope_filter)
        if not syms and not scope_filter:
            sublime.status_message("No symbols indexed yet.")
            return

        km = {"function": sublime.KIND_FUNCTION, "variable": sublime.KIND_VARIABLE,
              "class": sublime.KIND_TYPE, "module": sublime.KIND_NAMESPACE}
        items = []
        for s in syms:
            fname = os.path.basename(s.get("file", ""))
            usages = s.get("usages", 0)
            items.append(sublime.QuickPanelItem(
                trigger=s["name"],
                details=f"{fname}:{s.get('line',0)+1}",
                annotation=f"×{usages}" if usages else "",
                kind=km.get(s.get("kind",""), sublime.KIND_AMBIGUOUS),
            ))

        if not items:
            items = [sublime.QuickPanelItem(
                trigger=f"No symbols match '{scope_filter}'",
                details="Try @filename:prefix or just prefix",
                kind=sublime.KIND_AMBIGUOUS,
            )]

        def _sel(idx: int) -> None:
            if idx < 0 or idx >= len(syms):
                return
            s = syms[idx]
            f = s.get("file")
            if f:
                self.window.open_file(
                    f"{f}:{s.get('line',0)+1}:1", sublime.ENCODED_POSITION
                )
            if _indexer:
                _indexer.bump_usage(s["name"])

        placeholder = (
            "Search: @filename:prefix  or just  prefix"
            if not scope_filter else f"Filtered: {scope_filter}"
        )
        self.window.show_quick_panel(
            items, _sel,
            flags=sublime.MONOSPACE_FONT | sublime.KEEP_OPEN_ON_FOCUS_LOST,
            placeholder=placeholder,
        )


class LoveRenameSymbolCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        sel = self.view.sel()
        if not sel: return
        old = get_word_at(self.view, sel[0].begin())
        def _cb(new):
            if new and new != old and _indexer:
                sublime.set_timeout_async(
                    lambda: _indexer.rename_symbol(self.view.window(), old, new), 0
                )
        self.view.window().show_input_panel(f"Rename '{old}' to:", old, _cb, None, None)
    def is_enabled(self):
        return is_lua_view(self.view)


class LoveAutoImportCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if not _indexer: return
        sel = self.view.sel()
        if not sel: return
        word  = get_word_at(self.view, sel[0].begin())
        cands = _indexer.find_module_for_symbol(self.view.window(), word)
        if not cands:
            sublime.status_message(f"No module found exporting '{word}'")
            return
        items = [
            sublime.QuickPanelItem(
                trigger=c["require_path"], details=c.get("file",""),
                kind=sublime.KIND_NAMESPACE
            ) for c in cands
        ]
        def _sel(idx):
            if idx >= 0:
                self.view.run_command("love_insert_require",
                    {"path": cands[idx]["require_path"], "symbol": word})
        self.view.window().show_quick_panel(items, _sel)
    def is_enabled(self):
        return is_lua_view(self.view)


class LoveInsertRequireCommand(sublime_plugin.TextCommand):
    def run(self, edit, path, symbol):
        lines = self.view.substr(sublime.Region(0, self.view.size())).split("\n")
        ins = 0
        for i, l in enumerate(lines):
            s = l.strip()
            if s.startswith("local ") and "require" in s:
                ins = i + 1
            elif s and not s.startswith("--") and i > 0:
                break
        rl = f'local {symbol} = require("{path}")\n'
        self.view.insert(edit, self.view.text_point(ins, 0), rl)
        sublime.status_message(f"Inserted: {rl.strip()}")


class LoveProjectScaffoldCommand(sublime_plugin.WindowCommand):
    def run(self):
        self.window.show_input_panel("New Love2D project name:", "my_game",
                                     self._on_name, None, None)
    def _on_name(self, name):
        if not name.strip(): return
        folders = self.window.folders()
        base = folders[0] if folders else os.path.expanduser("~")
        path = os.path.join(base, name.strip())
        sublime.set_timeout_async(lambda: self._create(path, name), 0)
    def _create(self, path, name):
        try:
            os.makedirs(path, exist_ok=True)
            _write(os.path.join(path, "main.lua"),   _MAIN_LUA.format(name=name))
            _write(os.path.join(path, "conf.lua"),   _CONF_LUA.format(name=name))
            _write(os.path.join(path, ".luarc.json"), _LUARC)
            for d in ("assets/images", "assets/sounds", "src"):
                os.makedirs(os.path.join(path, d), exist_ok=True)
            self.window.open_file(os.path.join(path, "main.lua"))
        except OSError as e:
            sublime.error_message(f"Scaffold failed: {e}")


class LoveMigrateFromLegacyCommand(sublime_plugin.WindowCommand):
    LEGACY = ("Lovely2d", "sublime_love", "luaLove", "LuaLove", "LOVELY2D")
    def run(self):
        pkgs_path = sublime.packages_path()
        ip_path   = sublime.installed_packages_path()
        found = []
        for p in self.LEGACY:
            if os.path.isdir(os.path.join(pkgs_path, p)):
                found.append(p)
            elif os.path.isfile(os.path.join(ip_path, f"{p}.sublime-package")):
                found.append(p)
        if not found:
            sublime.message_dialog("No legacy Love2D packages detected.")
            return
        if not sublime.ok_cancel_dialog(
            f"Disable: {', '.join(found)}\nProceed?", ok_title="Disable"
        ):
            return
        prefs   = sublime.load_settings("Preferences.sublime-settings")
        ignored = prefs.get("ignored_packages", [])
        report  = ["# Love2D Migration Report\n"]
        for p in found:
            if p not in ignored:
                ignored.append(p)
                report.append(f"+ Disabled: {p}")
            else:
                report.append(f"  Already ignored: {p}")
        prefs.set("ignored_packages", ignored)
        sublime.save_settings("Preferences.sublime-settings")
        report.append("\nDone. Restart Sublime Text.")
        v = self.window.new_file()
        v.set_name("Migration Report")
        v.set_scratch(True)
        v.run_command("append", {"characters": "\n".join(report)})


class LoveFormatFileCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        sublime.set_timeout_async(self._run, 0)
    def _run(self):
        import subprocess
        fname = self.view.file_name()
        if not fname:
            sublime.status_message("Save the file first.")
            return
        fmt  = settings().get("formatter", "stylua")
        cmds = {"stylua": ["stylua", fname], "luaformatter": ["lua-format","-i",fname]}
        try:
            r = subprocess.run(cmds.get(fmt, cmds["stylua"]),
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                self.view.run_command("revert")
                sublime.status_message(f"Formatted with {fmt}")
            else:
                sublime.status_message(f"Format error: {r.stderr[:100]}")
        except FileNotFoundError:
            sublime.status_message(f"'{fmt}' not found.")
        except Exception as e:
            sublime.status_message(f"Format failed: {e}")
    def is_enabled(self):
        return is_lua_view(self.view)


class LoveToggleInlineHintsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        s  = settings()
        nv = not s.get("inline_type_hints", False)
        s.set("inline_type_hints", nv)
        sublime.save_settings(SETTINGS_FILE)
        sublime.status_message(f"Inline hints {'ON' if nv else 'OFF'}")


class LoveReindexWorkspaceCommand(sublime_plugin.WindowCommand):
    def run(self):
        if _indexer:
            sublime.status_message("Love2D: re-indexing ...")
            _indexer.clear_cache()
            _indexer.index_window(self.window)


class LoveShowQuickFixesCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if _quick_fixes:
            _quick_fixes.show_panel(self.view)
    def is_enabled(self):
        return is_lua_view(self.view)


def _write(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


_MAIN_LUA = """\
-- {name} — main.lua
function love.load()
end
function love.update(dt)
end
function love.draw()
    love.graphics.print("Hello, {name}!", 400, 300)
end
function love.keypressed(key)
    if key == "escape" then love.event.quit() end
end
"""
_CONF_LUA = """\
-- {name} — conf.lua
function love.conf(t)
    t.title         = "{name}"
    t.version       = "11.5"
    t.window.width  = 800
    t.window.height = 600
    t.window.resizable = false
end
"""
_LUARC = """\
{
  "$schema": "https://raw.githubusercontent.com/sumneko/vscode-lua/master/setting/schema.json",
  "runtime": { "version": "LuaJIT" },
  "diagnostics": { "globals": ["love"] },
  "workspace": { "library": [] }
}
"""
