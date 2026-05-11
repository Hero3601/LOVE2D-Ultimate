"""
refactoring.py — Code Refactoring Tools v1.0
=============================================
Commands:
  1. love_extract_function    — extract selection into a new local function
  2. love_extract_variable    — extract expression into a local variable
  3. love_inline_variable     — inline a local variable wherever it's used
  4. love_wrap_pcall          — wrap a call in pcall(func, ...) safety guard
  5. love_toggle_local        — add/remove 'local' from assignment
  6. love_convert_function_style — convert between  function f()  and  f = function()
  7. love_add_type_annotation — add EmmyLua @param + @return above function
  8. love_surround_with       — surround selection with if/for/while/function
"""
from __future__ import annotations
import logging, re
import sublime, sublime_plugin

log = logging.getLogger("Love2D_Ultimate.refactor")

RE_FUNC_DEF = re.compile(
    r"^([ \t]*)(?:local\s+)?function\s+([\w.:]+)\s*\(([^)]*)\)",
    re.M,
)
RE_LOCAL_ASSIGN = re.compile(r"^([ \t]*)local\s+(\w+)\s*=\s*(.+)$")
RE_ASSIGN       = re.compile(r"^([ \t]*)(\w+)\s*=\s*(.+)$")


def _get_indent(view: sublime.View, pt: int) -> str:
    lr   = view.line(pt)
    line = view.substr(lr)
    return line[: len(line) - len(line.lstrip())]


class LoveExtractFunctionCommand(sublime_plugin.TextCommand):
    """
    Extracts the selected code into a new local function defined above
    the current function.  Replaces selection with a call to the new function.
    """
    def run(self, edit: sublime.Edit) -> None:
        sel = self.view.sel()
        if not sel or sel[0].empty():
            sublime.status_message("Select code to extract first.")
            return

        region   = sel[0]
        code     = self.view.substr(region)
        indent   = _get_indent(self.view, region.begin())

        def _on_name(name: str) -> None:
            if not name or not name.strip():
                return
            name = name.strip()

            # Build the new function
            indented_body = "\n".join(
                f"    {line}" for line in code.splitlines()
            )
            func_def = (
                f"{indent}local function {name}()\n"
                f"{indented_body}\n"
                f"{indent}end\n\n"
            )
            call = f"{indent}{name}()"

            # Find insertion point: before the enclosing function
            src   = self.view.substr(sublime.Region(0, self.view.size()))
            lines = src.splitlines()
            row   = self.view.rowcol(region.begin())[0]

            # Walk backwards to find start of enclosing function
            RE_OPEN = re.compile(
                r"^\s*(?:(?:local\s+)?function\b|if\b.+\bthen\b"
                r"|for\b.+\bdo\b|while\b.+\bdo\b)"
            )
            insert_row = 0
            for i in range(row, -1, -1):
                if RE_OPEN.match(lines[i]):
                    insert_row = i
                    break

            insert_pt = self.view.text_point(insert_row, 0)

            # Apply edits: first replace selection, then insert function
            self.view.replace(edit, region, call)
            self.view.insert(edit, insert_pt, func_def)
            sublime.status_message(f"Extracted to local function '{name}'")

        self.view.window().show_input_panel(
            "New function name:", "extracted", _on_name, None, None
        )

    def is_enabled(self) -> bool:
        sel = self.view.sel()
        return (self.view.match_selector(0, "source.lua")
                and bool(sel) and not sel[0].empty())


class LoveExtractVariableCommand(sublime_plugin.TextCommand):
    """
    Extracts selected expression into a local variable on the line above.
    """
    def run(self, edit: sublime.Edit) -> None:
        sel = self.view.sel()
        if not sel or sel[0].empty():
            sublime.status_message("Select an expression to extract.")
            return

        region = sel[0]
        expr   = self.view.substr(region).strip()
        indent = _get_indent(self.view, region.begin())

        def _on_name(name: str) -> None:
            if not name or not name.strip():
                return
            name  = name.strip()
            decl  = f"{indent}local {name} = {expr}\n"
            # Insert above current line
            lr    = self.view.line(region.begin())
            self.view.replace(edit, region, name)
            self.view.insert(edit, lr.begin(), decl)
            sublime.status_message(f"Extracted to 'local {name}'")

        self.view.window().show_input_panel(
            "Variable name:", "extracted", _on_name, None, None
        )

    def is_enabled(self) -> bool:
        sel = self.view.sel()
        return (self.view.match_selector(0, "source.lua")
                and bool(sel) and not sel[0].empty())


class LoveInlineVariableCommand(sublime_plugin.TextCommand):
    """
    Inlines a local variable: finds  local x = EXPR  and replaces all
    uses of  x  with  EXPR, then removes the declaration.
    Cursor must be on the  local x = ...  line.
    """
    def run(self, edit: sublime.Edit) -> None:
        sel = self.view.sel()
        if not sel:
            return
        pt   = sel[0].begin()
        lr   = self.view.line(pt)
        line = self.view.substr(lr)

        m = RE_LOCAL_ASSIGN.match(line)
        if not m:
            sublime.status_message("Put cursor on a  local x = expr  line.")
            return

        var_name = m.group(2).strip()
        expr     = m.group(3).strip()
        src      = self.view.substr(sublime.Region(0, self.view.size()))

        # Replace all occurrences of var_name (as whole word) with expr
        import re as _re
        pat     = _re.compile(r"\b" + _re.escape(var_name) + r"\b")
        new_src = pat.sub(expr, src)

        # Remove the declaration line
        decl_region = sublime.Region(lr.begin(), lr.end() + 1)
        new_src2 = (
            new_src[: decl_region.begin()]
            + new_src[decl_region.end():]
        )

        self.view.replace(edit, sublime.Region(0, self.view.size()), new_src2)
        sublime.status_message(f"Inlined '{var_name}' = {expr}")

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")


class LoveWrapPcallCommand(sublime_plugin.TextCommand):
    """
    Wraps selected function call in pcall().
    Selected:   myFunc(a, b)
    Result:     local ok, result = pcall(myFunc, a, b)
    """
    def run(self, edit: sublime.Edit) -> None:
        sel = self.view.sel()
        if not sel or sel[0].empty():
            sublime.status_message("Select a function call to wrap.")
            return

        region = sel[0]
        code   = self.view.substr(region).strip()

        # Parse: funcName(args)
        m = re.match(r"([\w.:]+)\s*\(([^)]*)\)", code)
        if not m:
            sublime.status_message("Selection doesn't look like a function call.")
            return

        func_name = m.group(1)
        args      = m.group(2).strip()
        if args:
            pcall_code = f"local ok, result = pcall({func_name}, {args})"
        else:
            pcall_code = f"local ok, result = pcall({func_name})"

        self.view.replace(edit, region, pcall_code)
        sublime.status_message(f"Wrapped in pcall()")

    def is_enabled(self) -> bool:
        sel = self.view.sel()
        return (self.view.match_selector(0, "source.lua")
                and bool(sel) and not sel[0].empty())


class LoveToggleLocalCommand(sublime_plugin.TextCommand):
    """
    Toggles 'local' on the current assignment line.
      x = 5       →  local x = 5
      local x = 5 →  x = 5
    """
    def run(self, edit: sublime.Edit) -> None:
        sel = self.view.sel()
        if not sel:
            return
        pt  = sel[0].begin()
        lr  = self.view.line(pt)
        line = self.view.substr(lr)

        if re.match(r"^\s*local\s+", line):
            new_line = re.sub(r"^(\s*)local\s+", r"\1", line)
            sublime.status_message("Removed 'local'")
        else:
            m = re.match(r"^(\s*)(\w+\s*=)", line)
            if not m:
                sublime.status_message("Not an assignment line.")
                return
            new_line = m.group(1) + "local " + line.lstrip()
            sublime.status_message("Added 'local'")

        self.view.replace(edit, lr, new_line)

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")


class LoveConvertFunctionStyleCommand(sublime_plugin.TextCommand):
    """
    Converts between the two Lua function declaration styles:
      function foo(x, y) ... end
      ↕
      local foo = function(x, y) ... end
    """
    def run(self, edit: sublime.Edit) -> None:
        sel = self.view.sel()
        if not sel:
            return
        pt   = sel[0].begin()
        lr   = self.view.line(pt)
        line = self.view.substr(lr)

        # Style 1: function foo(params)
        m1 = re.match(r"^(\s*)function\s+(\w+)\s*\(([^)]*)\)", line)
        if m1:
            indent, name, params = m1.group(1), m1.group(2), m1.group(3)
            rest = line[m1.end():]
            self.view.replace(edit, lr,
                f"{indent}local {name} = function({params}){rest}")
            sublime.status_message("Converted to  local fn = function()")
            return

        # Style 2: local foo = function(params)
        m2 = re.match(r"^(\s*)local\s+(\w+)\s*=\s*function\s*\(([^)]*)\)", line)
        if m2:
            indent, name, params = m2.group(1), m2.group(2), m2.group(3)
            rest = line[m2.end():]
            self.view.replace(edit, lr,
                f"{indent}function {name}({params}){rest}")
            sublime.status_message("Converted to  function name()")
            return

        sublime.status_message("Not on a function declaration line.")

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")


class LoveAddTypeAnnotationCommand(sublime_plugin.TextCommand):
    """
    Adds EmmyLua @param and @return annotations above the current function.
    Reads params from the function declaration.
    """
    def run(self, edit: sublime.Edit) -> None:
        sel = self.view.sel()
        if not sel:
            return
        pt   = sel[0].begin()
        lr   = self.view.line(pt)
        line = self.view.substr(lr)

        m = re.match(r"^\s*(?:local\s+)?function\s+[\w.:]+\s*\(([^)]*)\)", line)
        if not m:
            sublime.status_message("Not on a function definition line.")
            return

        params   = [p.strip() for p in m.group(1).split(",") if p.strip()]
        indent   = line[: len(line) - len(line.lstrip())]
        ann_lines = []
        for p in params:
            pname = p.split(":")[0].strip()
            ptype = p.split(":")[-1].strip() if ":" in p else "any"
            if pname and pname not in ("self", "..."):
                ann_lines.append(f"{indent}---@param {pname} {ptype}")
        ann_lines.append(f"{indent}---@return any")
        ann_block = "\n".join(ann_lines) + "\n"
        self.view.insert(edit, lr.begin(), ann_block)
        sublime.status_message("Added EmmyLua annotations")

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")


class LoveSurroundWithCommand(sublime_plugin.TextCommand):
    """
    Surrounds selected lines with a chosen block structure.
    """
    TEMPLATES = {
        "if condition then … end": (
            "if {0} then\n{body}\nend",
            "condition"
        ),
        "for i = 1, n do … end": (
            "for i = 1, {0} do\n{body}\nend",
            "n"
        ),
        "for k, v in pairs(t) do … end": (
            "for k, v in pairs({0}) do\n{body}\nend",
            "t"
        ),
        "while condition do … end": (
            "while {0} do\n{body}\nend",
            "condition"
        ),
        "local ok, err = pcall(function() … end)": (
            "local ok, err = pcall(function()\n{body}\nend)",
            ""
        ),
        "local function name() … end": (
            "local function {0}()\n{body}\nend",
            "name"
        ),
    }

    def run(self, edit: sublime.Edit) -> None:
        sel = self.view.sel()
        if not sel or sel[0].empty():
            sublime.status_message("Select lines to surround first.")
            return

        keys  = list(self.TEMPLATES.keys())
        items = [sublime.QuickPanelItem(trigger=k, kind=sublime.KIND_SNIPPET)
                 for k in keys]

        def _on_template(idx: int) -> None:
            if idx < 0:
                return
            key      = keys[idx]
            template, placeholder = self.TEMPLATES[key]

            if placeholder:
                def _on_value(value: str) -> None:
                    self._apply(edit, sel[0], template.format(value, body="{body}"))
                self.view.window().show_input_panel(
                    f"Value for '{placeholder}':", placeholder, _on_value, None, None
                )
            else:
                self._apply(edit, sel[0], template)

        self.view.window().show_quick_panel(items, _on_template)

    def _apply(self, edit: sublime.Edit, region: sublime.Region, template: str) -> None:
        body_lines = self.view.substr(region).splitlines()
        indented   = "\n".join(f"    {l}" for l in body_lines)
        filled     = template.replace("{body}", indented)
        self.view.replace(edit, region, filled)
        sublime.status_message("Surrounded with block")

    def is_enabled(self) -> bool:
        sel = self.view.sel()
        return (self.view.match_selector(0, "source.lua")
                and bool(sel) and not sel[0].empty())
