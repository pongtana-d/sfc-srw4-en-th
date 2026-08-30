-- Record the stock command writer inputs at the only two reflow boundaries.
-- The state is read-only; the output is a compact census keyed by source
-- pointer, decoded glyph code, tilemap cursor and arena base.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local OPEN_AT = tonumber(os.getenv("SRW4_OPEN_AT") or "180")
local END_AT = tonumber(os.getenv("SRW4_END_AT") or "300")

local loaded, armed, frame = false, true, 0
local samples = {}

local function word(address)
  return emu.read(address, emu.memType.snesMemory, false)
    | (emu.read(address + 1, emu.memType.snesMemory, false) << 8)
end

local function pointer(address)
  return word(address) | (emu.read(address + 2, emu.memType.snesMemory, false) << 16)
end

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

local function sample(where)
  if not loaded then return end
  local bank = emu.read(0x1C, emu.memType.snesMemory, false)
  local source = pointer(0x1A)
  if bank ~= 0xFA and not (bank == 0xD2 and word(0x1A) >= 0x8614 and word(0x1A) < 0x865B) then return end
  local key = string.format(
    "%s A=%04X src=%06X cell=%04X tile=%04X base=%04X",
    where,
    emu.getRegister(emu.registers.a) & 0xFFFF,
    source, word(0x18), word(0xD0), word(0x0E18)
  )
  samples[key] = (samples[key] or 0) + 1
end
-- In a naming-enabled P7 build `$C1:8456` jumps to the naming width hook.
-- Sample both locations; only the one actually executed contributes.
emu.addMemoryCallback(function() sample("parser") end, emu.callbackType.exec, 0x818456, 0x818456, emu.cpuType.snes)
emu.addMemoryCallback(function() sample("width-hook") end, emu.callbackType.exec, 0xFD0200, 0xFD0200, emu.cpuType.snes)
emu.addMemoryCallback(function() sample("command-width") end, emu.callbackType.exec, 0xFD0700, 0xFD0700, emu.cpuType.snes)
emu.addMemoryCallback(function() sample("native-route-2") end, emu.callbackType.exec, 0xFD0600, 0xFD0600, emu.cpuType.snes)
emu.addMemoryCallback(function() sample("menu-parser-2") end, emu.callbackType.exec, 0xFD0400, 0xFD0400, emu.cpuType.snes)
emu.addMemoryCallback(function() sample("shared-raster") end, emu.callbackType.exec, 0xFD0900, 0xFD0900, emu.cpuType.snes)
emu.addMemoryCallback(function() sample("raster") end, emu.callbackType.exec, 0x8184E4, 0x8184E4, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  local input = {}
  if frame == 30 then input.b = true end
  if frame == OPEN_AT then input.a = true end
  if next(input) then emu.setInput(input, 0) end
  if frame ~= END_AT then return end
  local handle = assert(io.open(OUT, "w"))
  handle:write(string.format("debug cursor=%04X tile=%04X\n", word(0x7ECED0), word(0x7ECED2)))
  local count = word(0x7ECEE4)
  handle:write(string.format("raster-count=%d\n", count // 2))
  for i = 0, math.min(count, 16) - 2, 2 do
    handle:write(string.format("raster-d0[%d]=%04X\n", i // 2, word(0x7ECEE8 + i)))
  end
  local keys = {}; for key in pairs(samples) do keys[#keys + 1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do handle:write(string.format("%s count=%d\n", key, samples[key])) end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
