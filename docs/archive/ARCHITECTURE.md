# โครงสร้าง Core ใหม่

## Data flow

```text
translation
    -> encoder
    -> text token stream
    -> layout/cluster rules
    -> renderer core
    -> screen adapter
    -> stock tile/VRAM contract
```

## ชั้นของระบบ

### ROM layer

รับผิดชอบ hash, address conversion, source-byte assertion, allocation, checksum
และ report เท่านั้น ชั้นนี้ไม่รู้จักภาษาไทย

### Text layer

รับผิดชอบ encoding, control code, shorthand, line width และการตรวจ round trip
ข้อมูลจริงอ่านจาก `font/` และ `translations/`

### Renderer layer

มี algorithm ภาษาไทยชุดเดียว Reference renderer ฝั่ง Python ใช้ตรวจ assembly renderer
แบบ pixel-for-pixel ส่วน state แยก ordinary/battle เพื่อไม่ชนกัน ชุดสระบนสองชั้น
ใช้ pair geometry ที่สร้างล่วงหน้า 30 แบบ โดยยังเก็บ encoding เป็นอักขระแยกตามปกติ
เพื่อไม่เปลี่ยนข้อความ ชื่อ และ save data

ป้ายคุณสมบัติอาวุธ (`<MAP_L>` `<MAP_R>` `<B>` `<P>` ซึ่งเดิมคือไบต์ `$EC`–`$EF`)
วาดเป็น glyph บนหน้าไทย ไม่ใช่ปล่อยไบต์เดิมให้ handler ของเกม เพราะ handler นั้น
ประกอบ cell จาก tile pool ตัวเดียวกับที่ VWF กำลังเติมอยู่ ป้ายหนึ่งอันจึงกิน 4 cell
ดัน tile index ของทุก cell ที่เหลือในหน้าไป `$18` แล้วฉีกแถวล่างสุดของรายการอาวุธ
ตัวอักษรลอกมาจากฟอนต์เดิมที่ `$2E8000 + code * 16` ทีละไบต์ ขนาดเท่าเดิมคือ 1 ไบต์
ต่อป้าย codes ทั้งสี่มาจาก spacing block โดยคืน shorthand cluster สี่ตัวให้ระบบ

### Adapter layer

เชื่อม renderer กับ text engine แต่ละชนิด เช่น pointer pool, dialogue, battle และ naming
adapter ระบุ source ranges และ memory contract ของตัวเอง แต่ห้ามทำ glyph layout ซ้ำ

การตัดสินว่าไบต์หนึ่งเป็นไทย ไทยแบบ fixed-width หรือของเดิม ใช้ตารางค้นหาใน `$FC`
ไม่ใช่การไล่เทียบ source range ทีละช่วง ตอนที่ยังไล่เทียบ ต้นทุนต่อไบต์โตตามจำนวน
ช่วงที่ประกาศไว้ พอเกินราวยี่สิบช่วง ทางเดินข้อความฝั่งฉากรบก็ทำงานไม่ทันเวลา และ
ลำดับฉากรบค้างถาวรทุกครั้งที่มีบทพูด ตารางแบ่งสามชั้น: bank ชี้ page table, page table
ตอบทั้งหน้าได้ในคำสั่งเดียว และเฉพาะหน้าที่ปนกันจึงอ่าน bitmap 1 บิตต่อไบต์

### Validation layer

ตรวจ static ก่อน จากนั้นจึงตรวจ emulator โดยเริ่มจาก cold boot และบังคับ redraw จริง

## พื้นที่ ROM ใหม่

พื้นที่ขยายถูกแบ่งเต็ม bank และห้าม adapter จองข้ามเขต:

- `$F0-$F9` — story/battle script
- `$FA-$FB` — translated data และ route tables
- `$FC` — ตารางค้นหา route ของ source pointer และพื้นที่สำรอง static font
- `$FD-$FE` — adapters
- `$FF` — glyph page, metrics, shorthand, shift tables, parser และ renderer Core กลาง

glyph และตารางที่ renderer อ่านแบบ 16-bit อยู่ bank เดียวกับ renderer เพราะ
stock rasterizer contract ใช้ Data Bank Register พื้นที่ `$FC` จะใช้เมื่อ Core
รองรับการอ่านแบบ absolute-long ครบทุกตารางแล้วเท่านั้น

รายละเอียดที่เครื่องมือตรวจได้อยู่ใน `config/memory-map.json`

## โครง directory

```text
config/              ROM map และ memory registry
src/srw4th/           Core ใหม่
tools/                CLI ของระบบใหม่
tests/                tests ของ Core ใหม่
translations/         source และคำแปลที่อนุมัติแล้ว
font/                 glyph/encoding source
assets/               source asset พิเศษ
docs/                 แผนและสัญญาของระบบใหม่
docs/legacy/          เอกสารระบบเดิม
legacy/tools/         source เดิมสำหรับอ้างอิง
legacy/tests/         tests เดิมสำหรับอ้างอิง
legacy/reports/       รายงาน build เดิมที่คัดไว้
```
