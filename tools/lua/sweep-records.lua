-- Draw records the route would never reach, and dump what the renderer made.
--
-- Playing to stage 37 to see one line is not a test anyone will run twice, so
-- the record under test is substituted instead: at $C1:9366 the engine has
-- just finished resolving a message and holds its full 24-bit pointer in
-- $CB-$CD, one instruction before it starts drawing. Overwriting those three
-- bytes there hands the engine a different record and nothing else changes --
-- the window, the cursor, the wrap limit and the terminator handling are all
-- still the game's own.
local OUT = os.getenv("SRW4_OUT") or "build/reports/sweep.bin"
local TARGETS = os.getenv("SRW4_TARGETS") or ""
local SPAN = tonumber(os.getenv("SRW4_SPAN") or "16384")
local WARMUP = tonumber(os.getenv("SRW4_WARMUP") or "2")
local PRESS_EVERY = tonumber(os.getenv("SRW4_EVERY") or "45")
-- "1016:031710,102B:400400" -- runtime name buffers to hold in WRAM. The game
-- refills them from its own tables, so they are rewritten every frame rather
-- than once.
local NAMES = {}
for pair in (os.getenv("SRW4_NAMES") or ""):gmatch("[^,]+") do
  local at, hex = pair:match("^(%x+):(%x+)$")
  if at then NAMES[#NAMES + 1] = { addr = tonumber(at, 16), hex = hex } end
end

local targets = {}
for hex in TARGETS:gmatch("[^,]+") do targets[#targets + 1] = tonumber(hex, 16) end

local index = 0            -- how many records we have substituted
local written = 0          -- how many have been dumped
local resolved = 0         -- how many times the engine resolved a message
local glyphs = 0
local frame = 0
local bases = {}
local out = io.open(OUT, "wb")
local meta = io.open(OUT .. ".txt", "w")

-- Only the glyphs the adapter drew itself say anything about where our lines
-- began. A `$FB xx 80` name comes out of a catalog bank, goes to the stock
-- rasteriser, and leaves the base alone -- counting it as a line would shift
-- everything after it.
emu.addMemoryCallback(function()
  local bank = emu.read(0xCD, emu.memType.snesMemory, false)
  if bank < 0xF0 or bank > 0xF8 then return end
  local base = emu.read(0x7EC7F2, emu.memType.snesMemory, false)
    | (emu.read(0x7EC7F3, emu.memType.snesMemory, false) << 8)
  if bases[#bases] ~= base then bases[#bases + 1] = base end
end, emu.callbackType.exec, 0x81923C, 0x81923C, emu.cpuType.snes)

local seen_at = nil
emu.addMemoryCallback(function()
  glyphs = glyphs + 1
  if seen_at == nil then
    seen_at = emu.read(0xCB, emu.memType.snesMemory, false)
      | (emu.read(0xCC, emu.memType.snesMemory, false) << 8)
      | (emu.read(0xCD, emu.memType.snesMemory, false) << 16)
  end
end, emu.callbackType.exec, 0x819238, 0x819238, emu.cpuType.snes)

-- Where to substitute. The story's messages are not resolved through the
-- master table -- $C1:9348 never runs -- and records sit end to end, so a
-- moving pointer says nothing either.
--
-- What does is the end of a message. $FF is a *return*: $C1:94DC pops the
-- call stack the `$FB` handler pushed, and only when that stack is empty, at
-- $C1:94FB, is the message over. $F7 ends one the other way, at $C1:92C7.
-- Arming there and writing the pointer at $C1:91F9 -- the instruction that
-- fetches the next byte -- means the very next byte read is ours.
local log = {}
local armed = false
local pending = nil        -- the record under test has reached its terminator

for _, site in ipairs({0x8194FB, 0x8192C7}) do
  emu.addMemoryCallback(function()
    armed = true
    -- Its own terminator is the exact end of the record under test. Waiting
    -- for the drawing to go quiet instead would let the engine's next record
    -- into the same arena first.
    if index > written and pending == nil then
      pending = { glyphs = glyphs, bases = bases }
    end
  end, emu.callbackType.exec, site, site, emu.cpuType.snes)
end

emu.addMemoryCallback(function()
  if not armed then return end
  armed = false
  resolved = resolved + 1
  if resolved <= WARMUP or index >= #targets or index > written then return end
  index = index + 1
  local p = targets[index]
  -- emu.read takes four arguments and emu.write takes three; passing the
  -- fourth throws, and a throw inside a callback is silent.
  emu.write(0xCB, p & 0xFF, emu.memType.snesMemory)
  emu.write(0xCC, (p >> 8) & 0xFF, emu.memType.snesMemory)
  emu.write(0xCD, (p >> 16) & 0xFF, emu.memType.snesMemory)
  glyphs = 0
  bases = {}
  seen_at = nil
  -- Read the pointer back: a write that did not take would otherwise look
  -- exactly like a record that renders identically to the scene's own.
  log[#log + 1] = string.format("-- %06X written, reads back %02X%02X%02X at frame %d", p,
    emu.read(0xCD, emu.memType.snesMemory, false),
    emu.read(0xCC, emu.memType.snesMemory, false),
    emu.read(0xCB, emu.memType.snesMemory, false), frame)
end, emu.callbackType.exec, 0x8191F9, 0x8191F9, emu.cpuType.snes)

local function dump()
  local glyphs, bases = pending.glyphs, pending.bases
  pending = nil
  local chunk = {}
  for offset = 0, SPAN - 1 do
    chunk[#chunk + 1] = string.char(emu.read(0x7F8000 + offset, emu.memType.snesMemory, false))
    if #chunk == 4096 then out:write(table.concat(chunk)); chunk = {} end
  end
  out:write(table.concat(chunk))
  local text = {}
  for i = 1, #bases do text[#text + 1] = string.format("%04X", bases[i]) end
  meta:write(string.format("%06X %d %s first=%06X\n", targets[index], glyphs, table.concat(text, ","), seen_at or 0))
  written = written + 1
end

emu.addEventCallback(function()
  frame = frame + 1
  for _, n in ipairs(NAMES) do
    for i = 1, #n.hex, 2 do
      emu.write(0x7E0000 + n.addr + (i - 1) // 2,
        tonumber(n.hex:sub(i, i + 1), 16), emu.memType.snesMemory)
    end
  end
  local p = {}
  for f = 60, 900, 30 do p[f] = "start" end
  p[950] = "a"
  for f = 1700, 1990, 40 do p[f] = "down" end
  p[2040] = "a"
  for f = 2100, 60000, PRESS_EVERY do p[f] = "a" end
  if p[frame] then emu.setInput({ [p[frame]] = true }, 0) end
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  if pending ~= nil then dump() end
  if written >= #targets then
    for _, l in ipairs(log) do meta:write(l .. "\n") end
    meta:write(string.format("frames %d\n", frame))
    out:close(); meta:close(); emu.stop(0)
  end
  if frame > 60000 then
    for _, l in ipairs(log) do meta:write(l .. "\n") end
    meta:write(string.format("timeout after %d of %d at frame %d (%d message ends seen)\n",
      written, #targets, frame, resolved))
    out:close(); meta:close(); emu.stop(1)
  end
end, emu.eventType.endFrame)
