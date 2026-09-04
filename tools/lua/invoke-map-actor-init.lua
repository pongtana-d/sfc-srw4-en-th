-- Experimental: call the game's own actor-initialization routine for five
-- empty actor records, then save before its RTL executes.  Output is separate
-- from user files and must be visually verified.
local STATE = assert(os.getenv('SRW4_STATE'))
local SAVE = assert(os.getenv('SRW4_SAVE'))
local party = {{0x1C,0x40},{0x62,0x3F},{0x64,0x41},{0x65,0x3F},{0x66,0x40}}
local loaded, armed, started, current = false, true, false, 1

local function r(a) return emu.read(a, emu.memType.snesMemory, false) end
local function w(a, v) emu.write(a, v, emu.memType.snesMemory) end

local function seed(n)
  local source = (n - 1) * 2
  local slot = 10 + n
  local target = slot * 2
  for base = 0x1565, 0x1DE5, 0x20 do
    w(0x7E0000 + base + target, r(0x7E0000 + base + source))
    w(0x7E0000 + base + target + 1, r(0x7E0000 + base + source + 1))
  end
  local pilot, unit = party[n][1], party[n][2]
  w(0x7E1088 + target, pilot); w(0x7E1089 + target, 0x63)
  w(0x7E1108 + target, 0); w(0x7E1109 + target, 0x10)
  w(0x7E1208 + target, unit); w(0x7E1209 + target, 0x80 + target)
  w(0x7E1565 + target, 0x0C + n); w(0x7E1566 + target, 0x44)
  w(0x7E1765 + target, 0x0A + n); w(0x7E1766 + target, 0x0A)
  w(0x7E1086, 0x10); w(0x7E1087, 0x0F)
  -- Scratch inputs consumed by the native routine at $80:9510.
  w(0x7E0010, pilot); w(0x7E0011, 0)
  w(0x7E0012, 0x63); w(0x7E0013, 0)
  w(0x7E0014, unit); w(0x7E0015, 0)
  w(0x7E0016, 0); w(0x7E0017, 0); w(0x7E0018, 0); w(0x7E0019, 0)
  w(0x7E0EA4, target)
end

local function jump_to_initializer()
  seed(current)
  local state = emu.getState()
  state['cpu.k'] = 0x80
  state['cpu.pc'] = 0x9510
  state['cpu.waiOver'] = false
  emu.setState(state)
end

local function boot()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local f = assert(io.open(STATE, 'rb')); emu.loadSavestate(f:read('a')); f:close()
  loaded = true
end
emu.addMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

local function returned()
  if not loaded then return end
  if current == #party then
    local f = assert(io.open(SAVE, 'wb')); f:write(emu.createSavestate()); f:close()
    emu.stop(0)
    return
  end
  current = current + 1
  jump_to_initializer()
end
emu.addMemoryCallback(returned, emu.callbackType.exec, 0x809580, 0x809580, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded or started then return end
  started = true
  jump_to_initializer()
end, emu.eventType.inputPolled)
