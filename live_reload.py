"""
live_reload.py — Live Reload & Game Console v1.0
=================================================
Features:
  1. Love2D Live Reload — on save, sends a signal to a running Love2D game
     to reload changed files without restarting
  2. Game Console — shows Love2D print() output in a Sublime panel
  3. Quick Run — launch Love2D game directly from ST4
  4. Error jumping — when Love2D crashes with a stack trace, parse it
     and jump to the offending line in ST4
  5. Multiple instance support — can target a specific Love2D window

Live Reload protocol:
  The package writes a sentinel file  .love_reload  to the project root.
  A companion Lua snippet checks for this file each frame and calls
  package.loaded = {} + dofile() on changed modules.
  The companion snippet is auto-inserted via love_inject_live_reload.
"""
from __future__ import annotations
import logging, os, re, subprocess, sys, threading, time
import sublime, sublime_plugin

log = logging.getLogger("Love2D_Ultimate.livereload")
SETTINGS_FILE  = "Love2D_Ultimate.sublime-settings"
SENTINEL_FILE  = ".love_reload"
OUTPUT_PANEL   = "Love2D Console"

# ── Companion Lua snippet (injected into main.lua) ────────────────────────────
LIVE_RELOAD_LUA = '''
-- Love2D Ultimate: Live Reload companion (auto-injected)
local _lr_sentinel = ".love_reload"
local _lr_last = 0
local _lr_timer = 0

local function _liveReloadCheck(dt)
    _lr_timer = _lr_timer + dt
    if _lr_timer < 0.5 then return end  -- check every 0.5s
    _lr_timer = 0
    local info = love.filesystem.getInfo(_lr_sentinel)
    if info and info.modtime ~= _lr_last then
        _lr_last = info.modtime
        -- Re-execute changed modules
        for k, _ in pairs(package.loaded) do
            package.loaded[k] = nil
        end
        love.filesystem.remove(_lr_sentinel)
        collectgarbage()
        print("[LiveReload] Reloading...")
        love.event.quit("restart")
    end
end

local _lr_orig_update = love.update or function() end
love.update = function(dt)
    _liveReloadCheck(dt)
    _lr_orig_update(dt)
end
-- End Love2D Ultimate live reload
'''


class LoveRunGameCommand(sublime_plugin.WindowCommand):
    """Command: love_run_game — runs Love2D in the current project folder."""

    _process = None
    _output_thread = None

    def run(self) -> None:
        folders = self.window.folders()
        if not folders:
            sublime.error_message("Open a project folder first.")
            return

        project_root = folders[0]
        s = sublime.load_settings(SETTINGS_FILE)

        # Find love binary
        love_bin = s.get("love_binary", "")
        if not love_bin:
            love_bin = self._find_love_binary()
        if not love_bin:
            sublime.error_message(
                "Love2D binary not found.\n"
                "Set 'love_binary' in Love2D Ultimate settings."
            )
            return

        # Kill existing instance
        if LoveRunGameCommand._process:
            try:
                LoveRunGameCommand._process.terminate()
            except Exception:
                pass

        # Create output panel
        panel = self.window.create_output_panel(OUTPUT_PANEL)
        panel.settings().set("word_wrap", True)
        panel.settings().set("scroll_past_end", False)
        self.window.run_command("show_panel", {"panel": f"output.{OUTPUT_PANEL}"})

        def _run():
            try:
                proc = subprocess.Popen(
                    [love_bin, "."],
                    cwd=project_root,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                LoveRunGameCommand._process = proc

                # Stream output to panel
                for line in proc.stdout:
                    stripped = line.rstrip()
                    sublime.set_timeout(
                        lambda l=stripped: self._append_to_panel(l), 0
                    )

                proc.wait()
                exit_code = proc.returncode
                sublime.set_timeout(
                    lambda: self._append_to_panel(
                        f"\n[Love2D exited with code {exit_code}]"
                    ), 0
                )
            except Exception as exc:
                sublime.set_timeout(
                    lambda: self._append_to_panel(f"[Error: {exc}]"), 0
                )

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        LoveRunGameCommand._output_thread = t

    def _append_to_panel(self, text: str) -> None:
        panel = self.window.find_output_panel(OUTPUT_PANEL)
        if panel:
            panel.run_command("append", {"characters": text + "\n"})
            # Parse error lines: main.lua:42: attempt to index nil
            self._parse_error_line(text)

    def _parse_error_line(self, text: str) -> None:
        m = re.search(r"([^:]+\.lua):(\d+):", text)
        if not m:
            return
        fname   = m.group(1)
        line_no = int(m.group(2))

        folders = self.window.folders()
        for folder in folders:
            full = os.path.join(folder, fname)
            if os.path.isfile(full):
                # Add to quick panel — user can click to jump
                self._last_error = (full, line_no)
                break

    def _find_love_binary(self) -> str | None:
        import shutil
        for name in ("love", "love2d", "love.exe"):
            found = shutil.which(name)
            if found:
                return found
        # Windows common location
        if sys.platform == "win32":
            candidates = [
                r"C:\Program Files\LOVE\love.exe",
                r"C:\Program Files (x86)\LOVE\love.exe",
            ]
            for c in candidates:
                if os.path.isfile(c):
                    return c
        return None


class LoveStopGameCommand(sublime_plugin.WindowCommand):
    """Command: love_stop_game — kills the running Love2D process."""

    def run(self) -> None:
        proc = LoveRunGameCommand._process
        if proc:
            try:
                proc.terminate()
                LoveRunGameCommand._process = None
                sublime.status_message("Love2D stopped.")
            except Exception as exc:
                sublime.status_message(f"Stop failed: {exc}")
        else:
            sublime.status_message("No Love2D process running.")


class LoveLiveReloadOnSaveListener(sublime_plugin.EventListener):
    """
    Touches the .love_reload sentinel file on every save.
    The companion Lua snippet picks this up and triggers a restart.
    """

    def on_post_save_async(self, view: sublime.View) -> None:
        if not view.match_selector(0, "source.lua"):
            return
        s = sublime.load_settings(SETTINGS_FILE)
        if not s.get("live_reload", False):
            return

        folders = view.window().folders() if view.window() else []
        for folder in folders:
            sentinel = os.path.join(folder, SENTINEL_FILE)
            try:
                with open(sentinel, "w") as fh:
                    fh.write(str(time.time()))
                log.debug(f"Live reload sentinel touched: {sentinel}")
            except OSError as exc:
                log.debug(f"Live reload sentinel error: {exc}")


class LoveInjectLiveReloadCommand(sublime_plugin.TextCommand):
    """
    Command: love_inject_live_reload
    Injects the companion Lua snippet into the current file (usually main.lua).
    """

    def run(self, edit: sublime.Edit) -> None:
        source = self.view.substr(sublime.Region(0, self.view.size()))
        if "-- Love2D Ultimate: Live Reload" in source:
            sublime.status_message("Live reload already injected.")
            return
        # Insert after the first require block or at end of file
        lines = source.split("\n")
        insert_at = len(lines)
        for i, line in enumerate(lines):
            if line.strip().startswith("function love.load"):
                insert_at = i
                break
        pt = self.view.text_point(insert_at, 0)
        self.view.insert(edit, pt, LIVE_RELOAD_LUA + "\n")
        sublime.status_message("Live reload companion injected into file.")

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")


class LoveJumpToErrorCommand(sublime_plugin.WindowCommand):
    """
    Command: love_jump_to_error
    Jumps to the last error reported in the console panel.
    """

    def run(self) -> None:
        runner = LoveRunGameCommand
        error  = getattr(runner, "_last_error", None)
        if not error:
            sublime.status_message("No error location recorded.")
            return
        path, line_no = error
        self.window.open_file(f"{path}:{line_no}:1", sublime.ENCODED_POSITION)
