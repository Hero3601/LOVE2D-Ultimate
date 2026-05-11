"""
auto_installer.py — Dependency Checker & Auto-Install Prompts v1.0
===================================================================
On every startup, checks for:
  1. LSP package (Package Control)
  2. lua-language-server binary
  3. stylua formatter (optional)
  4. luacheck linter (optional)

For each missing dependency shows a friendly dialog:
  "Would you like to install lua-language-server?"
  [Yes — Show Instructions]  [Remind Me Later]  [Never]

Installation is guided step-by-step inside ST4 — no terminal knowledge needed.
All "never" choices are persisted so the dialog never appears twice.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import threading
import webbrowser

import sublime
import sublime_plugin

log = logging.getLogger("Love2D_Ultimate.installer")
SETTINGS_FILE  = "Love2D_Ultimate.sublime-settings"
STATE_FILE     = "Love2D_Ultimate_state.json"   # persisted in Packages/User/


# ── Dependency definitions ────────────────────────────────────────────────────

DEPENDENCIES = [
    {
        "id":          "lsp_package",
        "name":        "LSP (Language Server Protocol)",
        "description": (
            "The LSP package connects Sublime Text to language servers.\n"
            "Without it, lua-language-server cannot provide type inference,\n"
            "go-to-definition, or advanced diagnostics."
        ),
        "check":       lambda: _lsp_installed(),
        "install_fn":  "_guide_install_lsp",
        "optional":    False,
    },
    {
        "id":          "lls_binary",
        "name":        "lua-language-server",
        "description": (
            "The official Lua Language Server by LuaLS.\n"
            "Provides full IntelliSense, type inference, and diagnostics\n"
            "for all Lua code — including Love2D API stubs."
        ),
        "check":       lambda: _lls_installed(),
        "install_fn":  "_guide_install_lls",
        "optional":    False,
    },
    {
        "id":          "stylua",
        "name":        "StyLua (code formatter)",
        "description": (
            "StyLua is a fast Lua code formatter.\n"
            "Used by Love2D: Format File (Ctrl+Alt+F).\n"
            "Optional — the package works without it."
        ),
        "check":       lambda: _binary_exists("stylua"),
        "install_fn":  "_guide_install_stylua",
        "optional":    True,
    },
    {
        "id":          "luacheck",
        "name":        "luacheck (linter)",
        "description": (
            "luacheck is a static analyser and linter for Lua.\n"
            "Used by the Love2D build system for syntax checking.\n"
            "Optional — the package works without it."
        ),
        "check":       lambda: _binary_exists("luacheck"),
        "install_fn":  "_guide_install_luacheck",
        "optional":    True,
    },
]


# ── Detection helpers ─────────────────────────────────────────────────────────

def _lsp_installed() -> bool:
    return os.path.isdir(os.path.join(sublime.packages_path(), "LSP"))


def _lls_installed() -> bool:
    s = sublime.load_settings(SETTINGS_FILE)
    user_path = s.get("lls_binary_path", "")
    if user_path and os.path.isfile(user_path):
        return True
    for name in ("lua-language-server", "lua-ls"):
        if shutil.which(name):
            return True
    system = platform.system()
    if system == "Windows":
        for p in [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\lua-language-server\bin\lua-language-server.exe"),
            r"C:\tools\lua-language-server\bin\lua-language-server.exe",
            r"C:\Program Files\lua-language-server\bin\lua-language-server.exe",
        ]:
            if os.path.isfile(p):
                return True
    elif system == "Darwin":
        for p in ["/usr/local/bin/lua-language-server",
                  "/opt/homebrew/bin/lua-language-server",
                  os.path.expanduser("~/.local/bin/lua-language-server")]:
            if os.path.isfile(p):
                return True
    else:
        for p in ["/usr/bin/lua-language-server",
                  "/usr/local/bin/lua-language-server",
                  os.path.expanduser("~/.local/bin/lua-language-server"),
                  os.path.expanduser("~/.local/share/nvim/mason/bin/lua-language-server")]:
            if os.path.isfile(p):
                return True
    return False


def _binary_exists(name: str) -> bool:
    return bool(shutil.which(name))


# ── State persistence ─────────────────────────────────────────────────────────

def _state_path() -> str:
    return os.path.join(sublime.packages_path(), "User", STATE_FILE)


def _load_state() -> dict:
    try:
        with open(_state_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    try:
        with open(_state_path(), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(state, fh, indent=2)
    except OSError as exc:
        log.debug(f"State save error: {exc}")


# ── Install guidance functions ─────────────────────────────────────────────────

def _guide_install_lsp(window: sublime.Window) -> None:
    msg = (
        "Install LSP via Package Control:\n\n"
        "1. Press Ctrl+Shift+P\n"
        "2. Type: Package Control: Install Package\n"
        "3. Press Enter\n"
        "4. Search for: LSP\n"
        "5. Press Enter to install\n"
        "6. Restart Sublime Text\n\n"
        "Love2D Ultimate will automatically configure LSP\n"
        "for lua-language-server after installation."
    )
    _show_install_panel(window, "Install LSP Package", msg,
                        url="https://packagecontrol.io/packages/LSP")


def _guide_install_lls(window: sublime.Window) -> None:
    system = platform.system()

    if system == "Windows":
        instructions = (
            "OPTION A — winget (recommended, automatic):\n"
            "  1. Open Command Prompt or PowerShell\n"
            "  2. Run: winget install LuaLS.lua-language-server\n"
            "  3. Restart Sublime Text\n\n"
            "OPTION B — Manual download:\n"
            "  1. Open the download page (button below)\n"
            "  2. Download: lua-language-server-X.X.X-win32-x64.zip\n"
            "  3. Extract to: C:\\tools\\lua-language-server\\\n"
            "  4. In Love2D Ultimate settings, set:\n"
            '     "lls_binary_path": "C:\\\\tools\\\\lua-language-server\\\\bin\\\\lua-language-server.exe"\n'
            "  5. Restart Sublime Text"
        )
    elif system == "Darwin":
        instructions = (
            "OPTION A — Homebrew (recommended):\n"
            "  1. Open Terminal\n"
            "  2. Run: brew install lua-language-server\n"
            "  3. Restart Sublime Text\n\n"
            "OPTION B — Manual download:\n"
            "  1. Download from the page (button below)\n"
            "  2. Choose: lua-language-server-X.X.X-darwin-x64.tar.gz\n"
            "  3. Extract and move to: /usr/local/bin/\n"
            "  4. Restart Sublime Text"
        )
    else:
        instructions = (
            "OPTION A — Package manager:\n"
            "  Ubuntu/Debian:  sudo snap install lua-language-server\n"
            "  Arch Linux:     sudo pacman -S lua-language-server\n"
            "  NixOS:          nix-env -i lua-language-server\n\n"
            "OPTION B — Manual download:\n"
            "  1. Download from the page (button below)\n"
            "  2. Choose: lua-language-server-X.X.X-linux-x64.tar.gz\n"
            "  3. Extract: tar -xf archive.tar.gz\n"
            "  4. Move:    sudo mv bin/lua-language-server /usr/local/bin/\n"
            "  5. Make executable: sudo chmod +x /usr/local/bin/lua-language-server\n"
            "  6. Restart Sublime Text"
        )

    _show_install_panel(
        window, "Install lua-language-server", instructions,
        url="https://github.com/LuaLS/lua-language-server/releases/latest",
    )


def _guide_install_stylua(window: sublime.Window) -> None:
    system = platform.system()
    if system == "Windows":
        cmd = "cargo install stylua\n  OR download .exe from GitHub releases"
    elif system == "Darwin":
        cmd = "brew install stylua\n  OR: cargo install stylua"
    else:
        cmd = "cargo install stylua\n  OR: check your distro's package manager"

    _show_install_panel(
        window, "Install StyLua",
        f"StyLua is a Lua code formatter.\n\nInstall:\n  {cmd}\n\n"
        "After installing, restart Sublime Text.\n"
        "Use Ctrl+Alt+F to format any Lua file.",
        url="https://github.com/JohnnyMorganz/StyLua/releases/latest",
    )


def _guide_install_luacheck(window: sublime.Window) -> None:
    _show_install_panel(
        window, "Install luacheck",
        "luacheck is a Lua linter.\n\n"
        "Install via LuaRocks:\n"
        "  luarocks install luacheck\n\n"
        "Or download a pre-built binary from GitHub.\n"
        "After installing, the Love2D build system\n"
        "can check your code for errors.",
        url="https://github.com/mpeterv/luacheck",
    )


def _show_install_panel(
    window: sublime.Window,
    title: str,
    instructions: str,
    url: str = "",
) -> None:
    """Shows instructions in a scratch view + optionally opens the browser."""
    view = window.new_file()
    view.set_name(f"Love2D: {title}")
    view.set_scratch(True)
    content = f"# {title}\n\n{instructions}\n"
    if url:
        content += f"\nDownload / More info:\n  {url}\n"
    content += "\nAfter installing, run: Love2D: Re-check Dependencies\n"
    view.run_command("append", {"characters": content})

    if url:
        if sublime.ok_cancel_dialog(
            f"{title}\n\nOpen download page in browser?",
            ok_title="Open Browser",
        ):
            webbrowser.open(url)


# ── Main checker ──────────────────────────────────────────────────────────────

class DependencyChecker:
    """Runs once on startup, checks all deps, shows prompts for missing ones."""

    _instance = None
    _lock      = threading.Lock()

    @classmethod
    def instance(cls) -> "DependencyChecker":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def run_startup_check(self, window: sublime.Window) -> None:
        """Called from plugin_loaded. Runs async so startup isn't delayed."""
        threading.Thread(
            target=self._check_all,
            args=(window,),
            daemon=True,
        ).start()

    def _check_all(self, window: sublime.Window) -> None:
        import time
        time.sleep(2.0)   # wait for ST4 to finish loading everything

        state   = _load_state()
        missing = []

        for dep in DEPENDENCIES:
            dep_id = dep["id"]
            if state.get(f"never_{dep_id}"):
                continue
            try:
                if not dep["check"]():
                    missing.append(dep)
            except Exception as exc:
                log.debug(f"Check failed for {dep_id}: {exc}")

        if not missing:
            log.info("All Love2D Ultimate dependencies satisfied.")
            return

        # Show prompts one at a time on the main thread
        for dep in missing:
            sublime.set_timeout(
                lambda d=dep: self._prompt_for(window, d, state), 0
            )
            import time
            time.sleep(0.5)   # small gap between dialogs

    def _prompt_for(
        self, window: sublime.Window, dep: dict, state: dict
    ) -> None:
        dep_id   = dep["id"]
        name     = dep["name"]
        desc     = dep["description"]
        optional = dep.get("optional", False)

        opt_label = " (optional)" if optional else " (required for full features)"

        choice = sublime.message_dialog(
            f"Love2D Ultimate — Missing Dependency\n\n"
            f"📦  {name}{opt_label}\n\n"
            f"{desc}\n\n"
            f"Would you like installation instructions?\n\n"
            f"• Click OK for step-by-step instructions\n"
            f"• Close this dialog to be reminded next startup\n"
        )
        # message_dialog returns None — use ok_cancel_dialog for real choice
        result = sublime.yes_no_cancel_dialog(
            f"Missing: {name}\n\n{desc}",
            yes_title="Show Instructions",
            no_title="Never Ask Again",
        )

        if result == sublime.DIALOG_YES:
            fn_name = dep.get("install_fn", "")
            fn      = globals().get(fn_name)
            if fn:
                fn(window)
        elif result == sublime.DIALOG_NO:
            state[f"never_{dep_id}"] = True
            _save_state(state)
            sublime.status_message(f"Love2D: {name} reminder disabled.")
        # CANCEL = remind next time (do nothing)


# ── Commands ──────────────────────────────────────────────────────────────────

class LoveRecheckDependenciesCommand(sublime_plugin.WindowCommand):
    """
    Command: love_recheck_dependencies
    Re-runs the dependency check manually (after user installs something).
    """
    def run(self) -> None:
        state   = _load_state()
        results = []
        for dep in DEPENDENCIES:
            try:
                ok = dep["check"]()
            except Exception:
                ok = False
            icon = "✓" if ok else "✗"
            results.append(f"  {icon}  {dep['name']}")

        msg = "Love2D Ultimate — Dependency Status\n\n" + "\n".join(results)
        msg += "\n\nRun this command again after installing dependencies."
        sublime.message_dialog(msg)

    def run_async_check(self) -> None:
        DependencyChecker.instance().run_startup_check(self.window)


class LoveShowInstallGuideCommand(sublime_plugin.WindowCommand):
    """
    Command: love_show_install_guide
    Shows the full installation guide for everything.
    """
    def run(self) -> None:
        view = self.window.new_file()
        view.set_name("Love2D Ultimate — Installation Guide")
        view.set_scratch(True)
        view.run_command("append", {"characters": _FULL_GUIDE})


_FULL_GUIDE = """
# Love2D Ultimate — Complete Installation Guide

This guide sets up everything needed for the best possible
Love2D development experience in Sublime Text 4.

══════════════════════════════════════════════════════════

STEP 1 — Install LSP (Language Server Protocol package)
────────────────────────────────────────────────────────
1. Press Ctrl+Shift+P
2. Type: Package Control: Install Package
3. Search for: LSP
4. Install and restart Sublime Text

══════════════════════════════════════════════════════════

STEP 2 — Install lua-language-server
─────────────────────────────────────

Windows (easiest):
  Open PowerShell and run:
    winget install LuaLS.lua-language-server

  If winget is not available, download from:
  https://github.com/LuaLS/lua-language-server/releases/latest
  Extract to C:\\tools\\lua-language-server\\
  Then in Love2D Ultimate settings add:
    "lls_binary_path": "C:\\\\tools\\\\lua-language-server\\\\bin\\\\lua-language-server.exe"

macOS:
  brew install lua-language-server

Linux:
  sudo snap install lua-language-server
  OR: sudo pacman -S lua-language-server (Arch)
  OR: download binary from GitHub releases

══════════════════════════════════════════════════════════

STEP 3 — Install StyLua formatter (optional but recommended)
─────────────────────────────────────────────────────────────

Windows:
  winget install JohnnyMorganz.StyLua
  OR: cargo install stylua (if Rust is installed)

macOS:
  brew install stylua

Linux:
  cargo install stylua
  OR check your distro's package manager

After installing, use Ctrl+Alt+F to format any Lua file.

══════════════════════════════════════════════════════════

STEP 4 — Write .luarc.json for your project
─────────────────────────────────────────────
Open your Love2D project folder in Sublime Text, then run:
  Ctrl+Shift+P → Love2D: Write .luarc.json

This tells lua-language-server about your Love2D environment.

══════════════════════════════════════════════════════════

STEP 5 — Verify everything works
──────────────────────────────────
Run: Ctrl+Shift+P → Love2D: Show Diagnostic Info

You should see:
  LSP package installed : ✓
  lua-language-server   : /path/to/binary
  Love2D API stubs      : ✓

══════════════════════════════════════════════════════════

OPTIONAL — luacheck linter
───────────────────────────
Install via LuaRocks:
  luarocks install luacheck

Or download from: https://github.com/mpeterv/luacheck

══════════════════════════════════════════════════════════

After all steps: restart Sublime Text once more.
Everything will be configured automatically.
"""
