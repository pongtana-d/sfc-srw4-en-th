-- Capture the source pointers feeding the naming screen's stock rasteriser.
-- The screen uses $1A-$1C, not the story engine's $CB-$CD.
--
-- Required environment:
--   SRW4_STATE  Mesen .mss to load
--   SRW4_OUT    output text file
-- Optional:
--   SRW4_PRESS  frame:button pairs, e.g. 60:a,150:a,240:a
--   SRW4_FRAMES frames to run after loading (default 600)
--   SRW4_NAMES  temporary WRAM name buffers, e.g. 1016:03171AFF
--   SRW4_ENTRY  optional adapter entry CPU address to count

local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local PRESS = os.getenv("SRW4_PRESS") or ""
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "600")
local ENTRY = tonumber(os.getenv("SRW4_ENTRY") or "0", 16)

local presses = {}
for pair in PRESS:gmatch("[^,]+") do
  local frame, button = pair:match("^(%d+):(%a+)$")
  if frame then presses[tonumber(frame)] = button end
end

local loaded, armed, frame = false, true, 0
local hits = {}
local parser_hits = {}
local entry_hits = 0
local entry_codes = {}
local names = {}
for pair in (os.getenv("SRW4_NAMES") or ""):gmatch("[^,]+") do
  local at, hex = pair:match("^(%x+):(%x+)$")
  if at then names[#names + 1] = { addr = tonumber(at, 16), hex = hex } end
end

local function on_boot()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(on_boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end
emu.addMemoryCallback(on_boot, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if not loaded then return end
  local pointer = emu.read(0x1A, emu.memType.snesMemory, false)
    | (emu.read(0x1B, emu.memType.snesMemory, false) << 8)
    | (emu.read(0x1C, emu.memType.snesMemory, false) << 16)
  hits[pointer] = (hits[pointer] or 0) + 1
end, emu.callbackType.exec, 0x8184E4, 0x8184E4, emu.cpuType.snes)

local function trace_parser()
  if not loaded then return end
  local pointer = emu.read(0x1A, emu.memType.snesMemory, false)
    | (emu.read(0x1B, emu.memType.snesMemory, false) << 8)
    | (emu.read(0x1C, emu.memType.snesMemory, false) << 16)
  local code = emu.getRegister(emu.registers.a) & 0xFFFF
  local key = string.format("%06X %04X", pointer, code)
  parser_hits[key] = (parser_hits[key] or 0) + 1
end
emu.addMemoryCallback(trace_parser, emu.callbackType.exec, 0x818402, 0x818402, emu.cpuType.snes)
emu.addMemoryCallback(trace_parser, emu.callbackType.exec, 0x81840F, 0x81840F, emu.cpuType.snes)
emu.addMemoryCallback(trace_parser, emu.callbackType.exec, 0xFD0000, 0xFD0000, emu.cpuType.snes)
emu.addMemoryCallback(trace_parser, emu.callbackType.exec, 0xFD0100, 0xFD0100, emu.cpuType.snes)

if ENTRY ~= 0 then
  emu.addMemoryCallback(function()
    if loaded then
      entry_hits = entry_hits + 1
      local pointer = emu.read(0x1A, emu.memType.snesMemory, false)
        | (emu.read(0x1B, emu.memType.snesMemory, false) << 8)
        | (emu.read(0x1C, emu.memType.snesMemory, false) << 16)
      local code = emu.getRegister(emu.registers.a) & 0xFFFF
      local key = string.format("%06X %04X", pointer, code)
      entry_codes[key] = (entry_codes[key] or 0) + 1
    end
  end, emu.callbackType.exec, ENTRY, ENTRY, emu.cpuType.snes)
end

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  for _, name in ipairs(names) do
    for i = 1, #name.hex, 2 do
      emu.write(0x7E0000 + name.addr + (i - 1) // 2,
        tonumber(name.hex:sub(i, i + 1), 16), emu.memType.snesMemory)
    end
  end
  if presses[frame] then emu.setInput({ [presses[frame]] = true }, 0) end
  if frame < LAST then return end
  local pointers = {}
  for pointer in pairs(hits) do pointers[#pointers + 1] = pointer end
  table.sort(pointers)
  local handle = assert(io.open(OUT, "w"))
  handle:write(string.format("ENTRY %d\n", entry_hits))
  local entry_keys = {}
  for key in pairs(entry_codes) do entry_keys[#entry_keys + 1] = key end
  table.sort(entry_keys)
  for _, key in ipairs(entry_keys) do
    handle:write(string.format("ENTRYCODE %s %d\n", key, entry_codes[key]))
  end
  for _, pointer in ipairs(pointers) do
    handle:write(string.format("%06X %d\n", pointer, hits[pointer]))
  end
  handle:write("PARSER\n")
  local parser_keys = {}
  for key in pairs(parser_hits) do parser_keys[#parser_keys + 1] = key end
  table.sort(parser_keys)
  for _, key in ipairs(parser_keys) do
    handle:write(string.format("%s %d\n", key, parser_hits[key]))
  end
  handle:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
