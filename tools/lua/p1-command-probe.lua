-- Capture the evidence package for the live en unit-command menu.
-- Loads a reproducible map state, opens the menu once, then records source
-- pointers reaching the en renderer, DMA launches, and the relevant WRAM
-- tilemap/arena bytes after the redraw.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local SHOT = assert(os.getenv("SRW4_SHOT"), "SRW4_SHOT is required")
-- en routes its menu glyphs through $F0:E045; clean reaches the stock
-- rasteriser at $81:84EB.  Keeping the capture otherwise identical makes the
-- two pointer/tilemap traces comparable.
local RENDERER = tonumber(os.getenv("SRW4_RENDERER") or "F0E045", 16)
local CAPTURE_AT = tonumber(os.getenv("SRW4_CAPTURE_AT") or "180")
local OPEN_AT = tonumber(os.getenv("SRW4_OPEN_AT") or "180")
local END_AT = tonumber(os.getenv("SRW4_END_AT") or "360")
local EXTRA_PRESS = os.getenv("SRW4_EXTRA_PRESS") or ""

local extra_presses = {}
for entry in EXTRA_PRESS:gmatch("[^,]+") do
  local at, button = entry:match("^(%d+):(%a+)$")
  if at then extra_presses[tonumber(at)] = button end
end

local loaded, armed, frame, capture = false, false, 0, false
local renderer_hits, dma_hits, caller_hits, caller_state = {}, {}, {}, {}
local parser_hits = {}
local shadow_writes = {}
local ppu_writes = {}
local last_caller = "before-capture"
local continuation_hits = 0
local callers = {
  [0x82843B] = "map-entry",
  [0x8389F5] = "menu-labels",
}

local function boot()
  if not armed then return end
  armed = false
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end

local function ptr(at)
  return emu.read(at, emu.memType.snesMemory, false)
    | (emu.read(at + 1, emu.memType.snesMemory, false) << 8)
    | (emu.read(at + 2, emu.memType.snesMemory, false) << 16)
end

emu.addMemoryCallback(function()
  if not loaded or not capture then return end
  local key = string.format("caller=%s CB=%06X 1A=%06X rec=%04X D0=%04X", last_caller, ptr(0xCB), ptr(0x1A),
    emu.read(0x7ECEEE, emu.memType.snesMemory, false)
      | (emu.read(0x7ECEEF, emu.memType.snesMemory, false) << 8),
    emu.read(0xD0, emu.memType.snesMemory, false)
      | (emu.read(0xD1, emu.memType.snesMemory, false) << 8))
  renderer_hits[key] = (renderer_hits[key] or 0) + 1
end, emu.callbackType.exec, RENDERER, RENDERER, emu.cpuType.snes)

for _, address in ipairs({0x818402, 0x81840F, 0x818456, 0xFD0000, 0xFD0100}) do
  emu.addMemoryCallback(function()
    if not loaded or not capture then return end
    local key = string.format("%06X bank=%02X ptr=%04X", address,
      emu.read(0x1C, emu.memType.snesMemory, false),
      emu.read(0x1A, emu.memType.snesMemory, false) | (emu.read(0x1B, emu.memType.snesMemory, false) << 8))
    parser_hits[key] = (parser_hits[key] or 0) + 1
  end, emu.callbackType.exec, address, address, emu.cpuType.snes)
end

for address, name in pairs(callers) do
  emu.addMemoryCallback(function()
    if not loaded or not capture then return end
    last_caller = name
    caller_hits[name] = (caller_hits[name] or 0) + 1
    local key = string.format(
      "%s A=%04X D0=%04X F5EC=%06X",
      name,
      emu.getRegister(emu.registers.a) & 0xFFFF,
      emu.read(0xD0, emu.memType.snesMemory, false) | (emu.read(0xD1, emu.memType.snesMemory, false) << 8),
      ptr(0xF5EC)
    )
    caller_state[key] = (caller_state[key] or 0) + 1
  end, emu.callbackType.exec, address, address, emu.cpuType.snes)
end

emu.addMemoryCallback(function()
  if loaded and capture then continuation_hits = continuation_hits + 1 end
end, emu.callbackType.exec, 0x80F612, 0x80F612, emu.cpuType.snes)

emu.addMemoryCallback(function(_, value)
  if not loaded or not capture then return end
  local mask = value
  local parts = { string.format("mask=%02X", mask) }
  for channel = 0, 7 do
    if (mask & (1 << channel)) ~= 0 then
      local base = 0x4300 + channel * 0x10
      parts[#parts + 1] = string.format(
        "ch%d mode=%02X bbus=%02X src=%02X:%02X%02X len=%02X%02X",
        channel,
        emu.read(base, emu.memType.snesMemory, false),
        emu.read(base + 1, emu.memType.snesMemory, false),
        emu.read(base + 4, emu.memType.snesMemory, false),
        emu.read(base + 3, emu.memType.snesMemory, false),
        emu.read(base + 2, emu.memType.snesMemory, false),
        emu.read(base + 6, emu.memType.snesMemory, false),
        emu.read(base + 5, emu.memType.snesMemory, false)
      )
    end
  end
  dma_hits[#dma_hits + 1] = string.format("frame=%d %s", frame, table.concat(parts, " "))
end, emu.callbackType.write, 0x00420B, 0x00420B, emu.cpuType.snes)

local function watch_shadow(name, start, stop)
  emu.addMemoryCallback(function(address)
    if not loaded or not capture then return end
    local pc = emu.getRegister(emu.registers.pc) & 0xFFFF
    local key = string.format("%s page=%04X pc=%04X", name, address & 0xFF00, pc)
    shadow_writes[key] = (shadow_writes[key] or 0) + 1
  end, emu.callbackType.write, start, stop, emu.cpuType.snes)
end
watch_shadow("a000", 0x7EA000, 0x7EA3FF)
watch_shadow("dd00", 0x7EDD00, 0x7EDFFF)
watch_shadow("df00", 0x7EDF00, 0x7EDFFF)

for address = 0x002115, 0x002122 do
  emu.addMemoryCallback(function()
    if not loaded or not capture then return end
    local value = emu.read(address, emu.memType.snesMemory, false)
    local pc = emu.getRegister(emu.registers.pc) & 0xFFFF
    local key = string.format("reg=%04X value=%02X pc=%04X", address, value, pc)
    ppu_writes[key] = (ppu_writes[key] or 0) + 1
  end, emu.callbackType.write, address, address, emu.cpuType.snes)
end

local function dump_memory(path, start, count, memory_type)
  local handle = assert(io.open(path, "wb"))
  local chunk = {}
  for offset = 0, count - 1 do
    chunk[#chunk + 1] = string.char(emu.read(start + offset, memory_type or emu.memType.snesMemory, false))
    if #chunk == 4096 then handle:write(table.concat(chunk)); chunk = {} end
  end
  handle:write(table.concat(chunk))
  handle:close()
end

emu.addEventCallback(function()
  if not loaded then
    if not armed then
      armed = true
      emu.addMemoryCallback(boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
    end
    return
  end
  frame = frame + 1
  if frame == 170 then
    dump_memory(OUT .. ".before.tilemap.bin", 0x7E8000, 0x4000)
    dump_memory(OUT .. ".before.arena.bin", 0x7F8000, 0x8000)
    if emu.memType.snesSpriteRam then
      dump_memory(OUT .. ".before.oam.bin", 0, 544, emu.memType.snesSpriteRam)
    end
  end
  if frame == CAPTURE_AT then
    capture = true
    emu.resetAccessCounters()
  end
  local input = {}
  if frame == OPEN_AT then input.a = true end
  if extra_presses[frame] then input[extra_presses[frame]] = true end
  emu.setInput(input, 0)
  if frame ~= END_AT then return end
  local shot = assert(io.open(SHOT, "wb")); shot:write(emu.takeScreenshot()); shot:close()
  dump_memory(OUT .. ".tilemap.bin", 0x7E8000, 0x4000)
  dump_memory(OUT .. ".arena.bin", 0x7F8000, 0x8000)
  if emu.memType.snesSpriteRam then
    dump_memory(OUT .. ".oam.bin", 0, 544, emu.memType.snesSpriteRam)
  end
  local report = assert(io.open(OUT .. ".txt", "w"))
  report:write(string.format("state 1A=%06X CB=%06X D0=%04X F5EC=%06X\n",
    ptr(0x1A), ptr(0xCB),
    emu.read(0xD0, emu.memType.snesMemory, false) | (emu.read(0xD1, emu.memType.snesMemory, false) << 8),
    ptr(0xF5EC)))
  report:write(string.format("menu active=%04X count=%04X current=%04X records=%02X,%02X,%02X,%02X last=%04X line=%04X\n",
    emu.read(0x7ECEE6, emu.memType.snesMemory, false) | (emu.read(0x7ECEE7, emu.memType.snesMemory, false) << 8),
    emu.read(0x7ECEE4, emu.memType.snesMemory, false) | (emu.read(0x7ECEE5, emu.memType.snesMemory, false) << 8),
    emu.read(0x7ECEEE, emu.memType.snesMemory, false) | (emu.read(0x7ECEEF, emu.memType.snesMemory, false) << 8),
    emu.read(0x7ECEE6, emu.memType.snesMemory, false), emu.read(0x7ECEE7, emu.memType.snesMemory, false), emu.read(0x7ECEE8, emu.memType.snesMemory, false), emu.read(0x7ECEE9, emu.memType.snesMemory, false),
    emu.read(0x7ECE2E, emu.memType.snesMemory, false) | (emu.read(0x7ECE2F, emu.memType.snesMemory, false) << 8),
    emu.read(0x7ECE32, emu.memType.snesMemory, false) | (emu.read(0x7ECE33, emu.memType.snesMemory, false) << 8)))
  local caller_names = {}; for name in pairs(caller_hits) do caller_names[#caller_names + 1] = name end
  table.sort(caller_names)
  for _, name in ipairs(caller_names) do report:write(string.format("caller %s %d\n", name, caller_hits[name])) end
  local state_keys = {}; for key in pairs(caller_state) do state_keys[#state_keys + 1] = key end
  table.sort(state_keys)
  for _, key in ipairs(state_keys) do report:write(string.format("caller-state %s %d\n", key, caller_state[key])) end
  report:write(string.format("continuation 80F612 %d\n", continuation_hits))
  local keys = {}; for key in pairs(renderer_hits) do keys[#keys + 1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do report:write(string.format("renderer %s %d\n", key, renderer_hits[key])) end
  keys = {}; for key in pairs(parser_hits) do keys[#keys + 1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do report:write(string.format("parser %s %d\n", key, parser_hits[key])) end
  for _, item in ipairs(dma_hits) do report:write("dma " .. item .. "\n") end
  keys = {}; for key in pairs(shadow_writes) do keys[#keys + 1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do report:write(string.format("shadow %s %d\n", key, shadow_writes[key])) end
  keys = {}; for key in pairs(ppu_writes) do keys[#keys + 1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do report:write(string.format("ppu %s %d\n", key, ppu_writes[key])) end
  local counts = emu.getAccessCounters(emu.memType.snesWorkRam, emu.counterType.writeCount)
  for _, region in ipairs({ { "a000", 0xA000, 0xA400 }, { "dd00", 0xDD00, 0xE000 } }) do
    local touched, total = 0, 0
    for address = region[2], region[3] - 1 do
      local count = counts[address] or 0
      if count > 0 then touched = touched + 1; total = total + count end
    end
    report:write(string.format("shadow-count %s bytes=%d writes=%d\n", region[1], touched, total))
  end
  report:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
