-- Capture every live call through the relocated dialogue raster while replaying
-- a supplied map state.  This is diagnostic only: it does not alter emulation.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local SHOT = assert(os.getenv("SRW4_SHOT"), "SRW4_SHOT is required")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "60")

local loaded, armed, frame = false, true, 0
local calls = {}
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

emu.addMemoryCallback(function()
  if not loaded then return end
  local pointer = emu.read(0xCB, emu.memType.snesMemory, false)
    | (emu.read(0xCC, emu.memType.snesMemory, false) << 8)
    | (emu.read(0xCD, emu.memType.snesMemory, false) << 16)
  local cursor = emu.read(0xD0, emu.memType.snesMemory, false)
    | (emu.read(0xD1, emu.memType.snesMemory, false) << 8)
  local key = string.format("%06X D0=%04X A=%04X", pointer, cursor,
    emu.getRegister(emu.registers.a) & 0xFFFF)
  calls[key] = (calls[key] or 0) + 1
end, emu.callbackType.exec, 0x819238, 0x819238, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if frame < LAST then return end
  local image = assert(io.open(SHOT, "wb")); image:write(emu.takeScreenshot()); image:close()
  local log = assert(io.open(OUT, "w"))
  local keys = {}; for key in pairs(calls) do keys[#keys + 1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do log:write(string.format("%s %d\n", key, calls[key])) end
  log:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
