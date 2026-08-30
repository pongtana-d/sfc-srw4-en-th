-- Trace the custom Thai renderer and the EN VWF tail for one relocated record.
-- Test harness only: redirects the emulated story pointer once and writes a log.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local RECORD = tonumber(assert(os.getenv("SRW4_RECORD"), "SRW4_RECORD is required"), 16)
local frame, loaded, armed, redirected = 0, false, true, false
local lines, draws = {}, 0

local function byte(address)
  return emu.read(address, emu.memType.snesMemory, false)
end

local function word(address)
  return byte(address) | (byte(address + 1) << 8)
end

local function pointer()
  return byte(0xCB) | (byte(0xCC) << 8) | (byte(0xCD) << 16)
end

local function note(stage)
  if #lines >= 500 then return end
  lines[#lines + 1] = string.format(
    "%s f=%03d ptr=%06X glyph=%04X page=%04X cursor=%04X d0=%04X d2=%04X " ..
    "sig=%04X pen=%02X expect=%04X cell=%04X shift=%04X",
    stage, frame, pointer(), word(0x02), word(0x7EFFDC), word(0x0E2A),
    word(0xD0), word(0xD2), word(0x7EFFC0), byte(0x7EFFC2),
    word(0x7EFFC4), word(0x7EFFC8), word(0x7FFFF0))
end

local function load_state()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(load_state, emu.callbackType.exec,
    0x808000, 0x80FFFF, emu.cpuType.snes)
  local h = assert(io.open(STATE, "rb"))
  emu.loadSavestate(h:read("a"))
  h:close()
  loaded = true
end
emu.addMemoryCallback(load_state, emu.callbackType.exec,
  0x808000, 0x80FFFF, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if not loaded then return end
  local source = pointer()
  if not redirected and source >= 0xEB8000 and source <= 0xEBFFFF then
    emu.write(0xCB, RECORD & 0xFF, emu.memType.snesMemory)
    emu.write(0xCC, (RECORD >> 8) & 0xFF, emu.memType.snesMemory)
    emu.write(0xCD, (RECORD >> 16) & 0xFF, emu.memType.snesMemory)
    redirected = true
  end
end, emu.callbackType.exec, 0x8191E3, 0x8191E3, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if loaded and redirected then
    draws = draws + 1
    note("renderer-in")
  end
end, emu.callbackType.exec, 0xFFA000, 0xFFA000, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if loaded and redirected then note("dispatch") end
end, emu.callbackType.exec, 0xFF8800, 0xFF8800, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if loaded and redirected then note("stock-draw") end
end, emu.callbackType.exec, 0xF0E049, 0xF0E049, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if loaded and redirected then note("renderer-out") end
end, emu.callbackType.exec, 0xF0E12D, 0xF0E12D, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if loaded and redirected then note("loop") end
end, emu.callbackType.exec, 0x8191E3, 0x8191E3, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  emu.setInput({a = frame == 30}, 0)
  if frame < 170 then return end
  local h = assert(io.open(OUT, "w"))
  h:write(string.format("redirected=%s draws=%d\n", tostring(redirected), draws))
  h:write(table.concat(lines, "\n"), "\n")
  h:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
