-- Find the hot instruction loop in a frozen state without depending on the
-- Mesen register enum.  Only execution addresses and counters are observed.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local loaded, armed, frames, total = false, true, 0, 0
local hits = {}

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

emu.addMemoryCallback(function(address)
  if not loaded then return end
  total = total + 1
  hits[address] = (hits[address] or 0) + 1
end, emu.callbackType.exec, 0x000000, 0xFFFFFF, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frames = frames + 1
  if frames < 2 then return end
  local ranked = {}
  for address, count in pairs(hits) do
    ranked[#ranked + 1] = { address = address, count = count }
  end
  table.sort(ranked, function(a, b)
    if a.count == b.count then return a.address < b.address end
    return a.count > b.count
  end)
  local h = assert(io.open(OUT, "w"))
  h:write(string.format("instructions=%d unique=%d\n", total, #ranked))
  for i = 1, math.min(40, #ranked) do
    h:write(string.format("%06X %d\n", ranked[i].address, ranked[i].count))
  end
  h:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
