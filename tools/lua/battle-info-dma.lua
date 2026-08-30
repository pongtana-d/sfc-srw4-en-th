local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "170")
local PRESS = os.getenv("SRW4_PRESS") or "5:a"

local presses = {}
for pair in PRESS:gmatch("[^,]+") do
  local at, button = pair:match("^(%d+):(%a+)$")
  if at then presses[tonumber(at)] = button end
end

local frame, loaded, armed = 0, false, true
local vmadd_lo, vmadd_hi = 0, 0
local rows = {}

local function boot()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(boot, emu.callbackType.exec,
    0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a")); handle:close()
  loaded = true
end
emu.addMemoryCallback(boot, emu.callbackType.exec,
  0x808000, 0x80FFFF, emu.cpuType.snes)

emu.addMemoryCallback(function(_, value)
  if loaded then vmadd_lo = value end
end, emu.callbackType.write, 0x002116, 0x002116, emu.cpuType.snes)

emu.addMemoryCallback(function(_, value)
  if loaded then vmadd_hi = value end
end, emu.callbackType.write, 0x002117, 0x002117, emu.cpuType.snes)

emu.addMemoryCallback(function(_, value)
  if not loaded then return end
  for channel = 0, 7 do
    if (value & (1 << channel)) ~= 0 then
      local base = 0x4300 + channel * 0x10
      rows[#rows + 1] = string.format(
        "f=%d ch=%d mode=%02X bbus=%02X src=%02X:%02X%02X len=%02X%02X vmadd=%02X%02X",
        frame, channel,
        emu.read(base, emu.memType.snesMemory, false),
        emu.read(base + 1, emu.memType.snesMemory, false),
        emu.read(base + 4, emu.memType.snesMemory, false),
        emu.read(base + 3, emu.memType.snesMemory, false),
        emu.read(base + 2, emu.memType.snesMemory, false),
        emu.read(base + 6, emu.memType.snesMemory, false),
        emu.read(base + 5, emu.memType.snesMemory, false),
        vmadd_hi, vmadd_lo)
    end
  end
end, emu.callbackType.write, 0x00420B, 0x00420B, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if presses[frame] then emu.setInput({ [presses[frame]] = true }, 0)
  else emu.setInput({}, 0) end
  if frame < LAST then return end
  local handle = assert(io.open(OUT, "w"))
  for _, row in ipairs(rows) do handle:write(row .. "\n") end
  handle:close(); emu.stop(0)
end, emu.eventType.inputPolled)
