-- Record every DMA launched while an Intro state redraws its next page.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "900")
local VRAM = os.getenv("SRW4_VRAM")
local frame, loaded, armed = 0, false, true
local rows = {}
local ppu = {}

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

emu.addMemoryCallback(function(_, value)
  if not loaded then return end
  local mask = value
  for channel = 0, 7 do
    if (mask & (1 << channel)) ~= 0 then
      local base = 0x4300 + channel * 0x10
      rows[#rows + 1] = string.format(
        "frame=%d ch=%d mode=%02X bbus=%02X src=%02X:%02X%02X len=%02X%02X vmadd=%02X%02X",
        frame, channel,
        emu.read(base, emu.memType.snesMemory, false),
        emu.read(base + 1, emu.memType.snesMemory, false),
        emu.read(base + 4, emu.memType.snesMemory, false),
        emu.read(base + 3, emu.memType.snesMemory, false),
        emu.read(base + 2, emu.memType.snesMemory, false),
        emu.read(base + 6, emu.memType.snesMemory, false),
        emu.read(base + 5, emu.memType.snesMemory, false),
        emu.read(0x2117, emu.memType.snesMemory, false),
        emu.read(0x2116, emu.memType.snesMemory, false))
    end
  end
end, emu.callbackType.write, 0x00420B, 0x00420B, emu.cpuType.snes)

for address = 0x002116, 0x002119 do
  emu.addMemoryCallback(function()
    if not loaded then return end
    local pc = emu.getRegister(emu.registers.pc) & 0xFFFF
    local key = string.format("pc=%04X reg=%04X vmadd=%02X%02X", pc, address,
      emu.read(0x2117, emu.memType.snesMemory, false),
      emu.read(0x2116, emu.memType.snesMemory, false))
    ppu[key] = (ppu[key] or 0) + 1
  end, emu.callbackType.write, address, address, emu.cpuType.snes)
end

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if frame < LAST then return end
  local handle = assert(io.open(OUT, "w"))
  for _, row in ipairs(rows) do handle:write(row .. "\n") end
  local keys = {}
  for key in pairs(ppu) do keys[#keys + 1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do handle:write(string.format("ppu %s hits=%d\n", key, ppu[key])) end
  handle:close()
  if VRAM then
    local video = assert(io.open(VRAM, "wb"))
    local chunk = {}
    for offset = 0, 0xFFFF do
      chunk[#chunk + 1] = string.char(emu.read(offset, emu.memType.snesVideoRam, false))
      if #chunk == 4096 then video:write(table.concat(chunk)); chunk = {} end
    end
    video:write(table.concat(chunk)); video:close()
  end
  emu.stop(0)
end, emu.eventType.endFrame)
