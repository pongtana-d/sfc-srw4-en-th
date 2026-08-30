-- Identify routines writing the active dialogue tile range after a savestate.
local state = assert(os.getenv("SRW4_STATE"), "SRW4_STATE required")
local out = assert(os.getenv("SRW4_OUT"), "SRW4_OUT required")
local frame, loaded, armed = 0, false, true
local writers = {}

local function boot()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(state, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end
emu.addMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

emu.addMemoryCallback(function(address)
  if not loaded then return end
  local pc = emu.getRegister(emu.registers.pc) & 0xFFFF
  local key = string.format("pc=%04X page=%04X", pc, address & 0xFFF0)
  writers[key] = (writers[key] or 0) + 1
end, emu.callbackType.write, 0x7FA000, 0x7FA7FF, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if frame > 100 then
    local keys = {}; for key in pairs(writers) do keys[#keys + 1] = key end
    table.sort(keys)
    local handle = assert(io.open(out, "w"))
    for _, key in ipairs(keys) do handle:write(string.format("%s count=%d\n", key, writers[key])) end
    handle:close()
    emu.stop(0)
  end
end, emu.eventType.inputPolled)
