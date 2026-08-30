-- Reach protagonist settings from an isolated cold boot, then apply a
-- caller-supplied input sequence.  Syntax: SRW4_PRESS="950:down,1000:a".
local PREFIX = assert(os.getenv("SRW4_PREFIX"), "SRW4_PREFIX is required")
local PRESS = os.getenv("SRW4_PRESS") or ""
local SHOTS = os.getenv("SRW4_SHOTS") or "900,1000,1100,1300"
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "1400")
local BOOT_END = tonumber(os.getenv("SRW4_BOOT_END") or "900")
local frame = 0

local presses = {}
for pair in PRESS:gmatch("[^,]+") do
  local at, button = pair:match("^(%d+):(%a+)$")
  if at then presses[tonumber(at)] = button end
end

local shots = {}
for value in SHOTS:gmatch("%d+") do shots[tonumber(value)] = true end

local function pulse(value, every, width)
  return value % every < width
end

emu.addEventCallback(function()
  frame = frame + 1
  local buttons = {}
  if frame >= 60 and frame <= BOOT_END and pulse(frame - 60, 30, 3) then
    buttons.start = true
  elseif presses[frame] then
    buttons[presses[frame]] = true
  end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  if shots[frame] then
    local handle = assert(io.open(string.format("%s-%04d.png", PREFIX, frame), "wb"))
    handle:write(emu.takeScreenshot())
    handle:close()
  end
  if frame >= LAST then emu.stop(0) end
end, emu.eventType.endFrame)
