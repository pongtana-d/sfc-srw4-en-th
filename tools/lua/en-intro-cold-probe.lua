-- Trace the active English-ROM opening crawl from a clean New Game route.
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "3300")
local ADVANCE = os.getenv("SRW4_ADVANCE") == "1"
local frame = 0
local hits = {}
local events = {}

local function pulse(value, every, width)
  return value % every < width
end

emu.addMemoryCallback(function()
  local pointer = emu.read(0x1A, emu.memType.snesMemory, false)
    | (emu.read(0x1B, emu.memType.snesMemory, false) << 8)
    | (emu.read(0x1C, emu.memType.snesMemory, false) << 16)
  local key = string.format("%06X", pointer)
  hits[key] = (hits[key] or 0) + 1
  events[#events + 1] = string.format(
    "frame=%d pointer=%s byte=%02X",
    frame,
    key,
    emu.read(pointer, emu.memType.snesMemory, false)
  )
end, emu.callbackType.exec, 0x818F32, 0x818F32, emu.cpuType.snes)

emu.addEventCallback(function()
  frame = frame + 1
  local buttons = {}
  if frame >= 60 and frame <= 900 and pulse(frame - 60, 30, 3) then
    buttons.start = true
  elseif frame >= 950 and frame <= 955 then
    buttons.a = true
  elseif frame >= 1580 and frame <= 1600 then
    buttons.down = true
  elseif frame >= 1640 and frame <= 1645 then
    buttons.a = true
  elseif ADVANCE and frame >= 3300 and pulse(frame - 3300, 180, 3) then
    buttons.a = true
  end
  emu.setInput(buttons, 0)
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  if frame < LAST then return end
  local keys = {}
  for key in pairs(hits) do keys[#keys + 1] = key end
  table.sort(keys)
  local handle = assert(io.open(OUT, "w"))
  for _, event in ipairs(events) do handle:write(event .. "\n") end
  handle:write("-- totals --\n")
  for _, key in ipairs(keys) do
    handle:write(string.format("%s %d\n", key, hits[key]))
  end
  handle:close()
  emu.stop(0)
end, emu.eventType.endFrame)
