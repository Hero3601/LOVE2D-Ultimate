"""
oop_completion.py — OOP Pattern Detection & Completion Engine
=============================================================
Detects and completes members for all common Lua OOP patterns:
  - setmetatable / __index  (prototype-based)
  - hump.class / classic.lua / middleclass / 30log
  - self:method() style completions within method bodies
  - table constructors returned from modules
  - @class / @type EmmyLua annotations

Does NOT parse a full AST — uses fast regex heuristics that tolerate
malformed or partially-typed code without ever crashing.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Any

import sublime

log = logging.getLogger("Love2D_Ultimate.oop")

SETTINGS_FILE = "Love2D_Ultimate.sublime-settings"

# ── Patterns ──────────────────────────────────────────────────────────────────

# local Foo = {} / local Foo = setmetatable({}, ...)
RE_CLASS_DECL = re.compile(
    # Matches both:  local Player = {}   AND  Player = {}   (without local)
    # Also matches setmetatable({}, ...) initialization forms
    r"^[ \t]*(?:local\s+)?(\w+)\s*=\s*(?:setmetatable\s*\(\s*\{\s*\}|{}|\{\s*\})",
    re.MULTILINE,
)
# Foo.__index = Foo
RE_INDEX_SELF = re.compile(r"(\w+)\.__index\s*=\s*\1")
# function Foo:method(params)
RE_COLON_METHOD = re.compile(
    r"^[ \t]*function\s+(\w+):(\w+)\s*\(([^)]*)\)",
    re.MULTILINE,
)
# Foo.field = value
RE_DOT_FIELD = re.compile(
    r"^[ \t]*(\w+)\.(\w+)\s*=\s*(?!function)(.+?)(?:\s*--.*)?$",
    re.MULTILINE,
)
# local instance = Foo.new(...)  or  local instance = Foo:new(...)
RE_CONSTRUCTOR_CALL = re.compile(
    r"local\s+(\w+)\s*=\s*(\w+)[.:]new\s*\(",
)
# hump.class / classic / middleclass: local X = Class:extend() etc.
RE_CLASS_EXTEND = re.compile(
    r"local\s+(\w+)\s*=\s*(\w+):extend\s*\(",
)
RE_CLASS_NEW_CALL = re.compile(
    r"local\s+(\w+)\s*=\s*(\w+)\s*\(",
)
# self.x = val  inside a function body
RE_SELF_ASSIGN = re.compile(
    r"[ \t]*self\.(\w+)\s*=\s*(.+?)(?:\s*--.*)?$",
    re.MULTILINE,
)
# ---@class ClassName
RE_EMMY_CLASS = re.compile(r"---@class\s+(\w+)")
# ---@field name type
RE_EMMY_FIELD = re.compile(r"---@field\s+(\w+)\s+(\S+)")

# Constructor body detection:  function ClassName:new(...)  ...body...  end
# Captures class_name and full body for instance-field extraction
RE_CTOR_FUNC = re.compile(
    r"^function\s+([\w.]+)[.:]new\s*\(([^)]*)\)\s*\n(.*?)^end\b",
    re.MULTILINE | re.DOTALL,
)
# instance.field = expr  inside a constructor body
RE_INST_ASSIGN = re.compile(
    r"^[ \t]*(\w+)\.(\w+)\s*=\s*(.+?)(?:\s*--.*)?$",
    re.MULTILINE,
)
# setmetatable(varname, {__index = self})  → confirms varname is the instance
RE_SETMETA_SELF = re.compile(
    r"setmetatable\s*\(\s*(\w+)\s*,.*?__index\s*=\s*self"
)

# ── Data ──────────────────────────────────────────────────────────────────────

@dataclass
class ClassInfo:
    name: str
    file: str
    line: int
    parent: str = ""
    methods: list["MethodInfo"] = field(default_factory=list)
    fields: list["FieldInfo"] = field(default_factory=list)

    def all_members(self) -> list[Any]:
        return self.methods + self.fields


@dataclass
class MethodInfo:
    name: str
    params: list[str]
    doc: str = ""
    line: int = 0
    is_colon: bool = True


@dataclass
class FieldInfo:
    name: str
    type_hint: str = ""
    doc: str = ""
    line: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Per-file OOP extractor
# ─────────────────────────────────────────────────────────────────────────────

class OopExtractor:
    """Extract class/instance info from a Lua source string."""

    @staticmethod
    def extract(source: str, path: str) -> list[ClassInfo]:
        lines = source.splitlines()
        classes: dict[str, ClassInfo] = {}

        # 1. Detect class declarations
        for m in RE_CLASS_DECL.finditer(source):
            name = m.group(1)
            line = source[:m.start()].count("\n")
            if name not in classes:
                classes[name] = ClassInfo(name=name, file=path, line=line)

        # 2. Detect EmmyLua @class annotations
        for m in RE_EMMY_CLASS.finditer(source):
            name = m.group(1)
            line = source[:m.start()].count("\n")
            if name not in classes:
                classes[name] = ClassInfo(name=name, file=path, line=line)

        # 3. Detect class:extend() / Class:new() patterns
        for m in RE_CLASS_EXTEND.finditer(source):
            child, parent = m.group(1), m.group(2)
            line = source[:m.start()].count("\n")
            if child not in classes:
                classes[child] = ClassInfo(name=child, file=path, line=line, parent=parent)
            else:
                classes[child].parent = parent

        # 4. Colon methods: function Foo:method(params)
        for m in RE_COLON_METHOD.finditer(source):
            class_name = m.group(1)
            method_name = m.group(2)
            raw_params = m.group(3)
            line = source[:m.start()].count("\n")

            params = [p.strip() for p in raw_params.split(",") if p.strip()]

            if class_name not in classes:
                classes[class_name] = ClassInfo(name=class_name, file=path, line=line)

            # Avoid duplicate methods
            existing = {mth.name for mth in classes[class_name].methods}
            if method_name not in existing:
                classes[class_name].methods.append(MethodInfo(
                    name=method_name,
                    params=params,
                    line=line,
                    is_colon=True,
                ))

        # 5. self.field assignments inside method bodies
        for class_name, cls_info in classes.items():
            # Scan inside each method for self.x = ...
            for m in RE_SELF_ASSIGN.finditer(source):
                field_name = m.group(1)
                rhs = m.group(2).strip()
                # Crude check: we're inside a method of this class
                existing_fields = {f.name for f in cls_info.fields}
                if field_name not in existing_fields:
                    type_hint = _infer_type(rhs)
                    line_no = source[:m.start()].count("\n")
                    cls_info.fields.append(FieldInfo(
                        name=field_name,
                        type_hint=type_hint,
                        line=line_no,
                    ))

        # 6. EmmyLua @field annotations
        for m in RE_EMMY_FIELD.finditer(source):
            field_name = m.group(1)
            type_hint = m.group(2)
            line_no = source[:m.start()].count("\n")
            for cls_name in reversed(list(classes.keys())):
                cls = classes[cls_name]
                if cls.line <= line_no:
                    existing = {f.name for f in cls.fields}
                    if field_name not in existing:
                        cls.fields.append(FieldInfo(
                            name=field_name,
                            type_hint=type_hint,
                            line=line_no,
                        ))
                    break

        # 7. Constructor field extraction:  instance.field = value  inside :new()
        # This is the key fix for  self.  showing all constructor fields.
        #
        # Pattern detected:
        #   function player:new(x, y, w, h, speed, image)
        #       local instance = {}
        #       instance.w     = w or 100           ← these become class fields
        #       instance.h     = h or 100
        #       instance.x     = x or (...)
        #       instance.image = image
        #       setmetatable(instance, {__index = self})   ← confirms it's a class
        #       return instance
        #   end
        for ctor_m in RE_CTOR_FUNC.finditer(source):
            ctor_class = ctor_m.group(1).split(".")[-1]   # "player" from "player:new"
            ctor_body  = ctor_m.group(3)

            # Only process if body has setmetatable(..., {__index = self})
            sm = RE_SETMETA_SELF.search(ctor_body)
            if not sm:
                continue

            instance_var = sm.group(1)   # the variable used before setmetatable
            ctor_line    = source[:ctor_m.start()].count("\n")

            # Ensure class exists
            if ctor_class not in classes:
                classes[ctor_class] = ClassInfo(
                    name=ctor_class, file=path, line=ctor_line
                )
            cls_info = classes[ctor_class]
            existing_fields = {f.name for f in cls_info.fields}

            # Extract  instance_var.field = expr  assignments
            for fm in RE_INST_ASSIGN.finditer(ctor_body):
                var    = fm.group(1)
                fname  = fm.group(2)
                rhs    = fm.group(3).strip()
                fline  = ctor_line + ctor_body[:fm.start()].count("\n")

                # Only process fields on the instance variable, not other tables
                if var != instance_var:
                    continue
                if fname in existing_fields:
                    continue

                type_hint, annotation = _smart_type_and_annotation(rhs)
                if not type_hint:
                    type_hint = _infer_type(rhs)

                # Store annotation in doc field so it shows in the panel
                doc_str = annotation if annotation else ""

                cls_info.fields.append(FieldInfo(
                    name=fname,
                    type_hint=type_hint,
                    doc=doc_str,
                    line=fline,
                ))
                existing_fields.add(fname)

        # Prune false positives: a bare  name = {}  with no methods or fields
        # is not a class (e.g. score = {}, lives = {}).
        # Keep a class only if:
        #   - It has at least one method OR at least one field from step 5/6/7
        #   - OR it has a parent (was declared via :extend())
        #   - OR it was explicitly annotated with ---@class
        emmy_classes = {m.group(1) for m in RE_EMMY_CLASS.finditer(source)}
        pruned = []
        for cls in classes.values():
            has_content = bool(cls.methods) or bool(cls.fields)
            has_parent  = bool(cls.parent)
            is_annotated = cls.name in emmy_classes
            if has_content or has_parent or is_annotated:
                pruned.append(cls)
        return pruned


def _infer_type(rhs: str) -> str:
    """Basic type inference from RHS expression."""
    rhs = rhs.strip()
    if rhs in ("true", "false"):
        return "boolean"
    if rhs.startswith(('"', "'", "[[")):
        return "string"
    if re.match(r"^-?\d+\.?\d*$", rhs):
        return "number"
    if rhs.startswith("{"):
        return "table"
    if rhs.startswith("love."):
        return rhs.split("(")[0]
    return ""


def _smart_type_and_annotation(rhs: str) -> tuple:
    """
    Smart type inference + concise annotation for constructor field display.

    Returns (type_hint, annotation) where annotation is what shows in the
    completion panel right column:

      instance.w     = w or 100        → type="number"  ann="= 100"
      instance.x     = x or (long...)  → type="number"  ann="number"
      instance.image = image            → type="any"     ann=""
      instance.speed = speed or 1000   → type="number"  ann="= 1000"
      instance.hp    = maxHp or 100    → type="number"  ann="= 100"
    """
    import re as _re
    rhs = rhs.strip()

    # Pattern 1: "param or LITERAL" → show the literal as default
    m_or_lit = _re.match(
        r"""\w+\s+or\s+([-\d.]+|true|false|"[^"]*"|'[^']*')$""", rhs
    )
    if m_or_lit:
        default = m_or_lit.group(1)
        if _re.match(r"^[-\d.]+$", default):
            return "number", f"= {default}"
        elif default in ("true", "false"):
            return "boolean", f"= {default}"
        else:
            return "string", f"= {default}"

    # Pattern 2: "param or (complex expression)" → just show type
    if " or " in rhs:
        after_or = rhs.split(" or ", 1)[1].strip()
        # The expression after 'or' hints at the type
        if any(op in after_or for op in ["+", "-", "*", "/",
               "getWidth", "getHeight", "getTime", "getDelta"]):
            return "number", "number"
        if after_or.startswith(('"', "'", "[[")):
            return "string", "string"
        return "", ""

    # Pattern 3: Pure literals
    if _re.match(r"^-?\d+\.?\d*$", rhs):
        return "number", f"= {rhs}"
    if rhs in ("true", "false"):
        return "boolean", f"= {rhs}"
    if rhs.startswith(('"', "'", "[[")):
        val = rhs[:20] + "..." if len(rhs) > 20 else rhs
        return "string", f"= {val}"
    if rhs.startswith("{"):
        return "table", "= {}"

    # Pattern 4: Love2D constructors
    love_types = {
        "image": "Image", "font": "Font", "source": "Source",
        "canvas": "Canvas", "shader": "Shader", "quad": "Quad",
        "body": "Body", "world": "World", "fixture": "Fixture",
        "sprite": "Image", "texture": "Image", "sound": "Source",
        "music": "Source", "audio": "Source",
    }
    rhs_lower = rhs.lower()
    for keyword, love_type in love_types.items():
        if keyword in rhs_lower:
            return love_type, ""

    # Pattern 5: arithmetic → number
    if any(op in rhs for op in ["*", "/", "+", "-"]) and not rhs.startswith('"'):
        return "number", "number"

    return "", ""
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Singleton Engine
# ─────────────────────────────────────────────────────────────────────────────

class OopCompletionEngine:
    """
    Manages per-file OOP extraction caches and serves completions/hover.
    """

    _instance: "OopCompletionEngine | None" = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "OopCompletionEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        self._class_cache: dict[str, list[ClassInfo]] = {}   # file_path → classes
        self._cache_lock = threading.Lock()

    # ── Completions ───────────────────────────────────────────────────────────

    def completions_for(
        self,
        view: sublime.View,
        pt: int,
        line: str,
        prefix: str,
        colon_only: bool = False,
        dot_only: bool   = False,
    ) -> list:
        """
        Returns completions for member access.

        colon_only=True  → only show methods defined as  ClassName:method()
        dot_only=True    → only show functions/fields defined as  ClassName.func()
        Neither flag     → show everything (used when we can't tell from context)

        Each item shows params in the annotation column:
          update     (dt) -> nil        ← annotation
          new        (x, y, w, h)       ← annotation
        """
        results: list = []

        # ── self: or self. inside a method body ───────────────────────────
        self_match = re.search(r"\bself[.:](\w*)$", line)
        if self_match:
            typed = self_match.group(1)
            cls   = self._find_class_for_view_cursor(view, pt)
            if cls:
                results.extend(self._class_members_completions(
                    cls, typed, view,
                    colon_only=colon_only,
                    dot_only=dot_only,
                ))
            return results

        # ── SomeIdentifier. or SomeIdentifier: ────────────────────────────
        dot_match = re.search(r"\b(\w+)[.:](\w*)$", line)
        if not dot_match:
            return results

        table_name = dot_match.group(1)
        typed      = dot_match.group(2)

        cls = self._find_class_by_name(view, table_name)
        if cls:
            results.extend(self._class_members_completions(
                cls, typed, view,
                colon_only=colon_only,
                dot_only=dot_only,
            ))

        return results

    def _class_members_completions(
        self,
        cls: ClassInfo,
        prefix: str,
        view: sublime.View,
        colon_only: bool = False,
        dot_only: bool   = False,
    ) -> list:
        """
        Builds CompletionItems for class members.

        Strict separation:
          colon_only → ONLY  function Foo:bar()  methods
          dot_only   → ONLY  function Foo.bar()  functions + fields
          neither    → everything

        Annotation column shows full signature:
          update     :(dt) -> nil          colon method
          new        .(x, y, w, h)         dot function
          speed                            field: number
        """
        items = []

        for mth in cls.methods:
            if prefix and not mth.name.lower().startswith(prefix.lower()):
                continue

            # Filter by separator
            if colon_only and not mth.is_colon:
                continue
            if dot_only and mth.is_colon:
                continue

            # Build snippet — skip self
            clean = [
                p.split(":")[0].strip()
                for p in mth.params
                if p.split(":")[0].strip() != "self"
            ]
            snip_parts = [f"${{{i+1}:{p}}}" for i, p in enumerate(clean)]
            snippet    = f"{mth.name}({', '.join(snip_parts)})"

            # Annotation: separator + (params)  visible in dropdown panel
            params_str = ", ".join(clean)
            sep        = ":" if mth.is_colon else "."
            annotation = f"{sep}({params_str})"

            # Details: doc or type label
            details = (
                f"colon method of {cls.name}" if mth.is_colon
                else f"dot function of {cls.name}"
            )
            if mth.doc:
                details = mth.doc[:50]

            items.append(sublime.CompletionItem.snippet_completion(
                trigger=mth.name,
                snippet=snippet,
                annotation=annotation,
                details=details,
                kind=sublime.KIND_FUNCTION,
            ))

        # Fields — only shown for dot access
        if not colon_only:
            for fld in cls.fields:
                if prefix and not fld.name.lower().startswith(prefix.lower()):
                    continue
                type_str = fld.type_hint or "any"
                # doc holds the smart annotation e.g. "= 100", "number", "= true"
                if fld.doc:
                    # "number  = 100" or just "= 100"
                    if type_str and type_str != "any" and not fld.doc.startswith(type_str):
                        annotation = f"{type_str}  {fld.doc}"
                    else:
                        annotation = fld.doc
                else:
                    annotation = type_str
                items.append(sublime.CompletionItem(
                    trigger=fld.name,
                    completion=fld.name,
                    completion_format=sublime.COMPLETION_FORMAT_TEXT,
                    annotation=annotation,
                    details=f"field of {cls.name}",
                    kind=sublime.KIND_VARIABLE,
                ))

        return items


    def hover_html_for(
        self, view: sublime.View, point: int, word: str
    ) -> str | None:
        """Return hover HTML if word is a known class name or method."""
        cls = self._find_class_by_name(view, word)
        if cls:
            return self._class_hover_html(cls)

        # Check if it's a method name
        for path, classes in self._class_cache.items():
            for c in classes:
                for mth in c.methods:
                    if mth.name == word:
                        return self._method_hover_html(mth, c)
        return None

    def _class_hover_html(self, cls: ClassInfo) -> str:
        css = (
            "body{font-family:system-ui;font-size:13px;margin:6px 10px}"
            ".kw{color:#569cd6}.nm{color:#4ec9b0}"
            ".sec{color:#9cdcfe;font-size:11px}"
            ".doc{color:#d4d4d4;margin-top:4px}"
        )
        parent_str = (
            f' <span class="kw">extends</span> <span class="nm">{cls.parent}</span>'
            if cls.parent
            else ""
        )
        methods_html = "".join(
            f'<li><span class="kw">function</span> '
            f'{m.name}({", ".join(m.params)})</li>'
            for m in cls.methods[:10]
        )
        fields_html = "".join(
            f'<li>{f.name}: <span class="sec">{f.type_hint or "any"}</span></li>'
            for f in cls.fields[:10]
        )
        return (
            f"<style>{css}</style>"
            f'<b class="kw">class</b> <span class="nm">{cls.name}</span>{parent_str}'
            f"<ul>{methods_html}</ul>"
            + (f"<b>Fields:</b><ul>{fields_html}</ul>" if fields_html else "")
        )

    def _method_hover_html(self, mth: MethodInfo, cls: ClassInfo) -> str:
        css = (
            "body{font-family:system-ui;font-size:13px;margin:6px 10px}"
            ".kw{color:#569cd6}.nm{color:#dcdcaa}"
            ".cls{color:#4ec9b0}.doc{color:#d4d4d4;margin-top:4px}"
        )
        params_html = ", ".join(
            f'<span style="color:#9cdcfe">{p}</span>' for p in mth.params
        )
        sep = ":" if mth.is_colon else "."
        doc_html = f'<p class="doc">{mth.doc}</p>' if mth.doc else ""
        return (
            f"<style>{css}</style>"
            f'<span class="kw">function</span> '
            f'<span class="cls">{cls.name}</span>{sep}'
            f'<span class="nm">{mth.name}</span>'
            f"({params_html})"
            f"{doc_html}"
        )

    # ── Cache management ──────────────────────────────────────────────────────

    def index_file(self, path: str, source: str) -> None:
        classes = OopExtractor.extract(source, path)
        with self._cache_lock:
            self._class_cache[path] = classes

    def _find_class_for_view_cursor(
        self, view: sublime.View, pt: int
    ) -> ClassInfo | None:
        """
        Determine which class body the cursor is inside by looking at the
        enclosing `function ClassName:` declaration above the cursor.
        """
        text_above = view.substr(sublime.Region(0, pt))
        # Walk backwards through colon-method declarations
        matches = list(RE_COLON_METHOD.finditer(text_above))
        if not matches:
            return None
        last = matches[-1]
        class_name = last.group(1)
        return self._find_class_by_name(view, class_name)

    def _find_class_by_name(
        self, view: sublime.View, name: str
    ) -> ClassInfo | None:
        """
        Find a class by name. Tries exact match first, then case-insensitive.
        Checks the current file first so local definitions take priority.

        This handles:  p = player:new()  where player.lua defines  local Player = {}
        Exact: "player" != "Player" → no match
        Case-insensitive: "player".lower() == "Player".lower() → match
        """
        fname      = view.file_name() or ""
        name_lower = name.lower()

        # Pass 1: exact match, current file first
        with self._cache_lock:
            exact_fallback = None
            for path, classes in self._class_cache.items():
                for cls in classes:
                    if cls.name == name:
                        if path == fname:
                            return cls   # exact + current file → best possible
                        if exact_fallback is None:
                            exact_fallback = cls
            if exact_fallback:
                return exact_fallback

            # Pass 2: case-insensitive match
            ci_fallback = None
            for path, classes in self._class_cache.items():
                for cls in classes:
                    if cls.name.lower() == name_lower:
                        if path == fname:
                            return cls
                        if ci_fallback is None:
                            ci_fallback = cls
            return ci_fallback

    def get_all_classes(self) -> list[ClassInfo]:
        with self._cache_lock:
            result = []
            for classes in self._class_cache.values():
                result.extend(classes)
            return result

    def is_known_class(self, view: sublime.View, name: str) -> bool:
        """
        True if name is a user-defined class in our OOP cache.
        Explicitly False for built-in Lua/Love2D globals so that
        love., math., table. etc. stay handled by the LOVE syntax package.
        """
        _BUILTINS = {
            "love", "math", "table", "string", "io", "os", "coroutine",
            "package", "debug", "bit", "jit", "ffi", "utf8",
        }
        if name in _BUILTINS:
            return False
        return self._find_class_by_name(view, name) is not None
