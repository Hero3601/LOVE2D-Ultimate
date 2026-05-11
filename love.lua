---@meta
-- Love2D Ultimate — Bundled API Stubs for lua-language-server (sumneko)
-- Covers Love2D 11.5 API surface.  Extend as needed.
-- These annotations give lua-language-server complete type information.

--------------------------------------------------------------------------------
-- love (top-level namespace)
--------------------------------------------------------------------------------

---@class love
love = {}

---Called once on startup to load game resources.
function love.load(arg) end

---Called every frame to update game state.
---@param dt number Delta time in seconds since the last update.
function love.update(dt) end

---Called every frame to render the game.
function love.draw() end

---Called when a key is pressed.
---@param key love.KeyConstant The key that was pressed.
---@param scancode love.Scancode The scancode of the key.
---@param isrepeat boolean Whether this is a key-repeat event.
function love.keypressed(key, scancode, isrepeat) end

---Called when a key is released.
---@param key love.KeyConstant
---@param scancode love.Scancode
function love.keyreleased(key, scancode) end

---Called when a mouse button is pressed.
---@param x number Mouse x position.
---@param y number Mouse y position.
---@param button integer Button index (1=left, 2=right, 3=middle).
---@param istouch boolean Whether from touch input.
---@param presses integer Number of presses (for double-click etc.).
function love.mousepressed(x, y, button, istouch, presses) end

---Called when a mouse button is released.
---@param x number
---@param y number
---@param button integer
---@param istouch boolean
---@param presses integer
function love.mousereleased(x, y, button, istouch, presses) end

---Called when the mouse is moved.
---@param x number
---@param y number
---@param dx number Delta x.
---@param dy number Delta y.
---@param istouch boolean
function love.mousemoved(x, y, dx, dy, istouch) end

---Called when the window is resized.
---@param w number New width.
---@param h number New height.
function love.resize(w, h) end

---Called when the game should quit. Return true to cancel.
---@return boolean cancel Return true to prevent quitting.
function love.quit() end

---Called when text input is triggered.
---@param text string UTF-8 text.
function love.textinput(text) end

---Called when the window gains or loses focus.
---@param focus boolean True if focused.
function love.focus(focus) end

--------------------------------------------------------------------------------
-- love.graphics
--------------------------------------------------------------------------------

---@class love.graphics
love.graphics = {}

---Clears the screen with a color.
---@param r number Red (0–1).
---@param g number Green (0–1).
---@param b number Blue (0–1).
---@param a number? Alpha (0–1, default 1).
function love.graphics.clear(r, g, b, a) end

---Draws a filled or outlined rectangle.
---@param mode love.DrawMode "fill" or "line".
---@param x number X position.
---@param y number Y position.
---@param width number Width.
---@param height number Height.
---@param rx number? Corner radius x.
---@param ry number? Corner radius y.
function love.graphics.rectangle(mode, x, y, width, height, rx, ry) end

---Draws a filled or outlined circle.
---@param mode love.DrawMode
---@param x number Center x.
---@param y number Center y.
---@param radius number Radius.
---@param segments integer? Number of segments (default 10).
function love.graphics.circle(mode, x, y, radius, segments) end

---Prints text at a position.
---@param text string The text to print.
---@param x number? X position.
---@param y number? Y position.
function love.graphics.print(text, x, y) end

---Draws a Drawable (Image, Canvas, etc.).
---@param drawable love.Drawable The drawable to draw.
---@param x number? X position.
---@param y number? Y position.
---@param r number? Rotation in radians.
---@param sx number? X scale.
---@param sy number? Y scale.
---@param ox number? X origin offset.
---@param oy number? Y origin offset.
function love.graphics.draw(drawable, x, y, r, sx, sy, ox, oy) end

---Sets the active color.
---@param r number
---@param g number
---@param b number
---@param a number?
function love.graphics.setColor(r, g, b, a) end

---Returns the current color.
---@return number r, number g, number b, number a
function love.graphics.getColor() end

---Sets the background color.
---@param r number
---@param g number
---@param b number
---@param a number?
function love.graphics.setBackgroundColor(r, g, b, a) end

---Creates a new Image from a path or FileData.
---@param filename string Path to the image file.
---@return love.Image
function love.graphics.newImage(filename) end

---Creates a new Font.
---@param filename string? Path to font file (nil = default font).
---@param size integer? Font size.
---@return love.Font
function love.graphics.newFont(filename, size) end

---Sets the active Font.
---@param font love.Font
function love.graphics.setFont(font) end

---Returns the current Font.
---@return love.Font
function love.graphics.getFont() end

---Creates a new Canvas (render target).
---@param width integer?
---@param height integer?
---@return love.Canvas
function love.graphics.newCanvas(width, height) end

---Sets the active Canvas (nil = screen).
---@param canvas love.Canvas?
function love.graphics.setCanvas(canvas) end

---Creates a new SpriteBatch.
---@param image love.Image
---@param maxSprites integer?
---@return love.SpriteBatch
function love.graphics.newSpriteBatch(image, maxSprites) end

---Creates a new Quad.
---@param x number
---@param y number
---@param width number
---@param height number
---@param sw number Sprite sheet width.
---@param sh number Sprite sheet height.
---@return love.Quad
function love.graphics.newQuad(x, y, width, height, sw, sh) end

---Draws a line between points.
---@param x1 number
---@param y1 number
---@param x2 number
---@param y2 number
function love.graphics.line(x1, y1, x2, y2) end

---Returns the screen dimensions.
---@return integer width, integer height
function love.graphics.getDimensions() end

---Returns the screen width.
---@return integer
function love.graphics.getWidth() end

---Returns the screen height.
---@return integer
function love.graphics.getHeight() end

---Pushes a transform onto the stack.
function love.graphics.push() end

---Pops the transform stack.
function love.graphics.pop() end

---Applies a translation.
---@param dx number
---@param dy number
function love.graphics.translate(dx, dy) end

---Applies a rotation.
---@param angle number Radians.
function love.graphics.rotate(angle) end

---Applies a scale.
---@param sx number
---@param sy number?
function love.graphics.scale(sx, sy) end

---Sets the line width.
---@param width number
function love.graphics.setLineWidth(width) end

---Sets the scissor rectangle.
---@param x integer
---@param y integer
---@param width integer
---@param height integer
function love.graphics.setScissor(x, y, width, height) end

---Resets the scissor.
function love.graphics.setScissor() end

---@alias love.DrawMode "fill" | "line"

--------------------------------------------------------------------------------
-- love.keyboard
--------------------------------------------------------------------------------

---@class love.keyboard
love.keyboard = {}

---Returns true if the key is held down.
---@param key love.KeyConstant
---@return boolean
function love.keyboard.isDown(key) end

---Sets whether key repeat is enabled.
---@param enable boolean
function love.keyboard.setKeyRepeat(enable) end

---@alias love.KeyConstant
---| '"a"' | '"b"' | '"c"' | '"d"' | '"e"' | '"f"' | '"g"' | '"h"'
---| '"i"' | '"j"' | '"k"' | '"l"' | '"m"' | '"n"' | '"o"' | '"p"'
---| '"q"' | '"r"' | '"s"' | '"t"' | '"u"' | '"v"' | '"w"' | '"x"'
---| '"y"' | '"z"' | '"0"' | '"1"' | '"2"' | '"3"' | '"4"' | '"5"'
---| '"6"' | '"7"' | '"8"' | '"9"' | '"space"' | '"return"' | '"escape"'
---| '"backspace"' | '"tab"' | '"up"' | '"down"' | '"left"' | '"right"'
---| '"lshift"' | '"rshift"' | '"lctrl"' | '"rctrl"' | '"lalt"' | '"ralt"'
---| '"f1"' | '"f2"' | '"f3"' | '"f4"' | '"f5"' | '"f6"'
---| '"f7"' | '"f8"' | '"f9"' | '"f10"' | '"f11"' | '"f12"'

---@alias love.Scancode string

--------------------------------------------------------------------------------
-- love.mouse
--------------------------------------------------------------------------------

---@class love.mouse
love.mouse = {}

---Returns the mouse position.
---@return number x, number y
function love.mouse.getPosition() end

---Returns the mouse x position.
---@return number
function love.mouse.getX() end

---Returns the mouse y position.
---@return number
function love.mouse.getY() end

---Returns whether a mouse button is held.
---@param button integer 1=left, 2=right, 3=middle.
---@return boolean
function love.mouse.isDown(button) end

---Sets the mouse position.
---@param x number
---@param y number
function love.mouse.setPosition(x, y) end

---Sets mouse visibility.
---@param visible boolean
function love.mouse.setVisible(visible) end

---Returns the mouse wheel movement this frame.
---@return number x, number y
function love.mouse.getWheel() end

--------------------------------------------------------------------------------
-- love.audio
--------------------------------------------------------------------------------

---@class love.audio
love.audio = {}

---Creates a new Source from a file.
---@param filename string
---@param type love.SourceType
---@return love.Source
function love.audio.newSource(filename, type) end

---Plays a Source.
---@param source love.Source
function love.audio.play(source) end

---Stops all or a specific Source.
---@param source love.Source?
function love.audio.stop(source) end

---Pauses all or a specific Source.
---@param source love.Source?
function love.audio.pause(source) end

---Sets the master volume.
---@param volume number 0–1.
function love.audio.setVolume(volume) end

---@alias love.SourceType "static" | "stream"

--------------------------------------------------------------------------------
-- love.filesystem
--------------------------------------------------------------------------------

---@class love.filesystem
love.filesystem = {}

---Reads a file as a string.
---@param name string Path to the file.
---@param size integer? Max bytes to read.
---@return string|nil contents, string|nil error
function love.filesystem.read(name, size) end

---Writes a string to a file.
---@param name string
---@param data string
---@param size integer?
---@return boolean success, string? error
function love.filesystem.write(name, data, size) end

---Returns whether a path exists.
---@param name string
---@return boolean
function love.filesystem.exists(name) end

---Returns the list of files in a directory.
---@param dir string
---@return string[] files
function love.filesystem.getDirectoryItems(dir) end

---Returns the save directory path.
---@return string
function love.filesystem.getSaveDirectory() end

---Returns file info.
---@param path string
---@return {type: string, size: integer, modtime: integer}|nil
function love.filesystem.getInfo(path) end

--------------------------------------------------------------------------------
-- love.math
--------------------------------------------------------------------------------

---@class love.math
love.math = {}

---Returns a random number.
---@param m number? Lower bound or upper bound if n is nil.
---@param n number? Upper bound.
---@return number
function love.math.random(m, n) end

---Seeds the random number generator.
---@param seed integer
function love.math.randomSeed(seed) end

---Converts HSV to RGB.
---@param h number 0–1.
---@param s number 0–1.
---@param v number 0–1.
---@return number r, number g, number b
function love.math.colorFromHSV(h, s, v) end

---Returns a new Transform object.
---@return love.Transform
function love.math.newTransform() end

--------------------------------------------------------------------------------
-- love.window
--------------------------------------------------------------------------------

---@class love.window
love.window = {}

---Sets the window title.
---@param title string
function love.window.setTitle(title) end

---Returns the window title.
---@return string
function love.window.getTitle() end

---Sets the window mode.
---@param width integer
---@param height integer
---@param flags {fullscreen: boolean?, resizable: boolean?, vsync: boolean?}?
---@return boolean success, string? error
function love.window.setMode(width, height, flags) end

---Returns the window dimensions.
---@return integer width, integer height, {fullscreen: boolean, vsync: boolean}
function love.window.getMode() end

---Returns whether the window has focus.
---@return boolean
function love.window.hasFocus() end

---Sets window fullscreen.
---@param fullscreen boolean
---@param fstype love.FullscreenType?
---@return boolean, string?
function love.window.setFullscreen(fullscreen, fstype) end

---@alias love.FullscreenType "desktop" | "exclusive"

--------------------------------------------------------------------------------
-- love.event
--------------------------------------------------------------------------------

---@class love.event
love.event = {}

---Pushes a quit event.
---@param exitstatus integer?
function love.event.quit(exitstatus) end

---Pumps events from the OS.
function love.event.pump() end

---@class love.timer
love.timer = {}

---Returns time since last frame.
---@return number
function love.timer.getDelta() end

---Returns the average FPS.
---@return number
function love.timer.getFPS() end

---Returns the time since program start.
---@return number
function love.timer.getTime() end

---Sleeps for a number of seconds.
---@param seconds number
function love.timer.sleep(seconds) end

--------------------------------------------------------------------------------
-- love.physics
--------------------------------------------------------------------------------

---@class love.physics
love.physics = {}

---Creates a new World.
---@param xg number? X gravity.
---@param yg number? Y gravity.
---@param sleep boolean? Allow sleeping bodies.
---@return love.World
function love.physics.newWorld(xg, yg, sleep) end

---Creates a new Body.
---@param world love.World
---@param x number
---@param y number
---@param type love.BodyType
---@return love.Body
function love.physics.newBody(world, x, y, type) end

---Creates a new CircleShape.
---@param radius number
---@return love.CircleShape
function love.physics.newCircleShape(radius) end

---Creates a new RectangleShape.
---@param width number
---@param height number
---@return love.PolygonShape
function love.physics.newRectangleShape(width, height) end

---Creates a new Fixture.
---@param body love.Body
---@param shape love.Shape
---@param density number?
---@return love.Fixture
function love.physics.newFixture(body, shape, density) end

---Sets the pixel-to-meter scale.
---@param scale number
function love.physics.setMeter(scale) end

---@alias love.BodyType "static" | "dynamic" | "kinematic"

--------------------------------------------------------------------------------
-- Object class stubs
--------------------------------------------------------------------------------

---@class love.Drawable
---@class love.Image : love.Drawable
---@class love.Canvas : love.Drawable
---@class love.SpriteBatch : love.Drawable
---@class love.Font
---@class love.Quad
---@class love.Source
---@class love.Transform
---@class love.World
---@class love.Body
---@class love.Shape
---@class love.CircleShape : love.Shape
---@class love.PolygonShape : love.Shape
---@class love.Fixture

---Returns the width and height of the image.
---@return integer width, integer height
function love.Image:getDimensions() end

---Returns the image width.
---@return integer
function love.Image:getWidth() end

---Returns the image height.
---@return integer
function love.Image:getHeight() end

---Adds a sprite to the SpriteBatch.
---@param x number
---@param y number
---@param r number?
---@param sx number?
---@param sy number?
function love.SpriteBatch:add(x, y, r, sx, sy) end

---Clears the SpriteBatch.
function love.SpriteBatch:clear() end

---Updates world physics.
---@param dt number
function love.World:update(dt) end

---Returns the body position.
---@return number x, number y
function love.Body:getPosition() end

---Sets the body position.
---@param x number
---@param y number
function love.Body:setPosition(x, y) end

---Returns linear velocity.
---@return number vx, number vy
function love.Body:getLinearVelocity() end

---Sets linear velocity.
---@param vx number
---@param vy number
function love.Body:setLinearVelocity(vx, vy) end

---Applies a force.
---@param fx number
---@param fy number
function love.Body:applyForce(fx, fy) end

---Destroys the body.
function love.Body:destroy() end

---Returns whether the body is active.
---@return boolean
function love.Body:isActive() end

---Returns the body angle in radians.
---@return number
function love.Body:getAngle() end

---Plays the source.
function love.Source:play() end

---Stops the source.
function love.Source:stop() end

---Returns whether the source is playing.
---@return boolean
function love.Source:isPlaying() end

---Sets the source volume.
---@param volume number 0–1.
function love.Source:setVolume(volume) end

---Enables/disables looping.
---@param loop boolean
function love.Source:setLooping(loop) end

---Returns the font height.
---@return number
function love.Font:getHeight() end

---Returns the width of a string in this font.
---@param text string
---@return number
function love.Font:getWidth(text) end
