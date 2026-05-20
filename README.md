# Love2D Ultimate

**The most complete Lua + Love2D development package for Sublime Text 4.**  
Smart completions, signature help, OOP intelligence, real-time diagnostics — all without a language server.

---

## What it does

Type `player.` and instantly see every exported function from `player.lua`.  
Type `p = player:new()` then `p:` and see all of player's colon methods.  
Type `love.graphics.draw(img,` and a popup shows every parameter with its type.  
Save a file and squiggly lines appear under typos, missing `end` blocks, and unused variables.

---

## Features at a glance

### Completions
| You type | You get |
|---|---|
| `module.` | Every dot function + field exported from that module |
| `module:` | Every colon method only |
| `self.` | Every field set in the constructor |
| `self:` | Every colon method of the current class |
| `p = M:new()` then `p.` / `p:` | Same as typing `M.` / `M:` directly |
| `love.graphics.newImage("` | Only image files from your project |
| `love.audio.newSource("` | Only audio files from your project |
| `require("` | Every `.lua` file in the project, dot-separated |

Arguments shown **inside** the dropdown — `new` shows as `new (x, y, w, h)`.

### Signature Help
Typing inside any function call shows a floating popup:
```
function  player:new( x: number,  y: number,  w: number,  h: number )
                                               ↑
                                          w  number   arg 3 of 4
```
Works for user-defined functions, all Love2D API, Lua stdlib, OOP methods.  
Fires **automatically** — no Ctrl+Space needed.

### Navigation
- **F12** — Go to definition (cross-file)
- **Ctrl+Shift+G** — Find all usages
- **Ctrl+Shift+O** — Symbol picker with `@filename:prefix` filtering
- **F2** — Scope-aware rename with diff preview

### Diagnostics (fires on every save, never while typing)
| Color | Meaning |
|---|---|
| Red squiggly | Unmatched bracket, missing `end` |
| Yellow squiggly | Love2D API typo, Lua keyword typo |
| Purple squiggly | Unused local, unused require, duplicate function |
| Orange squiggly | Alloc in loop, string concat in loop, missing `* dt`, no push/pop |

`Ctrl+.` opens a panel listing every issue with one-click jump.

### OOP Intelligence

```lua
local Player = {}
Player.__index = Player

function Player:new(x, y, w, h)
    local instance = {}
    instance.x = x or 0      -- detected: field  number  = 0
    instance.w = w or 100    -- detected: field  number  = 100
    setmetatable(instance, {__index = self})
    return instance
end

function Player:update(dt) end   -- colon method
function Player.getCount() end   -- dot function
```

`self.` → all fields with types and defaults  
`self:` → colon methods only  
`Player.` → dot functions + fields  
`Player:` → colon methods only  
`p = Player:new()` then `p.` / `p:` → same completions as Player itself

### Other Features
- **Breadcrumbs** — status bar shows `love.update › Player:move`, Ctrl+Shift+B to jump
- **Color tools** — hover over `setColor(r,g,b)` for a swatch, Ctrl+Alt+C to pick a color
- **Refactoring** — extract function, extract variable, inline variable, wrap in pcall, toggle local
- **Live game** — Ctrl+F5 runs Love2D and streams output; F8 jumps to last error
- **Asset completions** — `newImage("` shows only image files, `newSource("` only audio files
- **Performance hints** — warns about draw calls, missing dt, allocation in loops
- **Smart typing** — auto-close `()[]{}""''`, smart backspace, pair highlighting

---

## Installation

1. Copy this folder to:  
   `C:\Users\YOU\AppData\Roaming\Sublime Text\Packages\Love2D_Ultimate\`

2. Restart Sublime Text.

3. Open your Love2D project folder (`File → Open Folder`).  
   Indexing runs in the background — takes a few seconds.

---

## lua-language-server (optional)

The package works fully without LLS. LLS adds deeper type inference.

```
Step 1 — Install LSP via Package Control
         Ctrl+Shift+P → Package Control: Install Package → LSP

Step 2 — Download LuaLS binary
         https://github.com/LuaLS/lua-language-server/releases
         Extract to C:\tools\lua-language-server\

Step 3 — Set path in user settings
         Preferences → Package Settings → Love2D Ultimate → Settings – User
         { "lls_binary_path": "C:\\tools\\lua-language-server\\bin\\lua-language-server.exe" }

Step 4 — Apply
         Ctrl+Shift+P → Love2D: Re-configure LSP

Step 5 — Verify
         Ctrl+Shift+P → Love2D: Show Diagnostic Info
```

After adding LLS, run `Ctrl+Shift+P → Love2D: Write .luarc.json` in your project.

---

## Key bindings

| Key | Action |
|---|---|
| `F1` | Docs for symbol under cursor |
| `F2` | Rename symbol |
| `F8` | Jump to last Love2D error |
| `F12` | Go to definition |
| `Ctrl+F5` | Run game |
| `Shift+F5` | Stop game |
| `Ctrl+.` | Show all diagnostics |
| `Ctrl+Shift+B` | Breadcrumbs / function list |
| `Ctrl+Shift+E` | Jump to matching `end` |
| `Ctrl+Shift+G` | Find all usages |
| `Ctrl+Shift+O` | Symbol picker |
| `Ctrl+Shift+Space` | Show signature help |
| `Ctrl+Alt+A` | Add type annotations |
| `Ctrl+Alt+C` | Insert color |
| `Ctrl+Alt+E` | Extract function |
| `Ctrl+Alt+F` | Format file |
| `Ctrl+Alt+I` | Inline variable |
| `Ctrl+Alt+L` | Strip .lua from requires |
| `Ctrl+Alt+P` | Wrap in pcall |
| `Ctrl+Alt+T` | Toggle local |
| `Ctrl+Alt+V` | Extract variable |
| `Alt+Down / Up` | Next / previous function |

---

## Settings

`Preferences → Package Settings → Love2D Ultimate → Settings – User`

```json
{
    "lls_binary_path":        "",      // path to lua-language-server binary
    "love_binary":            "",      // path to love.exe (for Ctrl+F5)
    "live_reload":            false,   // restart game on every save
    "signature_help_enabled": true,    // parameter popup in function calls
    "smart_typing":           true,    // auto-close brackets and quotes
    "breadcrumbs":            true,    // scope path in status bar
    "color_preview":          true,    // color swatch on setColor() hover
    "code_intelligence":      true,    // unused vars, duplicate functions
    "perf_hints":             true,    // allocation-in-loop, missing dt
    "format_on_save":         false,   // auto-format with stylua on save
    "max_function_lines":     60,      // warn on functions longer than N lines
    "max_draw_calls_hint":    50       // warn when love.draw() has too many calls
}
```

---

## Snippets

| Trigger | Inserts |
|---|---|
| `lovemain` | Full `love.load / update / draw` skeleton |
| `lclass` | Complete OOP class with new, update, draw, return |
| `lmodule` | `local M = {}` module template |
| `lconf` | `love.conf(t)` with all window settings |
| `lrect` | `love.graphics.rectangle(...)` |
| `lcolor` | `love.graphics.setColor(r, g, b, a)` |
| `lprint` | `love.graphics.print(text, x, y)` |
| `lkeypressed` | `love.keypressed` with escape-quit |
