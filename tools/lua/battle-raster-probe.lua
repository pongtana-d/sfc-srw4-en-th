-- Trace the raster/arena contract during the first enemy battle from a state.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local ENTRY = tonumber(os.getenv("SRW4_RASTER_ENTRY") or "0x8184EB")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "1500")
local PRESS = os.getenv("SRW4_PRESS") or ""

local presses = {}
for pair in PRESS:gmatch("[^,]+") do
  local f, b = pair:match("^(%d+):(%a+)$")
  if f then presses[tonumber(f)] = b end
end

local function word(address)
  return emu.read(address, emu.memType.snesMemory, false)
    | (emu.read(address + 1, emu.memType.snesMemory, false) << 8)
end

local function pointer(address)
  return word(address) | (emu.read(address + 2, emu.memType.snesMemory, false) << 16)
end

local loaded, armed, frame = false, true, 0
local samples, writes = {}, {}
local function boot()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(
    boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end
emu.addMemoryCallback(
  boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if not loaded then return end
  samples[#samples + 1] = string.format(
    "frame=%d A=%04X CB=%06X 1A=%06X D0=%04X 18=%04X E2A=%04X D1=%02X FD=%02X FE=%04X",
    frame, emu.getRegister(emu.registers.a) & 0xFFFF,
    pointer(0xCB), pointer(0x1A), word(0xD0), word(0x18),
    word(0x0E2A), emu.read(0xD1, emu.memType.snesMemory, false),
    emu.read(0xFD, emu.memType.snesMemory, false), word(0xFE))
end, emu.callbackType.exec, ENTRY, ENTRY, emu.cpuType.snes)

emu.addMemoryCallback(function(address)
  if not loaded then return end
  local page = address & 0xFFFFE0
  writes[page] = (writes[page] or 0) + 1
end, emu.callbackType.write, 0x7F0000, 0x7FFFFF, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if presses[frame] then
    emu.setInput({[presses[frame]] = true}, 0)
  else
    emu.setInput({}, 0)
  end
  if frame <= LAST then return end
  local handle = assert(io.open(OUT, "w"))
  for _, sample in ipairs(samples) do handle:write(sample .. "\n") end
  local pages = {}
  for page in pairs(writes) do pages[#pages + 1] = page end
  table.sort(pages)
  for _, page in ipairs(pages) do
    handle:write(string.format("write=%06X count=%d\n", page, writes[page]))
  end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
