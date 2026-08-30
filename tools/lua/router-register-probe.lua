-- Read-only probe for the EN private-font loader.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local SITE = tonumber(os.getenv("SRW4_SITE") or "FF28F5", 16)
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "300")

local loaded, armed, frame = false, true, 0
local rows = {}

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

emu.addMemoryCallback(function()
  if not loaded then return end
  rows[#rows + 1] = string.format("frame=%d A=%04X X=%04X", frame,
    emu.getRegister(emu.registers.a) & 0xFFFF,
    emu.getRegister(emu.registers.x) & 0xFFFF)
end, emu.callbackType.exec, SITE, SITE, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if frame % 30 == 0 then emu.setInput({ A = true }, 0) else emu.setInput({}, 0) end
  if frame <= LAST then return end
  local handle = assert(io.open(OUT, "w"))
  for _, row in ipairs(rows) do handle:write(row, "\n") end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
