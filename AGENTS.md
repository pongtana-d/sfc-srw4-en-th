# Project Scope

- เป้าหมายปัจจุบันคือทำม็อดภาษาไทยสำหรับ **ROM English (EN)** เท่านั้น
- การ build, แก้โค้ด, ทดสอบ Mesen และใช้ savestate ต้องอ้างอิง ROM EN และ state ฝั่ง EN
- ROM Japanese (JP) เป็นงานเก่า ใช้เป็น reference ทางเทคนิคและแหล่งอ้างอิงคำแปลเท่านั้น
- ห้ามเปลี่ยนเป้าหมายไป build/release ROM JP หรือใช้ savestate JP เพื่อยืนยันบั๊กของ ROM EN เว้นแต่ผู้ใช้สั่งชัดเจน
- Mesen2 savestate อยู่ที่ `/Users/mono-tong/Library/Application Support/Mesen2/SaveStates`

# Objective Policy

- Objective/เงื่อนไขภารกิจต้องคงภาษาอังกฤษจาก ROM EN เดิม (story block 1)
- ห้ามนำคำแปล block 1 ใน `script.th.json` กลับเข้า build หรือ repack block นี้
- ต้องสำรองช่วงข้อมูลเดิมจาก allocator และผ่าน `verify_stock_objectives` ก่อนเขียน ROM/IPS
- การเปลี่ยนนโยบายนี้ต้องมีคำสั่งผู้ใช้ชัดเจน

# Savestate Selection

- เมื่อผู้ใช้สั่งตรวจหรือโหลด `sstate` / `savestate` ให้ค้นหาใน `/Users/mono-tong/Library/Application Support/Mesen2/SaveStates` เป็นค่าเริ่มต้นเสมอ เว้นแต่ผู้ใช้ระบุ path อื่นชัดเจน
- `sstate1` หมายถึง slot 1 ของ ROM EN: `/Users/mono-tong/Library/Application Support/Mesen2/SaveStates/srw4-en-th_1.mss`; `sstateN` ให้ใช้ `srw4-en-th_N.mss` ตามหมายเลข slot
- ไฟล์ slot ในโฟลเดอร์นี้คือ savestate ที่ผู้ใช้ระบุ ห้ามตีความว่าเป็นเพียง cache แล้วเปลี่ยนไปใช้ไฟล์อื่น
- ห้ามใช้ state ใน workspace เช่น `bil.mss` หรือไฟล์ใน `build/` แทนเอง แม้ภาพหน้าจอจะคล้ายกัน หากไม่พบไฟล์ที่ระบุให้แจ้งผู้ใช้ก่อนเลือก state อื่น
- ก่อนทดสอบ ให้ยืนยัน path ของ state และ ROM EN ที่ใช้จริง ไม่ใช้ภาพหน้าจออย่างเดียวเป็นหลักฐานว่าโหลดถูกไฟล์

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
