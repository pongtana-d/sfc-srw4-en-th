-- Observe an isolated cold boot without input so the title redraw cannot be
-- skipped by an automated Start pulse.
local PREFIX = assert(os.getenv("SRW4_PREFIX"), "SRW4_PREFIX is required")
local frame = 0

emu.addEventCallback(function()
  frame = frame + 1
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  if frame >= 60 and frame <= 1200 and frame % 60 == 0 then
    local handle = assert(io.open(string.format("%s-%04d.png", PREFIX, frame), "wb"))
    handle:write(emu.takeScreenshot())
    handle:close()
  end
  if frame >= 1200 then emu.stop(0) end
end, emu.eventType.endFrame)
