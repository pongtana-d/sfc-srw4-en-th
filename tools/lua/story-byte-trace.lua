-- Log every byte the EN story fetch helper reads after a supplied state loads.
--
-- This is runtime evidence for the P2 grammar.  It records the pointer before
-- `$C1:9763` advances it, so a control's operands remain distinguishable from
-- later glyph fetches.  The state file itself is only read.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local PRESS = os.getenv("SRW4_PRESS") or ""
local AUTO_A_EVERY = tonumber(os.getenv("SRW4_AUTO_A_EVERY") or "0")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "600")

local presses = {}
for pair in PRESS:gmatch("[^,]+") do
  local f, button = pair:match("^(%d+):(%a+)$")
  if f then presses[tonumber(f)] = button end
end

local loaded, armed, frame = false, true, 0
local samples = {}
local entries = {}

local function pointer(address)
  return emu.read(address, emu.memType.snesMemory, false)
    | (emu.read(address + 1, emu.memType.snesMemory, false) << 8)
    | (emu.read(address + 2, emu.memType.snesMemory, false) << 16)
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

-- Mesen names this executable mirror `$81:9763`; the story loop reaches it
-- through the `$C1` mirror in the ROM disassembly.
emu.addMemoryCallback(function()
  if not loaded then return end
  local source = pointer(0xCB)
  local byte = emu.read(source, emu.memType.snesMemory, false)
  local message = emu.read(0x0E30, emu.memType.snesMemory, false)
  local block = emu.read(0x0E31, emu.memType.snesMemory, false)
  samples[#samples + 1] = string.format(
    "frame=%d message=%02X block=%02X ptr=%06X byte=%02X",
    frame, message, block, source, byte)
end, emu.callbackType.exec, 0x819763, 0x819763, emu.cpuType.snes)

-- The two return sites are executable `$81` mirrors.  They tell us the exact
-- glyph code handed from the parser to the EN story loop and the code handed
-- to the raster call; callbacks in high-ROM banks are not portable in Mesen.
for _, address in ipairs({0x819776, 0x81977A, 0x819238, 0x81923C}) do
  emu.addMemoryCallback(function()
    if not loaded then return end
    entries[#entries + 1] = string.format(
      "return=%06X frame=%d a=%04X glyph=%04X ptr=%06X",
      address, frame, emu.getRegister(emu.registers.a) & 0xFFFF,
      (emu.read(0x02, emu.memType.snesMemory, false)
        | (emu.read(0x03, emu.memType.snesMemory, false) << 8)), pointer(0xCB))
  end, emu.callbackType.exec, address, address, emu.cpuType.snes)
end

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if presses[frame] then
    emu.setInput({[presses[frame]] = true}, 0)
  elseif AUTO_A_EVERY > 0 and frame % AUTO_A_EVERY == 0 then
    emu.setInput({A = true}, 0)
  else
    emu.setInput({}, 0)
  end
  if frame <= LAST then return end
  local handle = assert(io.open(OUT, "w"))
  for _, sample in ipairs(samples) do handle:write(sample .. "\n") end
  for _, entry in ipairs(entries) do handle:write(entry .. "\n") end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
