-- P0 boot check: run the built ROM from a cold boot, press start a few times,
-- and save a screenshot. Proves the expanded image still runs; it is not a
-- substitute for judging text, which must always come from a live redraw.
local OUT = os.getenv("SRW4_SHOT") or "build/reports/boot.png"
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "900")

local frame = 0

local function onInput()
  frame = frame + 1
  if frame > 60 and frame % 30 == 0 then
    emu.setInput({ start = true }, 0)
  end
end

local function onFrame()
  if frame >= LAST then
    local png = emu.takeScreenshot()
    local f = io.open(OUT, "wb")
    f:write(png)
    f:close()
    emu.log("screenshot written to " .. OUT .. " at frame " .. frame)
    emu.stop(0)
  end
end

emu.addEventCallback(onInput, emu.eventType.inputPolled)
emu.addEventCallback(onFrame, emu.eventType.endFrame)
