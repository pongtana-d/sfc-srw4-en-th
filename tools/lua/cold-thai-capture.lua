-- Cold boot, enter the default protagonist route, then freeze input as soon
-- as the story parser consumes a relocated Thai stream.  The resulting frame
-- is proof from freshly rendered VRAM, not a save-state thumbnail.
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local META = os.getenv("SRW4_META")
local ARENA = os.getenv("SRW4_ARENA")
local frame, capture_at, captured = 0, nil, false
local first_pointer, first_bank = nil, nil

local function pulse(value, every, width)
  return value % every < width
end

emu.addMemoryCallback(function()
  if frame < 1800 or capture_at then return end
  local bank = emu.read(0xCD, emu.memType.snesMemory, false)
  if bank == 0xEB or (bank >= 0xF1 and bank <= 0xFC) then
    first_bank = bank
    first_pointer = emu.read(0xCB, emu.memType.snesMemory, false)
      + emu.read(0xCC, emu.memType.snesMemory, false) * 0x100
    capture_at = frame + 90
  end
end, emu.callbackType.exec, 0x819238, 0x819238, emu.cpuType.snes)

emu.addEventCallback(function()
  frame = frame + 1
  local buttons = {}
  if not capture_at then
    if frame >= 60 and frame <= 900 and pulse(frame - 60, 30, 3) then
      buttons.start = true
    elseif frame >= 950 and frame <= 955 then
      buttons.a = true
    elseif frame >= 1580 and frame <= 1600 then
      buttons.down = true
    elseif frame >= 1640 and frame <= 1645 then
      buttons.a = true
    elseif frame >= 1800 and pulse(frame - 1800, 45, 3) then
      buttons.a = true
    end
  end
  emu.setInput(buttons, 0)
  if capture_at and frame >= capture_at then
    local f = assert(io.open(OUT, "wb")); f:write(emu.takeScreenshot()); f:close()
    if META then
      local m = assert(io.open(META, "w"))
      m:write(string.format("bank=%02X pointer=%04X frame=%d\n",
        first_bank or 0, first_pointer or 0, frame))
      m:close()
    end
    if ARENA then
      local a = assert(io.open(ARENA, "wb"))
      local bytes = {}
      for offset = 0, 0x7FFF do
        bytes[#bytes + 1] = string.char(
          emu.read(0x7F8000 + offset, emu.memType.snesMemory, false))
      end
      a:write(table.concat(bytes)); a:close()
    end
    captured = true
    emu.stop(0)
  elseif frame >= 15000 then
    error("Thai renderer was not reached from cold boot")
  end
end, emu.eventType.inputPolled)
