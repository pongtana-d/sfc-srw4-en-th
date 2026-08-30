-- Verify that a stale Thai dialogue page cannot capture EN menu/status draws.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local SHOT = assert(os.getenv("SRW4_SHOT"), "SRW4_SHOT is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local frame, loaded, armed = 0, false, true
local thai_hits, stock_hits = 0, 0
local presses = { [80] = "down", [120] = "down", [160] = "a",
                  [220] = "right", [260] = "a" }

local function load_state()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(load_state, emu.callbackType.exec,
    0x808000, 0x80FFFF, emu.cpuType.snes)
  local h = assert(io.open(STATE, "rb"))
  emu.loadSavestate(h:read("a"))
  h:close()
  loaded = true
end
emu.addMemoryCallback(load_state, emu.callbackType.exec,
  0x808000, 0x80FFFF, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if loaded then thai_hits = thai_hits + 1 end
end, emu.callbackType.exec, 0xFFA000, 0xFFA000, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if loaded then stock_hits = stock_hits + 1 end
end, emu.callbackType.exec, 0xF0E045, 0xF0E045, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  -- Simulate the stale dialogue page that corrupted the user's EN screen.
  emu.write(0x7EFFDC, 0x02, emu.memType.snesMemory)
  emu.write(0x7EFFDD, 0x00, emu.memType.snesMemory)
  emu.write(0x7EFFDE, 0x00, emu.memType.snesMemory)
  emu.write(0x7EFFDF, 0x00, emu.memType.snesMemory)
  local buttons = {}
  if presses[frame] then buttons[presses[frame]] = true end
  emu.setInput(buttons, 0)
  if frame < 350 then return end
  local image = assert(io.open(SHOT, "wb"))
  image:write(emu.takeScreenshot())
  image:close()
  local log = assert(io.open(OUT, "w"))
  log:write(string.format("thai_renderer_hits=%d stock_renderer_hits=%d\n",
    thai_hits, stock_hits))
  log:close()
  emu.stop(thai_hits == 0 and 0 or 1)
end, emu.eventType.inputPolled)
