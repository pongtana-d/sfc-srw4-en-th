-- Minimal command-menu smoke test from a Mesen savestate.
-- No memory callbacks after loading: keep the test runner fast enough to use
-- on states whose untouched WRAM produces many diagnostic reads.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local SHOT = assert(os.getenv("SRW4_SHOT"), "SRW4_SHOT is required")
local TILEMAP = assert(os.getenv("SRW4_TILEMAP"), "SRW4_TILEMAP is required")
local ARENA = os.getenv("SRW4_ARENA")
local VRAM = os.getenv("SRW4_VRAM")
local WRAM = os.getenv("SRW4_WRAM")
local TRACE = os.getenv("SRW4_TRACE")
local OPEN_AT = tonumber(os.getenv("SRW4_OPEN_AT") or "5")
local END_AT = tonumber(os.getenv("SRW4_END_AT") or "60")
local PRESS = os.getenv("SRW4_PRESS") or ""
local TRACE_EXEC = os.getenv("SRW4_TRACE_EXEC") == "1"
local presses = {}
for pair in PRESS:gmatch("[^,]+") do
  local at, button = pair:match("^(%d+):(%a+)$")
  if at then presses[tonumber(at)] = button end
end

local loaded, armed, frame = false, false, 0
local trace = {}
local exec_hits = {}

if TRACE_EXEC then
  local function count_exec(address)
    if not loaded then return end
    exec_hits[address] = (exec_hits[address] or 0) + 1
    local low = address & 0xFFFF
    if TRACE and (exec_hits[address] or 0) <= 40
        and (low == 0x8402 or low == 0xB000 or low == 0xB0A3) then
      local pointer = emu.read(0x1A, emu.memType.snesMemory, false)
        | (emu.read(0x1B, emu.memType.snesMemory, false) << 8)
      local bank = emu.read(0x1C, emu.memType.snesMemory, false)
      trace[#trace + 1] = string.format(
        "f=%d route=%06X a=%04X source=%02X:%04X", frame, address,
        emu.getRegister(emu.registers.a) & 0xFFFF, bank, pointer)
    end
  end
  for bank = 0, 3 do
    emu.addMemoryCallback(count_exec, emu.callbackType.exec,
      bank << 16, (bank << 16) | 0xFFFF, emu.cpuType.snes)
  end
  for bank = 0x80, 0x83 do
    emu.addMemoryCallback(count_exec, emu.callbackType.exec,
      bank << 16, (bank << 16) | 0xFFFF, emu.cpuType.snes)
  end
  emu.addMemoryCallback(count_exec, emu.callbackType.exec,
    0xFB0000, 0xFBFFFF, emu.cpuType.snes)
  emu.addMemoryCallback(count_exec, emu.callbackType.exec,
    0xFD0000, 0xFDFFFF, emu.cpuType.snes)
  emu.addMemoryCallback(count_exec, emu.callbackType.exec,
    0xFF0000, 0xFFFFFF, emu.cpuType.snes)
end

local function load_state()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(load_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end

local function dump(path, first, count)
  local handle = assert(io.open(path, "wb"))
  local bytes = {}
  for offset = 0, count - 1 do
    bytes[#bytes + 1] = string.char(emu.read(first + offset, emu.memType.snesMemory, false))
    if #bytes == 4096 then handle:write(table.concat(bytes)); bytes = {} end
  end
  handle:write(table.concat(bytes))
  handle:close()
end

emu.addEventCallback(function()
  if not loaded then
    if not armed then
      armed = true
      emu.addMemoryCallback(load_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
    end
    return
  end
  frame = frame + 1
  local buttons = {}
  if frame == OPEN_AT then buttons.a = true end
  if presses[frame] then buttons[presses[frame]] = true end
  emu.setInput(buttons, 0)
  if frame ~= END_AT then return end
  local image = assert(io.open(SHOT, "wb"))
  image:write(emu.takeScreenshot())
  image:close()
  dump(TILEMAP, 0x7EA000, 0x0800)
  if WRAM then dump(WRAM, 0x7E0000, 0x20000) end
  if ARENA then dump(ARENA, 0x7F8000, 0x8000) end
  if VRAM then
    local handle = assert(io.open(VRAM, "wb"))
    local bytes = {}
    for offset = 0, 0xFFFF do
      bytes[#bytes + 1] = string.char(emu.read(offset, emu.memType.snesVideoRam, false))
      if #bytes == 4096 then handle:write(table.concat(bytes)); bytes = {} end
    end
    handle:write(table.concat(bytes)); handle:close()
  end
  if TRACE then
    local handle = assert(io.open(TRACE, "w"))
    for _, row in ipairs(trace) do handle:write(row .. "\n") end
    local machine = emu.getState()
    handle:write(string.format("final cpu=%02X:%04X a=%04X x=%04X y=%04X sp=%04X d=%04X p=%02X\n",
      machine["cpu.k"], machine["cpu.pc"], machine["cpu.a"] & 0xFFFF,
      machine["cpu.x"] & 0xFFFF, machine["cpu.y"] & 0xFFFF,
      machine["cpu.sp"] & 0xFFFF, machine["cpu.d"] & 0xFFFF,
      machine["cpu.ps"] & 0xFF))
    handle:write(string.format("final active=%02X%02X count=%d selected=%d\n",
      emu.read(0x7ECED7, emu.memType.snesMemory, false),
      emu.read(0x7ECED6, emu.memType.snesMemory, false),
      emu.read(0x7ECEE4, emu.memType.snesMemory, false),
      emu.read(0x0E3A, emu.memType.snesMemory, false)))
    handle:write(string.format(
      "final frame=%02X%02X rec=%02X%02X flags=%02X%02X,%02X%02X,%02X%02X ctrl=%02X,%02X,%02X\n",
      emu.read(0x7ECEDB, emu.memType.snesMemory, false),
      emu.read(0x7ECEDA, emu.memType.snesMemory, false),
      emu.read(0x7ECEEF, emu.memType.snesMemory, false),
      emu.read(0x7ECEEE, emu.memType.snesMemory, false),
      emu.read(0x0E27, emu.memType.snesMemory, false),
      emu.read(0x0E26, emu.memType.snesMemory, false),
      emu.read(0x0E29, emu.memType.snesMemory, false),
      emu.read(0x0E28, emu.memType.snesMemory, false),
      emu.read(0x0E2B, emu.memType.snesMemory, false),
      emu.read(0x0E2A, emu.memType.snesMemory, false),
      emu.read(0x18, emu.memType.snesMemory, false),
      emu.read(0x16, emu.memType.snesMemory, false),
      emu.read(0xD0, emu.memType.snesMemory, false)))
    if TRACE_EXEC then
      local ranked = {}
      for address, count in pairs(exec_hits) do
        ranked[#ranked + 1] = { address = address, count = count }
      end
      table.sort(ranked, function(a, b) return a.count > b.count end)
      for index = 1, math.min(32, #ranked) do
        handle:write(string.format("exec %06X %d\n", ranked[index].address, ranked[index].count))
      end
    end
    handle:close()
  end
  emu.stop(0)
end, emu.eventType.inputPolled)

emu.addMemoryCallback(function()
  if not loaded then return end
  local d0 = emu.read(0xD0, emu.memType.snesMemory, false)
    | (emu.read(0xD1, emu.memType.snesMemory, false) << 8)
  trace[#trace + 1] = string.format("f=%d d0=%04X count=%d", frame, d0,
    emu.read(0x7ECEE4, emu.memType.snesMemory, false))
end, emu.callbackType.exec, 0xFB0448, 0xFB0448, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if not loaded then return end
  local pointer = emu.read(0x1A, emu.memType.snesMemory, false)
    | (emu.read(0x1B, emu.memType.snesMemory, false) << 8)
  local bank = emu.read(0x1C, emu.memType.snesMemory, false)
  trace[#trace + 1] = string.format("f=%d raster=%02X:%04X", frame, bank, pointer)
end, emu.callbackType.exec, 0xFB03D3, 0xFB03D3, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if not loaded then return end
  local pointer = emu.read(0x1A, emu.memType.snesMemory, false)
    | (emu.read(0x1B, emu.memType.snesMemory, false) << 8)
  local bank = emu.read(0x1C, emu.memType.snesMemory, false)
  trace[#trace + 1] = string.format("f=%d stock=%02X:%04X", frame, bank, pointer)
end, emu.callbackType.exec, 0x8184EB, 0x8184EB, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if not loaded or not TRACE then return end
  local bank = emu.read(0x1C, emu.memType.snesMemory, false)
  if bank ~= 0xFA then return end
  local d0 = emu.read(0xD0, emu.memType.snesMemory, false)
    | (emu.read(0xD1, emu.memType.snesMemory, false) << 8)
  trace[#trace + 1] = string.format("f=%d writer d0=%04X cell=%d a=%04X y=%04X", frame, d0,
    emu.read(0x7ECEF8, emu.memType.snesMemory, false),
    emu.getRegister(emu.registers.a) & 0xFFFF,
    emu.getRegister(emu.registers.y) & 0xFFFF)
end, emu.callbackType.exec, 0x01848E, 0x01848E, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if not loaded or not TRACE then return end
  trace[#trace + 1] = string.format("f=%d prepare cell=%d", frame,
    emu.read(0x7ECEF8, emu.memType.snesMemory, false))
end, emu.callbackType.exec, 0xFB052E, 0xFB052E, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if not loaded then return end
  trace[#trace + 1] = string.format("f=%d open a=%04X", frame,
    emu.getRegister(emu.registers.a) & 0xFFFF)
end, emu.callbackType.exec, 0x82843B, 0x82843B, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if not loaded then return end
  trace[#trace + 1] = string.format("f=%d owner a=%04X", frame,
    emu.getRegister(emu.registers.a) & 0xFFFF)
end, emu.callbackType.exec, 0xFB04E1, 0xFB04E1, emu.cpuType.snes)

emu.addMemoryCallback(function(address)
  if not loaded then return end
  trace[#trace + 1] = string.format("f=%d tilemap pc=%04X at=%04X", frame,
    emu.getRegister(emu.registers.pc) & 0xFFFF, address & 0xFFFF)
end, emu.callbackType.write, 0x7EA000, 0x7EA7FF, emu.cpuType.snes)

emu.addMemoryCallback(function()
  if not loaded then return end
  trace[#trace + 1] = string.format("f=%d selected-write pc=%04X", frame,
    emu.getRegister(emu.registers.pc) & 0xFFFF)
end, emu.callbackType.write, 0x7E0E3A, 0x7E0E3A, emu.cpuType.snes)

local function trace_frame_store(where)
  if not loaded or not TRACE then return end
  trace[#trace + 1] = string.format(
    "f=%d %s a=%04X x=%04X active=%02X%02X", frame, where,
    emu.getRegister(emu.registers.a) & 0xFFFF,
    emu.getRegister(emu.registers.x) & 0xFFFF,
    emu.read(0x7ECED7, emu.memType.snesMemory, false),
    emu.read(0x7ECED6, emu.memType.snesMemory, false))
end

emu.addMemoryCallback(function() trace_frame_store("repeat-stock") end,
  emu.callbackType.exec, 0x818440, 0x818440, emu.cpuType.snes)
emu.addMemoryCallback(function() trace_frame_store("repeat-stock-01") end,
  emu.callbackType.exec, 0x018440, 0x018440, emu.cpuType.snes)
emu.addMemoryCallback(function() trace_frame_store("repeat-stock-41") end,
  emu.callbackType.exec, 0x418440, 0x418440, emu.cpuType.snes)
emu.addMemoryCallback(function() trace_frame_store("repeat-stock-C1") end,
  emu.callbackType.exec, 0xC18440, 0xC18440, emu.cpuType.snes)
emu.addMemoryCallback(function() trace_frame_store("repeat-hook") end,
  emu.callbackType.exec, 0xFB069B, 0xFB069B, emu.cpuType.snes)
emu.addMemoryCallback(function() trace_frame_store("repeat-hook-7B") end,
  emu.callbackType.exec, 0x7B069B, 0x7B069B, emu.cpuType.snes)
emu.addMemoryCallback(function() trace_frame_store("frame-stock") end,
  emu.callbackType.exec, 0x81844B, 0x81844B, emu.cpuType.snes)
emu.addMemoryCallback(function() trace_frame_store("frame-stock-01") end,
  emu.callbackType.exec, 0x01844B, 0x01844B, emu.cpuType.snes)
emu.addMemoryCallback(function() trace_frame_store("frame-stock-41") end,
  emu.callbackType.exec, 0x41844B, 0x41844B, emu.cpuType.snes)
emu.addMemoryCallback(function() trace_frame_store("frame-stock-C1") end,
  emu.callbackType.exec, 0xC1844B, 0xC1844B, emu.cpuType.snes)
emu.addMemoryCallback(function() trace_frame_store("frame-hook") end,
  emu.callbackType.exec, 0xFB067B, 0xFB067B, emu.cpuType.snes)
emu.addMemoryCallback(function() trace_frame_store("frame-hook-7B") end,
  emu.callbackType.exec, 0x7B067B, 0x7B067B, emu.cpuType.snes)

emu.addMemoryCallback(function(address, value)
  if not loaded or not TRACE then return end
  trace[#trace + 1] = string.format(
    "f=%d legacy-tail at=%04X value=%04X pc=%04X a=%04X x=%04X active=%02X%02X",
    frame, address & 0xFFFF, value & 0xFFFF,
    emu.getRegister(emu.registers.pc) & 0xFFFF,
    emu.getRegister(emu.registers.a) & 0xFFFF,
    emu.getRegister(emu.registers.x) & 0xFFFF,
    emu.read(0x7ECED7, emu.memType.snesMemory, false),
    emu.read(0x7ECED6, emu.memType.snesMemory, false))
end, emu.callbackType.write, 0x00A4AE, 0x00A4B3, emu.cpuType.snes)
