-- Trace the active EN Spirit-name path from the reproducible post-battle map state.
local STATE = assert(os.getenv("SRW4_STATE"))
local OUT = assert(os.getenv("SRW4_OUT"))
local frame, loaded, armed = 0, false, true
local events, counts = {}, {}

local function word(dp)
  return emu.read(dp, emu.memType.snesMemory, false)
    | (emu.read(dp + 1, emu.memType.snesMemory, false) << 8)
end

local function trace(label, address)
  counts[label] = 0
  emu.addMemoryCallback(function()
    if not loaded then return end
    counts[label] = counts[label] + 1
    if frame >= 240 and #events < 240 then
      events[#events + 1] = label .. " p=" .. tostring(
        emu.read(0x1A, emu.memType.snesMemory, false)) .. "," .. tostring(
        emu.read(0x1B, emu.memType.snesMemory, false)) .. "," .. tostring(
        emu.read(0x1C, emu.memType.snesMemory, false))
    end
  end, emu.callbackType.exec, address, address, emu.cpuType.snes)
end

for _, item in ipairs({
  {"parser1", 0xFD9800}, {"parser2", 0xFD99C0},
  {"class1", 0xFD9AC0}, {"class2", 0xFD9BC0},
  {"dispatch", 0xFD9D50}, {"cluster", 0xFFF200},
  {"spirit", 0xEC0200}, {"catalog", 0xFFF800},
  {"stock", 0xF0E045},
}) do trace(item[1], item[2]) end

local function load_state()
  if not armed then return end
  armed = false
  emu.removeMemoryCallback(load_state, emu.callbackType.exec,
    0x808000, 0x80FFFF, emu.cpuType.snes)
  local file = assert(io.open(STATE, "rb"))
  emu.loadSavestate(file:read("a")); file:close(); loaded = true
end
emu.addMemoryCallback(load_state, emu.callbackType.exec,
  0x808000, 0x80FFFF, emu.cpuType.snes)

local presses = {
  [30]="down", [60]="down", [90]="right", [120]="a",
  [180]="down", [210]="down", [240]="a",
}
emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  if presses[frame] then emu.setInput({[presses[frame]]=true}, 0)
  else emu.setInput({}, 0) end
  if frame == 300 then
    local shot = assert(io.open(OUT .. ".png", "wb"))
    shot:write(emu.takeScreenshot()); shot:close()
  end
  if frame >= 340 then
    local log = assert(io.open(OUT .. ".txt", "w"))
    for _, line in ipairs(events) do log:write(line, "\n") end
    for label, count in pairs(counts) do
      log:write(string.format("COUNT %-12s %d\n", label, count))
    end
    log:close(); emu.stop(0)
  end
end, emu.eventType.inputPolled)
