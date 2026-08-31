-- Exercise Character Archives through a genuine redraw and trace all three
-- private bitmap pages.  The framebuffer stored in a savestate is deliberately
-- never captured: only the list and the profile opened after live input count.
--
--   SRW4_STATE       Character Archives detail-screen savestate
--   SRW4_OUT         output prefix (.txt, -list.png, -profile.png)
--   SRW4_RIGHT_COUNT archive pages to move right after returning to the list
--   SRW4_DOWN_COUNT  entries to move down after returning to the list
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local RIGHT_COUNT = tonumber(os.getenv("SRW4_RIGHT_COUNT") or "0")
local DOWN_COUNT = tonumber(os.getenv("SRW4_DOWN_COUNT") or "0")
local DOWN_PERIOD = tonumber(os.getenv("SRW4_DOWN_PERIOD") or "20")

local EXIT_AT = 30
local FIRST_RIGHT_AT = 60
local FIRST_DOWN_AT = FIRST_RIGHT_AT + RIGHT_COUNT * DOWN_PERIOD + 20
local ENTER_AT = FIRST_DOWN_AT + DOWN_COUNT * DOWN_PERIOD + 30
local LIST_SHOT_AT = ENTER_AT - 10
local PROFILE_SHOT_AT = ENTER_AT + 120
local STOP_AT = PROFILE_SHOT_AT + 10

local frame, loaded, armed = 0, false, false
local rows = {}
local counts = { page1 = 0, page2 = 0, page3 = 0, renderer = 0, stock = 0 }

local function read16(address)
  return emu.read(address, emu.memType.snesMemory, false)
    | (emu.read(address + 1, emu.memType.snesMemory, false) << 8)
end

local function source_pointer()
  return read16(0x1A)
    | (emu.read(0x1C, emu.memType.snesMemory, false) << 16)
end

local function capture(path)
  local handle = assert(io.open(path, "wb"))
  handle:write(emu.takeScreenshot())
  handle:close()
end

local function load_state()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(
    load_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes
  )
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end

local function trace_page(kind)
  if not loaded then return end
  counts[kind] = counts[kind] + 1
  if #rows < 1000 then
    rows[#rows + 1] = string.format(
      "f=%d kind=%s src=%06X page=%04X cursor=%04X",
      frame, kind, source_pointer(), read16(0x7EFFBC), read16(0xD0)
    )
  end
end

emu.addMemoryCallback(function() trace_page("page1") end,
  emu.callbackType.exec, 0xEC7800, 0xEC7800, emu.cpuType.snes)
emu.addMemoryCallback(function() trace_page("page2") end,
  emu.callbackType.exec, 0xEC7810, 0xEC7810, emu.cpuType.snes)
emu.addMemoryCallback(function() trace_page("page3") end,
  emu.callbackType.exec, 0xEC7820, 0xEC7820, emu.cpuType.snes)
emu.addMemoryCallback(function()
  if loaded then counts.renderer = counts.renderer + 1 end
end, emu.callbackType.exec, 0xEC6800, 0xEC6800, emu.cpuType.snes)
emu.addMemoryCallback(function()
  if loaded then counts.stock = counts.stock + 1 end
end, emu.callbackType.exec, 0xF0E045, 0xF0E045, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then
    if not armed then
      armed = true
      emu.addMemoryCallback(
        load_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes
      )
    end
    return
  end

  frame = frame + 1
  local button = nil
  if frame == EXIT_AT then
    button = "b"
  elseif frame >= FIRST_RIGHT_AT and frame < FIRST_RIGHT_AT + RIGHT_COUNT * DOWN_PERIOD
      and (frame - FIRST_RIGHT_AT) % DOWN_PERIOD == 0 then
    button = "right"
  elseif frame >= FIRST_DOWN_AT and frame < FIRST_DOWN_AT + DOWN_COUNT * DOWN_PERIOD
      and (frame - FIRST_DOWN_AT) % DOWN_PERIOD == 0 then
    button = "down"
  elseif frame == ENTER_AT then
    button = "a"
  end
  emu.setInput(button and { [button] = true } or {}, 0)

  if frame == LIST_SHOT_AT then capture(OUT .. "-list.png") end
  if frame == PROFILE_SHOT_AT then capture(OUT .. "-profile.png") end
  if frame < STOP_AT then return end

  local log = assert(io.open(OUT .. ".txt", "w"))
  log:write(string.format(
    "right=%d down=%d page1=%d page2=%d page3=%d renderer=%d stock=%d\n",
    RIGHT_COUNT, DOWN_COUNT, counts.page1, counts.page2, counts.page3,
    counts.renderer, counts.stock
  ))
  for _, row in ipairs(rows) do log:write(row .. "\n") end
  log:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
