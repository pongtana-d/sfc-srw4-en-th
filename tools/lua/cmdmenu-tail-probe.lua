-- Trace the two stock command-frame stores that can expose a transient
-- footer to the right of the expanded command surface.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "110")
local PRESS = os.getenv("SRW4_PRESS") or "5:b,60:a"

local presses = {}
for pair in PRESS:gmatch("[^,]+") do
  local at, button = pair:match("^(%d+):(%a+)$")
  if at then presses[tonumber(at)] = button end
end

local loaded, armed, frame = false, false, 0
local hits = {}

local function word(address)
  return emu.read(address, emu.memType.snesMemory, false)
    | (emu.read(address + 1, emu.memType.snesMemory, false) << 8)
end

local function boot()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(boot, emu.callbackType.exec,
    0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end
local function watch(label, address)
  emu.addMemoryCallback(function()
    if not loaded then return end
    local a = emu.getRegister(emu.registers.a) & 0xFFFF
    local x = emu.getRegister(emu.registers.x) & 0xFFFF
    hits[#hits + 1] = string.format(
      "%s f=%d A=%04X X=%04X active=%04X old=%04X",
      label, frame, a, x, word(0x7ECED6), word(0x7E8000 + x))
  end, emu.callbackType.exec, address, address, emu.cpuType.snes)
end

watch("repeat-stock", 0xC18440)
watch("frame-stock", 0xC1844B)
watch("repeat-hook", 0xFB069B)
watch("frame-hook", 0xFB067B)
watch("raster-hook", 0xFB03D3)

emu.addEventCallback(function()
  if not loaded then
    if not armed then
      armed = true
      emu.addMemoryCallback(boot, emu.callbackType.exec,
        0x808000, 0x80FFFF, emu.cpuType.snes)
    end
    return
  end
  frame = frame + 1
  if presses[frame] then
    emu.setInput({ [presses[frame]] = true }, 0)
  else
    emu.setInput({}, 0)
  end
  if frame < LAST then return end
  local handle = assert(io.open(OUT, "w"))
  for _, hit in ipairs(hits) do handle:write(hit .. "\n") end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
