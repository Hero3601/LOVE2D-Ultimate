"""
color_preview.py — Love2D Color Preview & Helper v1.0
======================================================
Features:
  1. Hover over love.graphics.setColor(r,g,b,a) calls → shows color swatch
  2. Color picker command → inserts setColor with visual picker
  3. Converts between 0-1 and 0-255 color formats
  4. Shows hex color preview in hover popup
  5. Detects named color constants and shows their actual color
"""
from __future__ import annotations

import logging
import re
import sublime
import sublime_plugin

log = logging.getLogger("Love2D_Ultimate.color")
SETTINGS_FILE = "Love2D_Ultimate.sublime-settings"

# Matches: setColor(0.5, 0.2, 1.0)  or  setColor(0.5, 0.2, 1.0, 0.8)
RE_SET_COLOR = re.compile(
    r"""love\.graphics\.setColor\s*\(\s*"""
    r"""([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)"""
    r"""(?:\s*,\s*([\d.]+))?\s*\)"""
)

# Named Love2D-friendly colors (0-1 range)
NAMED_COLORS: dict[str, tuple] = {
    "red":     (1.0, 0.0, 0.0, 1.0),
    "green":   (0.0, 1.0, 0.0, 1.0),
    "blue":    (0.0, 0.0, 1.0, 1.0),
    "white":   (1.0, 1.0, 1.0, 1.0),
    "black":   (0.0, 0.0, 0.0, 1.0),
    "yellow":  (1.0, 1.0, 0.0, 1.0),
    "cyan":    (0.0, 1.0, 1.0, 1.0),
    "magenta": (1.0, 0.0, 1.0, 1.0),
    "orange":  (1.0, 0.5, 0.0, 1.0),
    "purple":  (0.5, 0.0, 0.5, 1.0),
    "pink":    (1.0, 0.75, 0.8, 1.0),
    "gray":    (0.5, 0.5, 0.5, 1.0),
    "grey":    (0.5, 0.5, 0.5, 1.0),
    "transparent": (0.0, 0.0, 0.0, 0.0),
}


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _to_hex(r: float, g: float, b: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        int(_clamp01(r) * 255),
        int(_clamp01(g) * 255),
        int(_clamp01(b) * 255),
    )


def _color_swatch_html(r: float, g: float, b: float, a: float = 1.0) -> str:
    """Build an HTML color swatch + info block."""
    hex_col  = _to_hex(r, g, b)
    r255     = int(r * 255)
    g255     = int(g * 255)
    b255     = int(b * 255)
    a_pct    = int(a * 100)

    # Text color: white on dark, black on light
    lum      = 0.299 * r + 0.587 * g + 0.114 * b
    txt_col  = "#ffffff" if lum < 0.5 else "#000000"

    css = (
        "<style>"
        "body{font-family:system-ui;font-size:12px;margin:4px 8px}"
        ".swatch{display:inline-block;width:48px;height:24px;"
        "border:1px solid #555;border-radius:3px;vertical-align:middle}"
        ".info{display:inline-block;margin-left:8px;vertical-align:middle}"
        ".hex{font-family:monospace;color:#4ec9b0}"
        ".rgb{color:#9cdcfe}"
        "</style>"
    )
    swatch = (
        f'<div class="swatch" style="background:{hex_col}">'
        f'<span style="color:{txt_col};font-family:monospace;font-size:10px;'
        f'padding:4px">{hex_col}</span></div>'
    )
    info = (
        f'<div class="info">'
        f'<span class="hex">{hex_col}</span><br>'
        f'<span class="rgb">rgba({r255}, {g255}, {b255}, {a_pct}%)</span><br>'
        f'<span class="rgb">love2d: ({r:.2f}, {g:.2f}, {b:.2f}, {a:.2f})</span>'
        f'</div>'
    )
    return f"{css}{swatch}{info}"


class ColorPreviewListener(sublime_plugin.EventListener):
    """Shows color swatches on hover over setColor calls."""

    def on_hover(self, view: sublime.View, point: int, hover_zone: int) -> None:
        if not view.match_selector(0, "source.lua"):
            return
        if hover_zone != sublime.HOVER_TEXT:
            return
        s = sublime.load_settings(SETTINGS_FILE)
        if not s.get("color_preview", True):
            return

        # Check if hovering near a setColor call
        # Expand search region around hover point
        region = sublime.Region(
            max(0, point - 120),
            min(view.size(), point + 120)
        )
        text = view.substr(region)
        m    = RE_SET_COLOR.search(text)
        if not m:
            return

        try:
            r = float(m.group(1))
            g = float(m.group(2))
            b = float(m.group(3))
            a = float(m.group(4)) if m.group(4) else 1.0
        except ValueError:
            return

        html = _color_swatch_html(r, g, b, a)
        view.show_popup(
            html,
            flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            location=point,
            max_width=350,
            max_height=100,
        )


class LoveInsertColorCommand(sublime_plugin.TextCommand):
    """
    Command: love_insert_color
    Shows a list of common colors and inserts the setColor call.
    """

    def run(self, edit: sublime.Edit) -> None:
        items = []
        color_list = []

        for name, (r, g, b, a) in NAMED_COLORS.items():
            hex_col = _to_hex(r, g, b)
            items.append(sublime.QuickPanelItem(
                trigger=name.capitalize(),
                details=f"{hex_col}  rgba({int(r*255)}, {int(g*255)}, {int(b*255)}, {int(a*100)}%)",
                annotation=f"({r:.1f}, {g:.1f}, {b:.1f})",
                kind=sublime.KIND_AMBIGUOUS,
            ))
            color_list.append((name, r, g, b, a))

        def _sel(idx: int) -> None:
            if idx < 0:
                return
            name, r, g, b, a = color_list[idx]
            if a < 1.0:
                code = f"love.graphics.setColor({r:.2f}, {g:.2f}, {b:.2f}, {a:.2f})"
            else:
                code = f"love.graphics.setColor({r:.2f}, {g:.2f}, {b:.2f})"
            sel = self.view.sel()
            if sel:
                self.view.run_command("insert", {"characters": code})

        self.view.window().show_quick_panel(items, _sel)

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")


class LoveConvertColorCommand(sublime_plugin.TextCommand):
    """
    Command: love_convert_color
    Converts selected color values between 0-1 and 0-255 ranges.
    Select something like  255, 128, 0  and run this to get  1.0, 0.50, 0.0
    """

    def run(self, edit: sublime.Edit) -> None:
        for sel in self.view.sel():
            if sel.empty():
                continue
            text = self.view.substr(sel).strip()
            nums = [float(x.strip()) for x in text.split(",") if x.strip()]
            if not nums:
                continue
            if max(nums) > 1.0:
                # Convert 255 → 0-1
                converted = [f"{v/255:.3f}" for v in nums]
                sublime.status_message("Converted 0-255 → 0-1")
            else:
                # Convert 0-1 → 255
                converted = [str(int(v * 255)) for v in nums]
                sublime.status_message("Converted 0-1 → 0-255")
            self.view.replace(edit, sel, ", ".join(converted))

    def is_enabled(self) -> bool:
        return self.view.match_selector(0, "source.lua")
