-- Trace the EN dialogue router while replaying a supplied savestate.
local state = assert(os.getenv("SRW4_STATE"), "SRW4_STATE required")
local out = assert(os.getenv("SRW4_OUT"), "SRW4_OUT required")
local frame, loaded = 0, false
local lines = {}

local function byte(address)
  return emu.read(address, emu.memType.snesMemory, false)
end

local function note(name)
  if #lines >= 200 then return end
  local pointer = byte(0xCB) | (byte(0xCC) << 8) | (byte(0xCD) << 16)
  local page = byte(0x7EC000) | (byte(0x7EC001) << 8)
  local glyph = byte(0x02) | (byte(0x03) << 8)
  local tile = byte(0xD0) | (byte(0xD1) << 8)
  local base = byte(0x0E18) | (byte(0x0E19) << 8)
  local sample = ""
  if name == "tail" then
    local arena = 0x7F8000 + tile * 32
    sample = string.format(" arena=%02X%02X/%02X%02X font=%02X", byte(arena), byte(arena + 2), byte(arena + 12), byte(arena + 0x2C), byte(0xFF42D6))
  end
  if name == "source" then
    sample = string.format(" a=%04X x=%04X y=%04X",
      emu.getRegister(emu.registers.a) & 0xFFFF,
      emu.getRegister(emu.registers.x) & 0xFFFF,
      emu.getRegister(emu.registers.y) & 0xFFFF)
  end
  if name == "raster" then
    sample = string.format(" shift=%02X", byte(0x7FFFF0))
  end
  lines[#lines + 1] = string.format("%s frame=%d ptr=%06X glyph=%04X page=%04X d0=%04X base=%04X%s", name, frame, pointer, glyph, page, tile, base, sample)
end

emu.addMemoryCallback(function()
  if loaded then return end
  local handle = assert(io.open(state, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

for name, address in pairs({source = 0xFF90D5, tail = 0xF0E12D}) do
  emu.addMemoryCallback(function() if loaded then note(name) end end,
    emu.callbackType.exec, address, address, emu.cpuType.snes)
end

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  emu.setInput({a = frame % 60 == 30}, 0)
  if frame > 300 then
    local handle = assert(io.open(out, "w"))
    handle:write(table.concat(lines, "\n"), "\n")
    handle:close()
    emu.stop(0)
  end
end, emu.eventType.inputPolled)
