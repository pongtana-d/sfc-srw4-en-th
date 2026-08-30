# 5. ฟอนต์ กลิฟ และการประกอบตัวอักษร

สถานะเอกสาร: asset และ metrics ในไฟล์นี้เป็น baseline ที่นำกลับมาใช้ได้ แต่ geometry
ของเมนูและนโยบาย English ต้องยึด PLAN.md/PROGRESS.md ไม่ใช่ข้อสรุป legacy ในเอกสารนี้
## ของที่มีอยู่ใน `data/font/`

| ไฟล์ | คืออะไร |
|---|---|
| `thai.json` | รูปกลิฟไทยของโปรเจกต์ (ชุดหลัก) |
| `encoding.json` | byte ↔ ตัวอักษร ของหน้าโค้ดแบบ combining |
| `shorthand.json` | โค้ดย่อ: หนึ่งไบต์แทน base+mark |
| `jp-kanji.json` | ตารางคันจิของเกม (ใช้ถอดต้นฉบับ) |
| `icons.json`, `renewal-icons.json` | ภาพที่แทรกในบรรทัด (badge อาวุธ ฯลฯ) |
| `renewal-clusters.json` | manifest ของ token/cluster ที่ล็อกไว้ (สัญญาที่เข้า git) |
| `renewal-stock.json`, `renewal-overrides.json` | กลิฟที่ยืมจากฟอนต์เดิม / ที่ทับด้วยมือ |
| `config.json` | ค่าตั้งของชุดฟอนต์ |

ฟอนต์ต้นทางเป็น TTF อยู่ที่ `assets/fonts/RD CHULAJARUEK/`

## Baseline ที่มีอยู่ และ target ใหม่

### Legacy: หน้าโค้ดแบบ combining (ไม่ใช่ production target)

หนึ่งไบต์ต่อหนึ่งตัวอักษร มาร์คไม่กินความกว้าง ใช้ base ไทย 57 ตัว + มาร์ค 13 ตัว
ครอบคลุมภาษาได้ทั้งหมด เทียบกับหน้า precomposed ที่มันแทนที่ ซึ่งใช้ 213 + 228 กลิฟ
สองหน้าแล้วยังสะกดไม่ครบ

**ข้อบังคับ**: `$30`–`$39` ต้องเป็นเลขของฟอนต์เดิม เพราะเมนูเขียนตัวเลข runtime
ด้วยการยัดโค้ดพวกนี้ตรง ๆ

### Target: precomposed cluster atlas + VWF

ประกอบ base+มาร์คเป็น "หนึ่ง cluster = หนึ่งกลิฟ" ตั้งแต่ตอน build แล้วให้ตัววาด
ในเกมทำแค่ blit ตัวเลข จาก corpus จริง:

- token ไม่ซ้ำ 625 ตัว (cluster ไทย 563 / char ละติน-ตัวเลข 55 / icon 7)
- direct 208 + extended 417 → coverage ของบล็อก direct 97.61%
- bitmap หลัง dedupe 624 ตัว เนื้อ bitmap 9,984 ไบต์ — **เล็กกว่าหนึ่งแบงก์**
- ทุกตัว `cell_span = 1` ยังไม่มีกลิฟที่ล้นเซลล์

metrics ใช้ schema เดียวกันหมดทุกแหล่ง: `advance`, `ink_width`, `left`, `top`, English production glyph ทุกตัวต้องผ่าน atlas นี้ด้วย
`cell_span`, `flags` → blitter ตัวเดียวรับได้ทั้ง cluster ไทย กลิฟที่ยืมจากฟอนต์เดิม
และ icon **ไม่มีการสลับ renderer กลางบรรทัด**

ข้อดีที่ตัดสินใจได้เลย: ไม่ต้องมีตรรกะ combining ตอน runtime (โค้ดใน ROM สั้นลงมาก
และเป็นที่มาของบั๊กน้อยลงมาก) แลกกับพื้นที่ 10 KB ซึ่งมีเหลือเฟือ

## Cluster shorthand — เครื่องมือซื้อไบต์

โค้ดว่างในบล็อกช่องไฟ ใช้แทน base+มาร์ค 1–2 ตัว ขยายตอนวาด มีไว้ซื้อ **ไบต์**
ไม่ใช่พิกเซล และควร re-pick ใหม่ทุก build จากคำแปลจริง วัดกับที่ที่ยังล้นจริง ๆ

ลำดับความสำคัญ: pool ล้น = build fail มีข้อความบอก ส่วนชื่อที่ล้นเซลล์ = เงียบสนิท
แล้วจอฉีกตอน runtime → **ตัวที่เงียบต้องได้โค้ดก่อน**

## Geometry note

- clean/legacy command path เคยวัดได้ 24 px = 3 cell และใช้ MOV/ATK/TFM
- ภาพ en ยืนยันว่า active command menu ขยายกรอบและแสดงคำเต็ม
- active en path, tile geometry, cursor และ source stream ต้อง trace ใน P1
- target ใหม่ใช้ dynamic window spec; ห้ามใช้ 3 cell เป็น release constraint
- กรอบ profile เดิม 240 px × 9 บรรทัดเป็น baseline เท่านั้น ต้อง recheck เมื่อใช้ VWF

## เครื่องมือ: `tools/font_editor.py`

```bash
python3 tools/font_editor.py
```

เปิดหน้าแก้กลิฟที่ `http://127.0.0.1:8731` — แก้ `data/font/thai.json` (bases 133,
marks 13) และ `data/font/renewal-overrides.json`

**พรีวิวเดินผ่าน `AtlasBuilder` ตัวจริง** ไม่ได้เขียนกฎการประกอบซ้ำในเบราว์เซอร์
สิ่งที่เห็นคือสิ่งที่ atlas จะสร้าง แก้ base แล้วทุกคลัสเตอร์ที่ใช้ base นั้น
เลื่อนมาร์คตามทันที (มาร์คเกาะขอบขวาของหมึก base ตามกฎใน `placement`)

เมตริกที่**อธิบายบิตแมป** ถูกคำนวณใหม่ทุกครั้งที่วาด จึงไม่มีทางเพี้ยนจากพิกเซล:

| ชนิด | คำนวณให้ | ยังแก้เองได้ |
|---|---|---|
| base | `left` `ink` `top` | `advance` |
| mark | `sprite` `height` `width` `y` | `dx` |
| icon | `sha256` | `advance` `cell_span` |

มาร์คถูกเก็บชิดซ้ายเสมอ วาดตรงไหนในเซลล์ก็ได้ ตอน commit จะเลื่อนชิดซ้ายให้

แท็บ `icons` แก้ `renewal-icons.json` ได้ — คู่ที่เป็นภาพเดียวกันสองเซลล์
(`AiL`+`AiR`, `SpL`+`SpR`, `MAP_L`+`MAP_R`) จะแสดงอีกครึ่งเป็นสีเทาข้างๆ
จะได้วาดข้ามรอยต่อได้ ไอคอนเป็น fixed artwork ไม่มีการประกอบทับ

`sha256` ในไฟล์นั้นเดิมมีไว้พิสูจน์ว่า bitmap ยังตรงกับ manifest ที่ย้ายมา
(§16.2) ถ้าวาดใหม่ คำกล่าวนั้นไม่จริงแล้ว editor จึงประทับ hash ใหม่พร้อมใส่
`"redrawn": true` ไม่ใช่แอบคำนวณให้ตรงเงียบๆ

ช่อง Live text พิมพ์ `<AiL><AiR>` แทรกไอคอนดูในบรรทัดจริงได้ด้วย

Override ยังต้องมี reason + sample และต้องอ้างหลักฐานใน PLAN.md/PROGRESS.md
ปุ่ม Revert ต้องกดสองครั้ง และ **ไม่มีอะไรลงดิสก์จนกว่าจะกด Save** — save ที่ไม่ได้
แก้อะไรเลยต้องได้ไฟล์เดิมทุกไบต์ (รักษาระดับ indent ของแต่ละไฟล์ไว้)

ช่อง Live text วัดความกว้างจริงเทียบกรอบใน `data/config/text-windows.json`
และนับไบต์ตามบล็อกตรง/extended จึงตอบได้ทันทีว่าประโยคนี้ล้น 240 px ไหม
