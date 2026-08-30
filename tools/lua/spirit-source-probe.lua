-- Locate the live EN Spirit-help strings after a genuine selector redraw.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local frame, loaded, armed = 0, false, true
local seen, rows = {}, {}

local presses = { [30] = "a", [100] = "down", [160] = "a" }

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

local function record_source()
  if not loaded or frame < 150 then return end
  local pointer = emu.read(0x1A, emu.memType.snesMemory, false)
    | (emu.read(0x1B, emu.memType.snesMemory, false) << 8)
    | (emu.read(0x1C, emu.memType.snesMemory, false) << 16)
  if not seen[pointer] then
    seen[pointer] = true
    rows[#rows + 1] = string.format(
      "%04d %06X A=%04X", frame, pointer,
      emu.getRegister(emu.registers.a) & 0xFFFF)
  end
end
for _, address in ipairs({
  0x0184E4, 0x4184E4, 0x8184E4, 0xC184E4,
  0x30E045, 0x70E045, 0xB0E045, 0xF0E045,
}) do
  emu.addMemoryCallback(record_source, emu.callbackType.exec,
    address, address, emu.cpuType.snes)
end

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  local button = presses[frame]
  emu.setInput(button and { [button] = true } or {}, 0)
  if frame >= 150 then
    local ordinary = emu.read(0x1A, emu.memType.snesMemory, false)
      | (emu.read(0x1B, emu.memType.snesMemory, false) << 8)
      | (emu.read(0x1C, emu.memType.snesMemory, false) << 16)
    local battle = emu.read(0xCB, emu.memType.snesMemory, false)
      | (emu.read(0xCC, emu.memType.snesMemory, false) << 8)
      | (emu.read(0xCD, emu.memType.snesMemory, false) << 16)
    local key = string.format("event %06X %06X", ordinary, battle)
    if not seen[key] then
      seen[key] = true
      rows[#rows + 1] = string.format(
        "%04d ordinary=%06X battle=%06X", frame, ordinary, battle)
    end
  end
  if frame < 300 then return end
  local handle = assert(io.open(OUT, "w"))
  for _, row in ipairs(rows) do handle:write(row .. "\n") end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
