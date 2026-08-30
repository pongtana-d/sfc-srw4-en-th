-- Count how often each address of interest is executed inside a window.
--
-- The engine tables in the docs disagree about who draws what, so rather than
-- trust either, the addresses are watched while the thing is actually on
-- screen. Watches go on the $80/$81 mirror, because that is the bank the CPU
-- really runs from; watching $C0/$C1 returns zero hits for code that is busy.
local WATCH = os.getenv("SRW4_WATCH") or ""
local LOAD = os.getenv("SRW4_LOAD")
local PRESS = os.getenv("SRW4_PRESS") or ""
local FROM = tonumber(os.getenv("SRW4_FROM") or "120")
local LAST = tonumber(os.getenv("SRW4_LAST") or "600")
local OUT = os.getenv("SRW4_OUT") or "build/reports/exec-watch.txt"
local SHOT = os.getenv("SRW4_SHOT")

local watches = {}
for entry in string.gmatch(WATCH, "[^,]+") do
  local name, address = string.match(entry, "([^=]+)=(%x+)")
  if name then
    watches[#watches + 1] = { name = name, address = tonumber(address, 16), hits = 0 }
  end
end

local presses = {}
for entry in string.gmatch(PRESS, "[^,]+") do
  local from, to, button = string.match(entry, "(%d+):(%d+):(%a+)")
  if from then
    presses[#presses + 1] = { from = tonumber(from), to = tonumber(to), button = button }
  end
end

local frame = 0
local counting = false
local loaded = false
local pending = nil
local armed = false

local function onExec()
  if armed then
    emu.removeMemoryCallback(onExec, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
    armed = false
  end
  if pending then
    local handle = io.open(pending, "rb")
    emu.loadSavestate(handle:read("a"))
    handle:close()
    pending = nil
  end
end

for _, watch in ipairs(watches) do
  emu.addMemoryCallback(function()
    if counting then
      watch.hits = watch.hits + 1
      local pointer = emu.read(0x1A, emu.memType.snesMemory, false)
        | (emu.read(0x1B, emu.memType.snesMemory, false) << 8)
        | (emu.read(0x1C, emu.memType.snesMemory, false) << 16)
      watch.pointers = watch.pointers or {}
      watch.pointers[pointer] = (watch.pointers[pointer] or 0) + 1
      watch.sample = string.format("%02X%02X%02X%02X",
        emu.read(0x7EA206, emu.memType.snesMemory, false),
        emu.read(0x7EA207, emu.memType.snesMemory, false),
        emu.read(0x7F800C, emu.memType.snesMemory, false),
        emu.read(0x7F800D, emu.memType.snesMemory, false))
      watch.arena = string.format("D0=%02X%02X D2=%02X%02X 8C=%02X%02X",
        emu.read(0xD1, emu.memType.snesMemory, false),
        emu.read(0xD0, emu.memType.snesMemory, false),
        emu.read(0xD3, emu.memType.snesMemory, false),
        emu.read(0xD2, emu.memType.snesMemory, false),
        emu.read(0x8D, emu.memType.snesMemory, false),
        emu.read(0x8C, emu.memType.snesMemory, false))
      local cursor = emu.read(0xD0, emu.memType.snesMemory, false)
        | (emu.read(0xD1, emu.memType.snesMemory, false) << 8)
      watch.cursor_first = watch.cursor_first or cursor
      watch.cursor_min = math.min(watch.cursor_min or cursor, cursor)
      watch.cursor_max = math.max(watch.cursor_max or cursor, cursor)
      watch.registers = {}
      for name, register in pairs(emu.registers) do
        local ok, value = pcall(emu.getRegister, register)
        if ok then watch.registers[name] = value end
      end
    end
  end, emu.callbackType.exec, watch.address, watch.address, emu.cpuType.snes)
end

emu.addEventCallback(function()
  frame = frame + 1
  local held, any = {}, false
  for _, press in ipairs(presses) do
    if frame >= press.from and frame <= press.to then
      held[press.button] = true
      any = true
    end
  end
  if any then emu.setInput(held, 0) end
end, emu.eventType.inputPolled)

emu.addEventCallback(function()
  if LOAD and not loaded then
    loaded = true
    pending = LOAD
    armed = true
    emu.addMemoryCallback(onExec, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
    return
  end
  if frame == FROM then counting = true end
  if frame >= LAST then
    local out = io.open(OUT, "w")
    for _, watch in ipairs(watches) do
      out:write(string.format("%s %06X %d\n", watch.name, watch.address, watch.hits))
      local pointers = watch.pointers or {}; local keys = {}
      for pointer in pairs(pointers) do keys[#keys + 1] = pointer end
      table.sort(keys)
      for _, pointer in ipairs(keys) do
        out:write(string.format("%s-pointer %06X %d\n", watch.name, pointer, pointers[pointer]))
      end
      if watch.sample then out:write(string.format("%s-sample %s\n", watch.name, watch.sample)) end
      if watch.arena then out:write(string.format("%s-arena %s\n", watch.name, watch.arena)) end
      if watch.cursor_first then out:write(string.format("%s-cursor first=%04X min=%04X max=%04X\n", watch.name, watch.cursor_first, watch.cursor_min, watch.cursor_max)) end
      local registers = watch.registers or {}; local names = {}
      for name in pairs(registers) do names[#names + 1] = name end
      table.sort(names)
      for _, name in ipairs(names) do out:write(string.format("%s-register %s=%s\n", watch.name, name, tostring(registers[name]))) end
    end
    out:close()
    if SHOT then
      local png = io.open(SHOT, "wb")
      png:write(emu.takeScreenshot())
      png:close()
    end
    emu.stop(0)
  end
end, emu.eventType.endFrame)
