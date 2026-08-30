-- Dump the tile arena the moment a message has just been drawn.
--
-- Watching the screen means guessing when to look. Watching the arena does
-- not: the dump is taken a fixed number of glyphs into a record, so what comes
-- out is whatever the renderer actually put there, whether or not the frame it
-- lands on happens to show it.
local OUT = os.getenv("SRW4_OUT") or "build/reports/arena.bin"
local SHOT = os.getenv("SRW4_SHOT")
local AFTER = tonumber(os.getenv("SRW4_AFTER") or "40")
local BYTES = tonumber(os.getenv("SRW4_BYTES") or "32768")
local LINE_BASE = tonumber(os.getenv("SRW4_LINE_BASE") or "7EC7F2", 16)
local PRESS_EVERY = tonumber(os.getenv("SRW4_EVERY") or "45")
local SKIP = tonumber(os.getenv("SRW4_SKIP") or "0")

local glyphs = 0
local frame = 0
local done = false
local idle = 0
local last_seen = 0
local first_pointer = nil
local bases = {}

-- The line base is read after the call returns, not before it: on the first
-- glyph of a line the adapter has not chosen the new base yet.
emu.addMemoryCallback(function()
  local base = emu.read(LINE_BASE, emu.memType.snesMemory, false)
    | (emu.read(LINE_BASE + 1, emu.memType.snesMemory, false) << 8)
  if bases[#bases] ~= base then bases[#bases + 1] = base end
end, emu.callbackType.exec, 0x81923C, 0x81923C, emu.cpuType.snes)

emu.addMemoryCallback(function()
  glyphs = glyphs + 1
  if first_pointer == nil then
    first_pointer = string.format("%02X%02X%02X",
      emu.read(0xCD, emu.memType.snesMemory, false),
      emu.read(0xCC, emu.memType.snesMemory, false),
      emu.read(0xCB, emu.memType.snesMemory, false))
  end
end, emu.callbackType.exec, 0x819238, 0x819238, emu.cpuType.snes)

emu.addEventCallback(function()
  frame = frame + 1
  local p = {}
  for f = 60, 900, 30 do p[f] = "start" end
  p[950] = "a"
  for f = 1700, 1990, 40 do p[f] = "down" end
  p[2040] = "a"
  for f = 2100, 6000, PRESS_EVERY do p[f] = "a" end
  if p[frame] then emu.setInput({ [p[frame]] = true }, 0) end
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  if done then return end
  -- Wait for the record to finish: a message is done when nothing has been
  -- drawn for a while, which is also when the arena holds the whole line.
  if glyphs == last_seen then
    idle = idle + 1
  else
    idle = 0
    last_seen = glyphs
  end
  if glyphs >= AFTER and idle >= 20 and SKIP > 0 then
    -- Let this record go by and start counting the next one from scratch.
    SKIP = SKIP - 1
    glyphs = 0
    last_seen = 0
    idle = 0
    first_pointer = nil
    bases = {}
    return
  end
  if glyphs >= AFTER and idle >= 20 then
    done = true
    local out = io.open(OUT, "wb")
    local chunk = {}
    for offset = 0, BYTES - 1 do
      chunk[#chunk + 1] = string.char(emu.read(0x7F8000 + offset, emu.memType.snesMemory, false))
      if #chunk == 4096 then out:write(table.concat(chunk)); chunk = {} end
    end
    out:write(table.concat(chunk))
    out:close()
    -- and where the engine was reading from, so the record can be identified
    local meta = io.open(OUT .. ".txt", "w")
    meta:write(string.format("first %s\n", first_pointer or "?"))
    local text = {}
    for i = 1, #bases do text[#text + 1] = string.format("%04X", bases[i]) end
    meta:write("bases " .. table.concat(text, ",") .. "\n")
    -- $0E2C holds the window's width limit in the engine's column unit (two
    -- per character cell) and $0E2D its line count. The engine wraps on them
    -- at $C1:9232, before the glyph is drawn, so they bound our lines too.
    meta:write(string.format("window %04X %04X\n",
      emu.read(0x0E2C, emu.memType.snesMemory, false)
        | (emu.read(0x0E2D, emu.memType.snesMemory, false) << 8),
      emu.read(0x0FE0, emu.memType.snesMemory, false)
        | (emu.read(0x0FE1, emu.memType.snesMemory, false) << 8)))
    meta:write(string.format("pointer %02X%02X%02X\nglyphs %d\nframe %d\n",
      emu.read(0xCD, emu.memType.snesMemory, false),
      emu.read(0xCC, emu.memType.snesMemory, false),
      emu.read(0xCB, emu.memType.snesMemory, false), glyphs, frame))
    meta:close()
    if SHOT then
      local screenshot = assert(io.open(SHOT, "wb"))
      screenshot:write(emu.takeScreenshot())
      screenshot:close()
    end
    emu.stop(0)
  end
  if frame > 6000 then emu.stop(1) end
end, emu.eventType.endFrame)
