# 8. การตรวจผลบนเครื่องจริง

## เครื่องมือ

Mesen (macOS: `/Applications/Mesen.app/Contents/MacOS/Mesen`) รันแบบไม่มีจอด้วย

```
Mesen --testRunner --testRunnerTimeout=<วินาที> --noAudio <rom.sfc> <script.lua>
```

สคริปต์ Lua ทำได้ครบ: โหลด/บันทึก save state, จำลองการกดปุ่ม, ถ่ายภาพจอ,
dump WRAM/VRAM, และ **ดัก read/write/exec ด้วย `emu.addMemoryCallback`**

API ที่ยืนยันแล้วว่าใช้ได้ในเวอร์ชันปัจจุบัน:

```lua
emu.addMemoryCallback(fn, emu.callbackType.exec,  lo, hi, emu.cpuType.snes)
emu.addMemoryCallback(fn, emu.callbackType.read,  lo, hi, emu.cpuType.snes)
emu.addMemoryCallback(fn, emu.callbackType.write, lo, hi, emu.cpuType.snes)
emu.addEventCallback(fn, emu.eventType.inputPolled)   -- ป้อนปุ่มตรงนี้
emu.addEventCallback(fn, emu.eventType.endFrame)      -- ถ่ายภาพ/ดัมพ์ตรงนี้
emu.read(addr, emu.memType.snesMemory, false)
emu.memType.snesWorkRam / snesVideoRam / snesPrgRom
```

**ที่อยู่ที่ใช้ดักต้องเป็นแบงก์ที่ CPU ใช้จริง** = มิเรอร์ `$80`/`$81` ไม่ใช่ `$C0`/`$C1`

## สูตรที่ใช้ได้ผล

**ดัก DMA** — เขียน callback ที่ write `$00:420B` (MDMAEN) แล้วอ่านพารามิเตอร์ของ
แชนแนลที่บิตถูกตั้ง: `$43x0` ctrl, `$43x1` ปลายทาง B-bus, `$43x2-4` ต้นทาง 24 บิต,
`$43x5-6` ขนาด, และ `$2116/$2117` คือที่อยู่ VRAM ปัจจุบัน

**หาว่าใครวาดข้อความ** — ดัก exec ที่ตัว parser/rasteriser แล้วอ่าน source pointer
จาก direct page (`$1A`/`$1C` ของฝั่ง ordinary) ตอน callback ยิง

**ปักหมุดหน้าต่างเวลา** — บันทึก state ที่เฟรมก่อนเหตุการณ์ แล้วรันสั้น ๆ จากตรงนั้น
เพื่อให้ log ไม่ท่วมและ cap ไม่ตัดข้อมูลที่ต้องการ

**เส้นทางบูตเปล่าไปถึงกลางเกม** (ไม่ต้องใช้ state ของใคร)

```
บูต → กด start ทุก 30 เฟรม (60–1300) → จอ LOAD
   → กด A ที่เฟรม 1350 บน DATA1 (ต้องมี .srm อยู่ในโฟลเดอร์ Saves ของ Mesen)
   → กด down 8 ครั้ง (เฟรม 1720 ทีละ 20) → A ที่ 1900 = "แผนที่ถัดไป"
   → กด A ทุก 20 เฟรม → การ์ดชื่อฉากขึ้นราวเฟรม 2800
```

## สี่ด่านที่ควรมีทุกครั้ง

1. unit test ของ pipeline (แปลง/เข้ารหัส/วางที่)
2. deterministic rebuild — build ซ้ำต้องได้ sha256 เดิม
3. byte diff เทียบบิลด์ก่อนหน้า — เห็นทุกอย่างที่เผลอแตะ
4. ภาพจากเครื่องจริงที่เกิดจากการวาดใหม่ระหว่างรัน ไม่ใช่ภาพที่ state พกมา

save state ที่มีอยู่แล้วอยู่ใน `saves/` (ของผู้เล่น) และ `saves/states/`
(ที่ทำไว้เพื่อเข้าจอเฉพาะ เช่น `battle-in-range`, `dialogue`, `pilot-intermission`,
`terrain-window`, `config-screen`, `blood-type`, `shielded-unit`)
