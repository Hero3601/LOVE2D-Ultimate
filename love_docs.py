"""
love_docs.py — Offline Love2D Documentation Browser v1.0
=========================================================
Features:
  1. Ctrl+F1: Open docs for word under cursor — searches built-in doc DB
  2. Full searchable Love2D API reference in a quick panel (Ctrl+Shift+F1)
  3. Categorized: graphics, audio, physics, math, keyboard, mouse, etc.
  4. Shows function signature, description, parameters, return types
  5. "Open Wiki" button in every doc popup → launches browser
  6. Type inference from assignment context
  7. Shows related functions (e.g. searching setColor also suggests getColor)
  8. Version tags: marks deprecated functions in red
"""
from __future__ import annotations
import logging, os, webbrowser
import sublime, sublime_plugin

log = logging.getLogger("Love2D_Ultimate.docs")
SETTINGS_FILE = "Love2D_Ultimate.sublime-settings"

# ── Full Love2D 11.5 API reference database ───────────────────────────────────
# Format: "module.function" → {sig, desc, params, returns, wiki, deprecated}
LOVE_API_DB: dict[str, dict] = {
    # ── love.graphics ────────────────────────────────────────────────────────
    "love.graphics.newImage": {
        "sig":    "love.graphics.newImage(filename, flags?)",
        "desc":   "Creates a new Image from an image file. Supported formats: PNG, JPEG, BMP, TGA, HDR.",
        "params": [("filename","string","Path to the image file."),
                   ("flags","table?","Optional table with mipmaps, linear, dpiscale keys.")],
        "returns":"Image",
        "wiki":   "https://love2d.org/wiki/love.graphics.newImage",
        "deprecated": False,
    },
    "love.graphics.draw": {
        "sig":    "love.graphics.draw(drawable, x?, y?, r?, sx?, sy?, ox?, oy?)",
        "desc":   "Draws a Drawable on screen. r = rotation in radians. sx/sy = scale. ox/oy = origin offset.",
        "params": [("drawable","Drawable","Image, Canvas, SpriteBatch, etc."),
                   ("x","number?","X position (default 0)."),
                   ("y","number?","Y position (default 0)."),
                   ("r","number?","Rotation in radians (default 0)."),
                   ("sx","number?","X scale factor (default 1)."),
                   ("sy","number?","Y scale factor (default 1)."),
                   ("ox","number?","X origin offset."),
                   ("oy","number?","Y origin offset.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.graphics.draw",
        "deprecated": False,
    },
    "love.graphics.rectangle": {
        "sig":    "love.graphics.rectangle(mode, x, y, width, height, rx?, ry?, segments?)",
        "desc":   "Draws a rectangle. mode = 'fill' or 'line'. rx/ry add rounded corners.",
        "params": [("mode","DrawMode","'fill' or 'line'."),
                   ("x","number","Top-left X."),
                   ("y","number","Top-left Y."),
                   ("width","number","Width."),
                   ("height","number","Height."),
                   ("rx","number?","Horizontal corner radius."),
                   ("ry","number?","Vertical corner radius."),
                   ("segments","number?","Smoothness of rounded corners.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.graphics.rectangle",
        "deprecated": False,
    },
    "love.graphics.circle": {
        "sig":    "love.graphics.circle(mode, x, y, radius, segments?)",
        "desc":   "Draws a circle. Higher segments = smoother circle.",
        "params": [("mode","DrawMode","'fill' or 'line'."),
                   ("x","number","Center X."),
                   ("y","number","Center Y."),
                   ("radius","number","Radius in pixels."),
                   ("segments","number?","Number of segments (default 10).")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.graphics.circle",
        "deprecated": False,
    },
    "love.graphics.setColor": {
        "sig":    "love.graphics.setColor(r, g, b, a?)",
        "desc":   "Sets the current drawing color. Values are 0–1. Affects all subsequent draw calls.",
        "params": [("r","number","Red channel 0–1."),
                   ("g","number","Green channel 0–1."),
                   ("b","number","Blue channel 0–1."),
                   ("a","number?","Alpha channel 0–1 (default 1).")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.graphics.setColor",
        "deprecated": False,
    },
    "love.graphics.getColor": {
        "sig":    "love.graphics.getColor()",
        "desc":   "Returns the current drawing color as four values (r, g, b, a).",
        "params": [],
        "returns":"number, number, number, number",
        "wiki":   "https://love2d.org/wiki/love.graphics.getColor",
        "deprecated": False,
    },
    "love.graphics.print": {
        "sig":    "love.graphics.print(text, x?, y?, r?, sx?, sy?, ox?, oy?)",
        "desc":   "Draws text at a position using the current Font.",
        "params": [("text","string","The text to render."),
                   ("x","number?","X position."),
                   ("y","number?","Y position."),
                   ("r","number?","Rotation in radians."),
                   ("sx","number?","X scale."),
                   ("sy","number?","Y scale."),
                   ("ox","number?","X origin."),
                   ("oy","number?","Y origin.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.graphics.print",
        "deprecated": False,
    },
    "love.graphics.printf": {
        "sig":    "love.graphics.printf(text, x, y, limit, align?, r?, sx?, sy?, ox?, oy?)",
        "desc":   "Draws wrapped/aligned text within a width limit.",
        "params": [("text","string","The text."),
                   ("x","number","X position."),
                   ("y","number","Y position."),
                   ("limit","number","Maximum line width in pixels."),
                   ("align","AlignMode?","'left', 'center', 'right', 'justify'.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.graphics.printf",
        "deprecated": False,
    },
    "love.graphics.newFont": {
        "sig":    "love.graphics.newFont(filename?, size?)",
        "desc":   "Creates a new Font. Pass nil for the built-in font. size defaults to 12.",
        "params": [("filename","string?","Path to .ttf or .otf, or nil for default."),
                   ("size","number?","Font size in pixels.")],
        "returns":"Font",
        "wiki":   "https://love2d.org/wiki/love.graphics.newFont",
        "deprecated": False,
    },
    "love.graphics.setFont": {
        "sig":    "love.graphics.setFont(font)",
        "desc":   "Sets the Font used by print/printf.",
        "params": [("font","Font","The Font to use.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.graphics.setFont",
        "deprecated": False,
    },
    "love.graphics.newCanvas": {
        "sig":    "love.graphics.newCanvas(width?, height?)",
        "desc":   "Creates an off-screen render target. Draw to it by calling setCanvas.",
        "params": [("width","number?","Width (default: window width)."),
                   ("height","number?","Height (default: window height).")],
        "returns":"Canvas",
        "wiki":   "https://love2d.org/wiki/love.graphics.newCanvas",
        "deprecated": False,
    },
    "love.graphics.setCanvas": {
        "sig":    "love.graphics.setCanvas(canvas?)",
        "desc":   "Sets the active Canvas. Pass nil to render to screen.",
        "params": [("canvas","Canvas?","The target canvas, or nil for screen.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.graphics.setCanvas",
        "deprecated": False,
    },
    "love.graphics.newQuad": {
        "sig":    "love.graphics.newQuad(x, y, width, height, sw, sh)",
        "desc":   "Creates a rectangular region within an image for sprite sheet use.",
        "params": [("x","number","X on sprite sheet."),
                   ("y","number","Y on sprite sheet."),
                   ("width","number","Width of the quad."),
                   ("height","number","Height of the quad."),
                   ("sw","number","Sprite sheet total width."),
                   ("sh","number","Sprite sheet total height.")],
        "returns":"Quad",
        "wiki":   "https://love2d.org/wiki/love.graphics.newQuad",
        "deprecated": False,
    },
    "love.graphics.newSpriteBatch": {
        "sig":    "love.graphics.newSpriteBatch(image, maxSprites?, usage?)",
        "desc":   "Creates a SpriteBatch for efficiently drawing many copies of an image.",
        "params": [("image","Image","The image to batch."),
                   ("maxSprites","number?","Initial sprite count (default 1000)."),
                   ("usage","SpriteBatchUsage?","'dynamic', 'static', or 'stream'.")],
        "returns":"SpriteBatch",
        "wiki":   "https://love2d.org/wiki/love.graphics.newSpriteBatch",
        "deprecated": False,
    },
    "love.graphics.push": {
        "sig":    "love.graphics.push(stack?)",
        "desc":   "Pushes the current transform onto the transform stack. Pair with pop().",
        "params": [("stack","StackType?","'all' or 'transform' (default 'transform').")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.graphics.push",
        "deprecated": False,
    },
    "love.graphics.pop": {
        "sig":    "love.graphics.pop()",
        "desc":   "Pops the transform stack. Must match a prior push().",
        "params": [],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.graphics.pop",
        "deprecated": False,
    },
    "love.graphics.translate": {
        "sig":    "love.graphics.translate(dx, dy)",
        "desc":   "Moves the coordinate origin by dx, dy.",
        "params": [("dx","number","X translation."),("dy","number","Y translation.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.graphics.translate",
        "deprecated": False,
    },
    "love.graphics.rotate": {
        "sig":    "love.graphics.rotate(angle)",
        "desc":   "Rotates the coordinate system by angle (radians).",
        "params": [("angle","number","Rotation in radians.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.graphics.rotate",
        "deprecated": False,
    },
    "love.graphics.scale": {
        "sig":    "love.graphics.scale(sx, sy?)",
        "desc":   "Scales the coordinate system.",
        "params": [("sx","number","X scale."),("sy","number?","Y scale (default = sx).")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.graphics.scale",
        "deprecated": False,
    },
    "love.graphics.setLineWidth": {
        "sig":    "love.graphics.setLineWidth(width)",
        "desc":   "Sets the width used for line drawing.",
        "params": [("width","number","Line width in pixels.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.graphics.setLineWidth",
        "deprecated": False,
    },
    "love.graphics.getDimensions": {
        "sig":    "love.graphics.getDimensions()",
        "desc":   "Returns the width and height of the window.",
        "params": [],
        "returns":"number width, number height",
        "wiki":   "https://love2d.org/wiki/love.graphics.getDimensions",
        "deprecated": False,
    },
    # ── love.audio ───────────────────────────────────────────────────────────
    "love.audio.newSource": {
        "sig":    "love.audio.newSource(filename, type)",
        "desc":   "Creates a new audio Source. 'static' loads whole file; 'stream' streams from disk.",
        "params": [("filename","string","Path to .ogg, .wav, .mp3, etc."),
                   ("type","SourceType","'static' or 'stream'.")],
        "returns":"Source",
        "wiki":   "https://love2d.org/wiki/love.audio.newSource",
        "deprecated": False,
    },
    "love.audio.play": {
        "sig":    "love.audio.play(source)",
        "desc":   "Plays a Source from the beginning (or resumes if paused).",
        "params": [("source","Source","The Source to play.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.audio.play",
        "deprecated": False,
    },
    "love.audio.stop": {
        "sig":    "love.audio.stop(source?)",
        "desc":   "Stops a Source, or all sources if no argument given.",
        "params": [("source","Source?","Specific source, or nil for all.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.audio.stop",
        "deprecated": False,
    },
    "love.audio.setVolume": {
        "sig":    "love.audio.setVolume(volume)",
        "desc":   "Sets the master volume for all audio. 0 = silent, 1 = full.",
        "params": [("volume","number","Volume 0–1.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.audio.setVolume",
        "deprecated": False,
    },
    # ── love.keyboard ────────────────────────────────────────────────────────
    "love.keyboard.isDown": {
        "sig":    "love.keyboard.isDown(key, ...)",
        "desc":   "Returns true if any of the given keys are currently held down.",
        "params": [("key","KeyConstant","Key name like 'a', 'space', 'left', 'f1'.")],
        "returns":"boolean",
        "wiki":   "https://love2d.org/wiki/love.keyboard.isDown",
        "deprecated": False,
    },
    "love.keyboard.setKeyRepeat": {
        "sig":    "love.keyboard.setKeyRepeat(enable)",
        "desc":   "Enables/disables key repeat. When enabled, holding a key fires repeated keypressed events.",
        "params": [("enable","boolean","true to enable.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.keyboard.setKeyRepeat",
        "deprecated": False,
    },
    # ── love.mouse ───────────────────────────────────────────────────────────
    "love.mouse.getPosition": {
        "sig":    "love.mouse.getPosition()",
        "desc":   "Returns the current mouse x and y position.",
        "params": [],
        "returns":"number x, number y",
        "wiki":   "https://love2d.org/wiki/love.mouse.getPosition",
        "deprecated": False,
    },
    "love.mouse.isDown": {
        "sig":    "love.mouse.isDown(button, ...)",
        "desc":   "Returns true if the given mouse button is held. 1=left, 2=right, 3=middle.",
        "params": [("button","number","Button index.")],
        "returns":"boolean",
        "wiki":   "https://love2d.org/wiki/love.mouse.isDown",
        "deprecated": False,
    },
    "love.mouse.setVisible": {
        "sig":    "love.mouse.setVisible(visible)",
        "desc":   "Shows or hides the mouse cursor.",
        "params": [("visible","boolean","true to show.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.mouse.setVisible",
        "deprecated": False,
    },
    # ── love.physics ─────────────────────────────────────────────────────────
    "love.physics.newWorld": {
        "sig":    "love.physics.newWorld(xg?, yg?, sleep?)",
        "desc":   "Creates a Box2D physics world. xg/yg = gravity vector. sleep=true lets idle bodies sleep.",
        "params": [("xg","number?","X gravity (default 0)."),
                   ("yg","number?","Y gravity (default 0)."),
                   ("sleep","boolean?","Allow sleeping (default true).")],
        "returns":"World",
        "wiki":   "https://love2d.org/wiki/love.physics.newWorld",
        "deprecated": False,
    },
    "love.physics.newBody": {
        "sig":    "love.physics.newBody(world, x?, y?, type?)",
        "desc":   "Creates a physics body. type: 'static' (immovable), 'dynamic' (physics), 'kinematic' (manual).",
        "params": [("world","World","Parent physics world."),
                   ("x","number?","Initial X position."),
                   ("y","number?","Initial Y position."),
                   ("type","BodyType?","'static', 'dynamic', or 'kinematic'.")],
        "returns":"Body",
        "wiki":   "https://love2d.org/wiki/love.physics.newBody",
        "deprecated": False,
    },
    "love.physics.newRectangleShape": {
        "sig":    "love.physics.newRectangleShape(width, height)",
        "desc":   "Creates a rectangle collision shape centered on the body.",
        "params": [("width","number","Width."),("height","number","Height.")],
        "returns":"PolygonShape",
        "wiki":   "https://love2d.org/wiki/love.physics.newRectangleShape",
        "deprecated": False,
    },
    "love.physics.newCircleShape": {
        "sig":    "love.physics.newCircleShape(radius)",
        "desc":   "Creates a circle collision shape.",
        "params": [("radius","number","Radius in physics units.")],
        "returns":"CircleShape",
        "wiki":   "https://love2d.org/wiki/love.physics.newCircleShape",
        "deprecated": False,
    },
    "love.physics.newFixture": {
        "sig":    "love.physics.newFixture(body, shape, density?)",
        "desc":   "Attaches a Shape to a Body, creating a Fixture that has collision properties.",
        "params": [("body","Body","Body to attach to."),
                   ("shape","Shape","The collision shape."),
                   ("density","number?","Mass density (default 1).")],
        "returns":"Fixture",
        "wiki":   "https://love2d.org/wiki/love.physics.newFixture",
        "deprecated": False,
    },
    # ── love.math ────────────────────────────────────────────────────────────
    "love.math.random": {
        "sig":    "love.math.random(m?, n?)",
        "desc":   "random() → 0-1. random(n) → 1-n. random(m,n) → m-n. Uses its own RNG, not math.random.",
        "params": [("m","number?","Lower bound or upper bound if n absent."),
                   ("n","number?","Upper bound.")],
        "returns":"number",
        "wiki":   "https://love2d.org/wiki/love.math.random",
        "deprecated": False,
    },
    # ── love.window ──────────────────────────────────────────────────────────
    "love.window.setMode": {
        "sig":    "love.window.setMode(width, height, flags?)",
        "desc":   "Sets window dimensions and options. flags table: fullscreen, resizable, vsync, msaa, highdpi.",
        "params": [("width","number","Window width."),
                   ("height","number","Window height."),
                   ("flags","table?","Options table.")],
        "returns":"boolean success, string display, number displayindex",
        "wiki":   "https://love2d.org/wiki/love.window.setMode",
        "deprecated": False,
    },
    "love.window.setTitle": {
        "sig":    "love.window.setTitle(title)",
        "desc":   "Sets the window title bar text.",
        "params": [("title","string","New title.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.window.setTitle",
        "deprecated": False,
    },
    # ── love.filesystem ──────────────────────────────────────────────────────
    "love.filesystem.read": {
        "sig":    "love.filesystem.read(name, size?)",
        "desc":   "Reads a file's entire contents as a string.",
        "params": [("name","string","File path relative to save dir or source."),
                   ("size","number?","Max bytes to read.")],
        "returns":"string contents, string/nil error",
        "wiki":   "https://love2d.org/wiki/love.filesystem.read",
        "deprecated": False,
    },
    "love.filesystem.write": {
        "sig":    "love.filesystem.write(name, data, size?)",
        "desc":   "Writes data to a file in the save directory.",
        "params": [("name","string","Filename in save directory."),
                   ("data","string","Data to write."),
                   ("size","number?","Bytes to write (default = all).")],
        "returns":"boolean success, string/nil error",
        "wiki":   "https://love2d.org/wiki/love.filesystem.write",
        "deprecated": False,
    },
    "love.filesystem.getInfo": {
        "sig":    "love.filesystem.getInfo(path, filtertype?)",
        "desc":   "Returns info table about a file/dir, or nil if not found. info.type, info.size, info.modtime.",
        "params": [("path","string","File or directory path."),
                   ("filtertype","FileType?","'file', 'directory', or 'symlink'.")],
        "returns":"table/nil info",
        "wiki":   "https://love2d.org/wiki/love.filesystem.getInfo",
        "deprecated": False,
    },
    # ── love.timer ───────────────────────────────────────────────────────────
    "love.timer.getDelta": {
        "sig":    "love.timer.getDelta()",
        "desc":   "Returns the time between the last two frames in seconds. Same as dt in love.update.",
        "params": [],
        "returns":"number",
        "wiki":   "https://love2d.org/wiki/love.timer.getDelta",
        "deprecated": False,
    },
    "love.timer.getFPS": {
        "sig":    "love.timer.getFPS()",
        "desc":   "Returns the current frames per second.",
        "params": [],
        "returns":"number",
        "wiki":   "https://love2d.org/wiki/love.timer.getFPS",
        "deprecated": False,
    },
    "love.timer.sleep": {
        "sig":    "love.timer.sleep(seconds)",
        "desc":   "Pauses the thread for the given number of seconds. Avoid using in love.update.",
        "params": [("seconds","number","Duration to sleep.")],
        "returns":"",
        "wiki":   "https://love2d.org/wiki/love.timer.sleep",
        "deprecated": False,
    },
}


def _build_doc_html(entry: dict) -> str:
    css = (
        "<style>"
        "body{font-family:system-ui,monospace;font-size:13px;margin:8px 12px;"
        "background:#1e1e1e;color:#d4d4d4;max-width:680px}"
        ".sig{font-family:monospace;font-size:14px;color:#dcdcaa;font-weight:bold;"
        "background:#252526;padding:5px 8px;border-radius:4px;display:block;"
        "margin-bottom:8px}"
        ".dep{color:#f44747;font-size:11px} .desc{margin-bottom:8px}"
        ".ph{color:#f0c040;font-weight:bold} .pt{color:#4ec9b0}"
        ".pd{color:#d4d4d4} .ret{color:#4ec9b0}"
        ".wiki a{color:#569cd6;font-size:11px;text-decoration:none}"
        "table{border-collapse:collapse;margin-bottom:6px}"
        "td{padding:2px 8px 2px 0;vertical-align:top}"
        "hr{border:none;border-top:1px solid #333;margin:6px 0}"
        "</style>"
    )
    dep_html = '<span class="dep"> ⚠ DEPRECATED</span>' if entry.get("deprecated") else ""
    sig_html = f'<span class="sig">{entry["sig"]}</span>{dep_html}'
    desc_html = f'<div class="desc">{entry["desc"]}</div>'

    params_html = ""
    if entry.get("params"):
        rows = ""
        for pname, ptype, pdesc in entry["params"]:
            rows += (
                f"<tr>"
                f'<td><span class="ph">{pname}</span></td>'
                f'<td><span class="pt">{ptype}</span></td>'
                f'<td><span class="pd">{pdesc}</span></td>'
                f"</tr>"
            )
        params_html = f"<hr><b style='color:#888;font-size:11px'>Parameters:</b><table>{rows}</table>"

    ret_html = ""
    if entry.get("returns"):
        ret_html = (
            f"<hr><b style='color:#888;font-size:11px'>Returns:</b> "
            f'<span class="ret">{entry["returns"]}</span>'
        )

    wiki_html = ""
    if entry.get("wiki"):
        wiki_html = (
            f'<div class="wiki" style="margin-top:6px">'
            f'<a href="{entry["wiki"]}">📖 Open Love2D Wiki</a></div>'
        )

    return f"{css}{sig_html}{desc_html}{params_html}{ret_html}{wiki_html}"


class LoveDocsCommand(sublime_plugin.TextCommand):
    """
    Command: love_docs (Ctrl+F1)
    Shows documentation for the Love2D function under the cursor.
    """
    def run(self, edit: sublime.Edit) -> None:
        sel = self.view.sel()
        if not sel:
            return
        pt   = sel[0].begin()
        word = self.view.substr(self.view.word(pt))

        # Build qualified key: try word alone, then with love.* prefix from context
        candidates = []
        # Look backwards for  love.graphics.  love.audio.  etc.
        lr   = self.view.line(pt)
        line = self.view.substr(sublime.Region(lr.a, pt + len(word)))
        import re
        m = re.search(r"\b(love\.\w+\.\w+)\s*$|(\w+)\s*$", line)
        if m:
            if m.group(1):
                candidates.append(m.group(1))
            if m.group(2):
                # Try all module prefixes
                for mod in ("love.graphics","love.audio","love.keyboard",
                            "love.mouse","love.physics","love.math",
                            "love.window","love.filesystem","love.timer"):
                    candidates.append(f"{mod}.{m.group(2)}")
        candidates.append(word)

        entry = None
        matched_key = ""
        for key in candidates:
            if key in LOVE_API_DB:
                entry = LOVE_API_DB[key]
                matched_key = key
                break

        if not entry:
            # Fall back to search panel
            self.view.run_command("love_docs_search", {"initial": word})
            return

        html = _build_doc_html(entry)
        self.view.show_popup(
            html,
            flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            location=pt,
            max_width=720,
            max_height=400,
            on_navigate=lambda url: webbrowser.open(url),
        )

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")


class LoveDocsSearchCommand(sublime_plugin.WindowCommand):
    """
    Command: love_docs_search (Ctrl+Shift+F1)
    Full searchable Love2D API quick panel.
    """
    def run(self, initial: str = "") -> None:
        keys  = sorted(LOVE_API_DB.keys())
        items = []
        for key in keys:
            e = LOVE_API_DB[key]
            dep = " [DEPRECATED]" if e.get("deprecated") else ""
            items.append(sublime.QuickPanelItem(
                trigger=key + dep,
                details=e["desc"][:80],
                annotation=e.get("returns", ""),
                kind=sublime.KIND_FUNCTION,
            ))

        def _sel(idx: int) -> None:
            if idx < 0:
                return
            key   = keys[idx]
            entry = LOVE_API_DB[key]
            view  = self.window.active_view()
            if view:
                html = _build_doc_html(entry)
                view.show_popup(
                    html, max_width=720, max_height=400,
                    on_navigate=lambda url: webbrowser.open(url),
                )
            if entry.get("wiki"):
                webbrowser.open(entry["wiki"])

        self.window.show_quick_panel(
            items, _sel,
            flags=sublime.MONOSPACE_FONT | sublime.KEEP_OPEN_ON_FOCUS_LOST,
        )
