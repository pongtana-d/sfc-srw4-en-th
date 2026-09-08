local output = assert(os.getenv('SRW4_OUT'))
local rows = {}
local function word(a)
 return emu.read(a, emu.memType.snesMemory, false) | (emu.read(a+1, emu.memType.snesMemory, false)<<8)
end
for _,pc in ipairs({0x8184E4,0xF0E045}) do
 emu.addMemoryCallback(function()
  if #rows < 2000 then
   rows[#rows+1] = string.format('pc=%06X src=%02X:%04X glyph=%04X',pc,word(0x1C)&255,word(0x1A),word(0))
  end
 end,emu.callbackType.exec,pc,pc,emu.cpuType.snes)
end
emu.addEventCallback(function()
 local h=assert(io.open(output..'-trace.txt','w'));h:write(table.concat(rows,'\n'));h:close()
end,emu.eventType.endFrame)
dofile('/Users/mono-tong/Projects/games/sfc-srw4-en-th/tools/lua/from-state.lua')
