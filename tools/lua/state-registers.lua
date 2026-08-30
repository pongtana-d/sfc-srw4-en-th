-- Read the story cursor after Mesen has restored a supplied savestate.
local state = assert(os.getenv("SRW4_STATE"), "SRW4_STATE required")
local out = assert(os.getenv("SRW4_OUT"), "SRW4_OUT required")
local loaded = false

emu.addMemoryCallback(function()
  if loaded then return end
  local handle = assert(io.open(state, "rb"))
  emu.loadSavestate(handle:read("a"))
  handle:close()
  loaded = true
end, emu.callbackType.exec, 0x808000, 0x80FFFF, emu.cpuType.snes)

emu.addEventCallback(function()
  if not loaded then return end
  local function read(address)
    return emu.read(address, emu.memType.snesMemory, false)
  end
  local pointer = read(0xCB) | (read(0xCC) << 8) | (read(0xCD) << 16)
  local output = assert(io.open(out, "w"))
  output:write(string.format("pointer=%06X glyph=%04X state=%04X\n",
    pointer,
    read(0x02) | (read(0x03) << 8),
    read(0x0E2A) | (read(0x0E2B) << 8)))
  local ok_lo, page_lo = pcall(emu.read, 0xFFDC, emu.memType.snesWorkRam, false)
  local ok_hi, page_hi = pcall(emu.read, 0xFFDD, emu.memType.snesWorkRam, false)
  if ok_lo and ok_hi then
    output:write(string.format("page_ffdc=%04X\n", page_lo | (page_hi << 8)))
  else
    output:write(string.format("page_error=%s / %s\n", tostring(page_lo), tostring(page_hi)))
  end
  for offset = 0, 31 do
    output:write(string.format("%02X%s", read(pointer + offset), offset == 31 and "\n" or " "))
  end
  output:close()
  emu.stop(0)
end, emu.eventType.inputPolled)
