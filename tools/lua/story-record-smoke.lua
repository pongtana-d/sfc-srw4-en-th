-- Draw one relocated story record from a live pre-dialogue state.  This is a
-- test harness only: it changes the emulated source pointer once and never
-- writes the ROM or savestate.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local RECORD = tonumber(assert(os.getenv("SRW4_RECORD"), "SRW4_RECORD is required"), 16)
local frame, loaded, armed, redirected, parser_hits = 0, false, true, false, 0

local function byte(address)
  return emu.read(address, emu.memType.snesMemory, false)
end

local function pointer()
  return byte(0xCB) | (byte(0xCC) << 8) | (byte(0xCD) << 16)
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
  if redirected then parser_hits = parser_hits + 1 end
end, emu.callbackType.exec, 0x8191E3, 0x8191E3, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  emu.setInput({ a = frame == 30 or frame == 150 or frame == 270 }, 0)
  if frame == 1 or frame == 60 or frame == 120 or frame == 180 or frame == 300 then
    local h = assert(io.open(string.format("%s-%04d.png", OUT, frame), "wb"))
    h:write(emu.takeScreenshot())
    h:close()
  end
  if frame < 320 then return end
  local h = assert(io.open(OUT .. ".txt", "w"))
  h:write(string.format("redirected=%s record=%06X pointer=%06X parser_hits=%d\n",
    tostring(redirected), RECORD, pointer(), parser_hits))
  h:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
