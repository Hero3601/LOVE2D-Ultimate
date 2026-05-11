"""
signature_help.py — VSCode-Style Signature Help v2.0
=====================================================
Major improvements over v1.0:
  - Bigger, readable popup (min 400px wide, proper font sizing)
  - Differentiates colon methods (obj:foo) from dot functions (obj.foo)
    Shows the separator used and whether 'self' is implicit
  - Shows parameter TYPES when available from @param annotations
  - Shows return type when available
  - Shows doc string for the current parameter
  - Full Love2D API with doc strings and types (not just names)
  - Overload support: shows all overloads with current one highlighted
  - Marks optional parameters with ?
  - Shows Love2D wiki link in popup
  - Cooperates with autocomplete dropdown (both show simultaneously)
"""
from __future__ import annotations
import logging, re, threading
import sublime, sublime_plugin

log = logging.getLogger("Love2D_Ultimate.sighel")
SETTINGS_FILE = "Love2D_Ultimate.sublime-settings"

# ── Full Love2D signature database ──────────────────────────────────────────
# Each entry: name → {"params": [...], "types": [...], "returns": str,
#                     "doc": str, "wiki": str, "optional_from": int}
# optional_from: index from which params are optional (0-based)

LOVE_SIGS: dict = {
    # ── love.graphics ────────────────────────────────────────────────────────
    "draw": {
        "params":  ["drawable","x","y","r","sx","sy","ox","oy"],
        "types":   ["Drawable","number","number","number?","number?","number?","number?","number?"],
        "returns": "",
        "doc":     "Draws a drawable object on screen.",
        "wiki":    "https://love2d.org/wiki/love.graphics.draw",
        "optional_from": 2,
    },
    "print": {
        "params":  ["text","x","y","r","sx","sy","ox","oy"],
        "types":   ["string","number","number","number?","number?","number?","number?","number?"],
        "returns": "",
        "doc":     "Draws text at a position.",
        "wiki":    "https://love2d.org/wiki/love.graphics.print",
        "optional_from": 1,
    },
    "printf": {
        "params":  ["text","x","y","limit","align","r","sx","sy","ox","oy"],
        "types":   ["string","number","number","number","AlignMode","number?","number?","number?","number?","number?"],
        "returns": "",
        "doc":     "Draws text bounded to a width with alignment.",
        "wiki":    "https://love2d.org/wiki/love.graphics.printf",
        "optional_from": 4,
    },
    "rectangle": {
        "params":  ["mode","x","y","width","height","rx","ry","segments"],
        "types":   ["DrawMode","number","number","number","number","number?","number?","number?"],
        "returns": "",
        "doc":     "Draws a rectangle. mode is 'fill' or 'line'.",
        "wiki":    "https://love2d.org/wiki/love.graphics.rectangle",
        "optional_from": 5,
    },
    "circle": {
        "params":  ["mode","x","y","radius","segments"],
        "types":   ["DrawMode","number","number","number","number?"],
        "returns": "",
        "doc":     "Draws a circle.",
        "wiki":    "https://love2d.org/wiki/love.graphics.circle",
        "optional_from": 4,
    },
    "ellipse": {
        "params":  ["mode","x","y","radiusx","radiusy","segments"],
        "types":   ["DrawMode","number","number","number","number","number?"],
        "returns": "",
        "doc":     "Draws an ellipse.",
        "wiki":    "https://love2d.org/wiki/love.graphics.ellipse",
        "optional_from": 5,
    },
    "line": {
        "params":  ["x1","y1","x2","y2","..."],
        "types":   ["number","number","number","number","number..."],
        "returns": "",
        "doc":     "Draws lines between points. Can pass multiple x,y pairs.",
        "wiki":    "https://love2d.org/wiki/love.graphics.line",
        "optional_from": 4,
    },
    "polygon": {
        "params":  ["mode","x1","y1","x2","y2","..."],
        "types":   ["DrawMode","number","number","number","number","number..."],
        "returns": "",
        "doc":     "Draws a polygon. Vertices must be convex.",
        "wiki":    "https://love2d.org/wiki/love.graphics.polygon",
        "optional_from": 2,
    },
    "setColor": {
        "params":  ["r","g","b","a"],
        "types":   ["number","number","number","number?"],
        "returns": "",
        "doc":     "Sets the active drawing color. Values are 0-1.",
        "wiki":    "https://love2d.org/wiki/love.graphics.setColor",
        "optional_from": 3,
    },
    "setBackgroundColor": {
        "params":  ["r","g","b","a"],
        "types":   ["number","number","number","number?"],
        "returns": "",
        "doc":     "Sets the background color. Values are 0-1.",
        "wiki":    "https://love2d.org/wiki/love.graphics.setBackgroundColor",
        "optional_from": 3,
    },
    "newImage": {
        "params":  ["filename","flags"],
        "types":   ["string","table?"],
        "returns": "Image",
        "doc":     "Creates a new Image from a file path.",
        "wiki":    "https://love2d.org/wiki/love.graphics.newImage",
        "optional_from": 1,
    },
    "newFont": {
        "params":  ["filename","size"],
        "types":   ["string?","number?"],
        "returns": "Font",
        "doc":     "Creates a Font. filename=nil uses the default font.",
        "wiki":    "https://love2d.org/wiki/love.graphics.newFont",
        "optional_from": 0,
    },
    "newCanvas": {
        "params":  ["width","height","format","msaa"],
        "types":   ["number?","number?","PixelFormat?","number?"],
        "returns": "Canvas",
        "doc":     "Creates a Canvas (off-screen render target).",
        "wiki":    "https://love2d.org/wiki/love.graphics.newCanvas",
        "optional_from": 0,
    },
    "newQuad": {
        "params":  ["x","y","width","height","sw","sh"],
        "types":   ["number","number","number","number","number","number"],
        "returns": "Quad",
        "doc":     "Creates a Quad for sprite-sheet rendering. sw/sh = sheet dimensions.",
        "wiki":    "https://love2d.org/wiki/love.graphics.newQuad",
        "optional_from": 6,
    },
    "newSpriteBatch": {
        "params":  ["image","maxSprites","usage"],
        "types":   ["Image","number?","SpriteBatchUsage?"],
        "returns": "SpriteBatch",
        "doc":     "Creates a SpriteBatch for efficiently drawing many images.",
        "wiki":    "https://love2d.org/wiki/love.graphics.newSpriteBatch",
        "optional_from": 1,
    },
    "setLineWidth": {
        "params":  ["width"],
        "types":   ["number"],
        "returns": "",
        "doc":     "Sets the line width for drawing.",
        "wiki":    "https://love2d.org/wiki/love.graphics.setLineWidth",
        "optional_from": 1,
    },
    "setFont": {
        "params":  ["font"],
        "types":   ["Font"],
        "returns": "",
        "doc":     "Sets the active Font.",
        "wiki":    "https://love2d.org/wiki/love.graphics.setFont",
        "optional_from": 1,
    },
    "setScissor": {
        "params":  ["x","y","width","height"],
        "types":   ["number?","number?","number?","number?"],
        "returns": "",
        "doc":     "Sets scissor rect. Call with no args to disable.",
        "wiki":    "https://love2d.org/wiki/love.graphics.setScissor",
        "optional_from": 0,
    },
    "translate": {"params": ["dx","dy"], "types": ["number","number"],
                  "returns": "", "doc": "Applies a translation transform.", "wiki": "", "optional_from": 2},
    "rotate":    {"params": ["angle"],   "types": ["number"],
                  "returns": "", "doc": "Applies a rotation (radians).",    "wiki": "", "optional_from": 1},
    "scale":     {"params": ["sx","sy"],  "types": ["number","number?"],
                  "returns": "", "doc": "Applies a scale transform.",        "wiki": "", "optional_from": 1},
    "push":      {"params": [], "types": [], "returns": "", "doc": "Pushes transform stack.", "wiki": "", "optional_from": 0},
    "pop":       {"params": [], "types": [], "returns": "", "doc": "Pops transform stack.",  "wiki": "", "optional_from": 0},
    "clear":     {"params": ["r","g","b","a"], "types": ["number?","number?","number?","number?"],
                  "returns": "", "doc": "Clears the screen.", "wiki": "", "optional_from": 0},
    "getDimensions": {"params": [], "types": [], "returns": "number, number",
                      "doc": "Returns screen width, height.", "wiki": "", "optional_from": 0},
    "getWidth":  {"params": [], "types": [], "returns": "number", "doc": "Returns screen width.",  "wiki": "", "optional_from": 0},
    "getHeight": {"params": [], "types": [], "returns": "number", "doc": "Returns screen height.", "wiki": "", "optional_from": 0},
    # ── love.audio ───────────────────────────────────────────────────────────
    "newSource": {
        "params":  ["filename","type"],
        "types":   ["string","SourceType"],
        "returns": "Source",
        "doc":     "Creates an audio Source. type = 'static' or 'stream'.",
        "wiki":    "https://love2d.org/wiki/love.audio.newSource",
        "optional_from": 2,
    },
    "play":  {"params": ["source"], "types": ["Source"], "returns": "", "doc": "Plays a Source.", "wiki": "", "optional_from": 1},
    "stop":  {"params": ["source"], "types": ["Source?"], "returns": "", "doc": "Stops a Source or all sources.", "wiki": "", "optional_from": 0},
    "setVolume": {"params": ["volume"], "types": ["number"], "returns": "", "doc": "Sets master volume 0-1.", "wiki": "", "optional_from": 1},
    # ── love.keyboard ────────────────────────────────────────────────────────
    "isDown": {"params": ["key","..."], "types": ["KeyConstant","KeyConstant..."],
               "returns": "boolean", "doc": "Returns true if key is held.", "wiki": "", "optional_from": 1},
    "setKeyRepeat": {"params": ["enable"], "types": ["boolean"], "returns": "",
                     "doc": "Sets whether key repeat events fire.", "wiki": "", "optional_from": 1},
    # ── love.mouse ───────────────────────────────────────────────────────────
    "getPosition": {"params": [], "types": [], "returns": "number, number",
                    "doc": "Returns mouse x, y.", "wiki": "", "optional_from": 0},
    "setPosition": {"params": ["x","y"], "types": ["number","number"],
                    "returns": "", "doc": "Sets mouse position.", "wiki": "", "optional_from": 2},
    # ── love.physics ─────────────────────────────────────────────────────────
    "newWorld": {
        "params":  ["xg","yg","sleep"],
        "types":   ["number","number","boolean?"],
        "returns": "World",
        "doc":     "Creates a physics World. xg/yg = gravity.",
        "wiki":    "https://love2d.org/wiki/love.physics.newWorld",
        "optional_from": 2,
    },
    "newBody": {
        "params":  ["world","x","y","type"],
        "types":   ["World","number","number","BodyType"],
        "returns": "Body",
        "doc":     "Creates a Body. type = 'static', 'dynamic', or 'kinematic'.",
        "wiki":    "https://love2d.org/wiki/love.physics.newBody",
        "optional_from": 4,
    },
    "newFixture": {
        "params":  ["body","shape","density"],
        "types":   ["Body","Shape","number?"],
        "returns": "Fixture",
        "doc":     "Attaches a Shape to a Body.",
        "wiki":    "https://love2d.org/wiki/love.physics.newFixture",
        "optional_from": 2,
    },
    "newRectangleShape": {"params": ["width","height"], "types": ["number","number"],
                          "returns": "PolygonShape", "doc": "Creates a rectangle collision shape.", "wiki": "", "optional_from": 2},
    "newCircleShape":    {"params": ["radius"], "types": ["number"],
                          "returns": "CircleShape", "doc": "Creates a circle collision shape.", "wiki": "", "optional_from": 1},
    # ── love.math ────────────────────────────────────────────────────────────
    "random": {"params": ["m","n"], "types": ["number?","number?"],
               "returns": "number", "doc": "Returns random number. random()=0-1, random(n)=1-n, random(m,n)=m-n.", "wiki": "", "optional_from": 0},
    "randomSeed": {"params": ["seed"], "types": ["number"], "returns": "", "doc": "Seeds the RNG.", "wiki": "", "optional_from": 1},
    "newTransform": {"params": [], "types": [], "returns": "Transform", "doc": "Creates a Transform object.", "wiki": "", "optional_from": 0},
    # ── love.window ──────────────────────────────────────────────────────────
    "setTitle": {"params": ["title"], "types": ["string"], "returns": "", "doc": "Sets window title.", "wiki": "", "optional_from": 1},
    "setMode": {
        "params":  ["width","height","flags"],
        "types":   ["number","number","table?"],
        "returns": "boolean, string",
        "doc":     "Sets window mode. flags: fullscreen, vsync, resizable, etc.",
        "wiki":    "https://love2d.org/wiki/love.window.setMode",
        "optional_from": 2,
    },
    "setFullscreen": {"params": ["fullscreen","fstype"], "types": ["boolean","FullscreenType?"],
                      "returns": "boolean", "doc": "Toggles fullscreen.", "wiki": "", "optional_from": 1},
    # ── love.filesystem ──────────────────────────────────────────────────────
    "read":  {"params": ["name","size"], "types": ["string","number?"],
              "returns": "string, string", "doc": "Reads a file. Returns contents, error.", "wiki": "", "optional_from": 1},
    "write": {"params": ["name","data","size"], "types": ["string","string","number?"],
              "returns": "boolean, string", "doc": "Writes data to a file.", "wiki": "", "optional_from": 2},
    "getDirectoryItems": {"params": ["dir"], "types": ["string"],
                          "returns": "table", "doc": "Returns files in directory.", "wiki": "", "optional_from": 1},
    # ── love.timer ───────────────────────────────────────────────────────────
    "getDelta": {"params": [], "types": [], "returns": "number", "doc": "Time since last frame in seconds.", "wiki": "", "optional_from": 0},
    "getFPS":   {"params": [], "types": [], "returns": "number", "doc": "Average FPS.", "wiki": "", "optional_from": 0},
    "getTime":  {"params": [], "types": [], "returns": "number", "doc": "Time since love.run started.", "wiki": "", "optional_from": 0},
    "sleep":    {"params": ["seconds"], "types": ["number"], "returns": "", "doc": "Sleeps for N seconds.", "wiki": "", "optional_from": 1},
    # ── love callbacks ───────────────────────────────────────────────────────
    "load":         {"params": ["arg","unfilteredArg"], "types": ["table","table"],
                     "returns": "", "doc": "Called once on startup.", "wiki": "", "optional_from": 2},
    "update":       {"params": ["dt"], "types": ["number"],
                     "returns": "", "doc": "Called every frame. dt = delta time in seconds.", "wiki": "", "optional_from": 1},
    "keypressed":   {"params": ["key","scancode","isrepeat"], "types": ["KeyConstant","Scancode","boolean"],
                     "returns": "", "doc": "Key pressed callback.", "wiki": "", "optional_from": 3},
    "keyreleased":  {"params": ["key","scancode"], "types": ["KeyConstant","Scancode"],
                     "returns": "", "doc": "Key released callback.", "wiki": "", "optional_from": 2},
    "mousepressed": {"params": ["x","y","button","istouch","presses"],
                     "types": ["number","number","number","boolean","number"],
                     "returns": "", "doc": "Mouse button pressed callback.", "wiki": "", "optional_from": 5},
    "mousereleased":{"params": ["x","y","button","istouch","presses"],
                     "types": ["number","number","number","boolean","number"],
                     "returns": "", "doc": "Mouse button released callback.", "wiki": "", "optional_from": 5},
    "mousemoved":   {"params": ["x","y","dx","dy","istouch"],
                     "types": ["number","number","number","number","boolean"],
                     "returns": "", "doc": "Mouse moved callback.", "wiki": "", "optional_from": 5},
    "wheelmoved":   {"params": ["x","y"], "types": ["number","number"],
                     "returns": "", "doc": "Mouse wheel moved callback.", "wiki": "", "optional_from": 2},
    "resize":       {"params": ["w","h"], "types": ["number","number"],
                     "returns": "", "doc": "Window resize callback.", "wiki": "", "optional_from": 2},
    "textinput":    {"params": ["text"], "types": ["string"],
                     "returns": "", "doc": "Text input callback (UTF-8).", "wiki": "", "optional_from": 1},
    "focus":        {"params": ["focus"], "types": ["boolean"],
                     "returns": "", "doc": "Window focus callback.", "wiki": "", "optional_from": 1},
    "quit":         {"params": [], "types": [], "returns": "boolean",
                     "doc": "Called on quit. Return true to cancel.", "wiki": "", "optional_from": 0},
    "conf":         {"params": ["t"], "types": ["table"],
                     "returns": "", "doc": "Config callback. Set t.window.*, t.modules.*, etc.", "wiki": "", "optional_from": 1},
    # ── Lua stdlib ───────────────────────────────────────────────────────────
    "format":  {"params": ["s","..."], "types": ["string","any..."],
                "returns": "string", "doc": "C-style string format.", "wiki": "", "optional_from": 1},
    "sub":     {"params": ["s","i","j"], "types": ["string","number","number?"],
                "returns": "string", "doc": "String substring.", "wiki": "", "optional_from": 2},
    "find":    {"params": ["s","pattern","init","plain"], "types": ["string","string","number?","boolean?"],
                "returns": "number, number", "doc": "Find pattern in string.", "wiki": "", "optional_from": 2},
    "match":   {"params": ["s","pattern","init"], "types": ["string","string","number?"],
                "returns": "string", "doc": "Match pattern in string.", "wiki": "", "optional_from": 2},
    "gmatch":  {"params": ["s","pattern"], "types": ["string","string"],
                "returns": "iterator", "doc": "Iterator over all pattern matches.", "wiki": "", "optional_from": 2},
    "gsub":    {"params": ["s","pattern","repl","n"], "types": ["string","string","string|table|function","number?"],
                "returns": "string, number", "doc": "Global string substitution.", "wiki": "", "optional_from": 3},
    "len":     {"params": ["s"], "types": ["string"], "returns": "number", "doc": "String length.", "wiki": "", "optional_from": 1},
    "upper":   {"params": ["s"], "types": ["string"], "returns": "string", "doc": "To upper case.", "wiki": "", "optional_from": 1},
    "lower":   {"params": ["s"], "types": ["string"], "returns": "string", "doc": "To lower case.", "wiki": "", "optional_from": 1},
    "rep":     {"params": ["s","n","sep"], "types": ["string","number","string?"],
                "returns": "string", "doc": "Repeat string n times.", "wiki": "", "optional_from": 2},
    "byte":    {"params": ["s","i","j"], "types": ["string","number?","number?"],
                "returns": "number...", "doc": "Returns byte values of characters.", "wiki": "", "optional_from": 1},
    "insert":  {"params": ["t","pos","value"], "types": ["table","number|any","any?"],
                "returns": "", "doc": "Insert into table. insert(t,v) appends.", "wiki": "", "optional_from": 1},
    "remove":  {"params": ["t","pos"], "types": ["table","number?"],
                "returns": "any", "doc": "Remove from table.", "wiki": "", "optional_from": 1},
    "concat":  {"params": ["t","sep","i","j"], "types": ["table","string?","number?","number?"],
                "returns": "string", "doc": "Concatenate table as string.", "wiki": "", "optional_from": 1},
    "sort":    {"params": ["t","comp"], "types": ["table","function?"],
                "returns": "", "doc": "Sort table in-place.", "wiki": "", "optional_from": 1},
    "abs":     {"params": ["x"], "types": ["number"], "returns": "number", "doc": "Absolute value.", "wiki": "", "optional_from": 1},
    "ceil":    {"params": ["x"], "types": ["number"], "returns": "number", "doc": "Ceiling.", "wiki": "", "optional_from": 1},
    "floor":   {"params": ["x"], "types": ["number"], "returns": "number", "doc": "Floor.", "wiki": "", "optional_from": 1},
    "sqrt":    {"params": ["x"], "types": ["number"], "returns": "number", "doc": "Square root.", "wiki": "", "optional_from": 1},
    "max":     {"params": ["x","..."], "types": ["number","number..."], "returns": "number", "doc": "Maximum value.", "wiki": "", "optional_from": 1},
    "min":     {"params": ["x","..."], "types": ["number","number..."], "returns": "number", "doc": "Minimum value.", "wiki": "", "optional_from": 1},
    "sin":     {"params": ["x"], "types": ["number"], "returns": "number", "doc": "Sine (radians).", "wiki": "", "optional_from": 1},
    "cos":     {"params": ["x"], "types": ["number"], "returns": "number", "doc": "Cosine (radians).", "wiki": "", "optional_from": 1},
    "tan":     {"params": ["x"], "types": ["number"], "returns": "number", "doc": "Tangent (radians).", "wiki": "", "optional_from": 1},
    "atan":    {"params": ["y","x"], "types": ["number","number?"], "returns": "number", "doc": "Arctangent. atan(y,x) = atan2.", "wiki": "", "optional_from": 1},
    "atan2":   {"params": ["y","x"], "types": ["number","number"], "returns": "number", "doc": "Two-argument arctangent.", "wiki": "", "optional_from": 2},
    "fmod":    {"params": ["x","y"], "types": ["number","number"], "returns": "number", "doc": "Remainder of x/y.", "wiki": "", "optional_from": 2},
    "pow":     {"params": ["x","y"], "types": ["number","number"], "returns": "number", "doc": "x to the power y.", "wiki": "", "optional_from": 2},
    "type":    {"params": ["v"], "types": ["any"], "returns": "string", "doc": "Returns type name of v.", "wiki": "", "optional_from": 1},
    "tostring":{"params": ["v"], "types": ["any"], "returns": "string", "doc": "Converts to string.", "wiki": "", "optional_from": 1},
    "tonumber":{"params": ["e","base"], "types": ["any","number?"], "returns": "number", "doc": "Converts to number.", "wiki": "", "optional_from": 1},
    "setmetatable":{"params": ["t","mt"], "types": ["table","table"],
                    "returns": "table", "doc": "Sets metatable of t.", "wiki": "", "optional_from": 2},
    "getmetatable":{"params": ["t"], "types": ["table"], "returns": "table", "doc": "Gets metatable.", "wiki": "", "optional_from": 1},
    "rawget":  {"params": ["t","k"], "types": ["table","any"], "returns": "any", "doc": "Table index without __index.", "wiki": "", "optional_from": 2},
    "rawset":  {"params": ["t","k","v"], "types": ["table","any","any"], "returns": "table", "doc": "Table newindex without __newindex.", "wiki": "", "optional_from": 3},
    "pairs":   {"params": ["t"], "types": ["table"], "returns": "iterator", "doc": "Iterates all key-value pairs.", "wiki": "", "optional_from": 1},
    "ipairs":  {"params": ["t"], "types": ["table"], "returns": "iterator", "doc": "Iterates integer-keyed values.", "wiki": "", "optional_from": 1},
    "next":    {"params": ["t","k"], "types": ["table","any?"], "returns": "any, any", "doc": "Next key-value pair.", "wiki": "", "optional_from": 1},
    "select":  {"params": ["index","..."], "types": ["number|string","any..."],
                "returns": "any...", "doc": "select('#',...) returns count. select(n,...) returns from nth.", "wiki": "", "optional_from": 1},
    "pcall":   {"params": ["f","..."], "types": ["function","any..."],
                "returns": "boolean, any", "doc": "Protected call. Returns ok, result.", "wiki": "", "optional_from": 1},
    "xpcall":  {"params": ["f","msgh","..."], "types": ["function","function","any..."],
                "returns": "boolean, any", "doc": "Protected call with error handler.", "wiki": "", "optional_from": 2},
    "error":   {"params": ["msg","level"], "types": ["any","number?"],
                "returns": "", "doc": "Raises an error.", "wiki": "", "optional_from": 1},
    "assert":  {"params": ["v","msg","..."], "types": ["any","string?","any..."],
                "returns": "any", "doc": "Raises error if v is falsy.", "wiki": "", "optional_from": 1},
    "require": {"params": ["modname"], "types": ["string"],
                "returns": "any", "doc": "Loads a module.", "wiki": "", "optional_from": 1},
}


def _count_arg_index(text: str) -> int:
    """Count top-level commas to determine 0-based argument index."""
    open_count = 0; in_str = False; str_ch = ""; arg = 0
    for ch in text:
        if in_str:
            if ch == str_ch: in_str = False
        elif ch in ('"', "'"): in_str = True; str_ch = ch
        elif ch == "(": open_count += 1
        elif ch == ")":
            open_count -= 1
            if open_count < 0: break
        elif ch == "," and open_count == 1:
            arg += 1
    return arg


def _find_call_context(view: sublime.View, pt: int):
    """
    Returns (func_name, full_name, arg_index, separator) or None.
    separator is '.' or ':' — used to differentiate dot vs colon calls.
    """
    lr        = view.line(pt)
    line_text = view.substr(sublime.Region(lr.a, pt))

    depth = 0; in_str = False; str_ch = ""; call_end = -1
    for i in range(len(line_text) - 1, -1, -1):
        ch = line_text[i]
        if in_str:
            if ch == str_ch and (i == 0 or line_text[i-1] != "\\"): in_str = False
        elif ch in ('"', "'"): in_str = True; str_ch = ch
        elif ch == ")": depth += 1
        elif ch == "(":
            if depth == 0: call_end = i; break
            depth -= 1

    if call_end < 0: return None
    before = line_text[:call_end].rstrip()
    if not before: return None

    # Detect separator: the character before the function name
    func_m = re.search(r"([.:]?)(\w+)\s*$", before)
    if not func_m: return None
    separator = func_m.group(1) or "."
    func_name = func_m.group(2)

    full_m = re.search(r"([\w.:]+)\s*$", before)
    full_name = full_m.group(1) if full_m else func_name

    args_so_far = line_text[call_end + 1:]
    arg_index   = _count_arg_index("(" + args_so_far)

    return func_name, full_name, arg_index, separator


class SignatureHelpEngine:

    _instance = None
    _lock     = threading.Lock()

    @classmethod
    def instance(cls) -> "SignatureHelpEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def get_sig(self, view: sublime.View, func_name: str, full_name: str,
                separator: str = ".") -> dict | None:
        """
        Lookup order — critical to get right:
          1. Current view's source (sync, instant) — catches user functions
             even before the background indexer finishes
          2. Module member via require() chain
          3. OOP class methods
          4. LOVE_SIGS built-in dict (LAST — so HC.rectangle beats love.graphics.rectangle)

        This ordering fixes:
          - "rectangle(...,...)" → finds HC:rectangle(x,y,w,h) in step 1
          - "no parameters" on fresh open → step 1 parses source synchronously
          - p = player:new() → step 3 resolves instance type to class
        """
        import re as _re

        # ── Step 0: resolve instance variable  p = Player.new() / player:new() ──
        # If func_name matches a method of the resolved class, use that
        try:
            from Love2D_Ultimate.symbol_indexer import SymbolIndexer
            indexer = SymbolIndexer.instance()

            # resolve  p.  or  p:  through constructor type
            if _re.search(r"[.:]", full_name):
                parts    = _re.split(r"[.:]", full_name)
                var_name = parts[0]
                fn_name  = parts[-1]
                class_name = indexer._resolve_var_class(view, var_name)
                if class_name:
                    # look up fn_name in that class via OOP engine
                    try:
                        from Love2D_Ultimate.oop_completion import OopCompletionEngine
                        oop = OopCompletionEngine.instance()
                        cls = oop._find_class_by_name(view, class_name)
                        if cls:
                            for mth in cls.methods:
                                if mth.name == fn_name:
                                    params = [p for p in mth.params if p != "self"]
                                    return {
                                        "params": params,
                                        "types":  [""] * len(params),
                                        "returns": "",
                                        "doc":    mth.doc,
                                        "wiki":   "",
                                        "optional_from": len(params),
                                        "is_method": separator == ":",
                                    }
                    except Exception:
                        pass
        except Exception:
            pass

        # ── Step 1: synchronous scan of current view source ───────────────────
        # This fires INSTANTLY — no waiting for background indexer.
        # Searches for  function funcname(params)  in the file the cursor is in.
        try:
            source = view.substr(sublime.Region(0, view.size()))
            # Pattern covers:  function foo(  /  function M.foo(  /  function M:foo(
            pat = _re.compile(
                r"function\s+(?:[\w.]+[.:])?(" + _re.escape(func_name) +
                r")\s*\(([^)]*)\)"
            )
            for m in pat.finditer(source):
                raw_params = m.group(2)
                params = [p.strip() for p in raw_params.split(",") if p.strip()]
                params = [p for p in params if p not in ("self",)]
                if params or raw_params.strip() == "":
                    types = []
                    # Check for ---@param annotations above the function
                    line_no = source[:m.start()].count("\n")
                    lines   = source.splitlines()
                    ann_params = {}
                    for i in range(line_no - 1, max(-1, line_no - 10), -1):
                        al = lines[i].strip() if i < len(lines) else ""
                        am = _re.match(r"---@param\s+(\w+)\s+(\S+)", al)
                        if am:
                            ann_params[am.group(1)] = am.group(2)
                        elif not al.startswith("--"):
                            break
                    for p in params:
                        pname = p.split(":")[0].strip()
                        types.append(ann_params.get(pname, ""))
                    return {
                        "params": params,
                        "types":  types,
                        "returns": "",
                        "doc": "",
                        "wiki": "",
                        "optional_from": len(params),
                        "is_method": separator == ":",
                    }
        except Exception as exc:
            import logging
            logging.getLogger("Love2D_Ultimate.sighel").debug(f"sync scan: {exc}")

        # ── Step 2: symbol indexer (background-indexed files) ─────────────────
        try:
            from Love2D_Ultimate.symbol_indexer import SymbolIndexer
            indexer = SymbolIndexer.instance()

            # Module member path:  module.func(  or  module:method(
            if _re.search(r"[.:]", full_name):
                parts    = _re.split(r"[.:]", full_name)
                var_name = parts[0]
                fn_name  = parts[-1]
                source   = view.substr(sublime.Region(0, view.size()))
                pat      = _re.compile(
                    r"(?:local\s+)?" + _re.escape(var_name) +
                    r"\s*=\s*require\s*\(\s*['\"]([^\'\"]+)['\"]\s*\)"
                )
                rm = pat.search(source)
                if rm:
                    folders  = view.window().folders() if view.window() else []
                    resolved = indexer._resolve_require_path(rm.group(1), folders)
                    if resolved:
                        fi = indexer.get_file_index(resolved)
                        if not fi:
                            try:
                                with open(resolved, encoding="utf-8", errors="replace") as fh:
                                    src = fh.read()
                                indexer._parse_and_cache(resolved, src, 0)
                                fi = indexer.get_file_index(resolved)
                            except OSError:
                                pass
                        if fi:
                            for sym in fi.symbols:
                                bare = sym.name.split(".")[-1].split(":")[-1]
                                if bare == fn_name and sym.params:
                                    params = [p.split(":")[0].strip() for p in sym.params
                                              if p.split(":")[0].strip() != "self"]
                                    types  = [p.split(":")[-1].strip() if ":" in p else ""
                                              for p in sym.params
                                              if p.split(":")[0].strip() != "self"]
                                    return {
                                        "params": params, "types": types,
                                        "returns": "",
                                        "doc": sym.doc, "wiki": "",
                                        "optional_from": len(params),
                                        "is_method": separator == ":",
                                    }

            # Direct symbol lookup
            sym = indexer._lookup(view, func_name)
            if sym and sym.params:
                params = [p.split(":")[0].strip() for p in sym.params
                          if p.split(":")[0].strip() != "self"]
                types  = [p.split(":")[-1].strip() if ":" in p else ""
                          for p in sym.params
                          if p.split(":")[0].strip() != "self"]
                return {
                    "params": params, "types": types,
                    "returns": ", ".join(sym.returns) if sym.returns else "",
                    "doc": sym.doc, "wiki": "",
                    "optional_from": len(params),
                    "is_method": separator == ":",
                }
        except Exception as exc:
            import logging
            logging.getLogger("Love2D_Ultimate.sighel").debug(f"indexer sig: {exc}")

        # ── Step 3: OOP engine (class method registry) ────────────────────────
        try:
            from Love2D_Ultimate.oop_completion import OopCompletionEngine
            oop = OopCompletionEngine.instance()
            for cls_info in oop.get_all_classes():
                for mth in cls_info.methods:
                    if mth.name == func_name:
                        params = [p for p in mth.params if p != "self"]
                        return {
                            "params": params,
                            "types":  [""] * len(params),
                            "returns": "",
                            "doc":    mth.doc,
                            "wiki":   "",
                            "optional_from": len(params),
                            "is_method": mth.is_colon or separator == ":",
                        }
        except Exception as exc:
            import logging
            logging.getLogger("Love2D_Ultimate.sighel").debug(f"oop sig: {exc}")

        # ── Step 4: Built-in LOVE_SIGS (LAST so user functions take priority) ─
        if func_name in LOVE_SIGS:
            d = dict(LOVE_SIGS[func_name])
            d["is_method"] = separator == ":"
            return d

        return None

    def build_html(self, func_name: str, sig: dict, arg_index: int) -> str:
        """
        Builds a clear, large, readable signature popup.

        Example:
        ┌─────────────────────────────────────────────────────┐
        │ function  player.new ( x, y, w, h, i )              │
        │                         ↑ arg 3 of 5                │
        │ w  number  Width of the player.                     │
        │ → number, number                                    │
        │ 🔗 wiki                                              │
        └─────────────────────────────────────────────────────┘
        """
        params      = sig.get("params", [])
        types       = sig.get("types", [])
        returns     = sig.get("returns", "")
        doc         = sig.get("doc", "")
        wiki        = sig.get("wiki", "")
        opt_from    = sig.get("optional_from", len(params))
        is_method   = sig.get("is_method", False)

        # Build parameter spans
        param_parts = []
        for i, p in enumerate(params):
            is_opt    = i >= opt_from
            ptype     = types[i] if i < len(types) else ""
            is_active = (i == arg_index)

            # Build param display
            label = p
            if is_opt and "?" not in ptype:
                label = f"{p}?"
            if ptype:
                display = f"{label}: {ptype}"
            else:
                display = label

            if is_active:
                param_parts.append(
                    f'<span style="color:#f0c040;font-weight:bold;'
                    f'text-decoration:underline">{display}</span>'
                )
            elif is_opt:
                param_parts.append(
                    f'<span style="color:#6a9955">{display}</span>'
                )
            else:
                param_parts.append(
                    f'<span style="color:#9cdcfe">{display}</span>'
                )

        comma_sep = '<span style="color:#d4d4d4">, </span>'
        params_html = comma_sep.join(param_parts) if param_parts else \
                      '<span style="color:#6a9955">no parameters</span>'

        # Method vs function label
        kind_label = "method" if is_method else "function"
        sep_html   = '<span style="color:#d4d4d4">:</span>' if is_method else \
                     '<span style="color:#d4d4d4">.</span>'

        # Arg info line
        total = len(params)
        if total > 0:
            current_param = params[min(arg_index, total - 1)]
            current_type  = types[min(arg_index, total - 1)] if arg_index < len(types) else ""
            is_opt_current = arg_index >= opt_from
            arg_info = (
                f'<span style="color:#888;font-size:12px">'
                f'arg {min(arg_index+1, total)} of {total}'
                f'{" (optional)" if is_opt_current else ""}</span>'
            )
            # Current param detail
            param_detail = f'<span style="color:#f0c040;font-weight:bold">{current_param}</span>'
            if current_type:
                param_detail += f' <span style="color:#4ec9b0">{current_type}</span>'
        else:
            arg_info = '<span style="color:#888;font-size:12px">no parameters</span>'
            param_detail = ""

        # Return type
        ret_html = ""
        if returns:
            ret_html = (
                f'<div style="margin-top:4px">'
                f'<span style="color:#888;font-size:11px">returns </span>'
                f'<span style="color:#4ec9b0;font-size:11px">{returns}</span>'
                f'</div>'
            )

        # Doc string
        doc_html = ""
        if doc:
            doc_html = (
                f'<div style="margin-top:4px;color:#d4d4d4;font-size:12px">'
                f'{doc}</div>'
            )

        # Wiki link
        wiki_html = ""
        if wiki:
            wiki_html = (
                f'<div style="margin-top:4px">'
                f'<a href="{wiki}" style="color:#569cd6;font-size:11px">📖 Love2D wiki</a>'
                f'</div>'
            )

        # Separator line
        sep_line = '<hr style="border:none;border-top:1px solid #333;margin:5px 0">'

        css = (
            "<style>"
            "body{font-family:monospace;font-size:14px;margin:8px 12px;"
            "background:#1e1e1e;color:#d4d4d4;min-width:420px}"
            ".fn{color:#dcdcaa;font-weight:bold;font-size:15px}"
            ".kind{color:#569cd6;font-size:11px;margin-right:6px}"
            ".paren{color:#d4d4d4;font-size:15px;font-weight:bold}"
            "</style>"
        )

        # Function signature line
        sig_line = (
            f'<span class="kind">{kind_label}</span>'
            f'<span class="fn">{func_name}</span>'
            f'<span class="paren">(</span>'
            f'{params_html}'
            f'<span class="paren">)</span>'
        )

        # Assemble
        html = (
            f"{css}"
            f'<div style="margin-bottom:6px">{sig_line}</div>'
        )
        if param_detail:
            html += f'<div style="margin-bottom:3px">{param_detail} &nbsp; {arg_info}</div>'
        if doc or returns or wiki:
            html += sep_line
        html += doc_html + ret_html + wiki_html
        return html


class SignatureHelpListener(sublime_plugin.ViewEventListener):

    @classmethod
    def is_applicable(cls, s: sublime.Settings) -> bool:
        return bool(sublime.load_settings(SETTINGS_FILE).get("signature_help_enabled", True))

    def __init__(self, view: sublime.View) -> None:
        super().__init__(view)
        self._pending = False

    def on_modified_async(self) -> None:
        if not self.view.match_selector(0, "source.lua"):
            return
        if not self._pending:
            self._pending = True
            sublime.set_timeout(self._update, 0)

    def on_selection_modified_async(self) -> None:
        if not self.view.match_selector(0, "source.lua"):
            return
        if not self._pending:
            self._pending = True
            sublime.set_timeout(self._update, 0)

    def _update(self) -> None:
        self._pending = False
        view = self.view
        sel  = view.sel()
        if not sel:
            view.hide_popup()
            return

        pt     = sel[0].begin()
        result = _find_call_context(view, pt)
        if result is None:
            view.hide_popup()
            return

        func_name, full_name, arg_index, separator = result
        engine = SignatureHelpEngine.instance()
        sig    = engine.get_sig(view, func_name, full_name, separator)
        if sig is None:
            view.hide_popup()
            return

        html = engine.build_html(func_name, sig, arg_index)

        if view.is_popup_visible():
            view.update_popup(html)
        else:
            view.show_popup(
                html,
                flags=sublime.COOPERATE_WITH_AUTO_COMPLETE,
                location=pt,
                max_width=700,
                max_height=200,
            )


class LoveShowSignatureHelpCommand(sublime_plugin.TextCommand):
    def run(self, edit: sublime.Edit) -> None:
        sel = self.view.sel()
        if not sel: return
        pt     = sel[0].begin()
        result = _find_call_context(self.view, pt)
        if not result:
            sublime.status_message("Not inside a function call")
            return
        func_name, full_name, arg_index, separator = result
        engine = SignatureHelpEngine.instance()
        sig    = engine.get_sig(self.view, func_name, full_name, separator)
        if not sig:
            sublime.status_message(f"No signature found for '{func_name}'")
            return
        html = engine.build_html(func_name, sig, arg_index)
        self.view.show_popup(
            html, flags=sublime.COOPERATE_WITH_AUTO_COMPLETE,
            location=pt, max_width=700, max_height=200,
        )
    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")
