-- Run the blitter fixture ROM and dump what it drew.
--
-- The harness sets a marker once it has finished every fixture, so this waits
-- for the marker rather than for a frame count: a run that never gets there is
-- a failure worth reporting, not a shorter dump.
local OUT = os.getenv("SRW4_OUT") or "build/fixture/dump.bin"
local BYTES = tonumber(os.getenv("SRW4_BYTES") or "8192")
local MARKER = tonumber(os.getenv("SRW4_MARKER") or "0x7FF000")
local LAST = tonumber(os.getenv("SRW4_LAST") or "180")

local frame = 0

local function onFrame()
  frame = frame + 1
  local low = emu.read(MARKER, emu.memType.snesMemory, false)
  local high = emu.read(MARKER + 1, emu.memType.snesMemory, false)
  local done = (low == 0xEF and high == 0xBE)

  if done or frame >= LAST then
    local out = io.open(OUT, "wb")
    local chunk = {}
    for offset = 0, BYTES - 1 do
      chunk[#chunk + 1] = string.char(
        emu.read(0x7F0000 + offset, emu.memType.snesMemory, false)
      )
      if #chunk == 4096 then
        out:write(table.concat(chunk))
        chunk = {}
      end
    end
    out:write(table.concat(chunk))
    out:close()
    emu.log(done and ("finished at frame " .. frame) or "MARKER NEVER SET")
    emu.stop(done and 0 or 1)
  end
end

emu.addEventCallback(onFrame, emu.eventType.endFrame)
