-- Diagnose save/freeze.mss against the current EN->Thai ROM.
-- This changes only emulated WRAM after loading the state.  It does not write
-- either the ROM or the .mss file.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local PAGE = 0x7EFFDC
local frame, loaded, parser_hits, draw_hits = 0, false, 0, 0
local samples = {}

local function byte(address)
  return emu.read(address, emu.memType.snesMemory, false)
end

local function word(address)
  return byte(address) | (byte(address + 1) << 8)
end

local function pointer()
  return byte(0xCB) | (byte(0xCC) << 8) | (byte(0xCD) << 16)
end

emu.addMemoryCallback(function()
  if loaded then return end
  local h = assert(io.open(STATE, "rb"))
  emu.loadSavestate(h:read("a"))
  h:close()
  -- The state stopped after consuming C1 3E 04 from record 02_0BE4.  Restore
  -- the selected Thai page and let the original parser resume at the first
  -- glyph; do not fabricate a new pointer or parser state.
  emu.write(PAGE, 0x02, emu.memType.snesMemory)
  emu.write(PAGE + 1, 0x00, emu.memType.snesMemory)
  loaded = true
end, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if loaded then parser_hits = parser_hits + 1 end
end, emu.callbackType.exec, 0x819238, 0x819238, emu.cpuType.snes)

-- Current draw dispatcher at ROM PC $3F:8800 = CPU $FF:8800.
emu.addMemoryCallback(function()
  if loaded then draw_hits = draw_hits + 1 end
end, emu.callbackType.exec, 0xFF8800, 0xFF8800, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  emu.setInput({}, 0)
  if frame == 1 or frame % 30 == 0 then
    samples[#samples + 1] = string.format(
      "frame=%d ptr=%06X byte=%02X page=%04X state=%04X parser=%d draw=%d",
      frame, pointer(), byte(pointer()), word(PAGE), word(0x0E2A),
      parser_hits, draw_hits)
  end
  if frame == 1 or frame == 30 or frame == 90 or frame == 180 then
    local h = assert(io.open(string.format("%s-%04d.png", OUT, frame), "wb"))
    h:write(emu.takeScreenshot())
    h:close()
  end
  if frame < 180 then return end
  local h = assert(io.open(OUT .. ".txt", "w"))
  h:write(table.concat(samples, "\n"), "\n")
  h:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
