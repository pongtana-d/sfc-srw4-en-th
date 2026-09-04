local STATE = assert(os.getenv('SRW4_STATE'))
local OUT = assert(os.getenv('SRW4_OUT'))
local loaded, armed = false, true
local function load_state()
  if not armed then return end
  armed=false
  emu.removeMemoryCallback(load_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local f=assert(io.open(STATE,'rb')); emu.loadSavestate(f:read('a')); f:close(); loaded=true
end
emu.addMemoryCallback(load_state, emu.callbackType.exec,0x808000,0x80FFFF,emu.cpuType.snes)
emu.addEventCallback(function()
 if not loaded then return end
 local f=assert(io.open(OUT,'w'))
 for base=0x1500,0x1e00,0x20 do
  f:write(string.format('%04X',base))
  for i=0,5 do f:write(string.format(' %02X%02X',emu.read(0x7e0000+base+i*2,emu.memType.snesMemory,false),emu.read(0x7e0000+base+i*2+1,emu.memType.snesMemory,false))) end
  f:write('\n')
 end
 f:close(); emu.stop(0)
end,emu.eventType.inputPolled)
