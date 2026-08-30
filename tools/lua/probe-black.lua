-- Record the CPU program counter while reproducing a black-screen save state.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local loaded, armed, frame = false, true, 0

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

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if frame < 180 then return end
  local handle = assert(io.open(OUT, "w"))
  for name, register in pairs(emu.registers) do
    local ok, value = pcall(emu.getRegister, register)
    if ok then handle:write(string.format("%s=%s\n", name, tostring(value))) end
  end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
