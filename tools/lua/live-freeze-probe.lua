-- Attach this to a running EN+Thai dialogue session.  Read-only: it never
-- changes memory, input, savestates, or emulation speed.
local frames, glyphs, last_pointer = 0, 0, 0

local function byte(address)
  return emu.read(address, emu.memType.snesMemory, false)
end

local function pointer()
  return byte(0xCB) | (byte(0xCC) << 8) | (byte(0xCD) << 16)
end

emu.addMemoryCallback(function()
  glyphs = glyphs + 1
  last_pointer = pointer()
end, emu.callbackType.exec, 0x819238, 0x819238, emu.cpuType.snes)

emu.addEventCallback(function()
  frames = frames + 1
  if frames % 60 ~= 0 then return end
  emu.log(string.format(
    "thai-freeze frame=%d pc=%06X sp=%04X a=%04X ptr=%06X glyphs=%d page=%04X",
    frames,
    emu.getRegister(emu.registers.pc) & 0xFFFFFF,
    emu.getRegister(emu.registers.sp) & 0xFFFF,
    emu.getRegister(emu.registers.a) & 0xFFFF,
    last_pointer,
    glyphs,
    byte(0x7EC000) | (byte(0x7EC001) << 8)))
  glyphs = 0
end, emu.eventType.endFrame)
