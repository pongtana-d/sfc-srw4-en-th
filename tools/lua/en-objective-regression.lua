-- Read-only replay of an EN state saved with Objectives open.
-- B closes the stale framebuffer; A requests a fresh native objective draw.
local state = assert(os.getenv("SRW4_STATE"))
local out = assert(os.getenv("SRW4_OUT"))
local loaded, frame = false, 0
local stock, thai = 0, 0
emu.addMemoryCallback(function()
  if loaded then return end
  loaded = true
  local f = assert(io.open(state, "rb"))
  emu.loadSavestate(f:read("a")); f:close()
end, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)
-- Public renderer entries from en_th_renderer.py.
for _, address in ipairs({0xFFA000, 0xFFB000, 0xFFC000}) do
  emu.addMemoryCallback(function()
    if not loaded or frame < 100 then return end
    if address == 0xFFC000 then stock = stock + 1 else thai = thai + 1 end
  end, emu.callbackType.exec, address, address, emu.cpuType.snes)
end
emu.addEventCallback(function()
  if not loaded then return end
  frame = frame + 1
  emu.setInput({b = frame >= 30 and frame < 45,
                a = frame >= 100 and frame < 115}, 0)
  if frame ~= 180 then return end
  local f = assert(io.open(out .. ".png", "wb"))
  f:write(emu.takeScreenshot()); f:close()
  f = assert(io.open(out .. ".txt", "w"))
  f:write(string.format("stock_glyphs=%d thai_glyphs=%d\n", stock, thai)); f:close()
  emu.stop(stock > 0 and thai == 0 and 0 or 1)
end, emu.eventType.inputPolled)
