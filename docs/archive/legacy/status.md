# Where the project stands

Last measured 2026-08-18, by rebuilding and reading the build report rather
than by trusting the previous version of this file.

## Coverage

| area | state |
|---|---|
| Weapon names | IDs 0-652, 502 unique text pointers |
| Unit names | 304 IDs / 295 unique pointers, all fixed names spelled |
| Pilot names | 320 IDs / 290 unique pointers, all fixed names spelled |
| Story script | 9,400 messages across 47 blocks, all with a Thai target |
| Weapon detail menu | stable English labels; Thai weapon names |
| Pilot-status screen | 15 stable English labels, 30 Thai spirit commands, all displayed Thai skills |
| Unit-ability screen | stable English labels; all 9 abilities and dynamic values remain Thai |
| Terrain boxes | all three copies — both tab bars and the combine-confirm screen |
| `$D2` label pool | type values and series names |
| Unit command menu | translated, but spelled in the stock font's `A`-`Z` |
| Map command menu | eight Thai labels, fixed block and route |
| Map HUD | Stock `TURN` / `FND` labels beside the dynamic values |
| Shield line | `ไม่มีโล่` / `มีโล่` |

## Fixed recently, and how it was confirmed

- **Latin battle-speaker names disappearing before Thai quotes.** The first
  Thai glyph treated any backwards counter change as an empty DMA queue, even
  when a stock prefix such as `AI` had already drawn two pending tiles. The
  battle restart now preserves forward pending stock ranges. Confirmed from
  `SRW4-FULL_1.mss`: `AIกรรรรรร!!` redraws with 10 battle-renderer calls.
- **Dialogue tile garbage and ghost text.** The dialogue compositor was already
  placing the real window while the Thai VWF wrote a second tilemap copy through
  the menu cursor. The dialogue path now uses the compositor's tile pair and
  placement and only rasterizes Thai glyphs. Confirmed from
  `SRW4-FULL_1.mss` with 34 consecutive A presses until the dialogue closed and
  the clean map returned.
- **Spirit-search records and right frame.** The screen was routed all along.
  Six-byte source records prevent row tearing, while the renderer now maps a
  tail only when pixels really spill and makes the engine's pending tilemap
  write repeat the current cell. The frame beside `กำแพง` is `$201C`, matching
  the Japanese redraw; `<Pad>` itself never reaches the renderer or uses a tile.
- **Detached tone mark on the unit screen.** The shield range was quoted at the
  string starts instead of one past them, so the mark drew from the stock font.
  `มีโล่` was unrouted end to end and had simply not been seen yet.
- **Third terrain box** on the combine-confirm screen, which needed a bank
  `$CD` arm in the classifier.
- **Attack-hit screen-wide corruption** — renderer state at `$7E:F000` overlapped
  the battle line tables, and ordinary/battle text also shared one run state.
  The two renderers now have separate blocks at `$7E:FFA0` and `$7E:FFC0`, with
  temporary work at `$7E:FFE0`; generated code cannot use renderer-owned direct
  page or overlap known stock WRAM.
- **Dialogue freeze on `STP`** — the older mark state was sharing `$D6` with the
  event script engine's condition register. It is covered by the same private
  WRAM contract.
- **Stray glyph after a run** — `restart` now begins one pair further on.
- **Stable `LV` / `WILL` on the unit screen.** The original labels share an
  eight-byte inline span. Direct stock-font labels plus zero-width tail padding
  keep the following dynamic values untouched. Confirmed by the unit-status
  payload and route-table validator.
- **Pilot-stat value columns match the Japanese screen.** English labels stay
  on the stock font; an invisible `<Gap>` advances the stock tilemap cursor by
  one 8px cell wherever a shorter label precedes a dynamic value. Measured on
  a real redraw from `SRW4-FULL_1.mss`: `LV`, `CQB`, and `RNG` gain 24px;
  `WILL`, `EVD`, `ACC`, `REA`, `SKL`, and `SP` gain 8px.
- **Map command menu and HUD.** The eight command labels use 43 of the 47
  available text bytes; four safe terminator pads retain the following script's
  address. The top-right HUD labels are now `TURN` and `FND`, with their
  dynamic values untouched. Confirmed on a genuine Mesen redraw.

## Not bugs, though they look like it

- The **star under `ยิงตก`** is drawn by the clean Japanese ROM too, in the same
  place. It is the game's own marker.
- The **`????` cells** in the spirit grid are spirits the pilot has not unlocked
  yet. The Japanese original shows the same.

## Open — needs a decision, not more investigation

- **`「」` quote brackets.** 8,752 of 9,400 messages carry them in the source.
  `translations/glossary.th.json` records dropping them as a deliberate
  style rule, not an oversight, and restoring them adds two cells to nearly
  every line in a 32-cell window where the widest line already draws 29.
- **Unit command menu in Thai.** Now unblocked in principle — the drift is the
  byte-counting cursor, same as the spirit cells. Eleven of fifteen commands
  have a natural Thai word inside both ceilings (24px and four bytes);
  `ข้อมูล` needs shorthand pointed at it; `โจมตี` fits neither and would have
  to become `ตี` or `ยิง`. **The four-byte figure is inferred from
  `UNIT_COMMAND_CURSOR_CELLS`, not measured with a write-watch — measure before
  building.**

## Open — still needs work

- **`FB` runtime-name pool.** Dialogue macros still resolve to Japanese
  (`リン`, `マオ` appear at the end of translated lines).

## Known cosmetic gaps

- **5 of 30 spirit commands overrun the 4-cell selector**, all by 1-3px:
  `แม่นยำ` (2), `ข่มขวัญ` (1), `เดินซ้ำ` (1), `ซ่อนตัว` (3), `วิญญาณ` (3).
  A shorter spelling is a translator's call, not a renderer change.
- **Below marks collide with the descenders of `ญ ฎ ฏ ฐ`**, because the lift
  only works upward. Left alone deliberately — those consonants do not take a
  below vowel in normal Thai.

## Hook space

Blocks in the `$3F0000` region sit on fixed strides. The tightest is
`thai_pool_parser_2` at 422 bytes of 512. Routing arms cost roughly 20 bytes
each and are emitted into several blocks, so check the report before adding
more.
