-- Recovery experiment for save/freeze.mss.  It changes only the emulated
-- pointer after the old state loads; neither the .mss nor the ROM is written.
local STATE = assert(os.getenv("SRW4_STATE"), "SRW4_STATE is required")
local OUT = assert(os.getenv("SRW4_OUT"), "SRW4_OUT is required")
local loaded, frame = false, 0

emu.addMemoryCallback(function()
  if loaded then return end
  local h = assert(io.open(STATE, "rb"))
  emu.loadSavestate(h:read("a"))
  h:close()
  -- 28_B118 was at $EB:B118 in the EN state.  The full Thai build moved its
  -- table slot 142 to $F5:84BE. Restarting the record is safe; mapping a
  -- mid-record byte offset is not, because Thai encoding has a different size.
  emu.write(0xCB, 0xBE, emu.memType.snesMemory)
  emu.write(0xCC, 0x84, emu.memType.snesMemory)
  emu.write(0xCD, 0xF5, emu.memType.snesMemory)
  emu.write(0x7EC000, 0x00, emu.memType.snesMemory)
  emu.write(0x7EC001, 0x00, emu.memType.snesMemory)
  loaded = true
end, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  emu.setInput({})
  if frame == 60 or frame == 120 then
    local h = assert(io.open(string.format("%s-%04d.png", OUT, frame), "wb"))
    h:write(emu.takeScreenshot())
    h:close()
  end
  if frame >= 140 then emu.stop(0) end
end, emu.eventType.inputPolled)
