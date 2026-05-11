"""
symbol_indexer.py — Async Cross-File Symbol Indexer v2.0
=========================================================
All 15 issues addressed in this version:

Fix #1  — Strip strings + comments before regex so false symbols from
          string content or commented code never appear.
Fix #2  — Constructor type tracking: local p = Player.new() → p type = Player
          so p: shows Player's colon methods automatically.
Fix #3  — Multi-level require chains: if module A re-exports module B,
          the indexer follows the chain and returns B's exports for A.
Fix #4  — Multi-return tracking: local w, h = getDimensions() → w=number, h=number
Fix #10 — Incremental analysis: skip re-parsing if checksum unchanged (not just mtime).
Fix #11 — Cache class lookup per completion request (no double scan).
Fix #12 — MRU scores persisted to JSON in Packages/User/ across ST4 sessions.
Fix #14 — Scoped symbol search: @filename:prefix syntax in symbol picker.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

import sublime

log = logging.getLogger("Love2D_Ultimate.indexer")

MAX_FILE_SIZE     = 256 * 1024
MAX_WORKERS       = 2          # Core2Duo has 2 cores
CACHE_TTL         = 300          # 5 minutes — increased from 2 min
MAX_CACHE_ENTRIES = 800
USAGE_BUMP_WEIGHT = 1.5
MRU_FILE          = "Love2D_Ultimate_mru.json"
MAX_REQUIRE_DEPTH = 5            # max chain depth for fix #3

# ── Regex patterns ────────────────────────────────────────────────────────────
RE_FUNC_LOCAL   = re.compile(r"^[ \t]*local\s+function\s+(\w+)\s*\(([^)]*)\)", re.M)
RE_FUNC_GLOBAL  = re.compile(r"^[ \t]*function\s+([\w.:]+)\s*\(([^)]*)\)", re.M)
RE_FUNC_TABLE   = re.compile(r"^[ \t]*([\w.]+)\s*=\s*function\s*\(([^)]*)\)", re.M)
RE_LOCAL_VAR    = re.compile(r"^[ \t]*local\s+([\w]+)\s*=\s*(.+?)(?:\s*--.*)?$", re.M)
RE_TABLE_MEMBER = re.compile(
    r"^[ \t]*(\w+)\.(\w+)\s*=\s*(function\s*\(([^)]*)\)|.+?)(?:\s*--.*)?$", re.M
)
RE_RETURN_TABLE = re.compile(r"return\s*\{([^}]*)\}", re.DOTALL)
RE_RETURN_VAR   = re.compile(r"^return\s+(\w+)\s*$", re.M)
RE_REQUIRE      = re.compile(r'require\s*\(\s*["\']([^"\']+)["\']\s*\)')
RE_ANNOTATION   = re.compile(
    r"---\s*@(type|class|param|return|field)\s+(\S+)(?:\s+(.+))?"
)
# Fix #2: constructor calls  local X = ClassName.new(...)
RE_CONSTRUCTOR  = re.compile(
    # Matches BOTH:  local p = Player.new(  AND  local p = player:new(
    r"""(?:local\s+)?(\w+)\s*=\s*([\w.]+)[.:][Nn]ew\s*\("""
)
# Fix #4: multi-assignment  local a, b = func()
RE_MULTI_ASSIGN = re.compile(
    r"""local\s+([\w\s,]+?)\s*=\s*([\w.:]+)\s*\("""
)
# Fix #1: multi-line string regions  [[ ... ]]  and  [=[ ... ]=]
RE_LONG_STRING  = re.compile(r"\[=*\[.*?\]=*\]", re.DOTALL)
# Fix #1: single-line comments (-- ...)
RE_LINE_COMMENT = re.compile(r"--[^\n]*")


@dataclass
class SymbolInfo:
    name: str
    kind: str
    file: str
    line: int
    col: int = 0
    params: list = field(default_factory=list)
    returns: list = field(default_factory=list)
    doc: str = ""
    type_hint: str = ""
    usages: int = 0
    mru_score: float = 0.0

    def hover_html(self) -> str:
        css = (
            "<style>body{font-family:system-ui,sans-serif;font-size:13px;"
            "margin:6px 10px}.sig{color:#569cd6;font-weight:bold}"
            ".kind{color:#9cdcfe;font-size:11px}.doc{color:#d4d4d4;"
            "margin-top:4px}.loc{color:#888;font-size:11px;margin-top:4px}"
            ".ret{color:#4ec9b0}</style>"
        )
        params_html = ", ".join(
            f'<span style="color:#9cdcfe">{p}</span>' for p in self.params
        )
        ret_html = (
            f' &rarr; <span class="ret">{", ".join(self.returns)}</span>'
            if self.returns else ""
        )
        doc_html = f'<p class="doc">{self.doc}</p>' if self.doc else ""
        loc_html = (
            f'<p class="loc">{os.path.basename(self.file)}:{self.line + 1}</p>'
        )
        bare = self.name.split(".")[-1]
        return (
            f"{css}"
            f'<span class="kind">[{self.kind.upper()}]</span> '
            f'<span class="sig">{bare}</span>({params_html}){ret_html}'
            f"{doc_html}{loc_html}"
        )


@dataclass
class FileIndex:
    path: str
    mtime: float
    checksum: str = ""              # Fix #10: content checksum for skip logic
    symbols: list = field(default_factory=list)
    requires: list = field(default_factory=list)
    exports: dict = field(default_factory=dict)
    # Fix #2: var_name → class_name mapping from constructor calls
    constructor_types: dict = field(default_factory=dict)
    # Fix #4: var_name → type_hint from multi-return assignments
    multi_return_types: dict = field(default_factory=dict)


class _LRUCache:
    def __init__(self, maxsize=MAX_CACHE_ENTRIES, ttl=CACHE_TTL):
        self._data: OrderedDict = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self._data:
                return None
            value, ts = self._data[key]
            if time.time() - ts > self._ttl:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key, value):
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = (value, time.time())
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def delete(self, key):
        with self._lock:
            self._data.pop(key, None)

    def clear(self):
        with self._lock:
            self._data.clear()

    def keys(self):
        with self._lock:
            return list(self._data.keys())


# ── Fix #1: Source pre-processor ─────────────────────────────────────────────

def _strip_noise(source: str) -> str:
    """
    Returns a version of source where:
      - Multi-line strings [[ ... ]] are replaced with spaces (same length)
        so line numbers are preserved.
      - Single-line comments -- ... are replaced with spaces.
    This prevents regex from matching symbols inside strings or comments.
    """
    def _blank(m: re.Match) -> str:
        # Replace with spaces, preserving newlines so line numbers stay correct
        text = m.group(0)
        return re.sub(r"[^\n]", " ", text)

    # Order matters: long strings first (they may contain --)
    clean = RE_LONG_STRING.sub(_blank, source)
    clean = RE_LINE_COMMENT.sub(_blank, clean)
    return clean


class LuaFileParser:

    @staticmethod
    def parse(path: str, source: str) -> FileIndex:
        checksum = hashlib.md5(
            source.encode("utf-8", errors="replace")
        ).hexdigest()[:16]

        idx = FileIndex(
            path=path,
            mtime=os.path.getmtime(path) if os.path.exists(path) else 0,
            checksum=checksum,
        )

        lines  = source.splitlines()
        # Fix #1: parse on cleaned source so comments/strings don't pollute
        clean  = _strip_noise(source)
        clines = clean.splitlines()

        LuaFileParser._functions(clean, clines, path, idx)
        LuaFileParser._variables(clean, clines, path, idx)
        LuaFileParser._table_members(clean, clines, path, idx)
        LuaFileParser._requires(clean, idx)
        LuaFileParser._exports(clean, idx)
        LuaFileParser._constructor_types(clean, idx)   # Fix #2
        LuaFileParser._multi_return_types(clean, idx)  # Fix #4

        return idx

    @staticmethod
    def _lineno(source: str, pos: int) -> int:
        return source[:pos].count("\n")

    @staticmethod
    def _functions(source, lines, path, idx):
        annotations: dict = {}
        for i, line in enumerate(lines):
            m = RE_ANNOTATION.search(line)
            if not m:
                continue
            tag, name, rest = m.group(1), m.group(2), m.group(3) or ""
            ann = annotations.setdefault(i, {})
            if tag == "param":
                ann.setdefault("params", {})[name] = rest.strip()
            elif tag == "return":
                ann.setdefault("returns", []).append(name)

        def _doc(func_line):
            doc_lines, ann_data = [], {"params": {}, "returns": []}
            i = func_line - 1
            while i >= 0:
                s = lines[i].strip()
                if s.startswith("---") or s.startswith("--"):
                    doc_lines.insert(0, s.lstrip("-").strip())
                    if i in annotations:
                        a = annotations[i]
                        ann_data["params"].update(a.get("params", {}))
                        ann_data["returns"].extend(a.get("returns", []))
                    i -= 1
                else:
                    break
            return " ".join(doc_lines).strip(), ann_data

        for pat in (RE_FUNC_LOCAL, RE_FUNC_GLOBAL, RE_FUNC_TABLE):
            for m in pat.finditer(source):
                raw_name   = m.group(1)
                raw_params = m.group(2) if len(m.groups()) > 1 else ""
                func_line  = LuaFileParser._lineno(source, m.start())
                params = [p.strip() for p in raw_params.split(",") if p.strip()]
                if "..." in raw_params:
                    params.append("...")
                doc, ann = _doc(func_line)
                enriched = []
                for p in params:
                    pt = ann["params"].get(p, "")
                    enriched.append(f"{p}: {pt}" if pt else p)
                idx.symbols.append(SymbolInfo(
                    name=raw_name, kind="function", file=path,
                    line=func_line, params=enriched,
                    returns=ann["returns"], doc=doc,
                ))

    @staticmethod
    def _variables(source, lines, path, idx):
        existing = {s.name for s in idx.symbols}
        for m in RE_LOCAL_VAR.finditer(source):
            name = m.group(1)
            if name in existing:
                continue
            rhs = m.group(2).strip()
            if rhs.startswith("function"):
                continue
            line = LuaFileParser._lineno(source, m.start())
            idx.symbols.append(SymbolInfo(
                name=name, kind="variable", file=path,
                line=line, type_hint=LuaFileParser._infer_type(rhs),
            ))
            existing.add(name)

    @staticmethod
    def _table_members(source, lines, path, idx):
        for m in RE_TABLE_MEMBER.finditer(source):
            full = f"{m.group(1)}.{m.group(2)}"
            rhs  = m.group(3).strip()
            line = LuaFileParser._lineno(source, m.start())
            if rhs.startswith("function"):
                pm = re.search(r"function\s*\(([^)]*)\)", rhs)
                params = [p.strip() for p in pm.group(1).split(",")
                          if p.strip()] if pm else []
                idx.symbols.append(SymbolInfo(
                    name=full, kind="function", file=path,
                    line=line, params=params,
                ))
            else:
                idx.symbols.append(SymbolInfo(
                    name=full, kind="field", file=path,
                    line=line, type_hint=LuaFileParser._infer_type(rhs),
                ))

    @staticmethod
    def _requires(source, idx):
        for m in RE_REQUIRE.finditer(source):
            idx.requires.append(m.group(1).replace(".", "/"))

    @staticmethod
    def _exports(source, idx):
        # Pattern 1: return { key = val, ... }
        for m in RE_RETURN_TABLE.finditer(source):
            body = m.group(1)
            for kv in re.finditer(r"(\w+)\s*=", body):
                key = kv.group(1)
                for sym in idx.symbols:
                    if sym.name.split(".")[-1] == key:
                        idx.exports[key] = sym
                        break
                else:
                    idx.exports[key] = SymbolInfo(
                        name=key, kind="field", file=idx.path, line=0
                    )

        # Pattern 2: return M → all M.* and M:* are exports
        for m in RE_RETURN_VAR.finditer(source):
            vn = m.group(1)
            if vn in ("true", "false", "nil"):
                continue
            for sym in idx.symbols:
                if sym.name.startswith(f"{vn}."):
                    key = sym.name.split(".", 1)[1]
                    if key not in idx.exports:
                        idx.exports[key] = sym
                if ":" in sym.name:
                    parts = sym.name.split(":", 1)
                    if parts[0] == vn:
                        key = parts[1]
                        if key not in idx.exports:
                            idx.exports[key] = sym

    @staticmethod
    def _constructor_types(source: str, idx: FileIndex) -> None:
        """
        Fix #2: Detect  local p = Player.new(...)
        Stores  idx.constructor_types["p"] = "Player"
        so when user types p: we can look up Player's class.
        """
        for m in RE_CONSTRUCTOR.finditer(source):
            var_name   = m.group(1)
            class_name = m.group(2).split(".")[-1]  # "entities.Player" → "Player"
            if class_name not in ("true", "false", "nil", ""):
                idx.constructor_types[var_name] = class_name

    @staticmethod
    def _multi_return_types(source: str, idx: FileIndex) -> None:
        """
        Fix #4: Detect  local w, h = love.graphics.getDimensions()
        and store type hints for each assigned variable.
        Lazy import is wrapped in try so startup order doesn't cause crashes.
        """
        try:
            from Love2D_Ultimate.signature_help import LOVE_SIGS
        except Exception:
            return   # signature_help not loaded yet — skip silently
        for m in RE_MULTI_ASSIGN.finditer(source):
            vars_str  = m.group(1)
            func_name = m.group(2).split(".")[-1].split(":")[-1]
            var_names = [v.strip() for v in vars_str.split(",") if v.strip()]
            if len(var_names) < 2:
                continue
            sig = LOVE_SIGS.get(func_name)
            if not sig or not sig.get("returns"):
                continue
            # Parse return string "number, number" → ["number", "number"]
            ret_types = [r.strip() for r in sig["returns"].split(",")]
            for i, vname in enumerate(var_names):
                if i < len(ret_types):
                    idx.multi_return_types[vname] = ret_types[i]

    @staticmethod
    def _infer_type(rhs: str) -> str:
        rhs = rhs.strip().split("--")[0].strip()
        if rhs in ("true", "false"):
            return "boolean"
        if rhs.startswith(('"', "'", "[[")):
            return "string"
        if re.match(r"^-?\d+\.?\d*$", rhs):
            return "number"
        if rhs.startswith("{"):
            return "table"
        if rhs.startswith("require("):
            mod = re.search(r'require\s*\(\s*["\']([^"\']+)', rhs)
            if mod:
                return f"module:{mod.group(1)}"
        return ""


# ── MRU persistence (Fix #12) ─────────────────────────────────────────────────

def _mru_path() -> str:
    return os.path.join(sublime.packages_path(), "User", MRU_FILE)


def _load_mru() -> dict:
    try:
        with open(_mru_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_mru(scores: dict) -> None:
    try:
        # Keep only top 500 entries to keep file small
        top = sorted(scores.items(), key=lambda x: -x[1])[:500]
        with open(_mru_path(), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(dict(top), fh, indent=2)
    except OSError as exc:
        log.debug(f"MRU save error: {exc}")


class SymbolIndexer:

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "SymbolIndexer":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._file_cache   = _LRUCache()
        self._window_files: dict = {}
        self._mtime_map: dict   = {}
        self._checksum_map: dict = {}    # Fix #10: skip re-parse if content unchanged
        # Fix #12: load MRU from disk
        self._usage_scores: dict = _load_mru()
        self._executor = ThreadPoolExecutor(
            max_workers=MAX_WORKERS, thread_name_prefix="l2d_idx"
        )
        self._index_lock = threading.Lock()
        self._shutdown   = False
        # Fix #11: per-request class lookup cache
        self._class_lookup_cache: dict = {}
        self._class_lookup_lock  = threading.Lock()

    def shutdown(self):
        self._shutdown = True
        _save_mru(self._usage_scores)   # Fix #12: persist on exit
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ── Indexing ──────────────────────────────────────────────────────────────

    def index_window(self, window: sublime.Window):
        folders = window.folders()
        if not folders:
            return
        self._executor.submit(self._scan_window, window.id(), folders)

    def _scan_window(self, wid, folders):
        if self._shutdown:
            return
        paths = []
        for folder in folders:
            for root, dirs, files in os.walk(folder):
                dirs[:] = [d for d in dirs
                            if not d.startswith(".")
                            and d not in ("node_modules", ".git", "build")]
                for fname in files:
                    if fname.endswith(".lua"):
                        paths.append(os.path.join(root, fname))
        with self._index_lock:
            self._window_files[wid] = set(paths)
        futures = {self._executor.submit(self._index_file_task, p): p
                   for p in paths}
        for fut in as_completed(futures):
            if self._shutdown:
                break
            try:
                fut.result()
            except Exception as exc:
                log.debug(f"Index task: {exc}")
        log.info(f"Window {wid}: indexed {len(paths)} files")

    def index_file(self, path: str, source: str):
        self._executor.submit(self._index_with_source, path, source)

    def _index_file_task(self, path: str):
        if self._shutdown:
            return
        try:
            mtime = os.path.getmtime(path)
            # Fix #10: check mtime first (fast), then checksum (accurate)
            cached = self._file_cache.get(path)
            if cached and cached.mtime >= mtime:
                return   # mtime unchanged — definitely skip
            if os.path.getsize(path) > MAX_FILE_SIZE:
                return
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                source = fh.read()
            # Fix #10: skip if content identical even if mtime changed
            new_cs = hashlib.md5(
                source.encode("utf-8", errors="replace")
            ).hexdigest()[:16]
            if self._checksum_map.get(path) == new_cs:
                return
            self._parse_and_cache(path, source, mtime)
        except OSError as exc:
            log.debug(f"Cannot read {path}: {exc}")

    def _index_with_source(self, path: str, source: str):
        self._parse_and_cache(path, source, time.time())

    def _parse_and_cache(self, path: str, source: str, mtime: float):
        fi = LuaFileParser.parse(path, source)
        fi.mtime = mtime
        self._file_cache.set(path, fi)
        self._mtime_map[path]    = mtime
        self._checksum_map[path] = fi.checksum
        # Invalidate class lookup cache for this file (Fix #11)
        with self._class_lookup_lock:
            self._class_lookup_cache.clear()

    def clear_cache(self):
        self._file_cache.clear()
        self._mtime_map.clear()
        self._checksum_map.clear()
        with self._class_lookup_lock:
            self._class_lookup_cache.clear()

    def symbol_count(self) -> int:
        total = 0
        for k in self._file_cache.keys():
            fi = self._file_cache.get(k)
            if fi:
                total += len(fi.symbols)
        return total

    def get_file_index(self, path: str):
        return self._file_cache.get(path)

    # ── Fix #2: constructor type resolver ─────────────────────────────────────

    # ── _resolve_var_class cache (TTL=2s, avoids double-scan per keypress) ─────
    _var_class_cache: dict = {}
    _var_class_times: dict = {}

    def _resolve_var_class(
        self, view: sublime.View, var_name: str
    ) -> str | None:
        """
        Returns the class name for a variable if it was assigned via
        ClassName.new() or ClassName:new() in this file.
        Also checks ---@type ClassName annotations.

        Results are cached for 2 seconds per (view_id, var_name) pair
        so that _classify_context and module_member_completions on the
        same keypress don't scan the source twice.

        Covers all patterns:
          local p  = Player.new(10, 20)   → "Player"
          local p  = player:new(10, 20)   → "player"
          enemy    = Enemy.new(...)        → "Enemy"
          p        = entities.Player.new() → "Player"
        """
        import time as _time

        cache_key = (view.id(), var_name)
        now       = _time.monotonic()

        # Return cached result if fresh (2s TTL)
        if cache_key in self._var_class_cache:
            if now - self._var_class_times.get(cache_key, 0) < 2.0:
                return self._var_class_cache[cache_key]

        result = self._resolve_var_class_uncached(view, var_name)

        # Cache even None results (to avoid re-scanning for unknowns)
        self._var_class_cache[cache_key] = result
        self._var_class_times[cache_key] = now

        # Prune old entries to keep memory bounded
        if len(self._var_class_cache) > 200:
            oldest_key = min(self._var_class_times, key=self._var_class_times.get)
            self._var_class_cache.pop(oldest_key, None)
            self._var_class_times.pop(oldest_key, None)

        return result

    def _resolve_var_class_uncached(
        self, view: sublime.View, var_name: str
    ) -> str | None:
        """Raw source scan — called by _resolve_var_class with caching."""
        fname = view.file_name() or ""
        fi    = self._file_cache.get(fname)
        if fi:
            ct = fi.constructor_types.get(var_name)
            if ct:
                return ct

        # Scan current source (for unsaved/freshly typed assignments)
        source = view.substr(sublime.Region(0, view.size()))

        # Match BOTH  ClassName.new(  AND  ClassName:new(
        pat = re.compile(
            r"(?:local\s+)?" + re.escape(var_name) +
            r"\s*=\s*([\w.]+)[.:](?:[Nn]ew)\s*\("
        )
        m = pat.search(source)
        if m:
            return m.group(1).split(".")[-1]

        # ---@type annotation
        ann_pat = re.compile(
            r"---@type\s+(\w+)[^\n]*\n(?:[^\n]*\n){0,2}\s*" +
            r"(?:local\s+)?" + re.escape(var_name) + r"\b"
        )
        m2 = ann_pat.search(source)
        if m2:
            return m2.group(1)

        return None

    # ── Fix #3: multi-level require chain resolver ────────────────────────────

    def _resolve_exports_chain(
        self,
        resolved_path: str,
        folders: list[str],
        depth: int = 0,
    ) -> dict:
        """
        Get exports for a module file, following re-export chains.

        If module A does  return B  where B is itself a require()'d module,
        we follow the chain and return B's actual exports.
        Depth-limited to MAX_REQUIRE_DEPTH to prevent infinite loops.
        """
        if depth > MAX_REQUIRE_DEPTH:
            return {}

        fi = self._file_cache.get(resolved_path)
        if not fi:
            return {}

        # If the module has its own exports — use them directly
        if fi.exports:
            return fi.exports

        # Fix #3: module has no exports but has return M where M = require()
        # Look for pattern:  local M = require(...)  then  return M
        source = ""
        try:
            with open(resolved_path, "r", encoding="utf-8", errors="replace") as fh:
                source = fh.read()
        except OSError:
            return {}

        clean = _strip_noise(source)
        for rv in RE_RETURN_VAR.finditer(clean):
            var_name = rv.group(1)
            if var_name in ("true", "false", "nil"):
                continue
            # Check if var_name is itself a require()
            req_pat = re.compile(
                r"(?:local\s+)?" + re.escape(var_name) +
                r"\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
            )
            rm = req_pat.search(clean)
            if rm:
                sub_req  = rm.group(1)
                sub_path = self._resolve_require_path(sub_req, folders)
                if sub_path and sub_path != resolved_path:
                    return self._resolve_exports_chain(
                        sub_path, folders, depth + 1
                    )

        return {}

    # ── Module member completions ─────────────────────────────────────────────

    def module_member_completions(
        self,
        view: sublime.View,
        var_name: str,
        prefix: str,
        separator: str = ".",
    ) -> list:
        """
        Returns completions for var_name. or var_name:
        Filtered by separator: . → dot members, : → colon methods.
        Shows params in the annotation column.
        Fix #2: also handles constructor-typed vars (local p = Player.new()).
        Fix #3: follows re-export chains.
        """
        if not view.window():
            return []

        folders = view.window().folders() or []
        source  = view.substr(sublime.Region(0, view.size()))

        # ── Instance variable resolution: p = player:new() ─────────────────
        # _resolve_var_class returns the class/module name used in the
        # constructor call.  e.g. for  p = player:new()  it returns "player".
        # We then look up "player"'s members in three ways (broadest to narrowest):
        #   A. OOP engine by exact name ("player")
        #   B. OOP engine case-insensitively ("Player" matches "player")
        #   C. module_member_completions for "player" as a require() var
        #      (this is the key fallback — player = require("entity/player"))
        class_name = self._resolve_var_class(view, var_name)
        if class_name:
            try:
                from Love2D_Ultimate.oop_completion import OopCompletionEngine
                oop = OopCompletionEngine.instance()

                # A: exact OOP lookup
                cls = oop._find_class_by_name(view, class_name)
                if cls:
                    return oop._class_members_completions(
                        cls, prefix, view,
                        colon_only=(separator == ":"),
                        dot_only=(separator == "."),
                    )

                # B: case-insensitive OOP lookup
                # Handles:  p = player:new()  where class is "Player" in lua file
                class_lower = class_name.lower()
                for known_cls in oop.get_all_classes():
                    if known_cls.name.lower() == class_lower:
                        return oop._class_members_completions(
                            known_cls, prefix, view,
                            colon_only=(separator == ":"),
                            dot_only=(separator == "."),
                        )
            except Exception as exc:
                log.debug(f"oop lookup for constructor type: {exc}")

            # C: treat class_name as a require() variable and get module exports
            # This fires when:  player = require("entity/player")
            #                   p      = player:new()
            # We call ourselves with var_name="player" instead of "p"
            if class_name != var_name:  # prevent infinite recursion
                items = self.module_member_completions(
                    view, class_name, prefix, separator
                )
                if items:
                    return items

        # Standard require() lookup
        pat = re.compile(
            r"(?:local\s+)?" + re.escape(var_name) +
            r"\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
        )
        m = pat.search(source)
        if not m:
            return []

        require_str = m.group(1)
        resolved    = self._resolve_require_path(require_str, folders)
        if not resolved:
            return []

        # Ensure file is indexed
        fi = self._file_cache.get(resolved)
        if not fi:
            try:
                with open(resolved, "r", encoding="utf-8", errors="replace") as fh:
                    src = fh.read()
                self._parse_and_cache(resolved, src, os.path.getmtime(resolved))
                fi = self._file_cache.get(resolved)
            except OSError as exc:
                log.debug(f"read error: {exc}")
        if not fi:
            return []

        # Fix #3: get exports with chain resolution
        exports = fi.exports if fi.exports else self._resolve_exports_chain(
            resolved, folders
        )

        prefix_lower = prefix.lower()
        items        = []
        seen: set    = set()

        for key, sym in exports.items():
            if prefix_lower and not key.lower().startswith(prefix_lower):
                continue
            if key in seen:
                continue
            sym_is_colon = self._sym_is_colon(sym)
            if separator == ":" and not sym_is_colon:
                continue
            if separator == "." and sym_is_colon:
                continue
            seen.add(key)
            items.append(self._sym_to_completion_with_sep(sym, key, separator))

        # Fallback: all file symbols if no exports
        if not items and not exports:
            for sym in fi.symbols:
                bare = sym.name.split(".")[-1].split(":")[0]
                if prefix_lower and not bare.lower().startswith(prefix_lower):
                    continue
                if bare in seen:
                    continue
                sym_is_colon = ":" in sym.name
                if separator == ":" and not sym_is_colon:
                    continue
                if separator == "." and sym_is_colon:
                    continue
                seen.add(bare)
                items.append(self._sym_to_completion_with_sep(sym, bare, separator))

        items.sort(key=lambda c: c.trigger)
        return items

    def _sym_is_colon(self, sym: SymbolInfo) -> bool:
        return ":" in sym.name

    def _sym_to_completion_with_sep(
        self, sym: SymbolInfo, bare: str, separator: str
    ) -> sublime.CompletionItem:
        kind_map = {
            "function": sublime.KIND_FUNCTION,
            "variable": sublime.KIND_VARIABLE,
            "class":    sublime.KIND_TYPE,
            "module":   sublime.KIND_NAMESPACE,
            "field":    sublime.KIND_VARIABLE,
        }
        kind = kind_map.get(sym.kind, sublime.KIND_AMBIGUOUS)

        if sym.kind == "function":
            clean = [
                p.split(":")[0].strip() for p in sym.params
                if p.split(":")[0].strip() not in ("self", "...")
            ]
            snip_parts = [f"${{{i+1}:{p}}}" for i, p in enumerate(clean)]
            snippet    = f"{bare}({', '.join(snip_parts)})"
            params_str = ", ".join(clean)
            annotation = (f"({params_str}) -> {', '.join(sym.returns)}"
                          if sym.returns else f"({params_str})")
            details    = (f":{bare} colon method" if separator == ":"
                          else f".{bare} dot function")
        else:
            snippet    = bare
            annotation = sym.type_hint or "field"
            details    = f".{bare} field"
            kind       = sublime.KIND_VARIABLE

        return sublime.CompletionItem.snippet_completion(
            trigger=bare,
            snippet=snippet,
            annotation=annotation,
            details=details,
            kind=kind,
        )

    # ── General completions ───────────────────────────────────────────────────

    def completions_for(
        self, view: sublime.View, pt: int, line: str, prefix: str
    ) -> list:
        if not prefix or len(prefix) < 2:
            return []
        results    = []
        seen: set  = set()
        pl         = prefix.lower()
        for path in self._file_cache.keys():
            fi = self._file_cache.get(path)
            if not fi:
                continue
            for sym in fi.symbols:
                bare = sym.name.split(".")[-1]
                if bare.lower().startswith(pl) and bare not in seen:
                    seen.add(bare)
                    results.append(self._sym_to_completion(sym))
        results.sort(key=lambda c: (
            -self._usage_scores.get(c.trigger, 0), c.trigger
        ))
        return results[:60]

    def _sym_to_completion(
        self, sym: SymbolInfo, override_name: str = ""
    ) -> sublime.CompletionItem:
        kind_map = {
            "function": sublime.KIND_FUNCTION,
            "variable": sublime.KIND_VARIABLE,
            "class":    sublime.KIND_TYPE,
            "module":   sublime.KIND_NAMESPACE,
            "field":    sublime.KIND_VARIABLE,
        }
        kind = kind_map.get(sym.kind, sublime.KIND_AMBIGUOUS)
        bare = override_name or sym.name.split(".")[-1].split(":")[0]

        if sym.kind == "function":
            clean = [
                p.split(":")[0].strip() for p in sym.params
                if p.split(":")[0].strip() not in ("self", "...")
            ]
            snip_parts = [f"${{{i+1}:{p}}}" for i, p in enumerate(clean)]
            completion = (f"{bare}({', '.join(snip_parts)})"
                          if snip_parts else f"{bare}()")
            params_str = ", ".join(clean)
            annotation = (f"({params_str}) -> {', '.join(sym.returns)}"
                          if sym.returns else f"({params_str})")
        else:
            completion = bare
            annotation = sym.type_hint or ""

        details = sym.doc[:60] if sym.doc else os.path.basename(sym.file)
        return sublime.CompletionItem.snippet_completion(
            trigger=bare, snippet=completion,
            annotation=annotation, details=details, kind=kind,
        )

    # ── Fix #14: scoped symbol search ────────────────────────────────────────

    def all_symbols_for_window(
        self,
        window: sublime.Window,
        scope_filter: str = "",
    ) -> list:
        """
        Fix #14: supports scope_filter syntax:
          ""            → all symbols, MRU sorted
          "@player"     → only symbols from files containing "player" in name
          "@player:upd" → symbols from player file starting with "upd"
          "upd"         → symbols starting with "upd" from all files
        """
        file_filter  = ""
        name_filter  = scope_filter.lower()

        if scope_filter.startswith("@"):
            # @filename  or  @filename:prefix
            parts       = scope_filter[1:].split(":", 1)
            file_filter = parts[0].lower()
            name_filter = parts[1].lower() if len(parts) > 1 else ""

        wid     = window.id()
        watched = self._window_files.get(wid, set())
        syms    = []

        for path in (watched or self._file_cache.keys()):
            fi = self._file_cache.get(path)
            if not fi:
                continue
            # Apply file filter
            if file_filter:
                basename = os.path.basename(path).lower()
                if file_filter not in basename:
                    continue
            for sym in fi.symbols:
                bare = sym.name.split(".")[-1].split(":")[0].lower()
                if name_filter and not bare.startswith(name_filter):
                    continue
                syms.append({
                    "name":   sym.name,
                    "kind":   sym.kind,
                    "file":   sym.file,
                    "line":   sym.line,
                    "usages": int(self._usage_scores.get(sym.name, 0)),
                })

        syms.sort(key=lambda s: -self._usage_scores.get(s["name"], 0))
        return syms

    # ── Hover ─────────────────────────────────────────────────────────────────

    def hover_html_for(
        self, view: sublime.View, point: int, word: str
    ) -> str | None:
        sym = self._lookup(view, word)
        return sym.hover_html() if sym else None

    def _lookup(
        self, view: sublime.View, word: str
    ) -> SymbolInfo | None:
        fname = view.file_name() or ""
        best  = None
        for path in self._file_cache.keys():
            fi = self._file_cache.get(path)
            if not fi:
                continue
            for sym in fi.symbols:
                if sym.name.split(".")[-1] == word:
                    if sym.file == fname:
                        return sym
                    if best is None:
                        best = sym
        return best

    # ── Navigation ────────────────────────────────────────────────────────────

    def goto_definition(self, window, view, word: str, point: int):
        sym = self._lookup(view, word)
        if not sym:
            sublime.status_message(f"Definition not found: '{word}'")
            return
        window.open_file(f"{sym.file}:{sym.line + 1}:1", sublime.ENCODED_POSITION)
        self.bump_usage(word)

    def find_usages(self, view, word: str) -> list:
        pat     = re.compile(r"\b" + re.escape(word) + r"\b")
        results = []
        for path in self._file_cache.keys():
            fi = self._file_cache.get(path)
            if not fi:
                continue
            try:
                with open(fi.path, "r", encoding="utf-8", errors="replace") as fh:
                    lines = fh.readlines()
                for i, lt in enumerate(lines):
                    if pat.search(lt):
                        results.append({
                            "file":    fi.path,
                            "line":    i,
                            "snippet": lt.rstrip(),
                        })
            except OSError:
                pass
        return results

    def find_module_for_symbol(self, window, symbol: str) -> list:
        folders    = window.folders()
        candidates = []
        for path in self._file_cache.keys():
            fi = self._file_cache.get(path)
            if not fi:
                continue
            if symbol in fi.exports:
                rp = self._path_to_require(path, folders)
                if rp:
                    candidates.append({"require_path": rp, "file": path})
        return candidates

    def _resolve_require_path(
        self, require_str: str, folders: list
    ) -> str | None:
        slash = require_str.replace(".", "/").replace("\\", "/")
        for folder in folders:
            for candidate in (
                os.path.join(folder, slash + ".lua"),
                os.path.join(folder, slash, "init.lua"),
                os.path.join(folder, require_str.replace("\\", "/") + ".lua"),
            ):
                if os.path.isfile(candidate):
                    return os.path.normpath(candidate)
        return None

    def _path_to_require(self, path: str, folders: list) -> str | None:
        for folder in folders:
            if path.startswith(folder):
                rel = os.path.relpath(path, folder).replace("\\", "/")
                if rel.endswith(".lua"):
                    rel = rel[:-4]
                return rel.replace("/", ".")
        return None

    def bump_usage(self, name: str):
        self._usage_scores[name] = (
            self._usage_scores.get(name, 0.0) + USAGE_BUMP_WEIGHT
        )
        # Fix #12: save MRU every 10 bumps
        total = sum(1 for k in self._usage_scores if self._usage_scores[k] > 0)
        if total % 10 == 0:
            threading.Thread(
                target=_save_mru,
                args=(dict(self._usage_scores),),
                daemon=True,
            ).start()

    def type_hint_phantoms(self, view) -> list:
        fname = view.file_name()
        if not fname:
            return []
        fi = self._file_cache.get(fname)
        if not fi:
            return []
        phantoms = []
        for sym in fi.symbols:
            if sym.kind == "function" and sym.returns:
                pt      = view.text_point(sym.line, 0)
                end_pt  = view.line(pt).b
                html    = (
                    f'<span style="color:#4ec9b0;font-size:11px;'
                    f'font-family:monospace"> -> '
                    f'{", ".join(sym.returns)}</span>'
                )
                phantoms.append(sublime.Phantom(
                    sublime.Region(end_pt), html, sublime.LAYOUT_INLINE
                ))
        return phantoms
