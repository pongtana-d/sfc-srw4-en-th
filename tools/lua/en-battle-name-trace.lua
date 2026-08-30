-- Trace the EN battle compositor around each glyph call after loading a state.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local PRESS_AT = tonumber(os.getenv("SRW4_PRESS_AT") or "60")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "260")

local frame, loaded = 0, false
local samples = {}

local function byte(address)
  return emu.read(address, emu.memType.snesMemory, false)
end

local function word(address)
  return byte(address) | (byte(address + 1) << 8)
end

local function pointer(address)
  return word(address) | (byte(address + 2) << 16)
end

local function boot()
  if loaded then return end
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end
emu.addMemoryCallback(
  boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

local function sample(label)
  if not loaded then return end
  local source = pointer(0x1A)
  samples[#samples + 1] = string.format(
    "%s frame=%d A=%04X glyph=%04X src=%06X CB=%06X D0=%04X D2=%04X " ..
    "sig=%04X pen=%04X expect=%04X cell=%04X base=%04X",
    label, frame, emu.getRegister(emu.registers.a) & 0xFFFF,
    word(0x02), source, pointer(0xCB), word(0xD0), word(0xD2),
    word(0x7EFFC0), word(0x7EFFC2), word(0x7EFFC4),
    word(0x7EFFC8), word(0x7EFFD4))
end

for _, address in ipairs({0x819238, 0xC19238}) do
  emu.addMemoryCallback(function() sample("before") end,
    emu.callbackType.exec, address, address, emu.cpuType.snes)
end
for _, address in ipairs({0x81923C, 0xC1923C}) do
  emu.addMemoryCallback(function() sample("after ") end,
    emu.callbackType.exec, address, address, emu.cpuType.snes)
end

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if frame == PRESS_AT then emu.setInput({a = true}, 0)
  else emu.setInput({}, 0) end
  if frame <= LAST then return end
  local handle = assert(io.open(OUT, "w"))
  handle:write(table.concat(samples, "\n"), "\n")
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
