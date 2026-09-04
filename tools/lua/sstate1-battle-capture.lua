-- Load a Mesen state, press A once, and capture freshly rendered battle frames.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local PRESS_FRAME = tonumber(os.getenv("SRW4_PRESS_FRAME") or "5")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "360")
local SHOTS = {}
for n in (os.getenv("SRW4_SHOTS") or "10,30,60,120,180,240,300,360"):gmatch("%d+") do
  SHOTS[tonumber(n)] = true
end

local loaded, armed, frame = false, true, 0
local function load_state()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(load_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end
emu.addMemoryCallback(load_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  emu.setInput(frame == PRESS_FRAME and {a = true} or {}, 0)
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  if not loaded then return end
  if SHOTS[frame] then
    local handle = assert(io.open(string.format("%s-%04d.png", OUT, frame), "wb"))
    handle:write(emu.takeScreenshot())
    handle:close()
  end
  if frame >= LAST then emu.stop(0) end
end, emu.eventType.endFrame)
