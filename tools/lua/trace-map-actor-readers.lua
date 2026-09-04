-- Identify CPU routines that read the live map actor tables.
-- Usage: SRW4_STATE=... SRW4_OUT=... Mesen --lua this-file ROM
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local loaded, armed, frames = false, true, 0
local hits = {}
local presses = {}
for pair in (os.getenv("SRW4_PRESS") or "60:right,120:left,180:right,240:left"):gmatch("[^,]+") do
  local at, button = pair:match("^(%d+):(%a+)$")
  if at then presses[tonumber(at)] = button end
end

local function load_state()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(load_state, emu.callbackType.exec,
    0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end
emu.addMemoryCallback(load_state, emu.callbackType.exec,
  0x808000, 0x80FFFF, emu.cpuType.snes)

local function record(address)
  if not loaded then return end
  local pc = emu.getRegister(emu.registers.pc) & 0xFFFFFF
  local key = string.format("%06X %04X", pc, address & 0xFFFF)
  hits[key] = (hits[key] or 0) + 1
end

-- Pilot and unit identity arrays for all 32 map slots.
emu.addMemoryCallback(record, emu.callbackType.read,
  0x7E17E5, 0x7E1804, emu.cpuType.snes)
emu.addMemoryCallback(record, emu.callbackType.read,
  0x7E1865, 0x7E1884, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frames = frames + 1
  emu.setInput(presses[frames] and {[presses[frames]] = true} or {}, 0)
  if frames < 360 then return end
  local rows = {}
  for key, count in pairs(hits) do rows[#rows + 1] = {key = key, count = count} end
  table.sort(rows, function(a, b) return a.key < b.key end)
  local handle = assert(io.open(OUT, "w"))
  for _, row in ipairs(rows) do handle:write(string.format("%s %d\n", row.key, row.count)) end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
