# 6. Surface — จอไหนอ่านข้อความจากที่ไหน

รายการนี้คือบัญชีที่เครื่องอ่านได้ ใช้เป็นเงื่อนไขของคำว่า "แปลครบ"
สถานะเอกสาร: นี่คือ surface inventory/reference ไม่ใช่ข้อสรุปว่าแต่ละจอต้องใช้ geometry เดิม
ทุก English ใน production target ต้องผ่าน new glyph; policy ที่เขียนว่า stock เป็น legacy wording
เมนูคำสั่งต้องใช้ active en path ที่ trace ใน P1 เพราะ source block เดิมยังไม่อธิบายภาพ reference
ไฟล์คำแปลทุกไฟล์อยู่ใน `data/translations/`

| surface | ข้อมูลอยู่ที่ | เครื่องยนต์ | นโยบาย |
|---|---|---|---|
| `battle.status_tokens` | clean ROM catalog $D2:8B8A (battle background names, including 夕/夜 variants) | ordinary | thai-or-new-english-glyph |
| `catalog.battle_pilot_labels` | `glossary.th.json` | battle | thai-with-new-english-glyph-and-digits |
| `catalog.pilot_names` | `pilots.th.json` | ordinary | thai-with-new-english-glyph-and-digits |
| `catalog.unit_names` | `units.th.json` | ordinary | thai-with-new-english-glyph-and-digits |
| `catalog.weapon_names` | `weapons.th.json` | ordinary | thai-with-new-english-glyph-and-digits |
| `intro.crawl_pages` | `intro*.th.json` | intro-special | thai-with-new-english-glyph-and-digits |
| `map.terrain_names` | `terrain-names.th.json` | ordinary | thai |
| `menu.bgm_titles` | clean ROM catalog $D2:9389 | ordinary | retain-original-japanese-song-titles-by-user-request |
| `menu.field_screens` | `screens.th.json` | ordinary | thai-or-new-english-glyph |
| `menu.intermission` | `intermission.th.json` | ordinary | thai-with-new-english-glyph-and-digits |
| `menu.main_and_system` | `main-menu-screens.th.json` | ordinary | thai-or-new-english-glyph |
| `menu.map_commands` | `map-menu.th.json` | ordinary | thai-or-new-english-glyph |
| `menu.map_hud` | `map-hud.th.json` | ordinary | new-english-glyph-and-digits |
| `menu.objective_text` | `script.th.json block 1` | ordinary | thai-with-new-english-glyph-and-digits |
| `menu.option_screen` | `option-menu.th.json` | ordinary | new-english-glyph-with-thai-prompts |
| `menu.part_effects` | clean ROM catalog $CC:E9BD | ordinary | thai-with-new-english-glyph-and-digits |
| `menu.pilot_status` | `pilot-status.th.json` | ordinary | thai-or-new-english-glyph |
| `menu.scenario_titles` | `scenario-titles.th.json` | ordinary | thai-with-new-english-glyph-and-digits |
| `menu.spirit_help` | `spirit-descriptions.th.json` | ordinary | thai-with-new-english-glyph-and-digits |
| `menu.spirit_selector` | `pilot-status.th.json` | ordinary | thai |
| `menu.unit_abilities` | `unit-abilities.th.json` | ordinary | thai-with-new-english-glyph-and-digits |
| `menu.unit_commands` | `unit-commands.th.json` | ordinary | thai-or-new-english-glyph |
| `menu.unit_status` | `unit-status.th.json` | ordinary | thai-or-new-english-glyph |
| `menu.unit_status_extras` | clean ROM catalog $D2:8103 records left by the unit-status adapter | ordinary | thai-or-new-english-glyph |
| `menu.weapon_detail` | `weapons.th.json and `weapon-detail.th.json` | ordinary | thai-or-new-english-glyph |
| `naming.keyboard` | font/thai.json | naming-special | thai-only-no-japanese-or-english-pages |
| `naming.labels` | `naming-screen.th.json and `protagonist-settings.th.json` | ordinary | thai |
| `naming.presets` | `naming-screen.th.json presets` | naming-special | thai |
| `naming.typed_buffer` | player input | ordinary-and-battle | thai |
| `song.lyrics` | clean ROM catalog $CB:667C | ordinary | retain-original-japanese-song-lyrics-by-user-request |
| `story.battle_quotes` | `script.th.json blocks 20-26` | battle | thai-with-new-english-glyph-and-digits |
| `story.dialogue` | `script.th.json` | ordinary | thai-with-new-english-glyph-and-digits |
| `story.runtime_fb_names` | `pilots.th.json and player buffers` | ordinary-and-battle | thai |
| `title.menu` | assets/title-menu.json | title-obj-resource | new-english-glyph |
| `title.stock_branding_and_credits` | `assets/title-logo.json` and stock legal-credit resources | title-resource | thai-logo-retain-original-legal-credits |
| `unknown.discovery` | master catalog table $C9:00D8 scan (tools/scan_catalog_residue.py) and runtime trace | unknown | must-resolve-before-release |

## หมายเหตุประกอบ

- **`intro.crawl_pages`** — หน้าเปิดเรื่อง 5 หน้า อยู่ใน record ของ `$CC:E9BD`
  slot 1–5 ตัวข้อความเป็นช่วงข้างในแต่ละ record ไม่ใช่ทั้ง record
  (`intro.th.json` + `intro-page2..5.th.json` เก็บ address/end/sha256 ไว้ครบ)
- **`battle.status_tokens` (`$D2:8B8A`)** — **ตัดออกได้** พิสูจน์แล้วด้วย read watch
  ตลอดวงจรการต่อสู้ว่าไม่มีจอไหนอ่าน เป็นตารางชื่อฉากหลังของนักพัฒนา
- **`menu.bgm_titles` / `song.lyrics`** — คงญี่ปุ่นตามที่ผู้ใช้ขอ
- **การ์ดชื่อฉาก `第N話`** — ไม่ได้อยู่ในบัญชีนี้เพราะไม่ใช่ข้อความ เป็นกราฟิก
- **ชื่อผู้เล่น** — อยู่ใน WRAM buffer ที่ `$00:1008`–`$00:104x` (มิเรอร์ `$7E:1000`)
  เข้าถึงผ่าน `FB` operand ช่วง `$8000`–`$81FF` ผ่านตาราง 24 บิตที่ `$C1:8E6E`
  (unit stride 11, pilot stride 7 และมีสำเนาชุดที่สองที่ `$00:1FA7`/`$00:1FD1`)

## จอที่รู้แล้วว่าอยู่ตรงไหน (สรุปจากงานที่ทำมา)

| จอ | ที่มาของข้อความ |
|---|---|
| หน้ารายชื่อ / ORDER คอลัมน์ซ้าย | catalog 7 (ชื่อสั้น) |
| หน้าสถานะยูนิต/นักบิน | สคริปต์ `$CC:9E80`–`$CC:A2A0` + catalog 13 |
| หน้าต่างอาวุธ (แผนที่/ฉากต่อสู้) | catalog 8 + หน้าต่าง 9/10 |
| เมนูคำสั่งยูนิต | `$D2:8613`–`$D2:865D` (ฟอนต์เดิม 3 ตัวอักษร) |
| กรอบทำนายผลก่อนเข้าฉากต่อสู้ | ชื่อยูนิต ชื่อนักบิน+LV ชื่ออาวุธ HIT — ไม่มีบรรทัดภูมิประเทศ |
| intermission | catalog 1 (pool) + `intermission.th.json` |
| หน้า LOAD / เซฟ | สคริปต์จอใน `$CC` + ชื่อฉากจาก catalog 14 |
| แถบ HUD บนแผนที่ | `$CC:9646` (`ターン数`), `$CC:9651` (`資金`), `$CC:96DE` (`搭載`) |
