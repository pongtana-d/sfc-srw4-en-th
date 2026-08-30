# Text Surface Coverage

บัญชีที่เครื่องอ่านได้อยู่ใน `config/text-surfaces.json` และเป็นเงื่อนไขของคำว่า 100%

กฎปลายทาง:

- ห้ามเหลืออักษรญี่ปุ่นใน surface ที่ผู้เล่นเห็น ยกเว้นรายการใน
  `final_rules.japanese_exceptions` ที่ผู้ใช้อนุมัติให้คงต้นฉบับไว้
  (โลโก้/เครดิต, ชื่อเพลง BGM และเนื้อเพลงประกอบ)
- อังกฤษและตัวเลขใช้ stock glyph ได้เมื่อปลอดภัยและประหยัดกว่า
- หน้าตั้งชื่อและตั้งค่าตัวเอกใช้แป้นไทย ป้ายไทย/stock English, preset ไทย
  และ buffer ที่กลับมาแสดงไทยได้
- surface ทุกจุดต้องมีเจ้าของเป็น Core, stock passthrough หรือ special adapter
- รายการ `unknown.discovery` ต้องถูกปิดด้วย static scan และ runtime trace ก่อน release

สถานะ `data_ready` หมายถึงมีคำแปล/ข้อมูลแล้ว ไม่ได้หมายความว่าแสดงใน ROM ได้แล้ว
สถานะจะเปลี่ยนเป็น `tested` ได้เมื่อผ่าน cold boot, redraw, reentry, navigation
และ save reload ตามลักษณะหน้าจอ

checkpoint ปัจจุบัน: catalog, battle speaker, runtime player-name, หน้าตั้งชื่อไทย,
หน้าสถานะยูนิต, หน้าสถานะนักบิน/Spirit/Skill และ Spirit Help บนแผนที่อยู่ที่
`adapter_active_needs_full_regression` เพราะ adapter ทำงานจริงแล้ว แต่ยังต้องสร้าง save
ใหม่จาก build เดียวกันในกลุ่มที่ยังไม่มี และทำ full-game regression ก่อนเลื่อนเป็น
`tested` (Spirit Help มี same-build save/reload แล้ว แต่ยังรอ reentry และ full-game run)

เมนูคำสั่งยูนิตเปิด adapter แล้ว: command labels ผ่าน cold boot, navigation, reentry
และ same-build save/reload ส่วน `ไม่มีโล่` / `มีโล่` ในระบบเดิมยังค้างที่ source/route
verification เพราะ byte-range routing ทำให้ไม่มีทางเรียก record ที่สองมาวาดจริงได้

ทั้งสองบรรทัดย้ายไป Renewal แล้วใน Phase 9 ข้อ 1 (`build/SRW4-renewal-catalog.sfc`)
เขียนทับที่เดิมในคลัง label แบงก์ `$D2` ไม่ขยับ pointer สักตัว การเลือกว่าจะวาดอันไหน
จึงยังเป็นของเกมทุกบิต และวาดผ่าน pen adapter ตัวเดียวกับชื่อยูนิต ผลบนฮาร์ดแวร์:
`ไม่มีโล่` ตรงทุกไบต์ใน VRAM หลัง genuine redraw, reentry และ same-build save/reload;
`มีโล่` ตรงทุกไบต์บน probe ROM ที่ชี้ slot มาที่ record นั้น เพราะปาร์ตี้ของ save ที่มี
ไม่มียูนิตที่ถือโล่เลยสักตัว — สถานะงานปัจจุบันติดตามใน `docs/PROGRESS.md` P8/P9;
รายละเอียดของ Renewal เดิมเป็น historical evidence ใน git history ก่อน cleanup

หน้าโปรไฟล์ของ CHARACTERS/ROBOTS (story block 48-51 รวม 560 รายการ) ใช้กรอบ
กว้าง 30 ช่อง (240 px) และสูง 9 บรรทัด เพราะกรอบเริ่มใต้หัวข้อ `โปรไฟล์` แล้วถูกขอบจอ
ตัดที่บรรทัดที่ 10 ต้นฉบับญี่ปุ่นก็ไม่เคยเขียนเกิน 9 บรรทัดเช่นกัน ข้อความไทยชุดเดิม
ถูกตัดบรรทัดด้วยการอัดทีละ cluster จึงมีคำขาดกลางบรรทัด (เช่น `เดลา`/`ส`) และมี
ช่องว่างเกินจากรอยต่อเดิม ตอนนี้จัดบรรทัดใหม่ตามขอบเขตคำไทยครบทั้ง 560 รายการ
และย่อ 28 รายการที่เกิน 9 บรรทัดลงมาแล้ว ตรวจซ้ำได้ด้วย

```bash
python3 tools/check_encyclopedia.py
```

หน้า Weapon Detail อยู่ที่ `tested`: ผ่าน cold boot, redraw, reentry, navigation
และ save reload จาก build เดียวกันแล้ว

Map Commands อยู่ที่ `tested` เช่นกัน: แสดง stock English ครบ 8 รายการโดยไม่มีญี่ปุ่น
และผ่าน cold boot, genuine redraw, navigation, reentry กับ same-build save/reload แล้ว

Map HUD อยู่ที่ `tested`: `TURN/FND` และค่าตัวเลข dynamic ผ่าน genuine redraw,
reentry, same-build save/reload และ cold boot โดยขอบขวาไม่ล้นกรอบ

Main/System fixed fields เปิด adapter แล้ว แต่พบในหน้า UNITS ว่า selector จากปุ่ม L/R
ยังมี `HP順`, `ユニット名`, `HP表示`, `パイロット名` ที่ไม่อยู่ใน inventory เดิม จึงเพิ่ม
source assertion และคำแปลครบ 6 จุดแล้ว สถานะกลับเป็น
`adapter_active_needs_full_regression` จนกว่าจะตรวจ L/R ด้วย save จาก build เดียวกัน
Objective body อยู่ใน story block 1 และแสดง `กำจัดศัตรูทั้งหมด` ผ่าน ordinary VWF แล้ว
แต่ยังต้องตรวจ objective ทุกฉากใน full-game regression เช่นกัน

Story dialogue และ Battle Quote เปิด adapter แล้วครบ 47 blocks / 9,400 ข้อความ
ordinary dialogue ผ่าน same-build reload และเดินต่อหลายข้อความพร้อมเปลี่ยนภาพผู้พูด
Battle Quote ผ่าน redraw/กดกลับหน้าสถานะ และ Objective ผ่านภาพจริง ทั้งสามรายการยังเป็น
`adapter_active_needs_full_regression` จนกว่าจะเล่นครบ route และตรวจ surface ตกหล่น

Title menu อยู่ที่ `tested`: resource `$16` ถูก repoint ไป payload ที่ allocator วางต่อจาก
stock pool, แสดง `START/LOAD/CONTINUE/OPTION` และ navigation/highlight ผ่านภาพจริง
โลโก้กับเครดิตลิขสิทธิ์ญี่ปุ่นเป็นข้อยกเว้น stock ที่ผู้ใช้อนุมัติให้คงเดิม

Intro crawl เปิด overlay ไทยครบ 5 assets แล้ว หน้า 1–4 ผ่าน runtime ต่อเนื่องโดยไม่มี
tile ค้างและ stock English ในวงเล็บแสดงร่วมได้ หน้า 5 มี source hash, 57 private glyphs
และ tilemap ที่ตรวจแล้ว แต่ยังรอ genuine alternate-route run จึงคงสถานะ
`adapter_active_needs_full_regression`

## Static discovery ผ่านตารางแม่ `$C9:00D8`

`FB` handler ใช้ตาราง 24-bit 19 ช่องที่ `$C9:00D8` เป็นสารบัญของ catalog ทุกชุด
จึงใช้ตารางนี้เป็นฐานการค้นหาแทนการเดา ตัวสแกนอ่านทุก record ของทุกตาราง แล้วเทียบ
ไบต์กับ ROM ที่ build ได้ record ที่ไม่ถูกแตะเลยคือข้อความญี่ปุ่นที่ยังเหลือ

```bash
python3 tools/scan_catalog_residue.py \
  --clean "rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc" \
  --built build/srw4-th-intro.sfc \
  --report build/catalog-residue.json
```

ผลจาก milestone `thai-intro-active`: catalog ที่ Core เป็นเจ้าของแล้ว (ชื่อนักบิน
`$D2:6B34`, ชื่อผู้พูด `$D2:772B`) ไม่เหลือ record ญี่ปุ่นเลย ส่วนชื่อยูนิต `$D2:6050`
เหลือ 7 record และอาวุธ `$CC:7760` เหลือ 2 record ซึ่งเป็น record ที่ชี้ต่อด้วย `FB`
ไม่ใช่ข้อความจริง

ตารางที่ยังเป็นญี่ปุ่นทั้งชุด รวม 1,034 record:

| catalog | records | สิ่งที่พบ | surface |
|---|---|---|---|
| `$CC:8E88` | 185 | สคริปต์หน้าจอ รวมหน้าเซฟ/โหลด | `menu.save_load` |
| `$CC:C1FF` | 186 | หน้าเซฟ/โหลด, ข้อความเตือนข้อมูล | `menu.save_load` |
| `$CC:E9BD` | 75 | คำอธิบายผลของพาร์ท (5 record แรกเป็นบทนำที่ overlay ทับแล้ว) | `menu.part_effects` |
| `$D2:7F03` | 56 | ชื่อภูมิประเทศบนแผนที่ | `map.terrain_names` |
| `$D2:9389` | 52 | ชื่อเพลง BGM | `menu.bgm_titles` |
| `$D2:9009` | 62 | ชื่อฉาก/ตอน | `menu.scenario_titles` |
| `$D2:8103` | 132 | ค่าที่ unit-status adapter ยังไม่ครอบคลุม | `menu.unit_status_extras` |
| `$D2:8B8A` | 143 | โทเคนสั้นในฉากต่อสู้ | `battle.status_tokens` |
| `$CB:667C` | 134 | เนื้อเพลงประกอบ (คงญี่ปุ่นตามที่ผู้ใช้ขอ) | `song.lyrics` |

surface เหล่านี้ถูกเพิ่มใน `config/text-surfaces.json` แล้วทั้งหมด และ
`unknown.discovery` เลื่อนเป็น `static_scan_done_runtime_trace_pending`
เพราะการสแกนแบบ static ปิดแล้ว เหลือ runtime trace ยืนยันว่าไม่มี surface
นอกตารางแม่ สถานะปัจจุบันของตารางข้างต้น:

- `map.terrain_names` และ `menu.scenario_titles` แปลแล้วและอยู่ที่
  `adapter_active_needs_full_regression`
- `menu.bgm_titles` และ `song.lyrics` อยู่ที่ `retained_japanese_by_user_request`
  ผู้ใช้ขอให้คงชื่อเพลงและเนื้อเพลงเป็นภาษาญี่ปุ่นตามต้นฉบับ จึงไม่นับเป็นงานค้าง
  และไม่ต้องแปลใน release
- `menu.intermission` (`$CC:C1FF`) แปลแล้วและย้าย catalog ไป `$FA:4500`
- `menu.field_screens` (`$CC:8E88`) แปลแล้วในที่เดิม โดยใช้พื้นที่ที่การย้าย
  Intermission ปล่อยคืนมา
- `menu.part_effects`, `battle.status_tokens` และ `menu.unit_status_extras`
  ยังเป็น `discovered_untranslated` รวม 309 record ซึ่งเป็นงานแปลที่เหลืออยู่จริง
  (ตัวเลขในตารางด้านบนเป็นของ milestone `thai-intro-active`)

## หน้าจอสนามรบ `$CC:8E88`

catalog นี้ไม่ใช่หน้าเซฟ/โหลดอย่างที่ inventory เดิมเขียนไว้ แต่เป็นสคริปต์หน้าจอ
ระหว่างเล่น คือหน้าเลือกยูนิตลงสนาม, ข้อความผลการรบ, แต้มพลังจิต, เมนูตอบโต้
และ sound test แปลแล้ว 45 คำ ลงตัว 69 จุดใน 39 record

```bash
python3 tools/build_screen_labels.py --catalog config/screens-labels.json \
  --clean "rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc" \
  --built build/SRW4-TH-intermission.sfc
python3 tools/build_screens.py \
  --input "rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc" \
  --output build/SRW4-TH.sfc --report build/SRW4-TH.json
```

record โตขึ้นรวม 33 ไบต์ และไปอยู่ในพื้นที่ 9,887 ไบต์ที่การย้าย Intermission
ปล่อยคืนแบงก์ `$CC` โดยตัดช่วงที่ adapter ก่อนหน้าเคยเขียนทิ้งไว้ออกก่อน
(main-menu กับ protagonist เขียนลง record ที่ย้ายออกไปแล้ว ไบต์พวกนั้นตายแต่ยังไม่
เท่ากับ clean ROM) เหลือ 14 ช่วงใช้ได้ 9,404 ไบต์ ทุก write จึงยัง assert clean byte ได้

ที่คงญี่ปุ่นไว้สองอย่าง: หน้าเตือนลิขสิทธิ์ (`0x9069`) ตามที่ผู้ใช้ขอให้ข้าม และ
ตารางเลือกตัวอักษรของหน้าตั้งชื่อ (`0x90F2`, `0x9223`, `0x92C5`, `0x93F9`, `0xAABA`,
`0xBD62`) ซึ่งเป็นแป้นตัวอักษรที่ script วาดเอง ถ้าจะทำเป็นไทยต้องเปลี่ยนทั้งตารางคีย์
และ mapping ของปุ่มแบบที่หน้าตั้งชื่อตัวเอกทำ ไม่ใช่แค่สลับคำ ตารางที่ `0xAABA` อยู่
ติดกับ `ロボット名` และ `名前を変更しますか？` จึงเป็นหน้าตั้งชื่อหุ่นที่เข้าจาก
`เปลี่ยนชื่อ` ในเมนู Intermission

ลำดับการรวม route สำคัญ: ต้องย้าย route ของ Intermission ให้เสร็จก่อน แล้วค่อยเติม
route ของ catalog นี้ ไม่งั้น route ที่อยู่ในพื้นที่ที่ปล่อยคืนจะถูกลากตามไปแบงก์ใหม่
ด้วย ตรวจแล้วข้อความหลังเซฟแสดง `บันทึกเสร็จแล้ว เล่นต่อไหม?` บนจอจริง

## เมนู Intermission

`$CC:C1FF` คือหน้าจอระหว่างแผนที่ ไม่ใช่หน้าเซฟ/โหลดอย่างที่ inventory เดิมเขียนไว้
หน้าเซฟ/โหลดเป็นสาขาหนึ่งของมัน record ปนข้อความกับสคริปต์หน้าต่างที่ยังไม่ได้ถอดรหัส
control byte จึงหาคำด้วยการ encode ญี่ปุ่นกลับเป็นไบต์แล้วหาในตัว record และรับเฉพาะ
จุดที่อยู่ในช่วงตัวอักษรจริง ไม่ใช่คร่อม operand ของ control

```bash
python3 tools/build_intermission_labels.py \
  --clean "rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc" \
  --built build/SRW4-TH.sfc
```

dictionary 90 คำลงตัว 144 จุดใน 70 record และทุกคำต้องเจออย่างน้อยหนึ่งจุด ไม่งั้น fail
ส่วน `--built` บอกตัวสร้างว่า record ไหนมี adapter อื่นเป็นเจ้าของข้อความอยู่แล้ว

catalog ต้องย้ายเพราะ record ที่สร้างใหม่ต้องการมากกว่าพื้นที่เดิมที่คืนมา 118 ไบต์
แต่แบงก์ `$CC` เหลือว่าง 19 ไบต์ (สแกนทั้งแบงก์แล้วมี FF run แค่ 2 ช่วง ถูกใช้หมดแล้ว)
จึงย้ายทั้งตารางและ pool ไป `$FA:4500` แล้วปล่อยพื้นที่คืนแบงก์ `$CC` 9,887 ไบต์
ซึ่งเป็นงบของ `$CC:8E88` กับ `$CC:E9BD` ที่เหลือ

ผลตรวจใน Mesen: cold boot 900 เฟรมได้ screen, tilemap และ tiles ตรง milestone ก่อนหน้า
ทุกไบต์ (VRAM ส่วนที่ไม่แสดงผลต่างตามพฤติกรรมเดิม) และเปิดเมนูแผนที่จาก save state
กดจริงเข้า SYSTEM, ORDER กับกล่องยืนยันบันทึกแล้ว หน้า SYSTEM/ตั้งปุ่ม และรายการ ORDER
ซึ่งเป็นข้อความของ main-menu ยังแสดงไทยครบหลังย้ายแบงก์ ส่วน `บันทึก` / `ยืนยันไหม?`
เป็น label ของ adapter นี้เอง หน้าจอ Intermission จริงยังต้องรอ save ระหว่างแผนที่จาก
build เดียวกัน ระหว่างตรวจพบว่าข้อความ `セーブを終了しました。ゲームをつづけますか？`
อยู่ที่ `0x0C9B1A` ซึ่งเป็น catalog `$CC:8E88` ไม่ใช่ catalog นี้

ต่างจาก terrain/scenario ตรงที่ catalog นี้มี adapter อื่นเขียนอยู่ข้างใน: main-menu
19 ช่องและ protagonist 7 ช่อง รวม 41 route ดังนั้น relocation อ่านไบต์ record จาก image
ที่ adapter เหล่านั้นเขียนแล้ว ไม่ใช่จาก clean ROM และย้าย route ของพวกเขาตาม record ไป
ที่อยู่ใหม่ โดย source assertion ยังอ้าง clean ROM ทุกจุด ถ้าช่องไหนถูกอ้างสิทธิ์ซ้ำ
จะ fail ทันทีแทนที่จะทับกันเงียบ ๆ

## วัดพื้นที่ก่อนแปล

ทุก surface ที่เหลือต้องวัดก่อนเลือกภาษา ไม่ใช่แปลแล้วค่อยดูว่าล้นหรือไม่

```bash
python3 tools/measure_residue.py --out build/residue-measure.json
```

ตัววัดอ่าน `build/catalog-residue.json` แล้วรายงานสอง budget ที่ไม่เท่ากัน คือ
จำนวนไบต์ของ record เดิม (เพดานของการเขียนทับในที่) กับความกว้างพิกเซล
กรอบญี่ปุ่น 1 ตัวอักษรเท่ากับ 1 cell 8 px เสมอ บรรทัดที่กว้างที่สุดใน catalog
เดียวกันจึงเป็นหลักฐานของกรอบ ไม่ใช่ความกว้างของ record ตัวเอง ถ้าส่ง
`--candidates` เป็น JSON `{pointer: {thai, english}}` ตัววัดจะวัดไทยผ่าน VWF จริง
และอังกฤษผ่าน stock 8 px แล้วบอกว่าเลือกอะไรได้บ้าง

ผลวัดกับข้อความจริงให้กฎเลือกภาษาแบบมีตัวเลข ไทยกินราว 6.5 px ต่ออักษร
ส่วน stock ตายตัว 8 px แต่คำไทยยาวกว่าตัวย่ออังกฤษ จุดคุ้มทุนจึงอยู่ที่ 32 px

| กรอบ | ไทย | stock English | เลือก |
|---|---|---|---|
| 8 px (1 cell) | พยัญชนะเดี่ยว 6–8 px พอดี | 3 ตัวอักษร 24 px ล้น | ไทยตัวเดียว ตามที่ญี่ปุ่นย่อเป็นคันจิตัวเดียว |
| 16–24 px | `โลก` 18, `ซาก` 19, `ภูเขา` 22 | `EARTH` 40, `DEBRIS` 48 | ไทย ถ้าเลือกคำสั้นได้ |
| 32–48 px | `อวกาศ` 31, `โคโลนี` 33 | `SPACE` 40, `COLONY` 48 | ไทย |
| 56–80 px | `มิโนฟสกี้คราฟต์` 73 | `MINOVSKY CRAFT` 112 | ไทย |
| ประโยค | ยาวกว่าญี่ปุ่นราว 1.5 เท่า | ตัวย่อสั้นแต่อ่านยาก | ไทย + ขึ้นบรรทัดใหม่ |

ที่ต้องระวังคือกรอบ 8 px กับ 16 px ที่ญี่ปุ่นย่อไว้แล้ว เช่น `新早乙女` 32 px
ซึ่งคำไทยเต็ม `สถาบันซาโอโตเมะ` กว้าง 88 px ต้องย่อไทยเองเช่นกัน
