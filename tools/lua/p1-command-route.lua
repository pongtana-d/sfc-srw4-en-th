-- Reproducible P1 route: cold boot reference ROM, choose the default
-- protagonist, then advance the opening until the map is reached.  It saves
-- sparse screenshots; later probes can start from the resulting map state.
local PREFIX = assert(os.getenv("SRW4_PREFIX"), "SRW4_PREFIX is required")
local LAST = tonumber(os.getenv("SRW4_LAST") or "12000")
local SAVE = os.getenv("SRW4_SAVE")
local PRESS_UNTIL = tonumber(os.getenv("SRW4_PRESS_UNTIL") or "16000")

local function pulse(frame, every, width)
  return frame % every < width
end

local frame = 0
local saved, pending = false, false
local function save_state()
  if not pending then return end
  pending = false
  emu.removeMemoryCallback(save_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(SAVE, "wb"))
  handle:write(emu.createSavestate())
  handle:close()
  saved = true
end
emu.addEventCallback(function()
  frame = frame + 1
  local buttons = {}
  if frame >= 60 and frame <= 900 and pulse(frame - 60, 30, 3) then
    buttons.start = true
  elseif frame >= 950 and frame <= 955 then
    buttons.a = true
  elseif frame >= 1580 and frame <= 1600 then
    buttons.down = true
  elseif frame >= 1640 and frame <= 1645 then
    buttons.a = true
  elseif frame >= 1800 and frame <= PRESS_UNTIL and pulse(frame - 1800, 45, 3) then
    buttons.a = true
  end
  if next(buttons) then emu.setInput(buttons, 0) end
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  if (frame >= 2000 and frame < 12000 and frame % 250 == 0)
      or (frame >= 12000 and frame % 10 == 0) then
    local handle = assert(io.open(string.format("%s-%05d.png", PREFIX, frame), "wb"))
    handle:write(emu.takeScreenshot())
    handle:close()
  end
  if SAVE and not saved and frame == 12000 then
    pending = true
    emu.addMemoryCallback(save_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  end
  if frame >= LAST then emu.stop(0) end
end, emu.eventType.endFrame)
