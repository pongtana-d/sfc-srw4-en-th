-- Instruction-level trace around the EN story compositor.  It intentionally
-- excludes the long Thai renderer body and records the hand-off into/out of it.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local PAGE = 0x7EFFDC
local frame, loaded, armed, lines = 0, false, true, 0
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

local function load_state()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(load_state, emu.callbackType.exec,
    0x808000, 0x80FFFF, emu.cpuType.snes)
  local h = assert(io.open(STATE, "rb"))
  emu.loadSavestate(h:read("a"))
  h:close()
  loaded = true
end
emu.addMemoryCallback(load_state, emu.callbackType.exec,
  0x808000, 0x80FFFF, emu.cpuType.snes)

local function flow(address)
  if not loaded or pointer() < 0xEBC2DC then return end
  lines = lines + 1
  log:write(string.format("%06X ptr=%06X glyph=%04X page=%04X shift=%04X d0=%04X d2=%04X state=%04X\n",
    address, pointer(), word(0x02), word(PAGE), word(0x7FFFF0),
    word(0xD0), word(0xD2), word(0x0E2A)))
  if lines % 32 == 0 then log:flush() end
end

emu.addMemoryCallback(flow, emu.callbackType.exec,
  0x8191E0, 0x8197FF, emu.cpuType.snes)
emu.addMemoryCallback(flow, emu.callbackType.exec,
  0xF0E000, 0xF0E4FF, emu.cpuType.snes)
for _, address in ipairs({0xFF8500, 0xFF8800, 0xFF9037, 0xFF9167, 0xFFA000}) do
  emu.addMemoryCallback(flow, emu.callbackType.exec,
    address, address, emu.cpuType.snes)
end

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  emu.setInput({ a = frame == 30 }, 0)
  if frame < 100 then return end
  log:flush()
  log:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
