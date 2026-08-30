-- Cold boot through protagonist confirmation, then observe the transition
-- without further input.  Used to distinguish transient stock effects from
-- corruption introduced by the translated build.
local PREFIX = assert(os.getenv("SRW4_PREFIX"), "SRW4_PREFIX is required")
local frame = 0

local function pulse(value, every, width)
  return value % every < width
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
  end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  if frame == 900 or frame == 1500
      or (frame >= 1600 and frame <= 3200 and frame % 100 == 0) then
    local handle = assert(io.open(string.format("%s-%04d.png", PREFIX, frame), "wb"))
    handle:write(emu.takeScreenshot())
    handle:close()
  end
  if frame >= 3200 then emu.stop(0) end
end, emu.eventType.endFrame)
