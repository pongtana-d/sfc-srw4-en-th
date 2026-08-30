-- Record calls through the three stock sites replaced by the P7 lifecycle hooks.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "2450")
local presses = {}
local press_spec = os.getenv("SRW4_PRESS")
  or "5:up,15:up,25:up,50:a,80:a,110:a"
for pair in press_spec:gmatch("[^,]+") do
  local at, button = pair:match("^(%d+):(%a+)$")
  if at then presses[tonumber(at)] = button end
end
if not os.getenv("SRW4_PRESS") then
  for at = 155, 2450, 45 do presses[at] = "a" end
end

local loaded, armed, frame = false, true, 0
local active_first = nil
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
emu.addMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

local function word(at)
  return emu.read(at, emu.memType.snesMemory, false)
    | (emu.read(at + 1, emu.memType.snesMemory, false) << 8)
end

local function watch(name, address)
  emu.addMemoryCallback(function()
    if not loaded then return end
    local key = string.format(
      "%s f=%d A=%04X X=%04X Y=%04X D0=%04X 0E26=%04X 2A=%04X 2E=%04X",
      name, frame, emu.getRegister(emu.registers.a) & 0xFFFF,
      emu.getRegister(emu.registers.x) & 0xFFFF,
      emu.getRegister(emu.registers.y) & 0xFFFF, word(0xD0), word(0x0E26),
      word(0x2A), word(0x2E))
    hits[key] = (hits[key] or 0) + 1
  end, emu.callbackType.exec, address, address, emu.cpuType.snes)
end

watch("open-82", 0x82843B)
watch("open-C2", 0xC2843B)
watch("selection-83", 0x8389F5)
watch("selection-C3", 0xC389F5)
watch("selection-03", 0x0389F5)
watch("selection-43", 0x4389F5)
watch("activation-82", 0x8284BB)
watch("activation-C2", 0xC284BB)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if active_first == nil then
    active_first = emu.read(0x7ECED6, emu.memType.snesMemory, false)
      | (emu.read(0x7ECED7, emu.memType.snesMemory, false) << 8)
  end
  if presses[frame] then emu.setInput({ [presses[frame]] = true }, 0) end
  if frame < LAST then return end
  local log = assert(io.open(OUT, "w"))
  local active_last = emu.read(0x7ECED6, emu.memType.snesMemory, false)
    | (emu.read(0x7ECED7, emu.memType.snesMemory, false) << 8)
  log:write(string.format("active-first=%04X active-last=%04X\n", active_first, active_last))
  local keys = {}
  for key in pairs(hits) do keys[#keys + 1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do log:write(key .. " " .. hits[key] .. "\n") end
  log:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
