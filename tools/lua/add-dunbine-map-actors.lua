-- Add five independent player-map actors to the five empty native slots 11-15.
-- The map table is 16 records wide; every record field is a 0x20-byte array
-- of 16 two-byte entries.  Do not write past slot 15.
local STATE = assert(os.getenv('SRW4_STATE'))
local SAVE = assert(os.getenv('SRW4_SAVE'))
local loaded, applied, armed = false, false, true
local party = {
  {0x1C, 0x40}, -- Shou / Bilbine
  {0x62, 0x3F}, -- Marvel / Dunbine
  {0x64, 0x41}, -- Nie / Wing Caliber
  {0x65, 0x3F}, -- Keen / Dunbine
  {0x66, 0x40}, -- Shiela / Bilbine
}
local function read(a) return emu.read(a, emu.memType.snesMemory, false) end
local function write(a,v) emu.write(a,v,emu.memType.snesMemory) end
local function load_state()
  if not armed then return end
  armed=false; emu.removeMemoryCallback(load_state,emu.callbackType.exec,0x808000,0x80FFFF,emu.cpuType.snes)
  local f=assert(io.open(STATE,'rb')); emu.loadSavestate(f:read('a')); f:close(); loaded=true
end
emu.addMemoryCallback(load_state,emu.callbackType.exec,0x808000,0x80FFFF,emu.cpuType.snes)
local function save_state()
  local f=assert(io.open(SAVE,'wb')); f:write(emu.createSavestate()); f:close(); emu.stop(0)
end
emu.addEventCallback(function()
  if not loaded or applied then return end
  applied=true
  for n,entry in ipairs(party) do
    local source = (n - 1) * 2
    local slot = 10 + n -- empty map slots 11-15
    local target = slot * 2
    -- Clone every per-actor field, including the active/side flags that the
    -- previous sparse clone missed.
    for base = 0x1565, 0x1DE5, 0x20 do
      write(0x7E0000+base+target,read(0x7E0000+base+source))
      write(0x7E0000+base+target+1,read(0x7E0000+base+source+1))
    end
    local pilot,unit=entry[1],entry[2]
    -- Persistent roster record.
    write(0x7E1088+target,pilot); write(0x7E1089+target,0x63)
    write(0x7E1108+target,0); write(0x7E1109+target,0x10)
    write(0x7E1208+target,unit); write(0x7E1209+target,0x80+target)
    -- New live map actor identity, Lv99, Will250.
    write(0x7E17E5+target,pilot); write(0x7E17E6+target,0x63)
    write(0x7E1865+target,unit); write(0x7E1866+target,0)
    write(0x7E1AE5+target,0xFA)
    -- Map slot -> persistent roster index.  The existing slots use this
    -- table as an indirection rather than their live identity fields alone.
    write(0x7E1565+target,0x0C+n)
    write(0x7E1566+target,0x44)
    -- Position is a two-byte record, not two adjacent slot arrays.
    write(0x7E1765+target,0x0A+n)
    write(0x7E1766+target,0x0A)
  end
  -- Native map ally-actor count: 11 original + 5 injected = table limit 16.
  write(0x7E1086,0x10)
  write(0x7E1087,0x0F)
  write(0x7E1408,0x63)
  emu.addMemoryCallback(save_state,emu.callbackType.exec,0x820000,0x82FFFF,emu.cpuType.snes)
end,emu.eventType.inputPolled)
