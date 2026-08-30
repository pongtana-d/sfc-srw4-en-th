-- Walk a scripted route and photograph the screen at set frames.
--
-- Used to hold two builds side by side: same route, same frames, and the
-- pictures must come out identical when the change was supposed to be
-- invisible.
local PRESS = os.getenv("SRW4_PRESS") or ""
local SHOTS = os.getenv("SRW4_SHOTS") or ""
local PREFIX = os.getenv("SRW4_PREFIX") or "build/route/shot"
local LAST = tonumber(os.getenv("SRW4_LAST") or "4200")

local presses = {}
for entry in string.gmatch(PRESS, "[^,]+") do
  local from, to, button = string.match(entry, "(%d+):(%d+):(%a+)")
  if from then
    presses[#presses + 1] = { from = tonumber(from), to = tonumber(to), button = button }
  end
end

local shots = {}
for frame in string.gmatch(SHOTS, "%d+") do shots[tonumber(frame)] = true end

local frame = 0

emu.addEventCallback(function()
  frame = frame + 1
  local held = {}
  for _, press in ipairs(presses) do
    if frame >= press.from and frame <= press.to then
      held[press.button] = true
    end
  end
  emu.setInput(held, 0)
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  if shots[frame] then
    local file = io.open(string.format("%s-%05d.png", PREFIX, frame), "wb")
    file:write(emu.takeScreenshot())
    file:close()
  end
  if frame >= LAST then emu.stop(0) end
end, emu.eventType.endFrame)
