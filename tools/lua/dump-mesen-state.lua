local STATE = assert(os.getenv('SRW4_STATE'))
local OUT = assert(os.getenv('SRW4_OUT'))
local loaded, armed = false, true
local function load_state()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(load_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local f = assert(io.open(STATE, 'rb'))
  emu.loadSavestate(f:read('a'))
  f:close()
  loaded = true
end
emu.addMemoryCallback(load_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
emu.addEventCallback(function()
  if not loaded then return end
  local state = emu.getState()
  local keys = {}
  for key in pairs(state) do keys[#keys + 1] = key end
  table.sort(keys)
  local f = assert(io.open(OUT, 'w'))
  for _, key in ipairs(keys) do f:write(string.format('%s=%s\n', key, tostring(state[key]))) end
  f:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
