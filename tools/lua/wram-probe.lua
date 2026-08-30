-- Measure which parts of WRAM the game leaves alone in one context.
--
-- Mesen counts every access natively, so there is no per-write Lua callback
-- here: the counters are reset once the context has been entered, and read
-- back at the end. Anything with a zero write count was never touched while
-- the game was doing whatever the input script made it do.
--
-- Driven by environment variables so the Python wrapper stays the only place
-- that knows about paths:
--   SRW4_PRESS      "frame:frame:button,..." buttons held over a frame range
--   SRW4_RESET_AT   frame at which to reset the counters (end of setup)
--   SRW4_LAST       frame at which to dump and stop
--   SRW4_LOAD       save state to load before anything else (optional)
--   SRW4_SAVE       "frame:path" save a state on the way through (optional)
--   SRW4_OUT        where to write the write-count dump
--   SRW4_SHOT       where to write a screenshot at the end (optional)

local function env(name, fallback)
  local value = os.getenv(name)
  if value == nil or value == "" then return fallback end
  return value
end

local RESET_AT = tonumber(env("SRW4_RESET_AT", "0"))
local LAST = tonumber(env("SRW4_LAST", "600"))
local OUT = env("SRW4_OUT", "build/reports/wram.bin")
local SHOT = env("SRW4_SHOT", nil)
local LOAD = env("SRW4_LOAD", nil)
local SAVE = env("SRW4_SAVE", nil)

local presses = {}
for entry in string.gmatch(env("SRW4_PRESS", ""), "[^,]+") do
  local from, to, button = string.match(entry, "(%d+):(%d+):(%a+)")
  if from then
    presses[#presses + 1] = { from = tonumber(from), to = tonumber(to), button = button }
  end
end

local save_frame, save_path
if SAVE then
  local frame, path = string.match(SAVE, "(%d+):(.+)")
  save_frame, save_path = tonumber(frame), path
end

local frame = 0
local loaded = false

-- Mesen only allows a savestate to be taken or restored on an instruction
-- boundary, so both go through a one-shot exec callback: arm it, let the next
-- instruction in the mirror bank fire it, then take it back down again.
local pending = nil
local armed = nil

local function onExec()
  local action = pending
  pending = nil
  if armed then
    emu.removeMemoryCallback(armed, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
    armed = nil
  end
  if action == nil then return end
  if action.kind == "save" then
    local handle = io.open(action.path, "wb")
    handle:write(emu.createSavestate())
    handle:close()
    emu.log("saved state to " .. action.path)
  else
    local handle = io.open(action.path, "rb")
    if handle == nil then error("cannot open state " .. action.path) end
    local data = handle:read("a")
    handle:close()
    emu.loadSavestate(data)
    emu.log("loaded state " .. action.path)
  end
end

local function request(kind, path)
  pending = { kind = kind, path = path }
  if armed == nil then
    armed = onExec
    emu.addMemoryCallback(onExec, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
  end
end

local function onInput()
  frame = frame + 1
  local held = {}
  local any = false
  for _, press in ipairs(presses) do
    if frame >= press.from and frame <= press.to then
      held[press.button] = true
      any = true
    end
  end
  if any then emu.setInput(held, 0) end
end

local function onFrame()
  if LOAD and not loaded then
    loaded = true
    request("load", LOAD)
    return
  end
  if frame == RESET_AT then
    emu.resetAccessCounters()
    emu.log("counters reset at frame " .. frame)
  end
  if save_frame and frame == save_frame then
    request("save", save_path)
  end
  if frame >= LAST then
    local counts = emu.getAccessCounters(emu.memType.snesWorkRam, emu.counterType.writeCount)
    local size = emu.getMemorySize(emu.memType.snesWorkRam)
    local out = io.open(OUT, "wb")
    -- One byte per address: 0 = never written, 1 = written at least once.
    local chunk = {}
    for address = 0, size - 1 do
      local count = counts[address] or 0
      chunk[#chunk + 1] = string.char(count > 0 and 1 or 0)
      if #chunk == 4096 then
        out:write(table.concat(chunk))
        chunk = {}
      end
    end
    out:write(table.concat(chunk))
    out:close()
    if SHOT then
      local png = io.open(SHOT, "wb")
      png:write(emu.takeScreenshot())
      png:close()
    end
    emu.log("dumped " .. size .. " counters to " .. OUT)
    emu.stop(0)
  end
end

emu.addEventCallback(onInput, emu.eventType.inputPolled)
emu.addEventCallback(onFrame, emu.eventType.endFrame)
