-- Capture the title screen's live OBJ layout and palettes for deterministic
-- logo reconstruction.  This is an analysis tool; it never writes emulator
-- memory.
local PREFIX = assert(os.getenv("SRW4_PREFIX"), "SRW4_PREFIX is required")
local frame = 0

local function dump(path, start, length, mem_type)
  local out = assert(io.open(path, "wb"))
  local bytes = {}
  for offset = 0, length - 1 do
    bytes[#bytes + 1] = string.char(emu.read(start + offset, mem_type))
  end
  out:write(table.concat(bytes))
  out:close()
end

emu.addEventCallback(function()
  frame = frame + 1
  local buttons = {}
  if frame >= 720 and frame <= 725 then
    buttons.start = true
  end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  if frame == 900 then
    local shot = assert(io.open(PREFIX .. ".png", "wb"))
    shot:write(emu.takeScreenshot())
    shot:close()
    dump(PREFIX .. ".oam.bin", 0, 544, emu.memType.snesSpriteRam)
    dump(PREFIX .. ".vram.bin", 0, 65536, emu.memType.snesVideoRam)
    dump(PREFIX .. ".cgram.bin", 0, 512, emu.memType.snesCgRam)
    emu.stop(0)
  end
end, emu.eventType.endFrame)
