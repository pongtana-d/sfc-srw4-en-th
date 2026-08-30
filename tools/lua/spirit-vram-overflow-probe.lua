-- Trace the Spirit selector's dynamic-tile allocator and DMA contract.
-- The supplied state is never saved; input only closes and reopens the route.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "300")
local PRESS = os.getenv("SRW4_PRESS") or "20:b,80:a,150:down,210:a"

local presses = {}
for pair in PRESS:gmatch("[^,]+") do
  local at, button = pair:match("^(%d+):(%a+)$")
  if at then presses[tonumber(at)] = button end
end

local frame, loaded, armed = 0, false, true
local rows = {}
local arena = {}
local dmas = {}

local function byte(address)
  return emu.read(address, emu.memType.snesMemory, false)
end

local function word(address)
  return byte(address) | (byte(address + 1) << 8)
end

local function pointer(address)
  return word(address) | (byte(address + 2) << 16)
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
emu.addMemoryCallback(boot, emu.callbackType.exec,
  0x808000, 0x80FFFF, emu.cpuType.snes)

local function raster(label)
  if not loaded then return end
  rows[#rows + 1] = string.format(
    "%s frame=%d pc=%06X A=%04X ptr=%06X D0=%04X D2=%04X col=%04X",
    label, frame, emu.getRegister(emu.registers.pc) & 0xFFFFFF,
    emu.getRegister(emu.registers.a) & 0xFFFF, pointer(0x1A),
    word(0xD0), word(0xD2), word(0x18))
end

for _, site in ipairs({
  { 0x8184E4, "shared" }, { 0xC184E4, "shared" },
  { 0x2C0200, "spirit" }, { 0x6C0200, "spirit" },
  { 0xAC0200, "spirit" }, { 0xEC0200, "spirit" },
  { 0x30E045, "en-vwf" }, { 0x70E045, "en-vwf" },
  { 0xB0E045, "en-vwf" }, { 0xF0E045, "en-vwf" },
}) do
  emu.addMemoryCallback(function() raster(site[2]) end,
    emu.callbackType.exec, site[1], site[1], emu.cpuType.snes)
end

emu.addMemoryCallback(function(address)
  if not loaded then return end
  local pc = emu.getRegister(emu.registers.pc) & 0xFFFFFF
  local key = string.format("frame=%d pc=%06X", frame, pc)
  local item = arena[key]
  if not item then
    item = { first = address, last = address, count = 0 }
    arena[key] = item
  end
  item.first = math.min(item.first, address)
  item.last = math.max(item.last, address)
  item.count = item.count + 1
end, emu.callbackType.write, 0x7F8000, 0x7FFFFF, emu.cpuType.snes)

emu.addMemoryCallback(function(_, value)
  if not loaded then return end
  for channel = 0, 7 do
    if (value & (1 << channel)) ~= 0 then
      local base = 0x4300 + channel * 0x10
      local source = byte(base + 2) | (byte(base + 3) << 8)
        | (byte(base + 4) << 16)
      local size = word(base + 5)
      if size == 0 then size = 0x10000 end
      dmas[#dmas + 1] = string.format(
        "dma frame=%d ch=%d dest=%02X source=%06X size=%d D0=%04X D2=%04X",
        frame, channel, byte(base + 1), source, size, word(0xD0), word(0xD2))
    end
  end
end, emu.callbackType.write, 0x00420B, 0x00420B, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  local button = presses[frame]
  emu.setInput(button and { [button] = true } or {}, 0)
  if frame < LAST then return end

  local handle = assert(io.open(OUT, "w"))
  for _, row in ipairs(rows) do handle:write(row .. "\n") end
  local keys = {}
  for key in pairs(arena) do keys[#keys + 1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do
    local item = arena[key]
    handle:write(string.format(
      "arena %s first=%06X last=%06X count=%d\n",
      key, item.first, item.last, item.count))
  end
  for _, row in ipairs(dmas) do handle:write(row .. "\n") end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
