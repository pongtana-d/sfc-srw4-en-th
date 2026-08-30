-- Record the stock command writer's cursor contract at its measured stores.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local OPEN_AT = tonumber(os.getenv("SRW4_OPEN_AT") or "180")
local END_AT = tonumber(os.getenv("SRW4_END_AT") or "300")

local loaded, armed, frame = false, true, 0
local hits = {}
local loop_exec = {}
local writer_state = {}

local function word(address)
  return emu.read(address, emu.memType.snesMemory, false)
    | (emu.read(address + 1, emu.memType.snesMemory, false) << 8)
end

local function pointer(address)
  return word(address) | (emu.read(address + 2, emu.memType.snesMemory, false) << 16)
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

local watch_labels = {
  [0x818402] = "parser",
  [0x81840F] = "parser-alt",
  [0x8184A8] = "top",
  [0x8184BD] = "pair",
  [0x8184D4] = "extra",
  [0x8184E4] = "raster-call",
  [0x8184E8] = "raster-return",
}

emu.addMemoryCallback(function(address)
  if not loaded then return end
  local key = string.format("loop=%06X", address)
  loop_exec[key] = (loop_exec[key] or 0) + 1
  local label = watch_labels[address]
  if label then
    local hit_key = string.format(
      "%s frame=%d 1A=%06X 18=%04X D0=%04X",
      label, frame, pointer(0x1A), word(0x18), word(0xD0)
    )
    hits[hit_key] = (hits[hit_key] or 0) + 1
  end
  if (address & 0xFFFF) == 0x84BD or (address & 0xFFFF) == 0x84D4 then
    local writer_key = string.format("writer=%06X 1A=%06X 18=%04X D0=%04X",
      address, pointer(0x1A), word(0x18), word(0xD0))
    writer_state[writer_key] = (writer_state[writer_key] or 0) + 1
  end
end, emu.callbackType.exec, 0x818400, 0x8184FF, emu.cpuType.snes)

local function sample_adapter(label, address)
  emu.addMemoryCallback(function()
    if not loaded then return end
    local key = string.format(
      "%s frame=%d 1A=%06X 18=%04X D0=%04X CODE=%04X PEN=%04X LAST=%04X FRAME=%04X",
      label, frame, pointer(0x1A), word(0x18), word(0xD0),
      word(0x7ECE30), word(0x7ECE20), word(0x7ECE2E), word(0x7EA2DA)
    )
    hits[key] = (hits[key] or 0) + 1
  end, emu.callbackType.exec, address, address, emu.cpuType.snes)
end
sample_adapter("menu-dispatch", 0xFB13D3)
sample_adapter("menu-draw", 0xFB12A0)
sample_adapter("menu-draw-cursor-store", 0xFB1329)
sample_adapter("menu-draw-cursor-set", 0xFB132E)
sample_adapter("menu-draw-exit", 0xFB1338)
sample_adapter("menu-draw-return", 0xFB1409)
sample_adapter("activation-hook", 0xC284BB)
sample_adapter("activation-hook-mirror", 0x8284BB)
sample_adapter("activation", 0xFB1426)
sample_adapter("menu-surface", 0xFB14BF)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if frame == OPEN_AT then emu.setInput({ a = true }, 0) end
  if frame ~= END_AT then return end
  local keys = {}; for key in pairs(hits) do keys[#keys + 1] = key end
  table.sort(keys)
  local handle = assert(io.open(OUT, "w"))
  for _, key in ipairs(keys) do handle:write(string.format("%s count=%d\n", key, hits[key])) end
  handle:write(string.format("probe hits=%04X 1A=%06X X=%04X D0=%04X A=%04X\n",
    word(0x7ECEFA), pointer(0x7ECEF0), word(0x7ECEF4), word(0x7ECEF6), word(0x7ECEF8)))
  for index = 0, 15 do
    handle:write(string.format("probe-x %d %04X\n", index, word(0x7ECEFC + index * 2)))
  end
  local loop_keys = {}; for key in pairs(loop_exec) do loop_keys[#loop_keys + 1] = key end
  table.sort(loop_keys)
  for _, key in ipairs(loop_keys) do handle:write(string.format("%s count=%d\n", key, loop_exec[key])) end
  local writer_keys = {}; for key in pairs(writer_state) do writer_keys[#writer_keys + 1] = key end
  table.sort(writer_keys)
  for _, key in ipairs(writer_keys) do handle:write(string.format("%s count=%d\n", key, writer_state[key])) end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
