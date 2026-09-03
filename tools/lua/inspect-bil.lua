-- Inspect party roster records in a supplied Mesen SRW4 savestate without
-- modifying it.  Outputs the persistent pilot/unit tables once the state loads.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local loaded, armed = false, true

local function byte(address)
  return emu.read(address, emu.memType.snesMemory, false)
end

local function load_state()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(load_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local h = assert(io.open(STATE, "rb"))
  emu.loadSavestate(h:read("a"))
  h:close()
  loaded = true
end
emu.addMemoryCallback(load_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  local h = assert(io.open(OUT, "w"))
  for i = 0, 63 do
    local pilot = 0x7E1088 + i * 2
    local unit = 0x7E1208 + i * 2
    h:write(string.format(
      "%02d pilot=%02X level=%02X squad=%02X%02X unit=%02X%02X status=%02X%02X\n",
      i, byte(pilot), byte(pilot + 1), byte(0x7E1108 + i * 2 + 1), byte(0x7E1108 + i * 2),
      byte(unit), byte(unit + 1), byte(0x7E1288 + i * 2), byte(0x7E1289 + i * 2)))
  end
  h:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
