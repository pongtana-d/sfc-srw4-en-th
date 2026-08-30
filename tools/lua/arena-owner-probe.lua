-- Capture the concrete arena pages and writers used by a genuine P7 command
-- redraw.  No ROM or emulator state is modified except the single A press.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local loaded, armed, frame = false, true, 0
local writes = {}

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

emu.addMemoryCallback(function(address)
  if not loaded then return end
  local pc = emu.getRegister(emu.registers.pc) & 0xFFFF
  local key = string.format("pc=%04X page=%04X", pc, address & 0xFFF0)
  writes[key] = (writes[key] or 0) + 1
end, emu.callbackType.write, 0x00A000, 0x00A3FF, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if frame == 180 then emu.setInput({ a = true }, 0) end
  if frame ~= 300 then return end
  local keys = {}; for key in pairs(writes) do keys[#keys + 1] = key end
  table.sort(keys)
  local handle = assert(io.open(OUT, "w"))
  for _, key in ipairs(keys) do handle:write(string.format("%s count=%d\n", key, writes[key])) end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
