# แหล่งอ้างอิงสำหรับแปลบทสนทนา

แพตช์เป้าหมายคือ ROM English (EN) เท่านั้น ให้ยึดข้อความและข้อจำกัดของ EN เมื่อแปล
ภาษาญี่ปุ่นใน `lookup` และ `script.source.json` เป็นบทพูดถอดเพื่อใช้อ้างอิงบริบทหรือ
ความหมายเมื่อ EN ไม่ชัดเจนเท่านั้น ไม่ใช่กฎการแปลหรือคำแปลมาตรฐาน

เปิด `dialogue.th.json` แล้วค้น `lookup` เพื่อเชื่อมบริบทของบทสนทนา ไฟล์เดียวนี้รวมชื่อ
และศัพท์ที่เกี่ยวข้องจาก:

- นักบินและชื่อสั้นบนป้าย (`pilots`, `pilot_labels`)
- ยูนิตและอาวุธ (`units`, `weapons`)
- ซีรีส์และภูมิประเทศ (`series`, `terrain`)
- บุคคล องค์กร สถานที่ และศัพท์ทั่วไป (`glossary`)

`dialogue.th.json` เป็นไฟล์ generated ห้ามแก้โดยตรง แก้ไฟล์ต้นทางใน
`data/translations/` แล้วสร้างใหม่ด้วย:

```bash
python3 tools/build_dialogue_reference.py
```

ตรวจชื่อและศัพท์อ้างอิงทั้งหมดในบทสนทนาด้วย:

```bash
python3 tools/audit_dialogue_reference.py --limit 10000 --samples 3
```

ตัวตรวจเทียบ `script.source.json` กับ `script.th.json` โดยใช้ `lookup` จาก reference
รวม ต้องตรวจผลแต่ละกลุ่มตามบริบทของข้อความ EN ห้าม bulk replace จากรายงาน
ภาษาญี่ปุ่นมีไว้ช่วยยืนยันความหมายเมื่อจำเป็นเท่านั้น

`glossary.th.json` ยังจำเป็น แต่มีหน้าที่เป็น **ศัพท์เสริมและคำสะกด canonical**
ที่ไม่มี record ใน catalog หรือใช้ override การสะกด ไม่ได้มีหน้าที่เก็บชื่อทุกชื่อ
ซ้ำกับ `pilots.th.json`, `units.th.json` และ `weapons.th.json`
