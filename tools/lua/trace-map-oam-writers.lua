-- Capture the routines that prepare the OAM buffer while a map state runs.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local loaded, armed, frame = false, true, 0
local hits = {}

local function boot()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(boot, emu.callbackType.exec,
    0x808000, 0x80FFFF, emu.cpuType.snes)
  local f = assert(io.open(STATE, "rb"))
  emu.loadSavestate(f:read("a"))
  f:close()
  loaded = true
end
emu.addMemoryCallback(boot, emu.callbackType.exec,
  0x808000, 0x80FFFF, emu.cpuType.snes)

local function record(address)
  if not loaded then return end
  local pc = emu.getRegister(emu.registers.pc) & 0xFFFFFF
  local key = string.format("%06X %04X", pc, address & 0xFFFF)
  hits[key] = (hits[key] or 0) + 1
end
emu.addMemoryCallback(record, emu.callbackType.write,
  0x7E0500, 0x7E071F, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  emu.setInput(frame == 60 and {right = true} or frame == 120 and {left = true} or {}, 0)
  if frame < 180 then return end
  local keys = {}
  for key in pairs(hits) do keys[#keys + 1] = key end
  table.sort(keys)
  local f = assert(io.open(OUT, "w"))
  for _, key in ipairs(keys) do f:write(string.format("%s %d\n", key, hits[key])) end
  f:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
