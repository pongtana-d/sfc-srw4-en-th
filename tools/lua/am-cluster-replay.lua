-- Replay a supplied ROM record through the live story compositor after A.
-- Only the isolated emulator pointer is changed; state and ROM files are read-only.
local state = assert(os.getenv('SRW4_STATE'))
local out = assert(os.getenv('SRW4_OUT'))
local record = tonumber(assert(os.getenv('SRW4_RECORD')), 16)
local loaded, redirected, frame = false, false, 0
local log = {}
local function read(a) return emu.read(a, emu.memType.snesMemory, false) end
local function load()
  if loaded then return end
  loaded = true
  emu.removeMemoryCallback(load, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local f = assert(io.open(state, 'rb')); emu.loadSavestate(f:read('a')); f:close()
end
emu.addMemoryCallback(load, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
emu.addMemoryCallback(function()
  if not loaded or redirected or frame < 10 then return end
  for i=0,2 do emu.write(0xCB+i, (record >> (8*i)) & 255, emu.memType.snesMemory) end
  redirected = true
end, emu.callbackType.exec, 0x8191E3, 0x8191E3, emu.cpuType.snes)
emu.addMemoryCallback(function()
  if not redirected then return end
  local p = read(0xCB) | (read(0xCC)<<8) | (read(0xCD)<<16)
  log[#log+1] = string.format('frame=%d ptr=%06X glyph=%04X page=%04X', frame,p,read(2)|(read(3)<<8),read(0x7EFFDC)|(read(0x7EFFDD)<<8))
end, emu.callbackType.exec, 0x819238, 0x819238, emu.cpuType.snes)
emu.addEventCallback(function()
  if not loaded then return end
  frame=frame+1
  emu.setInput({a=frame>=10 and frame<=15},0)
end, emu.eventType.inputPolled)
emu.addEventCallback(function()
  if not loaded or frame<180 then return end
  local f=assert(io.open(out..'.png','wb')); f:write(emu.takeScreenshot()); f:close()
  f=assert(io.open(out..'.txt','w')); f:write('redirected='..tostring(redirected)..'\n'..table.concat(log,'\n')); f:close()
  emu.stop(0)
end, emu.eventType.endFrame)
