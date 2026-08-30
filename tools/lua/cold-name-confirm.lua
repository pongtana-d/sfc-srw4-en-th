-- Cold-boot through the native setup route, then use Start to confirm naming.
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "4200")
local frame = 0
emu.addEventCallback(function()
  frame = frame + 1
  local input = {}
  if frame > 60 and frame <= 1300 and frame % 30 == 0 then input.start = true end
  if frame == 1350 or frame == 1900 then input.a = true end
  if frame >= 1720 and frame < 1880 and (frame - 1720) % 20 == 0 then input.down = true end
  if frame == 1940 then input.start = true end
  if frame > 2100 and frame <= 4200 and frame % 60 == 0 then input.start = true end
  emu.setInput(input, 0)
  if frame < LAST then return end
  local image = assert(io.open(OUT, "wb")); image:write(emu.takeScreenshot()); image:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
