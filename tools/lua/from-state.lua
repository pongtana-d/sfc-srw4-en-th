-- Start from a save state, drive it live, and note every record drawn.
--
-- A save state is a picture as much as a machine: what is already on screen
-- was drawn by whatever ROM made the state, so nothing on it counts as
-- evidence. Only what the game redraws after loading does -- which is why
-- this presses a button and photographs later frames rather than frame one.
--
--   SRW4_STATE   the .mss to load
--   SRW4_OUT     prefix for "-NNNN.png" shots and "-pointers.txt"
--   SRW4_PRESS   "60:a,120:b" -- what to press, and when
--   SRW4_SHOTS   frames to photograph
--   SRW4_NAMES   "1016:03171AFF" -- temporary WRAM name buffers for a test
local STATE = os.getenv("SRW4_STATE")
local OUT   = os.getenv("SRW4_OUT")
local PRESS = os.getenv("SRW4_PRESS") or ""      -- "frame:button,frame:button"
local AUTO_A_EVERY = tonumber(os.getenv("SRW4_AUTO_A_EVERY") or "0")
local SHOTS = os.getenv("SRW4_SHOTS") or "30,90,180,300,450,600"
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "900")
local SAVE = os.getenv("SRW4_SAVE")
local TILEMAP = os.getenv("SRW4_TILEMAP")
local TEXT_TILEMAP = os.getenv("SRW4_TEXT_TILEMAP")
local ARENA = os.getenv("SRW4_ARENA")
local VRAM = os.getenv("SRW4_VRAM")
local SAVE_AT = tonumber(os.getenv("SRW4_SAVE_AT") or "-1")

local presses = {}
for pair in PRESS:gmatch("[^,]+") do
  local f, b = pair:match("^(%d+):(%a+)$")
  if f then presses[tonumber(f)] = b end
end
local shots = {}
for n in SHOTS:gmatch("%d+") do shots[tonumber(n)] = true end

local frame, loaded, armed = 0, false, true
local save_pending, saved = false, false

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

local function dump_vram(path)
  local handle = assert(io.open(path, "wb"))
  local bytes = {}
  for address = 0, 0xFFFF do
    bytes[#bytes + 1] = string.char(
      emu.read(address, emu.memType.snesVideoRam, false)
    )
    if #bytes == 4096 then handle:write(table.concat(bytes)); bytes = {} end
  end
  handle:write(table.concat(bytes)); handle:close()
end

local function onExec()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(onExec, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local h = io.open(STATE, "rb")
  emu.loadSavestate(h:read("a"))
  h:close()
  loaded = true
end

local names = {}
for pair in (os.getenv("SRW4_NAMES") or ""):gmatch("[^,]+") do
  local at, hex = pair:match("^(%x+):(%x+)$")
  if at then names[#names + 1] = { addr = tonumber(at, 16), hex = hex } end
end
emu.addMemoryCallback(onExec, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

local function save_state()
  if not save_pending then return end
  save_pending = false
  emu.removeMemoryCallback(save_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  local handle = assert(io.open(SAVE, "wb"))
  handle:write(emu.createSavestate())
  handle:close()
  saved = true
end

-- Every pointer the story loop draws from, noted when it jumps rather than
-- steps: that is a new record.
local seen, last = {}, -1
emu.addMemoryCallback(function()
  if not loaded then return end
  local p = emu.read(0xCB, emu.memType.snesMemory, false)
    | (emu.read(0xCC, emu.memType.snesMemory, false) << 8)
    | (emu.read(0xCD, emu.memType.snesMemory, false) << 16)
  if last < 0 or p < last or p - last > 8 then
    seen[#seen + 1] = string.format("%06X @%d", p, frame)
  end
  last = p
end, emu.callbackType.exec, 0x819238, 0x819238, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  for _, name in ipairs(names) do
    for i = 1, #name.hex, 2 do
      emu.write(0x7E0000 + name.addr + (i - 1) // 2,
        tonumber(name.hex:sub(i, i + 1), 16), emu.memType.snesMemory)
    end
  end
  -- A scripted press is a one-frame pulse.  Explicitly releasing on every
  -- other frame matters for dialogue/animation waits, which react to a new
  -- button edge rather than key repeat.
  if presses[frame] then
    emu.setInput({ [presses[frame]] = true }, 0)
  elseif AUTO_A_EVERY > 0 and frame % AUTO_A_EVERY == 0 then
    emu.setInput({ a = true }, 0)
  else
    emu.setInput({}, 0)
  end
  if SAVE and not saved and frame >= SAVE_AT then
    save_pending = true
    emu.addMemoryCallback(save_state, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  end
  if shots[frame] then
    local f = io.open(string.format("%s-%04d.png", OUT, frame), "wb")
    f:write(emu.takeScreenshot()); f:close()
  end
  if frame > LAST then
  if TILEMAP then dump(TILEMAP, 0x7EA000, 0x0800) end
  if TEXT_TILEMAP then dump(TEXT_TILEMAP, 0x7E8000, 0x4000) end
  if ARENA then dump(ARENA, 0x7F8000, 0x8000) end
  if VRAM then dump_vram(VRAM) end
  local f = io.open(OUT .. "-pointers.txt", "w")
  for _, v in ipairs(seen) do f:write(v) f:write("\n") end
  f:close(); emu.stop(0)
  end
end, emu.eventType.inputPolled)
