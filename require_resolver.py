"""
require_resolver.py — require() Path Resolution & .lua Auto-Stripper v1.1
=========================================================================
Three detection layers, each catching what the others miss:

  Layer 1 — ON SAVE (most reliable):
    After every save, scan the entire file for require("...lua") and strip.
    Runs via on_post_save_async → love_require_strip_lua command.
    This is the safety net that catches everything.

  Layer 2 — ON COMPLETE STATEMENT (smart real-time):
    on_modified_async checks the FULL current line (not just up to cursor).
    Fires when it detects a closed require call containing .lua on the
    current line — e.g. the moment you type the closing ) or ".
    Uses a 400ms debounce so it doesn't fire mid-typing.

  Layer 3 — MANUAL:
    Ctrl+Alt+L runs love_require_strip_lua on the whole file at any time.

Stripping is always validated against the filesystem — a path is only
stripped if the .lua file actually exists on disk, so dynamic/false
positives are impossible.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time

import sublime
import sublime_plugin

log = logging.getLogger("Love2D_Ultimate.require")
SETTINGS_FILE = "Love2D_Ultimate.sublime-settings"

# ── Patterns ──────────────────────────────────────────────────────────────────

# Detects an open require call the cursor is inside:  require("  require('
RE_REQUIRE_OPEN = re.compile(r"""require\s*\(\s*['"][^'"]*$""")

# Matches any complete require call, capturing the path and optional .lua
# Groups: (1) quote char  (2) path without extension  (3) .lua or empty
RE_REQUIRE_FULL = re.compile(
    r"""require\s*\(\s*(['"])((?:[^'"\\]|\\.)*?)(\.lua)?\s*\1\s*\)"""
)

# Detects a CLOSED require call with .lua on the current line — used to
# trigger real-time stripping only when the statement looks complete.
# Matches:  require("anything.lua")  or  require('anything.lua')
RE_REQUIRE_WITH_LUA = re.compile(
    r"""require\s*\(\s*['"][^'"]*\.lua['"]\s*\)"""
)


class RequireResolver:
    """Singleton. Completions + .lua stripping."""

    _instance: "RequireResolver | None" = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "RequireResolver":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        self._path_cache: dict[str, list[str]] = {}
        self._cache_time: dict[str, float]     = {}
        self._scan_ttl = 30.0   # seconds before path cache refreshes

    # ── require() path completions ────────────────────────────────────────────

    def completions_for(
        self, view: sublime.View, pt: int, line: str
    ) -> list[sublime.CompletionItem]:
        """
        Return path completions when cursor is inside require("...").
        Paths are dot-separated, no .lua extension — ready to use in Love2D.
        """
        if not RE_REQUIRE_OPEN.search(line):
            return []

        # Extract what the user has typed after the opening quote
        m = RE_REQUIRE_OPEN.search(line)
        # Everything after the quote character
        after_quote = re.search(r"""['"]([^'"]*)$""", line)
        typed = after_quote.group(1) if after_quote else ""

        folders = view.window().folders() if view.window() else []
        if not folders:
            return []

        # Normalise typed prefix to slash form for matching
        typed_slash = typed.replace(".", "/").replace("\\", "/")

        results: list[sublime.CompletionItem] = []
        for folder in folders:
            for rel in self._lua_paths(folder):
                # rel is slash-separated, no .lua  e.g. "entities/player"
                if not rel.lower().startswith(typed_slash.lower()):
                    # also try dot-separated match
                    if not rel.replace("/", ".").lower().startswith(typed.lower()):
                        continue

                dot_path = rel.replace("/", ".")
                basename = rel.split("/")[-1]

                results.append(sublime.CompletionItem(
                    trigger=basename,
                    completion=dot_path,
                    completion_format=sublime.COMPLETION_FORMAT_TEXT,
                    kind=sublime.KIND_NAMESPACE,
                    annotation="require path",
                    details=f"{folder}/{rel}.lua",
                ))

        return results[:40]

    def _lua_paths(self, folder: str) -> list[str]:
        """
        Slash-separated require paths (no .lua) for all .lua files under
        folder.  Cached with TTL.
        """
        now  = time.time()
        last = self._cache_time.get(folder, 0)
        if folder in self._path_cache and (now - last) < self._scan_ttl:
            return self._path_cache[folder]

        paths = []
        try:
            for root, dirs, files in os.walk(folder):
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith(".")
                    and d not in (".git", "node_modules", "build")
                ]
                for fname in files:
                    if not fname.endswith(".lua"):
                        continue
                    full = os.path.join(root, fname)
                    rel  = os.path.relpath(full, folder).replace("\\", "/")
                    if rel.endswith(".lua"):
                        rel = rel[:-4]
                    # "src/player/init" → "src/player"
                    if rel.endswith("/init"):
                        rel = rel[:-5]
                    paths.append(rel)
        except OSError as exc:
            log.debug(f"Scan error {folder}: {exc}")

        paths.sort()
        self._path_cache[folder] = paths
        self._cache_time[folder] = now
        return paths

    # ── .lua stripping ────────────────────────────────────────────────────────

    def strip_all_in_view(
        self, view: sublime.View, edit: sublime.Edit
    ) -> int:
        """
        Scan the entire view for require("...lua") and strip the extension.
        Validates each path against the filesystem before touching it.
        Returns the number of replacements made.
        """
        folders = view.window().folders() if view.window() else []
        source  = view.substr(sublime.Region(0, view.size()))
        count   = 0

        def _replace(m: re.Match) -> str:
            nonlocal count
            quote = m.group(1)
            path  = m.group(2)
            ext   = m.group(3) or ""   # ".lua" or ""

            if not ext:
                return m.group(0)   # already clean

            # Only strip if the target file actually exists on disk
            if not self._file_exists(path, folders):
                return m.group(0)

            count += 1
            return f'require({quote}{path}{quote})'

        new_source = RE_REQUIRE_FULL.sub(_replace, source)

        if new_source != source:
            view.replace(edit, sublime.Region(0, view.size()), new_source)
            msg = f"Love2D: stripped .lua from {count} require call(s)"
        else:
            msg = "Love2D: no .lua extensions found in require() calls"

        sublime.status_message(msg)
        log.debug(msg)
        return count

    def _file_exists(self, dot_or_slash_path: str, folders: list[str]) -> bool:
        """
        Returns True if dot_or_slash_path resolves to a real .lua file.
        Handles both dot-separated and slash-separated paths, and
        init.lua folder modules.
        """
        slash = dot_or_slash_path.replace(".", "/").replace("\\", "/")
        for folder in folders:
            for candidate in (
                os.path.join(folder, slash + ".lua"),
                os.path.join(folder, slash, "init.lua"),
            ):
                if os.path.isfile(candidate):
                    return True
        return False

    def resolve(self, dot_path: str, folders: list[str]) -> str | None:
        """Resolve a require path string to an absolute file path."""
        slash = dot_path.replace(".", "/")
        for folder in folders:
            for suffix in (f"{slash}.lua", f"{slash}/init.lua"):
                full = os.path.join(folder, suffix)
                if os.path.isfile(full):
                    return full
        return None

    def invalidate_cache(self, folder: str) -> None:
        """Force a re-scan of folder on next access."""
        self._cache_time.pop(folder, None)
        self._path_cache.pop(folder, None)


# ─────────────────────────────────────────────────────────────────────────────
# Real-time + on-save auto-strip listener
# ─────────────────────────────────────────────────────────────────────────────

class RequireAutoStripListener(sublime_plugin.EventListener):
    """
    Two triggers:
      1. on_post_save_async — runs strip on every save automatically.
         This is the reliable safety net.
      2. on_modified_async — detects a COMPLETED require("x.lua") statement
         on the current line and strips within 400ms.
         Checks the FULL line (not just up to cursor) so it works whether
         the cursor is before or after the closing quote/paren.
    """

    _timers: dict[int, threading.Timer] = {}

    # ── On save: always strip the whole file ─────────────────────────────────

    def on_post_save_async(self, view: sublime.View) -> None:
        if not view.match_selector(0, "source.lua"):
            return
        s = sublime.load_settings(SETTINGS_FILE)
        if not s.get("require_auto_strip", True):
            return
        # Run the strip command — it obtains its own edit token safely
        sublime.set_timeout(
            lambda: view.run_command("love_require_strip_lua"), 50
        )

    # ── On modify: detect completed require("x.lua") on current line ─────────

    def on_modified_async(self, view: sublime.View) -> None:
        if not view.match_selector(0, "source.lua"):
            return
        s = sublime.load_settings(SETTINGS_FILE)
        if not s.get("require_auto_strip", True):
            return

        vid = view.id()
        # Cancel any pending timer for this view
        t = self._timers.pop(vid, None)
        if t:
            t.cancel()

        def _check():
            # Get the FULL current line (not just up to cursor)
            sel = view.sel()
            if not sel:
                return
            pt          = sel[0].begin()
            full_line   = view.substr(view.line(pt))

            # Only fire if this line contains a CLOSED require("...lua") call.
            # We check for the closing ) so we don't fire mid-typing.
            if RE_REQUIRE_WITH_LUA.search(full_line):
                sublime.set_timeout(
                    lambda: view.run_command("love_require_strip_lua"), 0
                )

        t2 = threading.Timer(
            0.4,   # 400ms — wait for user to finish typing the statement
            lambda: sublime.set_timeout_async(_check, 0),
        )
        self._timers[vid] = t2
        t2.start()
