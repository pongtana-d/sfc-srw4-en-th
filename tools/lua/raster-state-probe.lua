-- Capture the parser and stream pointers precisely at the shared raster JSL.
-- This is intentionally read-only except for the one A press that opens the
-- command menu from the supplied reproducible state.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local OPEN_AT = tonumber(os.getenv("SRW4_OPEN_AT") or "180")
local END_AT = tonumber(os.getenv("SRW4_END_AT") or "300")

local loaded, armed, frame = false, true, 0
local samples = {}

local function word(address)
  return emu.read(address, emu.memType.snesMemory, false)
    | (emu.read(address + 1, emu.memType.snesMemory, false) << 8)
end

local function pointer(address)
  return word(address) | (emu.read(address + 2, emu.memType.snesMemory, false) << 16)
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

local function sample()
  if not loaded then return end
  local key = string.format(
    "frame=%d A=%04X 1A=%06X CB=%06X D0=%04X",
    frame,
    emu.getRegister(emu.registers.a) & 0xFFFF,
    pointer(0x1A), pointer(0xCB), word(0xD0)
  )
  samples[key] = (samples[key] or 0) + 1
end
-- The game enters this routine through both the $81 and $C1 HiROM mirrors;
-- Mesen reports the canonical one for the loaded mapping.
emu.addMemoryCallback(sample, emu.callbackType.exec, 0x8184EB, 0x8184EB, emu.cpuType.snes)
emu.addMemoryCallback(sample, emu.callbackType.exec, 0xC184EB, 0xC184EB, emu.cpuType.snes)
emu.addMemoryCallback(sample, emu.callbackType.exec, 0x8084EB, 0x8084EB, emu.cpuType.snes)
-- Current cumulative P7 placement: dispatch and Thai glyph entry in bank FB.
emu.addMemoryCallback(sample, emu.callbackType.exec, 0xFB03D3, 0xFB03D3, emu.cpuType.snes)
emu.addMemoryCallback(sample, emu.callbackType.exec, 0xFB02A0, 0xFB02A0, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if frame == OPEN_AT then emu.setInput({ a = true }, 0) end
  if frame ~= END_AT then return end
  local keys = {}; for key in pairs(samples) do keys[#keys + 1] = key end
  table.sort(keys)
  local handle = assert(io.open(OUT, "w"))
  for _, key in ipairs(keys) do handle:write(string.format("%s count=%d\n", key, samples[key])) end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
