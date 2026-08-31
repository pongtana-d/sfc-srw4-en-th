# แหล่งอ้างอิงสำหรับแปลบทสนทนา

เปิด `dialogue.th.json` แล้วค้นคำภาษาญี่ปุ่นจาก `lookup` เมื่อต้องแปล
บทสนทนา ไฟล์เดียวนี้รวมชื่อและศัพท์ที่เกี่ยวข้องจาก:

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

ตัวตรวจเทียบ `script.source.json` กับ `script.th.json` โดยใช้ `lookup` จาก
reference รวม ต้องตรวจผลแต่ละกลุ่มตามบริบท ห้าม bulk replace จากรายงานโดยไม่อ่าน
ต้นฉบับญี่ปุ่น

`glossary.th.json` ยังจำเป็น แต่มีหน้าที่เป็น **ศัพท์เสริมและคำสะกด canonical**
ที่ไม่มี record ใน catalog หรือใช้ override การสะกด ไม่ได้มีหน้าที่เก็บชื่อทุกชื่อ
ซ้ำกับ `pilots.th.json`, `units.th.json` และ `weapons.th.json`
