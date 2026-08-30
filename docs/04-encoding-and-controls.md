# 4. การเข้ารหัสข้อความและ control byte

สถานะเอกสาร: ตาราง byte เดิมและ encoding v1 เป็น baseline ของงานก่อนหน้า
รูปแบบ production สุดท้ายต้อง re-lock ใน P2 ของ PLAN.md หลัง census corpus และ runtime controls
## ฝั่งต้นฉบับ (ไบต์ของเกม)

| ไบต์ | ความหมาย |
|---|---|
| `$00`–`$EF` | glyph ตัวเดียวจากฟอนต์ของเกม (คานะ/ตัวเลข/สัญลักษณ์) |
| `$F0`–`$F5` + 1 ไบต์ | คันจิ — index = `(lead−$F0)*$100 + operand` |
| `$F6` | ขึ้นบรรทัด |
| `$F7` | terminator ตัวที่สอง (ความหมายต่างจาก `$FF`) |
| `$FB` + 2 ไบต์ | แทรก record จาก catalog หรือชื่อ runtime |
| `$FC` + 1 ไบต์ | format/branch เช่น `<FC:08>` แตกตามนิสัยตัวเอก |
| `$FD` + 1 ไบต์ | ตั้งตำแหน่ง |
| `$FE` | นำหน้า operand ของ portrait/ผู้พูด |
| `$FF` | terminator หลัก |

จาก corpus จริง: escape ทั้งหมด 12,336 ครั้ง lead ไม่ซ้ำ 157 ตัว แต่ **lead ที่มี
operand จริงมีแค่สามตัว** คือ `$FB`, `$FC`, `$FD` ที่เหลือเป็นไบต์เดี่ยวหรือ operand
ของคำสั่งก่อนหน้า

## ฝั่งไฟล์แปล (escape notation)

| รูปแบบ | ตัวอย่าง | ความหมาย |
|---|---|---|
| `<XX>` | `<FE>` | engine byte หนึ่งไบต์ |
| `<XX:YY…>` | `<FC:05>` | lead + operand |
| `<ENDXX>` | `<ENDFF>`, `<ENDF7>` | terminator ของ record |
| `<NAME:$xxxx>` | `<NAME:$8012>` | แทรกชื่อ runtime |
| `<Name>` | `<AiL>`, `<B>` | icon ที่เป็น glyph ปกติ **ไม่ใช่ control** |
| `\n` | — | ขึ้นบรรทัด (`$F6`) |

**ห้ามตั้งชื่อ icon เป็นเลขฐานสิบหกสองหลัก** เพราะ tokenizer อ่าน escape ก่อน
`<B>` ปลอดภัยเพราะ B ตัวเดียวไม่ใช่เลขสองหลัก แต่ต้องอ่านทั้งวงเล็บ — `<B>` คือ
badge ของอาวุธ ไม่ใช่ตัวอักษร B

## นโยบายที่ควรใช้ต่อ: engine byte เดินทางแบบดิบ

ตัว renderer **ไม่ตีความ control byte ของเกมเลย** ทุกตัวถูกส่งคืนเครื่องยนต์เดิม
ตรง ๆ ผลคือความหมายเดิมไม่เปลี่ยนแม้จะเปลี่ยนการเข้ารหัสข้อความทั้งหมด
และไม่มีการชนกันระหว่าง control byte กับ glyph id

## byte map ของสตรีมใหม่ — historical baseline; final contract จะล็อกใหม่ใน P2

| ช่วง | ชนิด | ยาว | ความหมาย |
|---|---|---:|---|
| `$00`–`$CF` | direct glyph | 1 | glyph id = ค่าไบต์ (208 ช่อง) |
| `$D0`–`$D3` | extended glyph | 2 | lead เลือกหน้า 0–3 → 1,024 glyph |
| `$D4`–`$DF` | reserved | — | decoder ต้อง reject |
| `$E0` | RAW1 | 2 | engine byte หนึ่งไบต์ |
| `$E1` | RAWN | 2+n | engine bytes n ไบต์ |
| `$E2` | NEWLINE | 1 | |
| `$E3` | NAME | 3 | pointer little-endian |
| `$E4`–`$FE` | reserved | — | format control ของเราเอง (สี/ดีเลย์/portrait) |
| `$FF` | END | 2 | operand คือ terminator เดิม (`$F7`/`$FF`) |

**กฎ decoder**: reject ทันทีเมื่อเจอ lead ในช่วง reserved, extended ที่ไม่มี index,
RAWN ที่ประกาศยาวเกินข้อมูล, END/NAME ที่ operand ขาด หรือ glyph id เกิน token map

## สตรีมแบบอยู่ร่วมกับ engine เดิม — legacy integration reference

ตอนที่ยังให้เครื่องยนต์เดิมทำ portrait/delay/ขึ้นบรรทัด/terminator เอง ใช้รูปแบบนี้:

- glyph ของเราที่ `$00`–`$D3`
- control byte ของเกม **ดิบ ๆ ไม่ต้อง escape** ตั้งแต่ `$EC` ขึ้นไป รวม operand

สองช่วงไม่ชนกันเพราะ glyph สูงสุด `$D3` และเครื่องยนต์เริ่มถือว่าเป็น control ที่ `$EC`
ช่องว่าง `$D4`–`$EB` คือเหตุผลที่ไม่ต้อง escape อะไรเลย adapter ตัดสินทีละไบต์:
`< $D4` เราวาดเอง, `>= $D4` ปล่อยให้ loop เดิมกินไปทั้งชุดคำสั่ง

ตัวเลขจาก corpus: stream ทั้งชุด 479,623 ไบต์ (เฉพาะสคริปต์ 463,421) ขณะที่ของเดิม
ใช้ 522,938 ไบต์ — **เล็กกว่าที่เดิมอยู่แล้ว ไม่ต้องขยาย ROM เพื่อเนื้อเรื่อง**
