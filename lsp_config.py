"""
lsp_config.py — LSP & lua-language-server Configuration v2.0
=============================================================
Fixed issues:
  - Now writes the correct LSP client configuration format
  - Creates LSP-lua.sublime-settings in Packages/User/ (how modern LSP works)
  - Also writes the legacy LSP.sublime-settings clients key for compatibility
  - Adds more Windows paths including the exact path from the install guide
  - Provides a working .luarc.json with correct stubs path
  - Shows a clear status message confirming LLS path was found/set

How LSP client registration works in ST4:
  Option A (modern, preferred):
    Create  Packages/User/LSP-lua.sublime-settings
    with the server config — LSP reads this automatically.

  Option B (legacy, also done for compatibility):
    Write to  LSP.sublime-settings  under  "clients": {"lua-language-server": {...}}

  We do BOTH so it works regardless of LSP package version.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import threading
from typing import Any

import sublime
import sublime_plugin

log = logging.getLogger("Love2D_Ultimate.lsp")
SETTINGS_FILE = "Love2D_Ultimate.sublime-settings"

# ── Love2D globals ────────────────────────────────────────────────────────────
LOVE2D_GLOBALS = ["love", "arg"]
LUA_RUNTIME    = "LuaJIT"

# ── Full server configuration ─────────────────────────────────────────────────
def _make_server_config(binary: str, stubs_path: str,
                        love_api_path: str = "") -> dict:
    """
    Returns the complete lua-language-server client configuration.
    Uses NESTED JSON format — flat keys like "runtime.version" are ignored by LuaLS.

    love_api_path: optional extra stubs dir (e.g. C:\tools\love-api)
    """
    library = []
    if stubs_path and os.path.isdir(stubs_path):
        library.append(stubs_path)
    if love_api_path and os.path.isdir(love_api_path):
        library.append(love_api_path)
        log.info(f"love-api stubs added: {love_api_path}")

    return {
        "enabled": True,
        "command": [binary, "--stdio"],
        "selector": "source.lua",
        "settings": {
            "Lua": {
                "runtime": {
                    "version": LUA_RUNTIME,
                    "path": ["?.lua", "?/init.lua"],
                    "pathStrict": False,
                },
                "diagnostics": {
                    "globals": LOVE2D_GLOBALS,
                    "enable": True,
                    "severity": {
                        "undefined-global": "Warning",
                        "missing-return":   "Warning",
                        "unused-local":     "Information",
                        "lowercase-global": "Information",
                    },
                    "neededFileStatus": {
                        "codestyle-check": "None",
                    },
                },
                "workspace": {
                    "library": library,
                    "checkThirdParty": False,
                    "ignoreDir": [".git", "node_modules", "build"],
                    "maxPreload": 2000,
                    "preloadFileSize": 500,
                },
                "completion": {
                    "enable": True,
                    "callSnippet": "Replace",
                    "keywordSnippet": "Replace",
                    "displayContext": 6,
                    "showParams": True,
                    "showWord": "Fallback",
                    "workspaceWord": True,
                },
                "hover": {
                    "enable": True,
                    "enumsLimit": 10,
                    "expandAlias": True,
                    "previewFields": 20,
                    "viewNumber": True,
                    "viewString": True,
                },
                "signatureHelp": {
                    "enable": True,
                },
                "hint": {
                    "enable": True,
                    "paramName": "All",
                    "paramType": True,
                    "setType": True,
                    "arrayIndex": "Enable",
                    "await": True,
                },
                "format": {
                    "enable": True,
                    "defaultConfig": {
                        "indent_style": "space",
                        "indent_size": "4",
                    },
                },
                "telemetry": {
                    "enable": False,
                },
            }
        },
        "initializationOptions": {},
        "env": {},
        # Critical: allow Love2D Ultimate completions to coexist with LLS
        # Without these, LSP blocks all other completion providers
        "inhibit_snippet_completions": False,
        "inhibit_word_completions":    False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Binary detection
# ─────────────────────────────────────────────────────────────────────────────

def _find_lls_binary() -> str | None:
    """
    Find lua-language-server binary.
    Checks in this order:
      1. User setting  lls_binary_path  in Love2D_Ultimate.sublime-settings
      2. PATH via shutil.which
      3. Common installation directories per platform
    """
    s = sublime.load_settings(SETTINGS_FILE)
    user_path = s.get("lls_binary_path", "").strip()
    if user_path and os.path.isfile(user_path):
        return user_path

    # PATH lookup — covers most Linux/macOS installs
    for name in ("lua-language-server", "lua-ls", "lua_ls"):
        found = shutil.which(name)
        if found:
            return found

    system = platform.system()

    if system == "Windows":
        candidates = [
            # winget default install location
            os.path.expandvars(
                r"%LOCALAPPDATA%\Programs\lua-language-server\bin\lua-language-server.exe"
            ),
            # Manual extraction paths (as shown in our install guide)
            r"C:\tools\lua-language-server\bin\lua-language-server.exe",
            r"C:\tools\lls\bin\lua-language-server.exe",
            r"C:\lua-language-server\bin\lua-language-server.exe",
            # Program Files variants
            r"C:\Program Files\lua-language-server\bin\lua-language-server.exe",
            r"C:\Program Files (x86)\lua-language-server\bin\lua-language-server.exe",
            # Scoop install
            os.path.expandvars(r"%USERPROFILE%\scoop\apps\lua-language-server\current\bin\lua-language-server.exe"),
        ]
    elif system == "Darwin":
        candidates = [
            "/usr/local/bin/lua-language-server",
            "/opt/homebrew/bin/lua-language-server",
            os.path.expanduser("~/.local/bin/lua-language-server"),
            os.path.expanduser("~/bin/lua-language-server"),
        ]
    else:  # Linux
        candidates = [
            "/usr/bin/lua-language-server",
            "/usr/local/bin/lua-language-server",
            os.path.expanduser("~/.local/bin/lua-language-server"),
            os.path.expanduser("~/.local/share/nvim/mason/bin/lua-language-server"),
            os.path.expanduser("~/bin/lua-language-server"),
            "/snap/bin/lua-language-server",
        ]

    for c in candidates:
        if os.path.isfile(c):
            return c

    return None


def _get_stubs_path() -> str:
    """Return the absolute path to our bundled Love2D API stubs."""
    return os.path.join(
        sublime.packages_path(), "Love2D_Ultimate", "love_api_stubs"
    )


def _lsp_package_available() -> bool:
    return os.path.isdir(os.path.join(sublime.packages_path(), "LSP"))


# ─────────────────────────────────────────────────────────────────────────────
# Write LSP configuration (both methods)
# ─────────────────────────────────────────────────────────────────────────────

def _write_lsp_lua_settings(config: dict) -> None:
    """
    Method A (modern): write Packages/User/LSP-lua.sublime-settings
    This is how the modern LSP package discovers custom servers.
    """
    path = os.path.join(sublime.packages_path(), "User", "LSP-lua.sublime-settings")
    existing = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                existing = json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass

    # Deep-merge: preserve any existing user keys
    _deep_merge(existing, config)

    try:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(existing, fh, indent=4)
        log.info(f"Wrote LSP-lua.sublime-settings to {path}")
    except OSError as exc:
        log.warning(f"Could not write LSP-lua.sublime-settings: {exc}")


def _write_lsp_clients_settings(config: dict) -> None:
    """
    Method B (legacy): write into LSP.sublime-settings clients dict.
    Uses key 'lua-language-server' which is the canonical name.
    """
    lsp_settings = sublime.load_settings("LSP.sublime-settings")
    clients: dict = lsp_settings.get("clients") or {}

    # Remove old bad key if present from previous versions
    clients.pop("sumneko", None)

    existing = clients.get("lua-language-server", {})
    _deep_merge(existing, config)
    clients["lua-language-server"] = existing

    lsp_settings.set("clients", clients)
    sublime.save_settings("LSP.sublime-settings")
    log.info("LSP.sublime-settings clients.lua-language-server updated")


def _deep_merge(base: dict, override: dict) -> None:
    """Merge override into base in-place. Lists are replaced."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


# ─────────────────────────────────────────────────────────────────────────────
# .luarc.json writer
# ─────────────────────────────────────────────────────────────────────────────

def write_luarc(project_path: str, stubs_path: str = "",
                love_api_path: str = "") -> None:
    """Write a .luarc.json configured for Love2D into project_path."""
    luarc_path = os.path.join(project_path, ".luarc.json")
    existing: dict = {}

    if os.path.isfile(luarc_path):
        try:
            with open(luarc_path, encoding="utf-8") as fh:
                existing = json.load(fh)
        except (json.JSONDecodeError, OSError):
            pass

    library = []
    if stubs_path and os.path.isdir(stubs_path):
        library.append(stubs_path)
    if love_api_path and os.path.isdir(love_api_path):
        library.append(love_api_path)

    template = {
        "$schema": (
            "https://raw.githubusercontent.com/LuaLS/vscode-lua/"
            "master/setting/schema.json"
        ),
        "runtime": {"version": LUA_RUNTIME},
        "diagnostics": {"globals": LOVE2D_GLOBALS},
        "workspace": {
            "library": library,
            "checkThirdParty": False,
        },
        "completion": {"callSnippet": "Replace"},
        "hint": {"enable": True, "paramName": "All"},
    }

    _deep_merge(existing, template)

    try:
        with open(luarc_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(existing, fh, indent=2)
        log.info(f".luarc.json written to {luarc_path}")
    except OSError as exc:
        log.warning(f"Could not write .luarc.json: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def ensure_lsp_configured() -> None:
    """
    Called once from plugin bootstrap (async, never blocks UI).
    1. Check if LSP package is installed
    2. Find lua-language-server binary
    3. Write both LSP config formats
    4. Show status message confirming what was found
    """
    if not _lsp_package_available():
        log.info("LSP package not found — skipping auto-configuration.")
        sublime.set_timeout(
            lambda: sublime.status_message(
                "Love2D: LSP package not found. "
                "Install it via Package Control for full IntelliSense."
            ), 0
        )
        return

    binary = _find_lls_binary()

    if not binary:
        log.warning("lua-language-server binary not found.")
        sublime.set_timeout(
            lambda: sublime.status_message(
                "Love2D: lua-language-server not found. "
                "Run 'Love2D: Show Installation Guide' for setup steps."
            ), 0
        )
        return

    log.info(f"lua-language-server found: {binary}")
    stubs = _get_stubs_path()

    # Also include user-supplied love-api path if set
    s = sublime.load_settings(SETTINGS_FILE)
    love_api = s.get("love_api_path", "").strip()

    config = _make_server_config(binary, stubs, love_api_path=love_api)

    # Write both formats
    _write_lsp_lua_settings(config)
    _write_lsp_clients_settings(config)

    # Confirm to user via status bar
    binary_short = os.path.basename(os.path.dirname(binary))  # "bin"
    binary_dir   = os.path.dirname(os.path.dirname(binary))   # install dir
    sublime.set_timeout(
        lambda: sublime.status_message(
            f"Love2D: lua-language-server configured  ({binary})"
        ), 0
    )
    log.info("LSP configuration complete.")


# ─────────────────────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────────────────────

class LoveWriteLuarcCommand(sublime_plugin.WindowCommand):
    """Command: love_write_luarc — writes .luarc.json to first project folder."""
    def run(self) -> None:
        folders = self.window.folders()
        if not folders:
            sublime.error_message("No project folder open.")
            return
        stubs    = _get_stubs_path()
        s        = sublime.load_settings(SETTINGS_FILE)
        love_api = s.get("love_api_path", "").strip()
        write_luarc(folders[0], stubs_path=stubs, love_api_path=love_api)
        sublime.status_message(f"Love2D: .luarc.json written to {folders[0]}")


class LoveDiagnosticInfoCommand(sublime_plugin.WindowCommand):
    """Command: love_diagnostic_info — shows full diagnostic status panel."""
    def run(self) -> None:
        binary   = _find_lls_binary()
        lsp_ok   = _lsp_package_available()
        stubs    = _get_stubs_path()
        stubs_ok = os.path.isdir(stubs)
        s        = sublime.load_settings(SETTINGS_FILE)
        user_bin = s.get("lls_binary_path", "").strip()

        # Check LSP-lua.sublime-settings
        lsp_lua_path = os.path.join(
            sublime.packages_path(), "User", "LSP-lua.sublime-settings"
        )
        lsp_lua_written = os.path.isfile(lsp_lua_path)

        lines = [
            "# Love2D Ultimate — Diagnostic Info",
            "",
            f"LSP package installed      : {'✓' if lsp_ok else '✗  Install via Package Control → LSP'}",
            f"lua-language-server        : {binary or '✗  NOT FOUND — see installation guide'}",
            f"lls_binary_path (setting)  : {user_bin or '(empty — using auto-detect)'}",
            f"Love2D API stubs           : {'✓' if stubs_ok else '✗'} {stubs}",
            f"LSP-lua.sublime-settings   : {'✓  Written' if lsp_lua_written else '✗  Not written yet'}",
            "",
            "── How to fix LSP not finding LLS ─────────────────────────────────",
            "1. Find where lua-language-server.exe is installed on your machine.",
            "2. Go to: Preferences → Package Settings → Love2D Ultimate → Settings – User",
            "3. Add this line (replace the path with yours):",
            '       "lls_binary_path": "C:\\\\tools\\\\lua-language-server\\\\bin\\\\lua-language-server.exe"',
            "4. Save the file.",
            "5. Run: Love2D: Re-check Dependencies  (from command palette)",
            "",
            f"Platform: {platform.system()} {platform.machine()}",
            f"ST4 Packages path: {sublime.packages_path()}",
        ]

        view = self.window.new_file()
        view.set_name("Love2D Diagnostics")
        view.set_scratch(True)
        view.run_command("append", {"characters": "\n".join(lines)})


class LoveReconfigureLspCommand(sublime_plugin.WindowCommand):
    """
    Command: love_reconfigure_lsp
    Forces a full re-write of the LSP configuration.
    Run this after setting lls_binary_path in settings.
    """
    def run(self) -> None:
        sublime.status_message("Love2D: configuring LSP...")
        import threading
        threading.Thread(target=ensure_lsp_configured, daemon=True).start()
