-- Read-only write watch for the proposed EN dialogue decoder buffer.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "600")
local loaded, armed, frame = false, true, 0
local writes = {}

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

emu.addMemoryCallback(function(address)
  if loaded then writes[address] = (writes[address] or 0) + 1 end
end, emu.callbackType.write, 0x7EFA36, 0x7EFE35, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if frame % 30 == 0 then emu.setInput({ A = true }, 0) else emu.setInput({}, 0) end
  if frame <= LAST then return end
  local keys = {}; for address in pairs(writes) do keys[#keys + 1] = address end
  table.sort(keys)
  local handle = assert(io.open(OUT, "w"))
  for _, address in ipairs(keys) do handle:write(string.format("%06X %d\n", address, writes[address])) end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
