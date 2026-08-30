-- Reproduce native setup up to the first protagonist page, then test one key.
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local KEY = os.getenv("SRW4_KEY") or "right"
local COUNT = tonumber(os.getenv("SRW4_COUNT") or "1")
local CONFIRM = os.getenv("SRW4_CONFIRM")
local CONFIRM2 = os.getenv("SRW4_CONFIRM2")
local TRACE = os.getenv("SRW4_TRACE")
local SKIP = os.getenv("SRW4_SKIP") == "1"
local SKIP_UNTIL = tonumber(os.getenv("SRW4_SKIP_UNTIL") or "999999")
local NEXT_AT = tonumber(os.getenv("SRW4_NEXT_AT") or "-1")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "2500")
local frame = 0
local hits = {}
local function ptr()
  return emu.read(0xCB, emu.memType.snesMemory, false)
    | (emu.read(0xCC, emu.memType.snesMemory, false) << 8)
    | (emu.read(0xCD, emu.memType.snesMemory, false) << 16)
end
if TRACE then
  emu.addMemoryCallback(function()
    hits[#hits + 1] = string.format("f=%d ptr=%06X glyph=%04X", frame, ptr(),
      emu.read(0x02, emu.memType.snesMemory, false)
        | (emu.read(0x03, emu.memType.snesMemory, false) << 8))
  end, emu.callbackType.exec, 0x819238, 0x819238, emu.cpuType.snes)
end
emu.addEventCallback(function()
  frame = frame + 1
  local input = {}
  if frame > 60 and frame <= 1300 and frame % 30 == 0 then input.start = true end
  if frame == 1350 or frame == 1900 then input.a = true end
  if frame >= 1720 and frame < 1880 and (frame - 1720) % 20 == 0 then input.down = true end
  if frame == 1940 then input.start = true end
  if frame >= 2100 and frame < 2100 + COUNT * 20 and (frame - 2100) % 20 == 0 then input[KEY] = true end
  if CONFIRM and frame == 2300 then input[CONFIRM] = true end
  if CONFIRM2 and frame == 2400 then input[CONFIRM2] = true end
  if SKIP and frame > 2500 and frame <= SKIP_UNTIL and frame % 45 == 0 then input.a = true end
  if frame == NEXT_AT then input.a = true end
  emu.setInput(input, 0)
  if frame < LAST then return end
  if TRACE then
    local trace = assert(io.open(TRACE, "w"))
    for _, row in ipairs(hits) do trace:write(row, "\n") end
    trace:write(string.format("final ptr=%06X glyph=%04X state=%04X\n", ptr(),
      emu.read(0x02, emu.memType.snesMemory, false)
        | (emu.read(0x03, emu.memType.snesMemory, false) << 8),
      emu.read(0x0E2A, emu.memType.snesMemory, false)
        | (emu.read(0x0E2B, emu.memType.snesMemory, false) << 8)))
    trace:close()
  end
  local image = assert(io.open(OUT, "wb")); image:write(emu.takeScreenshot()); image:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
