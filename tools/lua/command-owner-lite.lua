-- Lightweight command-menu trace: only the WRAM regions that can supply the
-- BG tilemap DMA.  Deliberately avoids PPU callbacks, which are too frequent
-- for deterministic test-runner capture.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local OPEN_AT = tonumber(os.getenv("SRW4_OPEN_AT") or "10")
local END_AT = tonumber(os.getenv("SRW4_END_AT") or "90")
local PRESS = os.getenv("SRW4_PRESS") or ""
local presses = {}
for pair in PRESS:gmatch("[^,]+") do
  local at, button = pair:match("^(%d+):(%a+)$")
  if at then presses[tonumber(at)] = button end
end

local loaded, armed, frame = false, false, 0
local hits = {}

local function boot()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end

local function watch(label, first, last)
  emu.addMemoryCallback(function(address)
    if not loaded then return end
    local pc = emu.getRegister(emu.registers.pc) & 0xFFFF
    local key = string.format("%s frame=%d at=%04X pc=%04X", label, frame, address & 0xFFFF, pc)
    hits[key] = (hits[key] or 0) + 1
  end, emu.callbackType.write, first, last, emu.cpuType.snes)
end

watch("a000", 0x00A000, 0x00A3FF)
watch("dd00", 0x00DD00, 0x00DFFF)

emu.addEventCallback(function()
  if not loaded then
    if not armed then
      armed = true
      emu.addMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
    end
    return
  end
  frame = frame + 1
  local buttons = {}
  if frame == OPEN_AT then buttons.a = true end
  if presses[frame] then buttons[presses[frame]] = true end
  emu.setInput(buttons, 0)
  if frame ~= END_AT then return end
  local keys = {}; for key in pairs(hits) do keys[#keys + 1] = key end
  table.sort(keys)
  local handle = assert(io.open(OUT, "w"))
  for _, key in ipairs(keys) do handle:write(string.format("%s count=%d\n", key, hits[key])) end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
