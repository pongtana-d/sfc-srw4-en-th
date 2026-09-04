local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local armed = true
local function boot()
  if not armed then return end
  armed = false
  local keys = {}
  for key in pairs(emu) do keys[#keys + 1] = key end
  table.sort(keys)
  local f = assert(io.open(OUT, "w"))
  for _, key in ipairs(keys) do f:write(key .. "\n") end
  local a = emu.getRegister(emu.registers.a)
  local ok, message = pcall(emu.setRegister, emu.registers.a, a)
  f:write(string.format("setRegister=%s %s\n", tostring(ok), tostring(message)))
  f:close()
  emu.stop(0)
end
emu.addMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
