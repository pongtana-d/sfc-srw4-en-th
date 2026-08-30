-- Trace ordinary catalog renderer lifecycle state through a genuine redraw.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local PRESS = os.getenv("SRW4_PRESS") or ""
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "360")

local presses = {}
for pair in PRESS:gmatch("[^,]+") do
  local at, button = pair:match("^(%d+):(%a+)$")
  if at then presses[tonumber(at)] = button end
end

local frame, loaded, armed = 0, false, false
local rows = {}
local hits = {}

local function read16(address)
  return emu.read(address, emu.memType.snesMemory, false)
    | (emu.read(address + 1, emu.memType.snesMemory, false) << 8)
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

emu.addMemoryCallback(function(address)
  if not loaded then return end
  local kind = address == 0xFFF200 and "thai" or "supplement"
  rows[#rows + 1] = string.format(
    "f=%d kind=%s A=%04X src=%02X:%04X D0=%04X col=%04X " ..
    "sig=%04X pen=%04X expect=%04X state_col=%04X expect_col=%04X",
    frame, kind, emu.getRegister(emu.registers.a) & 0xFFFF,
    emu.read(0x1C, emu.memType.snesMemory, false), read16(0x1A),
    read16(0xD0), read16(0x18), read16(0x7EFFA0), read16(0x7EFFA2),
    read16(0x7EFFA4), read16(0x7EFFAA), read16(0x7EFFAC)
  )
end, emu.callbackType.exec, 0xFFF200, 0xFFF200, emu.cpuType.snes)

emu.addMemoryCallback(function(address)
  if not loaded then return end
  local kind = "supplement"
  rows[#rows + 1] = string.format(
    "f=%d kind=%s A=%04X src=%02X:%04X D0=%04X col=%04X " ..
    "sig=%04X pen=%04X expect=%04X state_col=%04X expect_col=%04X",
    frame, kind, emu.getRegister(emu.registers.a) & 0xFFFF,
    emu.read(0x1C, emu.memType.snesMemory, false), read16(0x1A),
    read16(0xD0), read16(0x18), read16(0x7EFFA0), read16(0x7EFFA2),
    read16(0x7EFFA4), read16(0x7EFFAA), read16(0x7EFFAC)
  )
end, emu.callbackType.exec, 0xFFF400, 0xFFF400, emu.cpuType.snes)

emu.addMemoryCallback(function(address)
  if not loaded then return end
  rows[#rows + 1] = string.format(
    "f=%d kind=unified A=%04X src=%02X:%04X D0=%04X col=%04X " ..
    "sig=%04X pen=%04X expect=%04X state_col=%04X expect_col=%04X page=%04X",
    frame, emu.getRegister(emu.registers.a) & 0xFFFF,
    emu.read(0x1C, emu.memType.snesMemory, false), read16(0x1A),
    read16(0xD0), read16(0x18), read16(0x7EFFA0), read16(0x7EFFA2),
    read16(0x7EFFA4), read16(0x7EFFAA), read16(0x7EFFAC), read16(0x7EFFBC)
  )
end, emu.callbackType.exec, 0xFFF800, 0xFFF800, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if not loaded then return end
  local src = read16(0x1A)
    | (emu.read(0x1C, emu.memType.snesMemory, false) << 16)
  rows[#rows + 1] = string.format(
    "f=%d kind=stock src=%06X glyph=%04X D0=%04X col=%04X " ..
    "stock_pen=%04X stock_f2=%04X stock_f4=%04X stock_sig=%04X",
    frame, src, read16(0x26), read16(0xD0), read16(0x18),
    read16(0x7FFFF0), read16(0x7FFFF2), read16(0x7FFFF4), read16(0x7FFFFC)
  )
end, emu.callbackType.exec, 0xF0E045, 0xF0E045, emu.cpuType.snes)

local function count_hit(address)
  if not loaded then return end
  local pc = address & 0xFFFFFF
  hits[pc] = (hits[pc] or 0) + 1
  if pc == 0xFFF804 then
    rows[#rows + 1] = string.format(
      "f=%d kind=unified glyph=%04X src=%02X:%04X D0=%04X D2=%04X col=%04X sig=%04X pen=%04X " ..
      "expect=%04X state_col=%04X expect_col=%04X page=%04X",
      frame, read16(0x7EFFEA), emu.read(0x1C, emu.memType.snesMemory, false), read16(0x1A),
      read16(0xD0), read16(0xD2), read16(0x18), read16(0x7EFFA0), read16(0x7EFFA2),
      read16(0x7EFFA4), read16(0x7EFFAA), read16(0x7EFFAC), read16(0x7EFFBC)
    )
  end
end
emu.addMemoryCallback(count_hit, emu.callbackType.exec,
  0xFD9800, 0xFD9FFF, emu.cpuType.snes)
emu.addMemoryCallback(count_hit, emu.callbackType.exec,
  0xFF0000, 0xFFFFFF, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if not loaded then return end
  rows[#rows + 1] = string.format(
    "f=%d kind=stock_fb operand=%04X D0=%04X col=%04X sig=%04X pen=%04X " ..
    "expect=%04X state_col=%04X expect_col=%04X",
    frame, read16(0x00), read16(0xD0), read16(0x18),
    read16(0x7EFFA0), read16(0x7EFFA2), read16(0x7EFFA4),
    read16(0x7EFFAA), read16(0x7EFFAC)
  )
end, emu.callbackType.exec, 0xFD9E40, 0xFD9E40, emu.cpuType.snes)


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
  if presses[frame] then
    emu.setInput({ [presses[frame]] = true }, 0)
  else
    emu.setInput({}, 0)
  end
  if frame < LAST then return end
  local log = assert(io.open(OUT .. ".txt", "w"))
  for _, row in ipairs(rows) do log:write(row .. "\n") end
  local ranked = {}
  for address, count in pairs(hits) do
    ranked[#ranked + 1] = { address = address, count = count }
  end
  table.sort(ranked, function(a, b)
    if a.count == b.count then return a.address < b.address end
    return a.count > b.count
  end)
  for _, hit in ipairs(ranked) do
    log:write(string.format("hit=%06X count=%d\n", hit.address, hit.count))
  end
  log:close()
  local shot = assert(io.open(OUT .. ".png", "wb"))
  shot:write(emu.takeScreenshot())
  shot:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
