-- Trace EN battle quote bytes through the private-page router and VWF.
--
-- SRW4_STATE: EN Mesen savestate immediately before the quote transition.
-- SRW4_OUT:   text trace destination.
-- SRW4_PRESS: frame that presses A (default 30).
-- SRW4_FRAMES: final frame (default 45).
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local PRESS = tonumber(os.getenv("SRW4_PRESS") or "30")
local AUTO_A_EVERY = tonumber(os.getenv("SRW4_AUTO_A_EVERY") or "0")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "45")

local frame, loaded, armed = 0, false, true
local rows = {}

local function byte(address)
  return emu.read(address, emu.memType.snesMemory, false)
end

local function word(address)
  return byte(address) | (byte(address + 1) << 8)
end

local function pointer(address)
  return word(address) | (byte(address + 2) << 16)
end

local function load_state()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(
    load_state, emu.callbackType.exec, 0x808000, 0x80FFFF,
    emu.cpuType.snes)
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
  rows[#rows + 1] = string.format(
    "loaded hook81=%02X%02X%02X%02X hookC1=%02X%02X%02X%02X " ..
    "entryFF=%02X%02X%02X%02X",
    byte(0x819238), byte(0x819239), byte(0x81923A), byte(0x81923B),
    byte(0xC19238), byte(0xC19239), byte(0xC1923A), byte(0xC1923B),
    byte(0xFF8800), byte(0xFF8801), byte(0xFF8802), byte(0xFF8803))
end

emu.addMemoryCallback(
  load_state, emu.callbackType.exec, 0x808000, 0x80FFFF,
  emu.cpuType.snes)

local function note(label, pc)
  if not loaded then return end
  local source = pointer(0xCB)
  rows[#rows + 1] = string.format(
    "%s frame=%d pc=%06X A=%04X glyph=%04X src=%06X next=%02X " ..
    "page=%04X active=%04X pen=%04X",
    label, frame, pc, emu.getRegister(emu.registers.a) & 0xFFFF,
    word(0x02), source, byte(source), word(0x7EFFDC),
    word(0x7EFFDE), word(0x7EFFC2))
end

-- The live EN battle loop executes the $81 mirror. Register only that mirror;
-- adding the matching $C1 callback can replace it in Mesen's ROM callback map.
emu.addMemoryCallback(function(pc)
  note("dispatch", pc)
end, emu.callbackType.exec, 0x819238, 0x819238, emu.cpuType.snes)

emu.addMemoryCallback(function(address, value)
  if not loaded then return end
  rows[#rows + 1] = string.format(
    "page_write frame=%d at=%06X value=%02X src=%06X glyph=%04X",
    frame, address, value, pointer(0xCB), word(0x02))
end, emu.callbackType.write, 0x7EFFDC, 0x7EFFDD, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if frame == PRESS or (AUTO_A_EVERY > 0 and frame % AUTO_A_EVERY == 0) then
    emu.setInput({a = true}, 0)
  else emu.setInput({}, 0) end
  if frame == 1 or frame % 30 == 0 then
    rows[#rows + 1] = string.format(
      "frame=%d src=%06X next=%02X page=%04X", frame, pointer(0xCB),
      byte(pointer(0xCB)), word(0x7EFFDC))
  end
  if frame <= LAST then return end
  local handle = assert(io.open(OUT, "w"))
  for _, row in ipairs(rows) do handle:write(row .. "\n") end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
