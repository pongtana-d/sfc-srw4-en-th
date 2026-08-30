-- Trace the current EN->Thai story route up to a fatal STP.  Every interesting
-- event is flushed immediately because end-frame callbacks stop after STP.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local PAGE = 0x7EFFDC
local frame, loaded, armed = 0, false, true
local log = assert(io.open(OUT, "w"))

local function byte(address)
  return emu.read(address, emu.memType.snesMemory, false)
end

local function word(address)
  return byte(address) | (byte(address + 1) << 8)
end

local function pointer()
  return byte(0xCB) | (byte(0xCC) << 8) | (byte(0xCD) << 16)
end

local function note(name, address, value)
  log:write(string.format(
    "%s frame=%d at=%06X ptr=%06X glyph=%04X page=%04X state=%04X d0=%04X d2=%04X d6=%04X%s\n",
    name, frame, address or 0, pointer(), word(0x02), word(PAGE),
    word(0x0E2A), word(0xD0), word(0xD2), word(0xD6),
    value and string.format(" value=%04X", value) or ""))
  log:flush()
end

local function load_state()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(load_state, emu.callbackType.exec,
    0x808000, 0x80FFFF, emu.cpuType.snes)
  local h = assert(io.open(STATE, "rb"))
  emu.loadSavestate(h:read("a"))
  h:close()
  loaded = true
  note("loaded")
end

emu.addMemoryCallback(load_state, emu.callbackType.exec,
  0x808000, 0x80FFFF, emu.cpuType.snes)

for name, address in pairs({
  story_loop = 0x8191E3,
  parser = 0x8191FC,
  dispatch = 0x819238,
  router = 0xFF9037,
  router_extension = 0xFF9167,
  width = 0xFF8500,
  draw = 0xFF8800,
  thai = 0xFFA000,
  draw_tail = 0xF0E12D,
}) do
  emu.addMemoryCallback(function(at)
    if loaded then note(name, at) end
  end, emu.callbackType.exec, address, address, emu.cpuType.snes)
end

emu.addMemoryCallback(function(at, value)
  if loaded then note("page_write", at, value) end
end, emu.callbackType.write, PAGE, PAGE + 1, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  emu.setInput({ a = frame == 30 }, 0)
  if frame == 1 or frame % 10 == 0 then note("frame") end
  if frame < 120 then return end
  log:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
