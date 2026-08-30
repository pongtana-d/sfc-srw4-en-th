-- Record the EN story parser/raster hand-off on a genuine redraw.
-- This intentionally has no memory-write callbacks: it is an observation-only
-- contract probe for map dialogue and battle quotes, which share this loop.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "600")
local EVERY = tonumber(os.getenv("SRW4_AUTO_A_EVERY") or "0")
local SITE = tonumber(os.getenv("SRW4_SITE") or "819238", 16)

local loaded, armed, frame = false, true, 0
local rows = {}
local function pointer()
  return emu.read(0xCB, emu.memType.snesMemory, false)
    | (emu.read(0xCC, emu.memType.snesMemory, false) << 8)
    | (emu.read(0xCD, emu.memType.snesMemory, false) << 16)
end
local function note(site)
  if not loaded then return end
  local glyph = emu.read(0x02, emu.memType.snesMemory, false)
    | (emu.read(0x03, emu.memType.snesMemory, false) << 8)
  local parsed = emu.read(0x00, emu.memType.snesMemory, false)
    | (emu.read(0x01, emu.memType.snesMemory, false) << 8)
  rows[#rows + 1] = string.format("%s frame=%d parsed=%04X glyph=%04X ptr=%06X", site, frame, parsed, glyph, pointer())
end
local function boot()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end
emu.addMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
emu.addMemoryCallback(function() note(string.format("site=%06X", SITE)) end,
  emu.callbackType.exec, SITE, SITE, emu.cpuType.snes)
emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if EVERY > 0 and frame % EVERY == 0 then emu.setInput({A = true}, 0) else emu.setInput({}, 0) end
  if frame <= LAST then return end
  local handle = assert(io.open(OUT, "w"))
  for _, row in ipairs(rows) do handle:write(row .. "\n") end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
