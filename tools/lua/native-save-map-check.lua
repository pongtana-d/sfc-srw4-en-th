-- Cold-boot the ROM and enter DATA1 through the native SRAM, then photograph
-- the first map.  Timing follows docs/08-verification.md's measured route.
local OUT = assert(os.getenv("SRW4_SHOT"), "SRW4_SHOT is required")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "3100")
local SAVE = os.getenv("SRW4_SAVE")
local TRACE = os.getenv("SRW4_TRACE")
local EXTRA_PRESS = os.getenv("SRW4_EXTRA_PRESS") or ""
local frame = 0
local hits = {}
local extra_presses = {}
for pair in EXTRA_PRESS:gmatch("[^,]+") do
  local at, button = pair:match("^(%d+):(%a+)$")
  if at then extra_presses[tonumber(at)] = button end
end

if TRACE then
  local function ptr(at)
    return emu.read(at, emu.memType.snesMemory, false)
      | (emu.read(at + 1, emu.memType.snesMemory, false) << 8)
      | (emu.read(at + 2, emu.memType.snesMemory, false) << 16)
  end
  emu.addMemoryCallback(function()
    local key = string.format(
      "f=%d A=%04X X=%04X Y=%04X 1A=%06X CB=%06X D0=%04X 0E26=%04X 2A=%04X 2E=%04X active=%04X",
      frame, emu.getRegister(emu.registers.a) & 0xFFFF, emu.getRegister(emu.registers.x) & 0xFFFF,
      emu.getRegister(emu.registers.y) & 0xFFFF, ptr(0x1A), ptr(0xCB),
      emu.read(0xD0, emu.memType.snesMemory, false) | (emu.read(0xD1, emu.memType.snesMemory, false) << 8),
      emu.read(0x0E26, emu.memType.snesMemory, false) | (emu.read(0x0E27, emu.memType.snesMemory, false) << 8),
      emu.read(0x2A, emu.memType.snesMemory, false) | (emu.read(0x2B, emu.memType.snesMemory, false) << 8),
      emu.read(0x2E, emu.memType.snesMemory, false) | (emu.read(0x2F, emu.memType.snesMemory, false) << 8),
      emu.read(0x7ECED6, emu.memType.snesMemory, false) | (emu.read(0x7ECED7, emu.memType.snesMemory, false) << 8))
    hits[key] = (hits[key] or 0) + 1
  end, emu.callbackType.exec, 0xFD0900, 0xFD0900, emu.cpuType.snes)
end

emu.addEventCallback(function()
  frame = frame + 1
  local input = {}
  if frame > 60 and frame <= 1300 and frame % 30 == 0 then input.start = true end
  if frame == 1350 or frame == 1900 then input.a = true end
  if frame >= 1720 and frame < 1880 and (frame - 1720) % 20 == 0 then input.down = true end
  if frame >= 1940 and frame <= 3000 and frame % 20 == 0 then input.a = true end
  if extra_presses[frame] then input[extra_presses[frame]] = true end
  emu.setInput(input, 0)
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  if frame < LAST then return end
  if SAVE then
    local state = assert(io.open(SAVE, "wb")); state:write(emu.createSavestate()); state:close()
  end
  if TRACE then
    local log = assert(io.open(TRACE, "w")); local keys = {}
    for key in pairs(hits) do keys[#keys + 1] = key end
    table.sort(keys); for _, key in ipairs(keys) do log:write(key .. " " .. hits[key] .. "\n") end
    local function word(at)
      return emu.read(at, emu.memType.snesMemory, false)
        | (emu.read(at + 1, emu.memType.snesMemory, false) << 8)
    end
    local f5ec = word(0x7ECEE6) | (emu.read(0x7ECEE8, emu.memType.snesMemory, false) << 16)
    log:write(string.format("WRAM hits=%04X A=%04X X=%04X Y=%04X F5EC=%06X\n",
      word(0x7ECEEA), word(0x7ECEE0), word(0x7ECEE2), word(0x7ECEE4), f5ec))
    log:close()
  end
  local image = assert(io.open(OUT, "wb")); image:write(emu.takeScreenshot()); image:close()
  emu.stop(0)
end, emu.eventType.endFrame)
