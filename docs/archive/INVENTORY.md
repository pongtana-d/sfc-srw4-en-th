# Inventory ที่เก็บก่อนเริ่มใหม่

ตรวจเมื่อ 2026-08-19

## ข้อมูลหลัก

| กลุ่ม | ตำแหน่ง | จำนวน/สถานะ |
|---|---|---|
| Story source | `translations/script.source.json` | 9,400 messages |
| Story Thai | `translations/script.th.json` | 9,400 messages |
| Weapon catalog | `translations/weapons.*.json` | 503 unique records |
| Unit catalog | `translations/units.*.json` | 295 unique records |
| Pilot catalog | `translations/pilots.*.json` | 290 unique records |
| Battle speaker labels | `translations/glossary.th.json` | 320 IDs / 285 unique records |
| Naming labels/presets | `translations/naming-screen.th.json` | 5 labels / 25 presets |
| Naming keyboard | `src/srw4th/naming.py` + `font/` | 63 Thai keys / 3 rows |
| UI/intro/status | `translations/*.th.json` | เก็บครบจากระบบเดิม |
| Font model | `font/` | Thai glyphs, icons, shorthand, encoding, JP kanji |
| Translation review | `translations/*.md` | เก็บไว้ข้างข้อมูลที่ตรวจแล้ว |
| Technical research | `docs/legacy/` | text engine, rendering, measurements, pitfalls |
| Legacy source | `legacy/tools/` | implementation และเครื่องมือวิเคราะห์เดิม |
| Legacy tests | `legacy/tests/` | regression knowledge เดิม |

## ROM contract

- ชื่อฐาน: `Dai-4-ji Super Robot Taisen (Japan) (Rev 1)`
- ขนาด: 3,145,728 bytes
- mapper: HiROM + FastROM
- SHA-256: `efd72094b2727c4903924cf9296b3946b95a354f639b600e1d76d9ec6b9ca18b`
- ROM อยู่ใน `rom/` และถูก ignore จาก Git

## รายงานที่เก็บไว้

- `legacy/reports/menu-build-report.json` — hook, allocation, pointer และ renderer
- `legacy/reports/script-build-report.json` — การ repack story script
- `legacy/reports/title-build-report.json` — title resource patch

รายงานเหล่านี้เป็นหลักฐานจาก build เดิม ไม่ใช่ source of truth ของ Core ใหม่
ทุกตำแหน่งต้องตรวจซ้ำกับ clean ROM ก่อนใช้

## สิ่งที่ไม่เก็บใน Git

- clean/patched ROM
- emulator save state
- VRAM/WRAM dump และ trace ชั่วคราว
- ภาพทดลองหลายร้อยไฟล์ใน `build/mesen`
- TTF ภายนอกใน `assets/fonts/`

ไฟล์เหล่านี้ยังอยู่ในเครื่องและไม่ได้ถูกลบ การเลือก golden fixture จะทำใหม่หลัง Core เสถียร
