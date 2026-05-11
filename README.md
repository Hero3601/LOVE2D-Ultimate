# Love2D Ultimate

**The definitive Lua & Love2D development package for Sublime Text 4.**  
VSCode-parity IntelliSense, OOP completions, require() intelligence, real-time diagnostics, and a seamless migration path from Lovely2d / sublime_love / luaLove.

---

## Table of Contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [lua-language-server Setup](#lua-language-server-setup)
5. [Project Configuration](#project-configuration)
6. [Key Bindings Reference](#key-bindings-reference)
7. [Command Reference](#command-reference)
8. [Settings Reference](#settings-reference)
9. [Migrating from Legacy Packages](#migrating-from-legacy-packages)
10. [OOP Patterns Supported](#oop-patterns-supported)
11. [require() Intelligence](#require-intelligence)
12. [Diagnostics & Quick Fixes](#diagnostics--quick-fixes)
13. [Validation Checklist](#validation-checklist)
14. [Performance Tuning](#performance-tuning)
15. [Troubleshooting](#troubleshooting)
16. [Architecture Reference](#architecture-reference)

---

## Features

| Feature | Love2D Ultimate | Lovely2d | sublime_love | luaLove |
|---|---|---|---|---|
| Love2D API completions | ✅ Full 11.5 | Partial | Partial | Snippets only |
| OOP completions (self:, Foo:) | ✅ | ❌ | ❌ | ❌ |
| Cross-module hover docs | ✅ | ❌ | ❌ | ❌ |
| Go to Definition | ✅ | ❌ | ❌ | ❌ |
| Find All Usages | ✅ | ❌ | ❌ | ❌ |
| Project-wide Rename | ✅ | ❌ | ❌ | ❌ |
| require() path completions | ✅ | ❌ | ❌ | ❌ |
| .lua auto-strip in require() | ✅ | ❌ | ❌ | ❌ |
| Real-time typo detection | ✅ | ❌ | ❌ | ❌ |
| Missing `end` detection | ✅ | ❌ | ❌ | ❌ |
| Inline type-hint phantoms | ✅ | ❌ | ❌ | ❌ |
| EmmyLua / @class support | ✅ | ❌ | ❌ | ❌ |
| lua-language-server (LSP) | ✅ Auto-config | ❌ | ❌ | ❌ |
| Project scaffold generator | ✅ | ❌ | ❌ | ❌ |
| stylua / luaformatter | ✅ | ❌ | ❌ | ❌ |
| Symbol picker with MRU | ✅ | ❌ | ❌ | ❌ |
| Auto-import suggestion | ✅ | ❌ | ❌ | ❌ |

---

## Requirements

- **Sublime Text 4** (build 4090+)
- **Python 3.8+** (bundled with ST4)
- **Lua syntax package** — either `LuaExtended` (recommended) or built-in `Lua`

**Optional but strongly recommended:**
- [LSP package](https://packagecontrol.io/packages/LSP) (via Package Control)
- [lua-language-server](https://github.com/LuaLS/lua-language-server/releases) binary

**Optional formatters:**
- [stylua](https://github.com/JohnnyMorganz/StyLua) (Rust, fast)
- [lua-format](https://github.com/Koihik/LuaFormatter)

---

## Installation

### Via Package Control (recommended)

1. Open Command Palette → `Package Control: Install Package`
2. Search for `Love2D Ultimate` and install.

### Manual Installation

```bash
# Navigate to ST Packages directory:
# Windows: %APPDATA%\Sublime Text\Packages\
# macOS:   ~/Library/Application Support/Sublime Text/Packages/
# Linux:   ~/.config/sublime-text/Packages/

git clone https://github.com/your-username/Love2D_Ultimate.git
```

Restart Sublime Text. The package is immediately active for `.lua` files.

---

## lua-language-server Setup

For full IntelliSense (hover types, LSP diagnostics, signature help):

### Step 1: Install lua-language-server

**Windows:**
```powershell
winget install lua-language-server
# OR download from GitHub releases and add to PATH
```

**macOS:**
```bash
brew install lua-language-server
```

**Linux:**
```bash
# Ubuntu/Debian — via snap:
sudo snap install lua-language-server

# Or download binary from GitHub releases:
# https://github.com/LuaLS/lua-language-server/releases
```

### Step 2: Install the LSP package

```
Package Control: Install Package → LSP
```

### Step 3: Verify

Open Command Palette → `Love2D: Show Diagnostic Info`

You should see:
```
LSP package installed : ✓
lua-language-server   : /usr/local/bin/lua-language-server
```

Love2D Ultimate automatically configures LSP with:
- LuaJIT runtime (Love2D's Lua engine)
- Love2D global (`love`) recognised as valid
- Bundled Love2D 11.5 API stubs injected as library
- Call snippet completions enabled
- Inline parameter hints enabled

---

## Project Configuration

### Automatic (.luarc.json)

Run: `Love2D: Write .luarc.json for This Project`

This creates a `.luarc.json` in your project root that lua-language-server reads
to understand your Love2D environment. Commit this file to version control.

### Manual .luarc.json

```json
{
  "$schema": "https://raw.githubusercontent.com/LuaLS/vscode-lua/master/setting/schema.json",
  "runtime": { "version": "LuaJIT" },
  "diagnostics": { "globals": ["love"] },
  "workspace": {
    "library": ["path/to/Love2D_Ultimate/love_api_stubs"],
    "checkThirdParty": false
  },
  "completion": { "callSnippet": "Replace" },
  "hint": { "enable": true, "paramName": "All" }
}
```

### Sublime Project file

Add this to your `.sublime-project` to activate Love2D Ultimate settings per-project:

```json
{
  "folders": [{ "path": "." }],
  "settings": {
    "Love2D_Ultimate": {
      "formatter": "stylua",
      "inline_type_hints": true,
      "qf_suggest_local": true
    }
  }
}
```

---

## Key Bindings Reference

| Key | Action |
|---|---|
| `F12` | Go to Definition (falls back to indexer if LSP unavailable) |
| `F2` | Rename Symbol — project-wide with preview |
| `Ctrl+Shift+G` | Find All Usages |
| `Ctrl+Shift+O` | Symbol Picker (MRU-sorted, usage-count badges) |
| `Ctrl+.` | Show Quick Fixes panel |
| `Ctrl+Alt+L` | Strip `.lua` from all `require()` calls in file |
| `Ctrl+Shift+I` | Auto-Import: insert `require()` for symbol under cursor |
| `Ctrl+Alt+F` | Format file (stylua or luaformatter) |

All bindings are scoped to `source.lua` and do not interfere with other file types.

To remap, create `Packages/User/Love2D_Ultimate.sublime-keymap` and override.

---

## Command Reference

All commands are accessible via `Ctrl+Shift+P`:

| Command | Description |
|---|---|
| `Love2D: Go to Definition` | Jump to symbol definition |
| `Love2D: Find All Usages` | Show all references in quick panel |
| `Love2D: Symbol Picker (@)` | Browse all indexed symbols MRU-first |
| `Love2D: Rename Symbol` | Project-wide rename with confirmation |
| `Love2D: Strip .lua from require()` | Clean up require paths in current file |
| `Love2D: Auto-Import Symbol` | Insert require() for undefined symbol |
| `Love2D: Format File` | Run stylua / luaformatter |
| `Love2D: Show Quick Fixes` | Panel of all diagnostics with one-click fixes |
| `Love2D: New Project Scaffold` | Create a new Love2D project skeleton |
| `Love2D: Write .luarc.json` | Configure lua-language-server for this project |
| `Love2D: Re-Index Workspace` | Force a full workspace re-scan |
| `Love2D: Toggle Inline Type Hints` | Show/hide `→ returnType` phantoms |
| `Love2D: Show Diagnostic Info` | Debug panel: LSP, LLS, stubs status |
| `Love2D: Migrate from Legacy Packages` | Disable Lovely2d / sublime_love / luaLove |

---

## Settings Reference

Open: `Preferences → Package Settings → Love2D Ultimate → Settings`

```jsonc
{
  // Path to lua-language-server binary. Empty = auto-detect.
  "lls_binary_path": "",

  // Show → returnType phantom annotations after function definitions.
  "inline_type_hints": false,

  // Enable require() path completions.
  "require_completions": true,

  // Auto-strip .lua from require() as you type.
  "require_auto_strip": true,

  // Show hover documentation popups.
  "hover_docs_enabled": true,

  // Master switch for all diagnostics and quick-fix phantoms.
  "quick_fixes_enabled": true,

  // Individual diagnostic checks:
  "qf_check_typos": true,       // Love2D API & Lua keyword typo detection
  "qf_check_blocks": true,      // Missing 'end' detection
  "qf_check_brackets": true,    // Unmatched () [] {} detection
  "qf_suggest_local": false,    // Suggest 'local' for bare global assignments

  // External formatter: "stylua" | "luaformatter" | "none"
  "formatter": "stylua",

  // Run formatter on every save.
  "format_on_save": false,

  // Max file size (bytes) to include in workspace index.
  "max_index_file_size": 262144,

  // Background indexer thread count.
  "index_workers": 4,

  // Enable OOP (self:, Foo:) completions.
  "oop_completions_enabled": true,

  // Show symbol count in status bar.
  "status_bar_enabled": true,

  // Glob patterns to exclude from indexing.
  "index_ignore": ["*.min.lua", "build/**", ".git/**"]
}
```

---

## Migrating from Legacy Packages

### Automatic (recommended)

1. Open Command Palette → `Love2D: Migrate from Legacy Packages`
2. Review the list of detected packages.
3. Click **Migrate** — the wizard will:
   - Add the detected packages to `ignored_packages` in ST preferences
   - Generate a migration report in a new scratch view
4. Restart Sublime Text.

### Manual

Add conflicting packages to your `Preferences.sublime-settings`:

```json
{
  "ignored_packages": ["Lovely2d", "sublime_love", "luaLove"]
}
```

### Compatibility Shims

Love2D Ultimate recognises snippet trigger names from all three legacy packages.
If you relied on `lprint`, `lfunc`, `love:load` etc., they still expand — no
muscle memory lost.

---

## OOP Patterns Supported

### setmetatable + __index (canonical Lua OOP)

```lua
local MyClass = {}
MyClass.__index = MyClass

function MyClass.new(x, y)
    return setmetatable({ x = x, y = y, hp = 100 }, MyClass)
end

function MyClass:update(dt)   -- completions: self.x, self.y, self.hp, self:update
    self.x = self.x + dt
end
```

### hump.class / classic.lua / middleclass

```lua
local Class = require("hump.class")
local Player = Class:extend()   -- detected via :extend() pattern
function Player:init(x, y) ... end
```

### EmmyLua annotations (most precise)

```lua
---@class Player
---@field x number
---@field y number
---@field hp number
local Player = {}

---@param x number
---@param y number
---@return Player
function Player.new(x, y) ... end

---@param dt number
function Player:update(dt) ... end
```

With annotations, lua-language-server (when installed) gives 100% precise type
information including return types, generic types, and union types.

---

## require() Intelligence

### Path completion

Type `require("` and Love2D Ultimate scans your project for `.lua` files,
offering dot-separated paths (the Lua convention), without the `.lua` extension.

```lua
local p = require("entities.  -- dropdown: player, enemy, boss
```

### Auto-strip on typing

If you paste `require("path/to/file.lua")`, the extension is stripped within
1.5 seconds automatically (configurable via `require_auto_strip`).

### Manual strip

`Ctrl+Alt+L` or `Love2D: Strip .lua from require() Calls` — processes the
entire current file. Only strips when the target file actually exists on disk
(validated per-path to avoid false positives).

### init.lua resolution

`require("src/player")` correctly resolves to both:
- `src/player.lua`
- `src/player/init.lua`

---

## Diagnostics & Quick Fixes

### Real-time (on modify, debounced 80ms)

- **Unmatched brackets** — `(`, `[`, `{` with no closing pair
- **Unmatched `end`** — detected via block-depth counter

### On save (full scan)

- **Love2D API typos** — `love.grphics` → `love.graphics` (20+ patterns)
- **Lua keyword typos** — `funciton` → `function`, `retrun` → `return` (15+ patterns)
- **Missing `end`** — with line number of the unclosed opener
- **Bare globals** (optional, `qf_suggest_local: true`) — `x = 5` → suggest `local x = 5`

### One-click fixes

Each diagnostic shows an inline `[Fix]` link. Clicking it applies the fix
immediately. Or use `Ctrl+.` for a quick-panel listing all issues.

---

## Validation Checklist

Use `test_project/` as the target. Open the folder in ST, then verify:

```
□ 1. require() completions
      Type: local x = require("
      Expect: dropdown shows "modules.utils", "modules.vector", "entities.player"

□ 2. .lua auto-strip
      Open intentional_errors.lua
      Press Ctrl+Alt+L
      Expect: require("modules.vector.lua") → require("modules.vector")

□ 3. Cross-module hover
      In main.lua, hover over: utils.distance
      Expect popup: "utils.distance(x1, y1, x2, y2) → number"

□ 4. OOP completions — self:
      In entities/player.lua, inside Player:update(), type: self:
      Expect: update, draw, onKeyPressed, takeDamage

□ 5. OOP completions — Foo:
      In main.lua, type: player:
      Expect: update, draw, onKeyPressed, takeDamage

□ 6. Signature help (LSP required)
      Type: love.graphics.rectangle(
      Expect: popup showing (mode, x, y, width, height, rx?, ry?)

□ 7. Typo diagnostic
      Open intentional_errors.lua
      Save (Ctrl+S)
      Expect: phantom under "love.grphics" with "⚠ Possible typo"

□ 8. Missing end diagnostic
      In any .lua file, delete a closing 'end'
      Save
      Expect: "Love2D: 1 error(s)" in status bar + phantom at line

□ 9. Go to Definition
      In main.lua, place cursor on "Player"
      Press F12
      Expect: jumps to entities/player.lua, line 1

□ 10. Find All Usages
       Place cursor on "update" anywhere
       Press Ctrl+Shift+G
       Expect: quick panel listing all files/lines that call update

□ 11. Rename Symbol
        Place cursor on "takeDamage"
        Press F2, enter "applyDamage"
        Expect: all files updated, ST reloads changed views

□ 12. Inline type hints
        Run: Love2D: Toggle Inline Type Hints
        Expect: "→ number" phantoms appear after function return type lines

□ 13. Symbol picker
        Press Ctrl+Shift+O
        Expect: all functions/classes listed, MRU-sorted with usage count

□ 14. Auto-import
        In main.lua, type a symbol name from a module you haven't required
        Press Ctrl+Shift+I
        Expect: require() inserted at top of file

□ 15. LSP hover (requires lua-language-server)
        Hover over: love.graphics.draw
        Expect: full parameter list with types from bundled stubs

□ 16. Project scaffold
        Run: Love2D: New Project Scaffold
        Enter project name
        Expect: main.lua, conf.lua, .luarc.json, assets/ created

□ 17. Legacy migration
        (If Lovely2d installed): Run Love2D: Migrate from Legacy Packages
        Expect: migration report, packages added to ignored_packages
```

---

## Performance Tuning

### Memory footprint

| Workspace size | Approx. index RAM |
|---|---|
| 50 files | ~4 MB |
| 200 files | ~12 MB |
| 500 files | ~25 MB |

The LRU cache caps at 800 entries and evicts after 120 seconds TTL. Tune via:

```json
{
  "max_index_file_size": 131072,   // 128KB — skip large generated files
  "index_workers": 2               // reduce threads on low-RAM machines
}
```

### Completion latency

Target: <150ms from keypress to dropdown.

- The indexer runs entirely on background threads.
- `on_query_completions` only reads from the in-memory cache (no I/O).
- Debounce for `on_modified_async` is 80ms — increase if you notice UI stutter:

```python
# In Love2D_Ultimate.py, change:
COMPLETION_DEBOUNCE_MS = 150   # ms
```

### Disabling subsystems

If you only want LSP and no custom features:

```json
{
  "quick_fixes_enabled": false,
  "oop_completions_enabled": false,
  "require_completions": false,
  "hover_docs_enabled": false,
  "inline_type_hints": false
}
```

---

## Troubleshooting

### Completions not appearing

1. Check the scope: open a `.lua` file, run `Tools → Developer → Show Scope Name`.
   Must contain `source.lua`.
2. Check other completion providers: All Autocomplete can interfere.
   Disable it or ensure Love2D Ultimate's `INHIBIT_*` flags are active.
3. Force re-index: `Love2D: Re-Index Workspace`

### lua-language-server not detected

1. Run `Love2D: Show Diagnostic Info`.
2. If binary path shows ✗, install LLS and either:
   - Add it to your `PATH`, or
   - Set `"lls_binary_path": "/absolute/path/to/lua-language-server"` in settings.
3. Ensure the `LSP` package is installed.

### Hover popups not showing

- Verify `"hover_docs_enabled": true` in settings.
- The popup appears after ~200ms — hover and hold the mouse still.
- If LSP hover works but custom hover doesn't: the indexer may not have scanned
  the file yet. Save the file once to trigger indexing.

### require() completions show wrong paths

- Love2D Ultimate uses your **project folders** (window folders) as the root.
  Ensure you opened the folder containing `main.lua` via `File → Open Folder`.
- Check that the target `.lua` files are within those folders.

### Diagnostics not appearing after save

- Verify `"quick_fixes_enabled": true`.
- Check the ST console (`Ctrl+`` `) for `[Love2D_Ultimate]` log lines.
- Phantoms require ST build 4073+.

### Format on save not working

- Verify the formatter binary is on PATH: run `stylua --version` in terminal.
- Set `"lls_binary_path"` to the absolute path if needed.
- Check the ST console for `[Love2D_Ultimate.quickfix]` errors.

### "Love2D Ultimate detected legacy packages" dialog on every start

- Run `Love2D: Migrate from Legacy Packages` to permanently disable them.
- Or manually add them to `ignored_packages` in Preferences.

---

## Architecture Reference

```
Love2D_Ultimate/
├── Love2D_Ultimate.py      Central event hub, command registry, lifecycle
│                           Routes ST events to subsystems; owns the
│                           on_query_completions merger and deduplicator.
│
├── symbol_indexer.py       Async workspace scanner
│                           ThreadPoolExecutor, LRU cache, mtime-based
│                           incremental re-index. Provides: completions,
│                           hover, goto-def, find-usages, rename, phantoms.
│
├── oop_completion.py       OOP pattern extractor + completion provider
│                           Detects: setmetatable, colon methods, self.*,
│                           Class:extend(), @class annotations.
│
├── require_resolver.py     require() completions + .lua stripper
│                           Scans filesystem for .lua paths, caches 30s TTL,
│                           handles init.lua folder modules.
│
├── lsp_config.py           LSP & lua-language-server auto-configurator
│                           Writes LSP.sublime-settings sumneko client config,
│                           detects LLS binary cross-platform.
│
├── quick_fixes.py          Real-time diagnostics engine
│                           Bracket balance, block depth, typo detection,
│                           inline phantom markers, one-click fix commands.
│
├── love_api_stubs/
│   └── love.lua            EmmyLua-format Love2D 11.5 API stubs
│                           Fed to lua-language-server as workspace library.
│
├── test_project/           Validation target (not shipped in release)
│   ├── main.lua
│   ├── conf.lua
│   ├── entities/player.lua
│   ├── entities/enemy.lua
│   ├── modules/utils.lua
│   ├── modules/vector.lua
│   └── intentional_errors.lua
│
├── settings/Love2D_Ultimate.sublime-settings
├── Commands/Love2D_Ultimate.sublime-commands
├── Keybindings/Love2D_Ultimate.sublime-keymap
├── messages.json
└── README.md
```

### Data flow

```
User types keystroke
        │
        ▼
Love2DEventListener.on_modified_async()
        │  (debounced 80ms)
        ▼
QuickFixEngine.on_modified()   ←── bracket + block check only
        │
        ▼ (on_query_completions)
RequireResolver.completions_for()   ──┐
OopCompletionEngine.completions_for()─┤ merged + deduped
SymbolIndexer.completions_for()     ──┘
        │
        ▼
sublime.CompletionList (INHIBIT_WORD | INHIBIT_EXPLICIT)

User hovers
        │
        ▼
Love2DEventListener.on_hover()
        │  (async, 0ms)
        ▼
SymbolIndexer.hover_html_for()  →  view.show_popup()
OopCompletionEngine.hover_html_for()  (fallback)

File saved
        │
        ▼
Love2DEventListener.on_post_save_async()  (debounced 600ms)
        │
        ├──▶ SymbolIndexer.index_file()          (re-parse)
        └──▶ QuickFixEngine.run_on_save()         (full analysis)
```

---

## License

MIT License. See `LICENSE` for details.

## Contributing

PRs welcome. Before submitting:
1. Run the full validation checklist against `test_project/`.
2. Ensure no regressions in completion latency (target <150ms).
3. Follow PEP 8 and Sublime Text plugin API conventions.
4. Add/update EmmyLua stubs for any new Love2D 11.x API coverage.
