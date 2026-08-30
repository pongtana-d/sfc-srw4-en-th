-- Verify the native command router's four-row record list after a genuine
-- command-menu redraw.  This is intentionally independent of screenshots.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local PRESS = os.getenv("SRW4_PRESS") or "180:a"
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "300")
local CLEAR_AT = tonumber(os.getenv("SRW4_CLEAR_AT") or "1")
local presses = {}
for pair in PRESS:gmatch("[^,]+") do
  local at, button = pair:match("^(%d+):(%a+)$")
  if at then presses[tonumber(at)] = button end
end
local loaded, armed, frame = false, true, 0
local ACTIVE = 0x7ECED6
local COUNT = 0x7ECEE4
local COOKIE = 0xC7A5

local function word(address)
  return emu.read(address, emu.memType.snesMemory, false)
    | (emu.read(address + 1, emu.memType.snesMemory, false) << 8)
end

local function boot()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end
emu.addMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  -- Savestates can retain a valid cookie and record list from an older menu.
  -- Clear both before driving input so only a genuine redraw can claim them.
  if frame == 1 or frame == CLEAR_AT then
    emu.write(ACTIVE, 0, emu.memType.snesMemory)
    emu.write(ACTIVE + 1, 0, emu.memType.snesMemory)
    emu.write(COUNT, 0, emu.memType.snesMemory)
    emu.write(COUNT + 1, 0, emu.memType.snesMemory)
  end
  -- Hold each scripted pulse for six input polls.  Map cursor reads are slower
  -- than menu reads in field/interlace states; shorter pulses can be ignored.
  local button = nil
  for age = 0, 5 do
    if presses[frame - age] then button = presses[frame - age]; break end
  end
  if button then emu.setInput({ [button] = true }, 0)
  else emu.setInput({}, 0) end
  if frame ~= LAST then return end
  local handle = assert(io.open(OUT, "w"))
  handle:write(string.format(
    "active=%04X max_pen=%04X pointer=%02X:%04X tile=%04X selected=%02X\n",
    word(ACTIVE), word(0x7ECED4),
    emu.read(0x1C, emu.memType.snesMemory, false), word(0x1A), word(0xD0),
    emu.read(0x0E3A, emu.memType.snesMemory, false)))
  local count = word(COUNT)
  handle:write(string.format("count=%d\n", count))
  if word(ACTIVE) == COOKIE then
    for index = 0, math.min(count, 4) - 1 do
      handle:write(string.format("record[%d]=%d\n", index,
        emu.read(0x7ECEE6 + index, emu.memType.snesMemory, false)))
    end
  end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
