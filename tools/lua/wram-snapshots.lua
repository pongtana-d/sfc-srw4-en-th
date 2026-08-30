-- Dump full WRAM at selected input frames while replaying a native Mesen state.
--
-- SRW4_STATE, SRW4_OUT, SRW4_PRESS and SRW4_SHOTS use the same syntax as
-- from-state.lua.  Each shot produces OUT-NNNN.wram and OUT-NNNN.png.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local PRESS = os.getenv("SRW4_PRESS") or ""
local SHOTS = os.getenv("SRW4_SHOTS") or ""
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "180")
local DMA_OUT = os.getenv("SRW4_DMA")
local frame, loaded, armed = 0, false, true

local presses = {}
for pair in PRESS:gmatch("[^,]+") do
  local frame, button = pair:match("^(%d+):(%a+)$")
  if frame then presses[tonumber(frame)] = button end
end

local shots = {}
for value in SHOTS:gmatch("%d+") do shots[tonumber(value)] = true end

local dma_rows = {}
local inidisp = emu.read(0x2100, emu.memType.snesMemory, false)
emu.addMemoryCallback(function(_, value)
  if loaded then inidisp = value end
end, emu.callbackType.write, 0x002100, 0x002100, emu.cpuType.snes)
emu.addMemoryCallback(function(_, value)
  if not loaded then return end
  local mask = value
  for channel = 0, 7 do
    if (mask & (1 << channel)) ~= 0 then
      local base = 0x4300 + channel * 0x10
      local length = emu.read(base + 5, emu.memType.snesMemory, false)
        | (emu.read(base + 6, emu.memType.snesMemory, false) << 8)
      if length == 0 then length = 0x10000 end
      dma_rows[#dma_rows + 1] = string.format(
        "%d,%d,%02X,%02X,%02X%02X%02X,%d,%02X%02X,%02X,%02X",
        frame, channel,
        emu.read(base, emu.memType.snesMemory, false),
        emu.read(base + 1, emu.memType.snesMemory, false),
        emu.read(base + 4, emu.memType.snesMemory, false),
        emu.read(base + 3, emu.memType.snesMemory, false),
        emu.read(base + 2, emu.memType.snesMemory, false),
        length,
        emu.read(0x2117, emu.memType.snesMemory, false),
        emu.read(0x2116, emu.memType.snesMemory, false),
        emu.read(0x4212, emu.memType.snesMemory, false),
        inidisp)
    end
  end
end, emu.callbackType.write, 0x00420B, 0x00420B, emu.cpuType.snes)

local function dump_wram(path)
  local handle = assert(io.open(path, "wb"))
  local bytes = {}
  for offset = 0, 0x1FFFF do
    bytes[#bytes + 1] = string.char(
      emu.read(0x7E0000 + offset, emu.memType.snesMemory, false))
    if #bytes == 4096 then
      handle:write(table.concat(bytes))
      bytes = {}
    end
  end
  handle:close()
end

local function load_state()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(
    load_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(STATE, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end
emu.addMemoryCallback(
  load_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if presses[frame] then
    emu.setInput({[presses[frame]] = true}, 0)
  else
    emu.setInput({}, 0)
  end
  if shots[frame] then
    local stem = string.format("%s-%04d", OUT, frame)
    dump_wram(stem .. ".wram")
    local handle = assert(io.open(stem .. ".png", "wb"))
    handle:write(emu.takeScreenshot())
    handle:close()
  end
  if frame > LAST then
    if DMA_OUT then
      local handle = assert(io.open(DMA_OUT, "w"))
      handle:write("frame,channel,mode,bbus,source,length,vmadd,hvbjoy,inidisp\n")
      for _, row in ipairs(dma_rows) do handle:write(row .. "\n") end
      handle:close()
    end
    emu.stop(0)
  end
end, emu.eventType.inputPolled)
