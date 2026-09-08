# 7. กับดัก — อ่านก่อนเสียเวลาซ้ำ

ทุกข้อในนี้เคยกินเวลาไปจริง ๆ เรียงตามความถี่ที่เจอ

## การวัดผล

**save state แสดงจอที่มันถูกบันทึกไว้ ไม่ใช่จอที่บิลด์ปัจจุบันจะวาด**
โหลด state แล้วดูจอเฉย ๆ = เห็นภาพที่ประกอบไว้แล้ว ต้อง **กดปุ่มให้เกิดการวาดใหม่จริง**
ระหว่างรันเสมอ ข้อสรุปผิด ๆ ว่า "story engine ไม่เคยถูก hook" มาจากความผิดพลาดนี้
และอยู่ในเอกสารนานมาก

**ห้ามใช้ save state ของบิลด์อื่นมาตัดสินผล** — WRAM ที่ state พกมาอาจมีข้อความเก่า
cache ไว้ ให้สร้าง state ใหม่จากบิลด์เดียวกัน หรือบูตเปล่าแล้วเดินเข้าไปเอง

**ดัก watch ผิดแบงก์** — เกมรันจากมิเรอร์ `$80`/`$81` การ watch `$C1:8402` ได้ศูนย์ hit
ทั้งที่โค้ดทำงานอยู่ วิธีกันคือ ก่อนเชื่อ "0 hits" ให้ watch ที่อยู่ควบคุมที่รู้แน่ว่า
ทำงานในรันเดียวกันด้วย

**watch ที่ไม่ยิงเลย ≠ โค้ดไม่ถูกเรียก** อาจเป็นเพราะหน้าต่างเฟรมสั้นเกินไป
หรือของถูกวาดไปแล้วก่อนหน้าเฟรมที่เฝ้า ให้ปักหมุดด้วย save state ก่อนแล้วค่อยเฝ้า

**DMA มองไม่เห็นด้วย memory watch** — อะไรที่อัปโหลดผ่าน DMA จะไม่มี CPU read/write
ให้เห็น ต้องดัก `$420B` แล้วอ่านพารามิเตอร์ของแชนแนล (`$43x0`–`$43x6`)

## เลขและช่วง

**ช่วง routing ต้องอ้าง "หนึ่งไบต์ถัดจากข้อความ"** (end แบบไม่รวม) อ้างสั้นไปหนึ่งไบต์
ตัวสุดท้ายจะหลุดไปฟอนต์เดิม

**record ที่มีความยาวตายตัวนับเป็น "จำนวนไบต์" ไม่ใช่ความกว้างพิกเซล**
เติมช่องที่เหลือด้วย pad ที่กว้างศูนย์ อย่าตัดคำแปลให้สั้นลงเพื่อลด padding

**โซ่ของ bank routing เป็นบันได ไม่ใช่ชุดเงื่อนไขอิสระ** ต้องเรียงจากน้อยไปมาก

**ตาราง pointer ของ `$D2` เริ่มที่ที่อยู่คี่**

**slot ที่ว่างไม่ใช่พื้นที่ว่าง** — มันชี้ไปที่ `$FF` โดด ๆ วาง record ทับแล้วช่องที่เคย
ว่างจะมีข้อความโผล่

**จองพื้นที่ต้องจองทั้ง record** ไม่ใช่แค่ไบต์แรก — slot ที่ไม่ถูก repoint ต้องยังอ่าน
record ที่ไม่ยาวกว่าเดิม

## สถานะและหน่วยความจำ

**direct page ไม่ใช่ scratch** — `$D6` เป็น condition register ของ script engine
เขียนทับแล้วบทสนทนาค้างที่ STP ให้จองพื้นที่ของตัวเองใน WRAM

**compositor ของ dialogue วาง tilemap ไว้ให้แล้ว** อย่าวางซ้ำ

**สองเครื่องยนต์ต้องการ guard ตรงข้ามกัน** (ดู `03-text-engines.md`)

**`FB` ของฝั่งฉากต่อสู้เป็นคนละตัวกับฝั่งเมนู** — hook ฝั่งเดียวแล้วอีกฝั่งจะอ่าน
operand ผิดเป็นชื่อ runtime แล้วเลยขอบ record ไป

## การ build

**EN Robot Archives uses the ordinary profile renderer.** Include all block-50
records and block-51 pointer rows 0–34 in `ProfileCatalogEncoder` (264 records).
The FF dialogue encoder produces garbage on this surface. Old JP static-text
macros `FB:F8C2`, `FB:F9C2`, and `FB:AEA1` must be translated inline from the EN
record, not passed to the runtime as name-buffer commands. EN slot 2 reproduces
the A-Taul case. Routing uses two bitplanes for four route values so the complete
archive corpus fits the reserved route-table region; bitmap offsets must also
fit the 15-bit offset mask. Evidence: `build/repro/robot-history/`.

**EN ending cards span two story blocks.** Block 51 rows 35 onward are only
one set. Block 42 rows 125–175 and 195–197 also render through the ordinary
profile compositor. Encode these 52 additional records with `ProfileCatalogEncoder`
and its font routes, not the FF dialogue encoder. EN slot 4 reproduces the
failure: Juzo's text at `$F6:ED2B` went to stock `$F0:E045` and displayed garbage.
Fresh card draws after the fix render Juzo, Daisaku, Chizuru and Kosuke in Thai.
Keep the adjacent block-42 dialogue rows on the story engine.

**record ของฉากต่อสู้เป็น bytecode ไม่ใช่คำ 16 บิตที่ซ้อนกัน**

**จำนวนไบต์ไม่ใช่ค่าคงที่** ให้คำนวณจากข้อมูลจริงทุกครั้ง

**ROM เต็มเป็น build artifact** สร้างใหม่ได้เสมอ ห้าม commit และห้ามถือว่าเป็นแหล่งความจริง

**deterministic rebuild คือเครื่องมือจับบั๊กที่ดีที่สุดอันหนึ่ง** — build สองครั้งต้องได้
sha256 เท่ากัน และ byte diff เทียบบิลด์ก่อนหน้าจะโชว์ทุกอย่างที่เผลอไปแตะ

## `emu.write` รับสามอาร์กิวเมนต์ ไม่ใช่สี่

`emu.read(addr, memType, disableSideEffects)` รับสี่ตัวได้ แต่ `emu.write` รับแค่
`(addr, value, memType)` ใส่ตัวที่สี่แล้ว **throw** และ throw ใน callback ของ Mesen
เงียบสนิท — callback ตายเฉย ๆ ไม่มีข้อความ ไม่มี exit code

อาการที่เจอ: ตัวนับก่อนหน้าบรรทัด `emu.write` เดินปกติ ทุกอย่างดูเหมือนทำงาน
แต่หน่วยความจำไม่เปลี่ยน ถ้าสงสัยให้ `pcall` แล้วอ่านค่ากลับมาดู

## `record_bytes` ในสรุปการแยกไม่ใช่ของประดับ

บล็อก 20–26 มีพื้นที่ตารางคำพูดอยู่ระหว่างตาราง pointer กับข้อความแรก มันไม่ใช่
message จึงไม่โผล่ใน audit ไม่โผล่ใน sweep ไม่โผล่ใน golden fixture — **มีแต่
ฉากต่อสู้จริงเท่านั้นที่รู้ว่ามันหายไป** ถ้าเขียนโค้ดที่คิดว่า "บล็อก = ตาราง +
ข้อความ" ให้เช็ค `record_bytes` ก่อนเสมอ

## EN savestate max-upgrade edits must preserve dynamic robot names

The English-combo ROM relocates the three editable robot names to WRAM
`$7E:14D0–14DC`, `$7E:14DD–14E9`, and `$7E:14EA–14F6` (13 bytes each).
Do not fill a broad upgrade-table range across these addresses. In the reported
2026-09-07 slots 1 and 2, a max-upgrade save edit had filled through `$14EB` with
`$77`, including both complete name buffers and the beginning of the third.
The EN font renders `$77` as `È`; losing the `$FF` terminator also makes the
name renderer read past the field. The corruption already exists before the
slot-1 A press and reproduces with the stock EN renderer.

Default EN strings are at ROM PC `$3EDC4D` (Grungust), `$3EDC56` (Wing Gust),
and `$3EDC60` (Gust Lander). Restore defaults only when the user authorizes
repair; custom names cannot be inferred from overwritten bytes. Future upgrade
edits must target verified real-unit entries and assert all three name buffers
remain byte-identical. Repair evidence/backups: `build/repro/robot-naming/repair/`.

## Objectives must remain stock English

The old English override was lost, allowing Thai block 1 back into builds.
The EN builder now skips block 1 and reserves its original ROM range before
packing other story blocks. Skipping the block alone is insufficient because
its original bank is also a repacking destination.

Before writing ROM/IPS, `verify_stock_objectives` checks the master pointer and
entire original block against the pinned EN base. Regression tests build without
objective translations and reject mutations to the pointer or payload.
Thai block 1 entries are legacy corpus data only; never enable them implicitly.
Existing savestates may contain an already rendered screen or obsolete repacked
cursors; reload the rebuilt ROM and reopen the objective window for a fresh draw.

Stock objective bytes alone do not ensure English rendering: `$F1` also holds
private Thai streams. The story parser, width adapter and draw adapter must all
exclude the stock objective extent, accounting for the already advanced cursor.
The baseline verifier pins that range to the renderer guard.
`tools/lua/en-objective-regression.lua` closes and reopens Objectives from an EN
state and fails if a Thai renderer handles the fresh draw. On 2026-09-07, user
slot 1 redrew “Within 6 turns, all members must retreat.” with stock glyphs.

## Diana A / Scarlet Beam upgrade allocation

The supplied EN slot-2 Diana A record has descriptor `$0C0A` at `$138A`:
three weapon levels starting at nibble 10, inherited from Aphrodite's size.
Diana's stock EN record declares four levels. Scarlet's upgrade index 3 writes
nibble 13 into the following unit, while `$80:B466` loads only three levels and
zero-fills Scarlet's temporary level. Actual A purchases reach 2600, then B/A
reentry recalculates 1200. This is not evidence of a Thai numeric-renderer bug.

The current `en_scarlet_upgrade.py` changes only PC `$0B9CB2`, the fourth
weapon entry's upgrade index, from 3 to 0. This uses the unused Repair level.
It does not change the count, allocate memory, migrate saves or install CPU
hooks. Native `$80:B3C7` and the upgrade-menu list both consume this index;
`$80:B416–B421` suppresses the upgrade bonus for support weapons. Repair stays
at zero and the native purchase gate rejects support weapons. Diana's record
has no other unit-table aliases and belongs to the non-sharing allocator group.

Native EN slot-2 input tests: seven Scarlet purchases, B/A reentry, power 2600;
Repair rejected with no fund/level change; Melee and Diana Missiles each bought
one level independently and retained it after reentry. Full-roster and form
stress both keep Scarlet 2600, original descriptors, other levels and EN names.
Pool ends at 353 / 310 respectively. These are synthetic allocator tests, not
all story routes or an actual battlefield healing-action test. The underlying
stock allocator's 544-level limit is unchanged. Evidence:
`build/repro/scarlet-repair-slot/`.

The withdrawn append-migration implementation and its release binaries were
removed. It expanded the pool 314→357 during the same roster stress, crossing
EN names at `$14D0` (356 levels). Historical diagnostic reports remain under
`build/repro/scarlet-roster-stress/` and `build/repro/scarlet-patch/`.

After loading a savestate made with the previous ROM, leave/reenter the weapon
menu before purchasing so the cached weapon indices are rebuilt. This patch
does not recover previously misdirected levels, refund funds, or undo save
allocations made by the withdrawn patch. Do not guess neighboring ownership.
