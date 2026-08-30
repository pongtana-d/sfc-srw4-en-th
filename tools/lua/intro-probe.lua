local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "900")
local armed, loaded, frame = false, false, 0
local pending = nil
local hits = {}

local function boot()
  if not armed then return end
  emu.removeMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  armed = false
  local h = assert(io.open(pending, "rb")); emu.loadSavestate(h:read("a")); h:close()
  pending = nil; loaded = true
end

emu.addMemoryCallback(function()
  if not loaded then return end
  local ptr = emu.read(0x1A, emu.memType.snesMemory, false)
    | (emu.read(0x1B, emu.memType.snesMemory, false) << 8)
    | (emu.read(0x1C, emu.memType.snesMemory, false) << 16)
  hits[ptr] = (hits[ptr] or 0) + 1
end, emu.callbackType.exec, 0x818F32, 0x818F32, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then
    pending = STATE; armed = true
    emu.addMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
    return
  end
  frame = frame + 1
  for f = 60, LAST - 60, 60 do if frame == f then emu.setInput({a=true}, 0) end end
  if frame < LAST then return end
  local h = assert(io.open(OUT, "w")); local keys = {}
  for ptr in pairs(hits) do keys[#keys + 1] = ptr end; table.sort(keys)
  for _, ptr in ipairs(keys) do h:write(string.format("%06X %d\n", ptr, hits[ptr])) end
  h:close(); emu.stop(0)
end, emu.eventType.inputPolled)
