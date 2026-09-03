# PLAN — Thai Dialogue Overlay บน English ROM

สถานะ: แผนก่อนเริ่ม implementation  
วันที่: 2026-08-28  
เป้าหมายฐาน: `rom/Dai-4-ji Super Robot Taisen (English).sfc`

## 1. ข้อสรุปความเป็นไปได้

**ทำได้** แต่ห้าม copy byte หรือใช้ offset ของ JP ไปเขียนทับ EN โดยตรง เพราะ English
patch ย้าย story blocks จากช่วงเดิม `$E8-$ED` ไป `$F1-$FC` และเปลี่ยน text renderer
ให้ ordinary/story เรียก code ใน `$F0`

หลักฐานปัจจุบัน:

- JP Rev 1: 3,145,728 bytes, SHA-256
  `efd72094b2727c4903924cf9296b3946b95a354f639b600e1d76d9ec6b9ca18b`
- English: 4,194,304 bytes, SHA-256
  `7cac9fc9c092c82cb753ebc8c8af6de25c2957ee4fbdee0f10676f1d0a661f2c`
- `srw4e.xdelta` สร้าง English ROM hash เดียวกันจาก JP Rev 1 จึงยืนยันว่าเป็นเกมฐานเดียวกัน
- story master table ยังมี 52 slots โดย 47 slots เป็น text blocks
- corpus ปัจจุบันมี pointer slots 10,439 ช่อง, message occurrences 9,400 รายการ
  และคำแปลไทย 9,382 unique records
- pointer ของ EN อยู่ใน block เป้าหมายถูกต้อง 10,439/10,439 ช่อง
- alias pattern ของ JP/EN ตรงกัน 10,375/10,439 ช่อง; 64 ช่องที่ต่างอยู่ใน block 48
  เพียง block เดียวและต้อง audit แบบ manual

ดังนั้น identity หลักใช้ `(master block slot, pointer index, control-flow signature)` ได้
ส่วนข้อความ JP/EN ใช้ยืนยันความหมายเท่านั้น ไม่ใช้ fuzzy text match แล้วเขียน ROM อัตโนมัติ

## 2. Scope

### รวมในงาน

- ใช้ English ROM hash ที่ล็อกไว้เป็น base ของ mod
- ย้ายคำแปลจาก `data/translations/script.th.json` เข้า story script ทั้ง 47 text blocks
- รองรับ map dialogue, event dialogue, battle quotes และ record ประกอบ story script
- พอร์ตเฉพาะส่วน font/encoding/parser/renderer ที่จำเป็นต่อการวาดภาษาไทยใน story path
- สร้าง patch, manifest, mapping report, build report และชุดทดสอบที่สร้างซ้ำได้

### ไม่รวมในงาน

- menu, unit/pilot/weapon names, status, option, encyclopedia, title และกราฟิกของ English ROM
- การพอร์ต Thai UI/catalog จาก JP-based build เดิม
- การแก้ clean JP ROM หรือ English base ROM โดยตรง
- การแจก ROM สำเร็จรูป

### Assumption ที่ต้องยืนยันใน P0

คำว่า “บทสนทนาทั้งหมด” ในแผนนี้หมายถึง **ทั้ง story corpus 47 blocks** รวม map/event
dialogue และ battle quotes ทุก route ที่ EN ROM เข้าถึงได้ ไม่ใช่เฉพาะ save state ตัวอย่าง
objective/game-over/system records ที่อยู่ใน pool เดียวกันให้คงอังกฤษ เว้นแต่เป็นบทสนทนา
โดยตรง; catalog/UI ภายนอก story corpus ไม่อยู่ใน scope

runtime name ที่แทรกจาก English catalog ให้คงเป็นอังกฤษตาม scope; ชื่อที่เป็นข้อความตรงใน
`script.th.json` ยังคงเป็นไทย การแปล catalog-backed names ถือเป็น scope เพิ่ม

## 3. หลักการออกแบบ

1. ROM ต้นฉบับทั้งสองไฟล์เป็น read-only; build เขียนเฉพาะ `build/`
2. ทุก hook ต้องตรวจ expected bytes ของ English hash ก่อนเขียน
3. ใช้ message identity และ pointer graph เป็นหลัก ห้าม match จาก offset หรือข้อความอย่างเดียว
4. แยก story adapter ออกจาก ordinary/menu path เพื่อรักษา English UI เดิม
5. `script.th.json` และ game-ready Thai atlas/metrics เป็น source of truth เพียงชุดเดียว
6. pointer/control/branch ของ target ต้อง preserve semantic behavior ของ EN/JP ที่ยืนยันแล้ว
7. ทุก allocation ต้องมี owner map ห้ามถือว่า byte `$00/$FF` คือพื้นที่ว่าง
8. overflow, unknown control, unmatched record และ unsupported glyph ต้อง fail build
9. output ต้อง deterministic และตรวจ binary diff นอก allowlist

## 4. Artifact ที่ต้องสร้าง

| Artifact | หน้าที่ |
|---|---|
| `data/reference/en-story.source.json` | extraction ของ master table, pointer tables, records และ controls จาก EN |
| `data/mappings/jp-en-story-map.json` | mapping Thai/JP message id ไป EN block/pointer/record พร้อม confidence และเหตุผล |
| `data/config/en-rom-map.json` | hook, allocation, protected ranges และ checksum contract ของ EN base |
| `src/srw4/en_story_extract.py` | extractor/decoder แบบไม่แก้ ROM |
| `src/srw4/en_story_align.py` | structural matcher และ exception handling |
| `src/srw4/en_story_build.py` | compiler/repacker สำหรับ English base |
| `tools/build_en_th_dialogue.py` | deterministic build entry point |
| `build/reports/en-th-dialogue-*.json` | mapping, allocation, pointer, glyph, overflow และ diff reports |
| `build/patches/` | release patch และ manifest; ไม่มี ROM |

ชื่อไฟล์อาจปรับตอน implementation ได้ แต่ต้องรักษาการแยก extraction, mapping และ build
ไม่รวม logic ทั้งหมดไว้ใน script เดียว

## 5. วิธี match JP/Thai → EN

ใช้ลำดับหลักฐานต่อ record ดังนี้:

1. **Block identity** — master slot 0–51 เป็น event/script identity ชั้นแรก
2. **Pointer identity** — เทียบ pointer index ภายใน block เดียวกัน
3. **Alias identity** — ตรวจว่าหลาย pointer ชี้ record เดียวกันเหมือน JP หรือไม่
4. **Control signature** — เทียบ terminator, line/page control, `<FB>`, `<FC>` และ branch target
5. **Call/branch context** — ตรวจ inbound pointer และ `$FC:08` protagonist branches
6. **Semantic confirmation** — ใช้ข้อความ JP/EN ยืนยันคนพูดและเหตุการณ์
7. **Manual exception** — split/merge/reorder ต้องบันทึก mapping แบบ explicit

ระดับ confidence:

- `A`: block + pointer index + alias + control signature ตรง
- `B`: identity ตรง แต่ alias/control ต่างโดยอธิบายได้
- `C`: ต้องยืนยันด้วย semantic/context แบบ manual
- `UNRESOLVED`: ห้าม build production

block 48 ต้องถือเป็น manual-audit block ตั้งแต่ต้น เพราะ alias ต่าง 64/240 pointer rows
ห้ามใช้ rule เดียวกับอีก 46 blocks โดยไม่ตรวจ

message id เช่น `00_011C` เป็น identity ที่ผูกกับตำแหน่ง JP เดิม ไม่ใช่ EN offset
ตัว builder ต้อง resolve ผ่าน mapping manifest เท่านั้น

## 6. Text และ control contract

- visible text มาจาก `script.th.json`
- control token ต้อง parse เป็น typed token ห้ามใช้ string replace
- รักษา `<ENDFF>`/`<ENDF7>`, `<FB:...>`, `<FC:...>` และ branch semantics
- control operands ที่เป็น target address ต้อง rebase จาก EN layout ใหม่
- line break ของ JP/EN เป็นหลักฐาน ไม่ใช่ตำแหน่งบังคับ; Thai ต้อง reflow ตาม pixel width
- runtime-inserted English name/number ต้องผ่าน story adapter โดยไม่ทำให้ atlas หรือ cursor พัง
- record ที่มี unknown raw token ต้องอยู่ใน exception manifest พร้อม test ก่อนอนุญาต
- ห้ามเอา English control skeleton หรือ JP control skeleton มาใช้ทั้งก้อนโดยไม่เทียบ semantics

## 7. Renderer/font strategy

English ROM เปลี่ยนทั้ง ordinary call `$C1:84E4` และ story call `$C1:9238` ให้ไป
`$F0:E045` แล้ว จึงห้าม overwrite shared English renderer แบบกว้าง

แนวทางเป้าหมาย:

- hook/dispatch เฉพาะ story entry/call site `$C1:9238` หรือ caller context ที่พิสูจน์แล้ว
- ปล่อย ordinary/menu `$C1:84E4` และ English UI renderer เดิมทำงานเหมือนเดิม
- ใช้ Thai precomposed cluster + VWF metrics จาก `data/font/`
- preserve story cursor, arena, tilemap, DMA และ timing contract ของ English ROM
- ตรวจ WRAM/VRAM owner จาก runtime trace ก่อนเลือก scratch/state
- atlas ที่ build ใช้ต้องเป็นไฟล์เดียวกับที่ editor/preview ใช้; ห้ามมี conversion มือซ้ำ
- Thai glyph ทุกตัวต้องผ่าน atlas coverage และ pixel/advance regression

หาก story path และ ordinary pathแยกอย่างปลอดภัยไม่ได้ ให้หยุดที่ phase gate และออกแบบ
caller-scoped dispatcher; ห้ามยึด shared renderer แล้วเสี่ยงทำ menu พัง

## 8. Storage/repack strategy

- inventory `$F0-$FF` ของ EN ก่อนเขียน เพราะ expansion มีข้อมูลจริงอย่างน้อย 785,702 bytes
- ระบุ ownership ของ EN story blocks, renderer/font, tables และ code ทุกช่วง
- reclaim เฉพาะพื้นที่ story เดิมที่ถูกแทนและพิสูจน์ว่าไม่มี owner อื่น
- repack เป็น variable-length pool; แต่ละ block ต้องอยู่ใน bank เดียวเพราะ pointer ภายในกว้าง 16 บิต
- เขียน master pointer 24 บิต, pointer table 16 บิต, alias และ intra-record branch ให้ครบ
- รักษา block dispatch data ของ battle quotes แยกจาก visible messages
- รายงาน used/free bytes ต่อ bank และ fail หาก block ใดเกิน 64 KiB

หากพื้นที่ 4 MB ไม่พอ ให้หยุดและเสนอทางเลือกตามลำดับ: ลด duplicate records อย่างปลอดภัย,
dictionary/compression ที่มี runtime proof, หรือขยาย ExHiROM เป็น scope ใหม่ ห้ามเขียนทับช่วงที่
ดูว่างหรือขยาย mapper โดยพลการ

## 9. Phases และ gates

### P0 — Lock scope และ baseline

งาน:

- ยืนยันนิยาม “บทสนทนาทั้งหมด” ตามหัวข้อ 2
- ตรวจ SHA-256/ขนาด/header/checksum ของ JP, EN, IPS และ xdelta
- ยืนยันว่า xdelta สร้าง EN hash ที่ล็อกไว้
- บันทึก protected non-dialogue surfaces และ release patch format

Gate:

- input ผิด hash ต้องหยุด
- scope/exception policy ต้องไม่มีจุดกำกวม
- clean ROM ไม่ถูกแก้และมี reproducibility report

### P1 — English ROM anatomy และ ownership map

งาน:

- extract master descriptors ทั้ง 52 slots
- map 47 story blocks, pointer tables, dispatch records, font, renderer และ hooks
- trace ordinary/story/battle call paths บน emulator
- สร้าง allocation/protected-range map ของ `$F0-$FF`

Gate:

- ทุก byte ที่จะเขียนมี owner และเหตุผล
- story/ordinary renderer separation มี static + runtime evidence
- ยังไม่ inject Thai text ใน phase นี้

### P2 — EN story extractor/decoder

งาน:

- สร้าง typed extractor สำหรับ EN records และ controls
- เก็บ pointer index, alias group, inbound references และ branch edges
- round-trip EN corpusแบบ byte-identical โดยไม่เปลี่ยนเนื้อหา

Gate:

- 47 text blocks และ 10,439 pointer slots ถูก extract ครบ
- ทุก pointer/branch อยู่ในขอบเขตที่อนุญาต
- decode → encode ได้ EN bytes เดิม 100% หรือมี explicit opaque record policy

### P3 — Structural alignment

งาน:

- สร้าง mapping ตามหัวข้อ 5
- audit block 48 ทั้ง 240 pointer rows
- ตรวจ split/merge/reorder, unused records, duplicate aliases และ protagonist branches
- สร้าง human-readable unmatched/ambiguous report

Gate:

- target records ครบ 100% ตาม scope
- ไม่มี `UNRESOLVED`
- confidence B/C ทุก record มีเหตุผลและ regression fixture
- ห้ามใช้ fuzzy match ตัดสิน production mapping โดยไม่มี manual confirmation

### P4 — Story-only architecture spike

งาน:

- ทำ one-block candidate จาก EN base
- inject Thai atlas/encoding และ story-only dispatch ขั้นต่ำ
- ทดสอบ map dialogue หนึ่งฉาก, battle quote หนึ่งชุด และ runtime name/control
- ตรวจ English title/menu/status ก่อนและหลังด้วย screenshot/hash

Gate:

- Thai วาดถูก genuine redraw
- English non-dialogue surface ไม่เปลี่ยน
- cursor, line break, wait/input, return path และ DMA timing ไม่เสีย
- ถ้า shared hook กระทบ ordinary/menu ให้ reject architecture ไม่ต่อยอด

### P5 — Full compiler/repacker

งาน:

- compile Thai corpus ทั้งหมดจาก source of truth
- reflow ตาม window width และ atlas metrics
- pack blocks, rewrite master/pointers/aliases/branches
- patch checksum/complement และสร้าง allocation/diff report

Gate:

- translated unique records 9,382 รายการหรือจำนวนตาม scope allowlist ตรงเป๊ะ
- overflow, unsupported glyph, unresolved control และ out-of-range pointer = 0
- build ซ้ำสองครั้งได้ SHA-256 เดียวกัน
- byte diff นอก allowlist = 0 ยกเว้น checksum/header fields ที่ประกาศ

### P6 — Static และ corpus verification

งาน:

- pointer graph round-trip ทุก block
- ตรวจ terminator/control balance และ branch targets
- ตรวจ Thai/English/Japanese residue ตาม allowlist
- pixel/metric test สำหรับ Thai cluster, ASCII, number และ runtime inserts
- ตรวจว่า EN story pool เก่าไม่ถูกอ่านจาก active route

Gate:

- static suite ผ่านทั้งหมด
- report นับ block/pointer/message/alias ตรง source manifest
- ไม่มี stale route หรือ orphan active record

### P7 — Emulator runtime verification

งาน:

- cold boot และ genuine redraw จาก build เดียวกัน
- sweep story blocks/scenarios ที่ทำได้ด้วย harness
- ทดสอบ dialogue, choices, protagonist variants, battle quotes, objective/game-over records
- ทดสอบ text speed, wait, page break, skip, save/load และ return-to-map
- regression English title/menu/status/naming/battle UI
- ตรวจ VRAM/DMA/VBlank/WRAM guard และ long-session stability

Gate:

- ไม่มี crash, hang, black frame, stale tile, wrap/overflow หรือ control leak
- critical routes มี screenshot/trace evidence
- English non-dialogue behavior และภาพไม่ถดถอย
- blocker ที่เข้าไม่ถึงต้องประกาศ ไม่สามารถนับเป็น pass

### P8 — Patch/release

งาน:

- สร้าง BPS หรือ xdelta จาก English base hash ที่ล็อกไว้
- ใส่ source/output SHA-256, patch SHA-256, version และ build command ใน manifest
- ทำ clean-room apply test แล้วเทียบ output hash
- เขียน README ระบุ base ROM ที่รองรับ, scope, known limitations และวิธี verify

Gate:

- patch apply กับ hash ที่ถูกต้องและ reject base อื่น
- patched ROM boot/runtime smoke ผ่านจากไฟล์ที่ apply ใหม่
- release ไม่มี ROM, save data หรือ copyrighted dump ที่ไม่จำเป็น

## 10. ชุดทดสอบขั้นต่ำ

### Static

- base identity/header/checksum
- 52 master slots / 47 text blocks
- 10,439 pointer slots in bounds
- 9,400 occurrences / 9,382 unique translated records ก่อน apply scope filter
- alias graph และ block 48 exception fixtures
- `$FC:08` branch relocation และ `<FB>/<FC>` operands
- block size ≤ 65,536 bytes
- glyph coverage/metrics/overflow
- deterministic output และ protected-range diff

### Runtime

- ordinary story dialogue
- battle dialogue/quotes blocks 20–26
- branch ของ protagonist/เพศ/ชื่อ runtime
- multi-line, page break, wait และ long line
- scene transition, battle → map, menu → dialogue และ save/load
- English menu/status/naming ที่ไม่อยู่ใน scope
- cold boot และ same-build savestate policy

## 11. ความเสี่ยงหลัก

| ความเสี่ยง | ผลกระทบ | การควบคุม |
|---|---|---|
| EN ใช้ shared renderer `$F0:E045` | menu อังกฤษเสีย | story-only hook + protected ordinary call + runtime regression |
| block 48 alias ต่าง 41 rows | ใส่คำแปลผิดเหตุการณ์ | manual mapping + semantic/context fixture |
| control stream JP/EN ต่าง | branch/wait/name พัง | typed control diff + target-specific relocation |
| expansion bank มี owner ซ้อน | code/data ถูกทับ | allocation map + read/write trace + expected-byte assertions |
| Thai block เกิน 64 KiB | pointer 16-bit ใช้ไม่ได้ | per-block overflow report + repack/compression gate |
| runtime insert มาจาก EN catalog | ข้อความไทยปนชื่ออังกฤษ | policy ชัดเจน; Thai catalog เป็น scope เพิ่ม |
| savestate พก VRAM/code เก่า | false pass/false failure | cold boot/genuine redraw และ same-build state เท่านั้น |

## 12. Definition of Done

- สร้าง mod จาก English ROM hash ที่กำหนดได้ด้วยคำสั่งเดียว
- mapping ครบทุก record ใน scope และ block 48 audit ครบ
- บท story ภาษาไทยแสดงครบโดยไม่แก้ English UI/catalog นอก scope
- static, deterministic, protected-diff และ emulator gates ผ่าน
- patch ที่แจก apply ซ้ำแล้วได้ output hash ตรง manifest
- ROM ต้นฉบับไม่ถูกแก้และ release ไม่มี ROM สำเร็จรูป

## 13. ลำดับเริ่มงาน

1. ยืนยัน scope assumption ใน P0
2. สร้าง EN extractor + ownership report โดยยังไม่เขียน ROM
3. สร้าง alignment report และปิด block 48
4. ทำ one-block story-only spike
5. ผ่าน P4 แล้วจึงทำ full repack และ release patch
