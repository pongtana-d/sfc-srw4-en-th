# เริ่มที่นี่

เอกสารหลักของงานรอบนี้มีสองไฟล์:

- PLAN.md — architecture และ phase gate ที่ต้องยึด
- docs/PROGRESS.md — สถานะงาน, evidence, decision และ blocker ปัจจุบัน

เป้าหมายคือทำระบบข้อความและ UI ให้คุณภาพเทียบ en-sample โดยใช้ new glyph,
Thai precompose + VWF, string pool แบบ variable-length และกรอบ tile ที่ขยายได้
ตาม surface ไม่ใช่การประคองข้อจำกัด 3 ช่องของระบบเดิม

## เอกสารอ้างอิง

เอกสารใน docs/01 ถึง docs/09 เป็นข้อเท็จจริงและวิธีตรวจที่ถอดจาก ROM/เครื่องจริง
ให้ใช้เป็น evidence/reference เท่านั้น หากขัดกับ PLAN.md ต้องตรวจหลักฐานใหม่ก่อน
ส่วน docs/99 เป็นรายการ unresolved evidence ที่ถูกรวมงานต่อใน PROGRESS.md

- docs/01-rom-and-addressing.md — ROM, HiROM, mirror, expansion และ hook
- docs/02-catalogs-and-pointers.md — master catalog และ pointer rules
- docs/03-text-engines.md — stock engine contracts และ state ที่ต้องระวัง
- docs/04-encoding-and-controls.md — source byte และ control boundary
- docs/05-font-and-glyphs.md — glyph, cluster, metrics และข้อจำกัด legacy
- docs/06-surfaces.md — surface inventory และ policy
- docs/07-pitfalls.md — กับดักจากการทดสอบที่ผ่านมา
- docs/08-verification.md — วิธีตรวจ genuine redraw และ emulator
- docs/09-translation-style.md — ศัพท์และนโยบายการแปล
- docs/99-open-questions.md — evidence ที่ยังไม่ปิด

เอกสารใน docs/archive/legacy เป็นหลักฐานเก่าที่เก็บไว้ย้อนตรวจได้
ไม่ใช่ source of truth และไม่ควรนำข้อจำกัดเก่ามาเป็น target โดยไม่ตรวจซ้ำ

## ไฟล์ข้อมูลสำคัญ

| ไฟล์ | หน้าที่ |
|---|---|
| data/translations/ | source และคำแปลของ script/catalog/menu |
| data/translations/references/ | reference รวมแบบ generated สำหรับแปลบทสนทนา |
| data/font/ | glyph, cluster, encoding, icon และ override |
| data/config/ | ROM map, hooks, allocation, windows และ surfaces |
| src/srw4/ | parser, tokenizer, atlas, reference, repack และ runtime support |
| tools/ | compiler, build, audit, emulator และ diagnostic tools |
| tests/ | unit, fixture, golden และ integration tests |
| assets/ | TTF และ resource ที่ใช้สร้าง asset |
| rom/ | clean ROM; ห้ามแก้โดยตรง |
| build/ | artifact ที่สร้างใหม่ได้; ไม่ใช่ source of truth |

## ลำดับการทำงาน

1. อ่าน PLAN.md
2. อ่าน docs/PROGRESS.md
3. อ่าน docs/07-pitfalls.md และ docs/08-verification.md ก่อนทดสอบ emulator
4. อ่าน docs/01 ถึง docs/06 เฉพาะตอนทำ phase ที่เกี่ยวข้อง
5. อัปเดต PROGRESS ทุกครั้งที่มีคำตัดสินหรือหลักฐานใหม่

ROM clean ต้อง read-only เสมอ และผลสำเร็จต้องพิสูจน์จาก genuine redraw,
deterministic build และ report ที่ย้อนตรวจได้
