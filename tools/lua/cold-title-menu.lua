-- Advance the publisher splash once, then stop sending input and observe the
-- title/menu redraw without accidentally entering protagonist settings.
local PREFIX = assert(os.getenv("SRW4_PREFIX"), "SRW4_PREFIX is required")
local frame = 0

emu.addEventCallback(function()
  frame = frame + 1
  local buttons = {}
  if frame >= 720 and frame <= 725 then
    buttons.start = true
  end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  if frame >= 700 and frame <= 1800 and frame % 50 == 0 then
    local handle = assert(io.open(string.format("%s-%04d.png", PREFIX, frame), "wb"))
    handle:write(emu.takeScreenshot())
    handle:close()
  end
  if frame >= 1800 then emu.stop(0) end
end, emu.eventType.endFrame)
