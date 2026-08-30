-- Trace one EN-ROM battle quote from a state immediately before battle entry.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local PRESS_FRAME = tonumber(os.getenv("SRW4_PRESS_FRAME") or "5")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "220")

local frame, loaded, armed = 0, false, true
local rows = {}

local function byte(address)
  return emu.read(address, emu.memType.snesMemory, false)
end

local function word(address)
  return byte(address) | (byte(address + 1) << 8)
end

local function pointer()
  return byte(0xCB) | (byte(0xCC) << 8) | (byte(0xCD) << 16)
end

local function note(name, address)
  if not loaded then return end
  rows[#rows + 1] = string.format(
    "%s frame=%d pc=%06X ptr=%06X glyph=%04X " ..
    "page=%04X active=%04X sig=%04X pen=%04X expect=%04X d0=%04X d2=%04X",
    name, frame, address, pointer(), word(0x02),
    word(0x7EFFDC), word(0x7EFFDE), word(0x7EFFC0), word(0x7EFFC2),
    word(0x7EFFC4), word(0xD0), word(0xD2))
end

local function load_state()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(
    load_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end

emu.addMemoryCallback(
  load_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

local sites = {
  {"fetch", 0x819763},
  {"loop", 0x8191E3},
  {"width", 0x819219},
  {"stock_width", 0x81921E},
  {"draw", 0x819238},
}

for _, site in ipairs(sites) do
  local name, address = site[1], site[2]
  emu.addMemoryCallback(function(at)
    local ok, err = pcall(note, name, at)
    if not ok then
      rows[#rows + 1] = string.format(
        "error frame=%d pc=%06X name=%s detail=%s", frame, at, name, tostring(err))
    end
  end,
    emu.callbackType.exec, address, address, emu.cpuType.snes)
end

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if frame == PRESS_FRAME then
    emu.setInput({a = true}, 0)
  else
    emu.setInput({}, 0)
  end
  if frame <= LAST then return end
  local handle = assert(io.open(OUT, "w"))
  for _, row in ipairs(rows) do handle:write(row .. "\n") end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
