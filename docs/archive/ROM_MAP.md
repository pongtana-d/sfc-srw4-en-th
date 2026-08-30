# ROM Map Registry

ไฟล์กลางคือ `config/rom-map.json` และ hook อยู่ใน `config/hooks.json`
โดยช่วง address ใช้ `start` แบบรวมจุดเริ่มและ
`end` แบบไม่รวมจุดจบ เพื่อให้คำนวณขนาดและตรวจพื้นที่ซ้อนได้ตรงกัน

สถานะของข้อมูลมีสามระดับ:

- `legacy` — มาจากระบบเดิมและยังห้าม patch
- `verified` — ตรวจ source bytes/โครงสร้างกับ clean ROM แล้ว
- `active` — ถูกใช้โดย Core ใหม่และมี regression test

ทุก hook ที่จะเปิดใช้ต้องเพิ่มข้อมูลต่อไปนี้:

- PC address และ CPU address
- source bytes ที่คาดไว้
- replacement หรือ trampoline owner
- continuation address
- register/flag contract ตอนเข้าและออก
- WRAM/VRAM ที่อ่านหรือเขียน
- test ที่ยืนยันจุดนั้น

รายงานเก่าใน `legacy/reports/` ใช้ช่วยดึงรายการ แต่ไม่ถือว่า verified โดยอัตโนมัติ

## Catalog checkpoint ที่ใช้งานใน Core แล้ว

- pointer table: weapon `$CC:7760`, unit `$D2:6050`, pilot `$D2:6B34`,
  battle speaker `$D2:772B`
- string pool ทุกช่วงยังอยู่ใน CPU bank เดิม เพราะ pointer ของเกมกว้าง 16-bit
- ใช้ original pool ก่อน แล้วจึงใช้เฉพาะ FF run ที่ตรวจ clean ROM แล้ว
- ช่วง `$D2:FF83-$D2:FFFF` ยังไม่ใช้ใน catalog เพื่อสงวนให้ spirit names
- stock English runs อยู่ใน expanded data region และอ้างผ่านตาราง 24-bit
- battle speaker pool `$D2:79AB-$D2:7F02` ใช้ 1,153/1,368 bytes

## Naming checkpoint ที่ใช้งานใน Core แล้ว

- ตารางคีย์ input อยู่ที่ PC `$03A082` และ `$03A106`; ใช้คีย์ไทย 63 ตัว
- ตาราง navigation/hitbox อยู่ในช่วง PC `$03A1CA-$03A26C`
- ข้อความ grid แบบ fixed-width มาจาก `$CC:AB5E-$CC:ABE2` และ
  `$CC:AC53-$CC:AC8A`
- label และจุด `F8` ที่วาด live buffer route เข้า ordinary Thai VWF
- runtime name route ครอบคลุม ROM bank `$00` และ WRAM `$7E:DFE5-$7E:DFFF`
- preset pointer table PC `$128347`; pool PC `$1288ED-$12897C` ใช้ครบ
  144 bytes โดยคง buffer limit เดิม
- fixed-width naming renderer อยู่ใน expanded ROM แยกจาก ordinary/battle renderer
  แต่ใช้ glyph/layout algorithm เดียวกัน

## Upper-stack checkpoint ที่ใช้งานใน Core แล้ว

- overlay 30 คู่ครอบคลุมสระบน 6 ตัวและวรรณยุกต์ 5 ตัว
- asset อยู่ใน Core bank `$FF`; address จริงบันทึกใน build report ทุกครั้ง
- renderer เก็บตำแหน่งสระชั้นแรกหลัง collision lift แล้ววางชั้นสองจาก pair geometry
- byte stream, pointer pool, runtime-name buffer และ save format ไม่เปลี่ยน
- ordinary fixture ครบ 30 คู่และ battle fixture ผ่าน pixel comparison กับ reference

milestone ปัจจุบันเปิด parser, stock-run FB handler และ renderer dispatch สำหรับ
catalog, runtime player-name และหน้าตั้งชื่อที่ตรวจแล้ว ยังไม่ใช่ ROM release เพราะ
story/menu/special renderer และ full-game regression ยังไม่ครบ

ตรวจ registry กับ clean ROM:

```bash
python3 tools/verify_rom_map.py \
  --input "rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc" \
  --report build/rom-map-verification.json
```

ตรวจ source text และ fixed-field offsets ทั้งหมดที่มีหลักฐานในไฟล์คำแปล:

```bash
python3 tools/verify_sources.py \
  --input "rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc" \
  --report build/source-verification.json
```

## ตารางแม่ของ catalog

`$C9:00D8` เก็บ pointer 24-bit จำนวน 19 ช่อง ชี้ไปยังตาราง pointer 16-bit ของแต่ละ
catalog ในแบงก์เดียวกัน pointer แรกของแต่ละตารางคือจุดเริ่ม pool จึงคำนวณจำนวน
record ได้โดยไม่ต้องเดา บางช่องเป็นฐานที่เลื่อนเข้าไปในตารางของช่องอื่น
(`$CC:7960`, `$CC:7B60`, `$D2:6250`, `$D2:82C3`) และช่อง 3 เป็นช่องว่าง ส่วนช่อง 18
ชี้ไปข้อมูลกราฟิกในแบงก์ `$A2` ไม่ใช่ catalog

ตรวจ record ที่ยังเป็นญี่ปุ่นในไฟล์ที่ build ได้:

```bash
python3 tools/scan_catalog_residue.py \
  --clean "rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc" \
  --built build/srw4-th-intro.sfc \
  --report build/catalog-residue.json
```

## Terrain checkpoint ที่ย้ายออกจากแบงก์เดิม

catalog 11 (`$D2:7F03` + pool `$D2:7FC3-$D2:8103`) ถูกอ้างจากตารางแม่จุดเดียว
(`long D2:7F03` มีที่เดียวใน ROM สะอาดคือ entry ที่ PC `0x0900F9`) และ handler
โหลด pointer ทั้ง 24 บิตเข้า `$1A-$1C` ดังนั้นสตริงอ่านจากแบงก์ของตารางเอง
Core จึงย้ายทั้งตารางและ pool ไปที่ region `text_data` แล้วแก้เฉพาะ entry ในตารางแม่
พื้นที่เดิมในแบงก์ `$D2` 576 ไบต์จึงว่างลงและยังไม่ถูกใช้

```bash
python3 tools/build_terrain.py \
  --input "rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc" \
  --output build/srw4-th-terrain.sfc \
  --report build/terrain-report.json
```
