local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local loaded, armed = false, true
local function boot()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local f = assert(io.open(STATE, "rb")); emu.loadSavestate(f:read("a")); f:close()
  loaded = true
end
emu.addMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
emu.addEventCallback(function()
  if not loaded then return end
  local a = emu.getRegister(emu.registers.a)
  local ok, message = pcall(emu.setRegister, emu.registers.a, a)
  local f = assert(io.open(OUT, "w"))
  f:write(string.format("ok=%s result=%s\n", tostring(ok), tostring(message)))
  f:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
