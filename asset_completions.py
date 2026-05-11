"""
asset_completions.py — Love2D Asset Path Completions v1.0
==========================================================
Whenever the cursor is inside a Love2D function that takes a filename,
this engine serves completions for actual files on disk.

Triggers on:
  love.graphics.newImage("         → shows images/
  love.audio.newSource("           → shows sounds/
  love.graphics.newFont("          → shows fonts/
  love.filesystem.read("           → shows all .lua + data files
  require("                        → handled by require_resolver
  love.graphics.newVideo("         → shows video files
  love.graphics.newShader("        → shows .glsl files

Features:
  - Scans project folders recursively (cached 10s TTL)
  - Groups by type: images, sounds, fonts, shaders, data
  - Shows file size hint in completion details
  - Differentiates by extension
  - Works with nested folders: assets/enemies/goblin.png
  - Strips project root for relative paths
"""
from __future__ import annotations
import logging, os, re, time, threading
import sublime, sublime_plugin

log = logging.getLogger("Love2D_Ultimate.assets")
SETTINGS_FILE = "Love2D_Ultimate.sublime-settings"

# Functions that take a filename as first argument → what extensions to show
ASSET_FUNCTIONS: dict[str, list[str]] = {
    # graphics
    "newImage":       [".png", ".jpg", ".jpeg", ".bmp", ".tga", ".hdr"],
    "newFont":        [".ttf", ".otf"],
    "newCanvas":      [],   # no filename
    "newShader":      [".glsl", ".frag", ".vert"],
    "newVideo":       [".ogv"],
    "newImageData":   [".png", ".jpg", ".jpeg", ".bmp", ".tga"],
    # audio
    "newSource":      [".ogg", ".wav", ".mp3", ".flac"],
    # filesystem
    "read":           [],   # all files
    "write":          [],
    "load":           [".lua"],
    "append":         [],
    "newFileData":    [],
    # misc
    "newData":        [],
}

# Regex: matches the opening of a known asset function call with string arg
# e.g.  love.graphics.newImage("   or   love.audio.newSource("
RE_ASSET_OPEN = re.compile(
    r"""(?:love\.\w+\.)?(\w+)\s*\(\s*['"]([^'"]*)$"""
)

IMAGE_EXTS  = {".png",".jpg",".jpeg",".bmp",".tga",".hdr",".gif",".webp"}
SOUND_EXTS  = {".ogg",".wav",".mp3",".flac",".aac"}
FONT_EXTS   = {".ttf",".otf"}
SHADER_EXTS = {".glsl",".frag",".vert"}
VIDEO_EXTS  = {".ogv",".mp4"}
LUA_EXTS    = {".lua"}

EXT_ICONS = {
    **{e: "🖼" for e in IMAGE_EXTS},
    **{e: "🔊" for e in SOUND_EXTS},
    **{e: "🅰" for e in FONT_EXTS},
    **{e: "✨" for e in SHADER_EXTS},
    **{e: "🎬" for e in VIDEO_EXTS},
    **{e: "📜" for e in LUA_EXTS},
}


def _human_size(size: int) -> str:
    if size < 1024:    return f"{size}B"
    if size < 1048576: return f"{size//1024}KB"
    return f"{size//1048576}MB"


class AssetScanner:
    _instance = None
    _lock     = threading.Lock()

    @classmethod
    def instance(cls) -> "AssetScanner":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._cache: dict[str, list[dict]] = {}   # folder → file list
        self._times: dict[str, float]      = {}
        self._ttl   = 10.0  # seconds

    def files_for_folder(self, folder: str) -> list[dict]:
        now  = time.time()
        last = self._times.get(folder, 0)
        if folder in self._cache and (now - last) < self._ttl:
            return self._cache[folder]
        files = []
        try:
            for root, dirs, fnames in os.walk(folder):
                dirs[:] = [d for d in dirs
                           if not d.startswith(".")
                           and d not in (".git","node_modules","build")]
                for fname in fnames:
                    full = os.path.join(root, fname)
                    rel  = os.path.relpath(full, folder).replace("\\", "/")
                    ext  = os.path.splitext(fname)[1].lower()
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        size = 0
                    files.append({"rel": rel, "ext": ext,
                                  "size": size, "full": full})
        except OSError:
            pass
        files.sort(key=lambda f: f["rel"])
        self._cache[folder]  = files
        self._times[folder]  = now
        return files

    def completions(
        self,
        view: sublime.View,
        func_name: str,
        typed: str,
    ) -> list[sublime.CompletionItem]:
        """
        Returns asset path completions for func_name, filtered by typed prefix.
        """
        folders = view.window().folders() if view.window() else []
        if not folders:
            return []

        allowed_exts = ASSET_FUNCTIONS.get(func_name)
        if allowed_exts is None:
            return []   # unknown function — don't show anything

        typed_lower  = typed.lower().replace("\\", "/")
        results      = []
        seen: set    = set()

        for folder in folders:
            for f in self.files_for_folder(folder):
                rel  = f["rel"]
                ext  = f["ext"]

                # Filter by extension
                if allowed_exts and ext not in allowed_exts:
                    continue

                # Filter by typed prefix
                if typed_lower and not rel.lower().startswith(typed_lower):
                    continue

                if rel in seen:
                    continue
                seen.add(rel)

                icon     = EXT_ICONS.get(ext, "📄")
                size_str = _human_size(f["size"])

                results.append(sublime.CompletionItem(
                    trigger=os.path.basename(rel),
                    completion=rel,
                    completion_format=sublime.COMPLETION_FORMAT_TEXT,
                    kind=sublime.KIND_AMBIGUOUS,
                    annotation=ext,
                    details=f"{icon} {rel}  ({size_str})",
                ))

        return results[:50]


class AssetCompletionListener(sublime_plugin.EventListener):
    """Provides asset path completions inside Love2D file-loading functions."""

    def on_query_completions(self, view, prefix, locations):
        if not view.match_selector(0, "source.lua"):
            return None
        if not locations:
            return None

        pt   = locations[0]
        lr   = view.line(pt)
        line = view.substr(sublime.Region(lr.a, pt))

        m = RE_ASSET_OPEN.search(line)
        if not m:
            return None

        func_name = m.group(1)
        typed     = m.group(2)   # what user has typed after the opening quote

        if func_name not in ASSET_FUNCTIONS:
            return None

        scanner = AssetScanner.instance()
        items   = scanner.completions(view, func_name, typed)
        if not items:
            return None

        return sublime.CompletionList(
            items,
            flags=sublime.INHIBIT_WORD_COMPLETIONS
                | sublime.INHIBIT_EXPLICIT_COMPLETIONS,
        )
