# Project Scope

- เป้าหมายปัจจุบันคือทำม็อดภาษาไทยสำหรับ **ROM English (EN)** เท่านั้น
- การ build, แก้โค้ด, ทดสอบ Mesen และใช้ savestate ต้องอ้างอิง ROM EN และ state ฝั่ง EN
- ROM Japanese (JP) เป็นงานเก่า ใช้เป็น reference ทางเทคนิคและแหล่งอ้างอิงคำแปลเท่านั้น
- ห้ามเปลี่ยนเป้าหมายไป build/release ROM JP หรือใช้ savestate JP เพื่อยืนยันบั๊กของ ROM EN เว้นแต่ผู้ใช้สั่งชัดเจน

# Dialogue Translation Reference

- ก่อนตรวจหรือแก้ชื่อ/ศัพท์ในบทสนทนา ต้องอ่าน `data/translations/references/README.md`
  และ `docs/09-translation-style.md`
- Source of truth คือไฟล์ catalog และ `glossary.th.json` ใน `data/translations/`;
  `data/translations/references/dialogue.th.json` เป็น generated file ห้ามแก้โดยตรง
- หลังแก้ source of truth ให้รัน `python3 tools/build_dialogue_reference.py` และยืนยัน
  `_meta.conflicts == 0`
- ตรวจบทสนทนาด้วย `python3 tools/audit_dialogue_reference.py --limit 10000 --samples 3`
- ต้องตรวจรายงานกับ `script.source.json` ทีละกลุ่ม ห้าม bulk replace โดยไม่อ่านบริบทญี่ปุ่น
- `rom-glossary.th.json` ใช้เฉพาะคำย่อสำหรับช่อง ROM แคบ ห้ามใช้เป็น canonical ของบทสนทนา
