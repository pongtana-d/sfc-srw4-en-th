-- Read-only freeze probe for an existing Mesen savestate.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local frame, loaded, parser_hits = 0, false, 0
local samples = {}

local function byte(address)
  return emu.read(address, emu.memType.snesMemory, false)
end

local function pointer()
  return byte(0xCB) | (byte(0xCC) << 8) | (byte(0xCD) << 16)
end

emu.addMemoryCallback(function()
  if loaded then return end
  local h = assert(io.open(STATE, "rb"))
  emu.loadSavestate(h:read("a"))
  h:close()
  loaded = true
end, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if loaded then parser_hits = parser_hits + 1 end
end, emu.callbackType.exec, 0x819238, 0x819238, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if frame % 30 == 0 then
    local source = pointer()
    samples[#samples + 1] = string.format(
      "frame=%d pc=%06X sp=%04X a=%04X ptr=%06X byte=%02X page=%04X d0=%04X hits=%d",
      frame,
      emu.getRegister(emu.registers.pc) & 0xFFFFFF,
      emu.getRegister(emu.registers.sp) & 0xFFFF,
      emu.getRegister(emu.registers.a) & 0xFFFF,
      source,
      byte(source),
      byte(0x7EC000) | (byte(0x7EC001) << 8),
      byte(0xD0) | (byte(0xD1) << 8),
      parser_hits)
  end
  if frame < 240 then return end
  local h = assert(io.open(OUT, "w"))
  h:write(table.concat(samples, "\n"), "\n")
  h:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
