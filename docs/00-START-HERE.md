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

เอกสาร archive, test suite, Lua probe และ builder ทดลองถูกนำออกจาก working tree แล้ว
ย้อนดูไฟล์ที่เคย commit ได้จาก Git history ข้อความใน PLAN.md และ PROGRESS.md
ที่กล่าวถึงเครื่องมือเหล่านี้เป็นบันทึกทางประวัติศาสตร์ ไม่ใช่คำสั่ง build ปัจจุบัน

## ไฟล์ข้อมูลสำคัญ

| ไฟล์ | หน้าที่ |
|---|---|
| data/translations/ | source และคำแปลของ script/catalog/menu |
| data/translations/references/ | reference รวมแบบ generated สำหรับแปลบทสนทนา |
| data/font/ | glyph, cluster, encoding, icon และ override |
| data/config/ | ROM map, hooks, allocation, windows และ surfaces |
| src/srw4/ | parser, tokenizer, atlas, reference, repack และ runtime support |
| tools/ | build, verification, translation maintenance และ asset editors |
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

## สร้างแพตช์ EN→TH ปัจจุบัน

ใช้ Python 3.10 ขึ้นไป และเตรียม ROM เอง (ไม่เก็บ ROM ใน Git):

- EN Combo: ส่ง path ผ่าน `--input`
- JP Rev 1 สำหรับอ้างอิงโครงสร้าง: `rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc`

```sh
python3 tools/build_en_th_full_dialogue.py --input rom/srw4-en-combo.sfc
python3 tools/verify_en_th_full_dialogue.py --rom build/srw4-en-th.sfc
```

ผลลัพธ์คือ `build/srw4-en-th.sfc` และ `build/srw4-en-th.ips`
ตัว build ตรวจ stock English objectives ก่อนเขียนไฟล์เสมอ
บั๊กฟิก bare FA selectors และ English speaker runs อยู่ใน production source แล้ว

`tools/repair_v13_battle_quotes.py` และ `tools/fix_goshogun_english_names.py`
ยังเก็บไว้เพราะใช้สร้าง artifact v1.4 จาก ROM EN-based Thai v1.3 โดยตรง
การ full rebuild และการซ่อม artifact มีการจัดวางไบต์ต่างกัน:
อย่าอ้างว่า full rebuild ได้ SHA เดียวกับ v1.4 ที่เผยแพร่โดยไม่ได้ตรวจเทียบ
แพ็กเกจ xdelta v1.4 เดิมอยู่ใน `build/` และไม่ได้เป็นไฟล์ tracked
