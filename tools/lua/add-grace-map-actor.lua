-- Add one new friendly ally ("Grace") map actor into the free native slot 13
-- of the grace.mss base state. Follows the field layout proven by
-- add-dunbine-map-actors.lua: the map/actor table is 16 records wide, each
-- record field is a 0x20-byte-stride array of 16 two-byte entries, base
-- $7E0000, per-actor-record fields spanning bases 0x1565-0x1DE5 (step 0x20).
--
-- Name-display note: this ROM's Pilot Display / roster name renderer reads a
-- fixed ROM name-pointer table indexed by a single-byte pilot id (see
-- data/translations/pilots.source.json) — it does NOT go through the
-- dialogue engine's <NAME:...> control-code / SRAM free-text buffer used by
-- the protagonist-naming screen. That free-text path is exclusive to
-- dialogue/UI text runs; the roster list renderer never calls it. Making the
-- roster display literally show "Grace" would require patching the ROM name
-- table itself, which is out of scope for a savestate-only edit. So this
-- clones the source slot's fields and points the pilot-id at id 200 (0xC8,
-- "DC Soldier" / "ＤＣ兵士"), a generic anonymous-troop name rather than an
-- existing named character, to avoid visually duplicating another cast
-- member's identity. The unit/mech id is reused from the source ally per the
-- task ("any mech is fine").

local STATE = assert(os.getenv('SRW4_STATE'))
local SAVE = assert(os.getenv('SRW4_SAVE'))
local SOURCE_SLOT = tonumber(os.getenv('SRW4_SOURCE_SLOT') or '0')
local NEW_SLOT = tonumber(os.getenv('SRW4_NEW_SLOT') or '13')
local NEW_PILOT = tonumber(os.getenv('SRW4_NEW_PILOT') or '0xC8')
local NEW_ROSTER_INDEX = tonumber(os.getenv('SRW4_NEW_ROSTER_INDEX') or tostring(NEW_SLOT))

local loaded, applied, armed = false, false, true
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
  local source = SOURCE_SLOT * 2
  local target = NEW_SLOT * 2
  -- Read the source's existing unit id so "any mech" reuses a known-good one.
  local unit = read(0x7E1208+source)

  -- Clone every per-actor field verbatim from the source slot, including the
  -- active/side flags that a sparse clone would miss.
  for base = 0x1565, 0x1DE5, 0x20 do
    write(0x7E0000+base+target,read(0x7E0000+base+source))
    write(0x7E0000+base+target+1,read(0x7E0000+base+source+1))
  end

  -- Persistent roster record.
  write(0x7E1088+target,NEW_PILOT); write(0x7E1089+target,0x63)
  write(0x7E1108+target,0); write(0x7E1109+target,0x10)
  write(0x7E1208+target,unit); write(0x7E1209+target,0x80+target)

  -- Live map-actor identity, Will 250.
  write(0x7E17E5+target,NEW_PILOT); write(0x7E17E6+target,0x63)
  write(0x7E1865+target,unit); write(0x7E1866+target,0)
  write(0x7E1AE5+target,0xFA)

  -- Map slot -> persistent roster index indirection.
  write(0x7E1565+target,NEW_ROSTER_INDEX)
  write(0x7E1566+target,0x44)

  -- Position: offset one tile right/down from the source actor's position so
  -- the two don't render stacked on the exact same tile.
  local posx = read(0x7E1765+source)
  local posy = read(0x7E1766+source)
  write(0x7E1765+target, (posx + 1) % 0x100)
  write(0x7E1766+target, posy)

  emu.addMemoryCallback(save_state,emu.callbackType.exec,0x820000,0x82FFFF,emu.cpuType.snes)
end,emu.eventType.inputPolled)
