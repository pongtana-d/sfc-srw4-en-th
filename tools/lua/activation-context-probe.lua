-- Record the live context at the P7 activation replacement ($82:84BB).
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "120")
local PRESS = os.getenv("SRW4_PRESS") or ""
local presses = {}
for pair in PRESS:gmatch("[^,]+") do
  local at, button = pair:match("^(%d+):(%a+)$")
  if at then presses[tonumber(at)] = button end
end

local loaded, armed, frame = false, true, 0
local hits = {}
local function boot()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(STATE, "rb")); emu.loadSavestate(handle:read("a")); handle:close()
  loaded = true
end
emu.addMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

local function ptr(at)
  return emu.read(at, emu.memType.snesMemory, false)
    | (emu.read(at + 1, emu.memType.snesMemory, false) << 8)
    | (emu.read(at + 2, emu.memType.snesMemory, false) << 16)
end
emu.addMemoryCallback(function()
  if not loaded then return end
  local key = string.format(
    "f=%d A=%04X X=%04X Y=%04X 1A=%06X CB=%06X D0=%04X 0E26=%04X 2A=%04X 2E=%04X",
    frame, emu.getRegister(emu.registers.a) & 0xFFFF, emu.getRegister(emu.registers.x) & 0xFFFF,
    emu.getRegister(emu.registers.y) & 0xFFFF, ptr(0x1A), ptr(0xCB),
    emu.read(0xD0, emu.memType.snesMemory, false) | (emu.read(0xD1, emu.memType.snesMemory, false) << 8),
    emu.read(0x0E26, emu.memType.snesMemory, false) | (emu.read(0x0E27, emu.memType.snesMemory, false) << 8),
    emu.read(0x2A, emu.memType.snesMemory, false) | (emu.read(0x2B, emu.memType.snesMemory, false) << 8),
    emu.read(0x2E, emu.memType.snesMemory, false) | (emu.read(0x2F, emu.memType.snesMemory, false) << 8))
  hits[key] = (hits[key] or 0) + 1
end, emu.callbackType.exec, 0x8284BB, 0x8284BB, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if presses[frame] then emu.setInput({ [presses[frame]] = true }, 0) end
  if frame < LAST then return end
  local log = assert(io.open(OUT, "w")); local keys = {}
  for key in pairs(hits) do keys[#keys + 1] = key end
  table.sort(keys); for _, key in ipairs(keys) do log:write(key .. " " .. hits[key] .. "\n") end
  log:close(); emu.stop(0)
end, emu.eventType.inputPolled)
