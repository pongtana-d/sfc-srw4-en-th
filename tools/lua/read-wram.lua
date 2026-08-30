local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local LAST = tonumber(os.getenv("SRW4_FRAMES") or "1800")
local frame = 0
emu.addEventCallback(function()
  frame = frame + 1
  if frame < LAST then return end
  local f = assert(io.open(OUT, "w"))
  for _, address in ipairs({0x7EC000, 0x7EFA30, 0x7EFA31, 0x7EFA32}) do
    f:write(string.format("%06X=%02X\n", address,
      emu.read(address, emu.memType.snesMemory, false)))
  end
  f:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
