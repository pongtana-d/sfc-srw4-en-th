# The text engine, as found in the clean ROM

All addresses are CPU addresses; file offsets follow HiROM (`PC = (bank & 0x3F)
<< 16 | addr`). Disassemble with `python3 tools/disasm65816.py C1:83FB --count
60 --m 16 --x 16`.

**The engine was already located by the earlier weapon/menu work.** The hook
list in `build/SRW4-TH.json` names every patch site, which saved this pass its whole
search phase. What follows is the clean-ROM reading of those sites.

## Main loop — `$C1:83FB`

```
$C1:83FB  JSR $8A71          ; fetch the next script byte
$C1:8400  BIT $2A / BVS      ; alternate entry for the second text path
$C1:8402  CMP #$00F0
          BCC $842A          ; < $F0 -> ordinary glyph
          AND #$000F
          ASL : TAX
          JMP ($9071,X)      ; >= $F0 -> control, dispatched on the low nibble
```

The alternate entry at `$C1:840F` handles the `$F0`-`$F5` kanji pages: it reads
a trail byte and folds the pair into one 16-bit glyph index with `XBA`.

## Glyph path — `$C1:842A`

```
$C1:842A  ADC $2E            ; add the active font page base
          STA $00
          JSR $8AA1
          LDX $18
          BIT $2A / BPL $8449
$C1:8437  LDA $7E8000,X      ; half-width: merge into the high half of the word
          AND #$FF00
          ORA $00
          STA $7E8000,X
          INC $18            ; advance one half-cell
          JMP $83FB
$C1:8449  LDA $00            ; full-width: write the whole word
          STA $7E8000,X
          INC $18
          INC $18            ; advance two half-cells
          JMP $83FB
```

The engine writes tile indices into a tilemap buffer at `$7E:8000`. It does not
place *pre-existing* tiles, though — see the rasterizer below, which builds a
fresh tile per glyph. `$2E` holds the active font page base and `$18` the
half-cell cursor.

## Glyph rasterizer — `$C1:84F2` … `$C1:855F` (hook `font_classifier_1`)

**This is the routine that makes runtime VWF tractable, and it was the biggest
unknown in the plan.** The engine already converts each 1bpp glyph into 4bpp
tiles in a WRAM shadow buffer, one glyph at a time:

```
$C1:850A  ASL ×4                  ; Y = glyph index × 16 (16 bytes per 8x16 glyph)
          TAY
          LDA $D0 : ASL ×5        ; X = running tile counter × 32 (4bpp tile = 32 bytes)
          TAX
          PHB : LDA #$EE : PHA : PLB    ; DB = the font bank
          LDA #$08 : STA $02            ; 8 rows per 8x8 tile
$C1:8526  LDA $8000,Y : STA $7F8000,X   ; plane 0, top tile
          LDA $8008,Y : STA $7F8020,X   ; plane 0, bottom tile
          LDA $FD     : STA $7F8001,X / $7F8021,X   ; plane 1 — constant colour
          LDA $FE     : STA $7F8010,X / $7F8030,X   ; planes 2/3 — constant colour
          INY : INX : INX
          DEC $02 : BNE $8526
$C1:8555  LDA $D0 : INC : INC : AND #$03FF : STA $D0   ; two tiles consumed
          PLB : RTL
```

Three consequences, all good:

1. **A pixel-composed glyph is a shift and an OR.** Only plane 0 carries the
   glyph; planes 1–3 are the constant colour bytes `$FD`/`$FE`. Compositing two
   glyphs into one cell means OR-ing plane 0 and leaving the colour planes
   alone.
2. **The shadow buffer already exists** at `$7F:8000`, indexed by the tile
   counter `$D0` (masked to `$03FF`). No new scratch pool has to be invented —
   only the allocation policy changes.
3. **Tile allocation is the thing to patch**, not the drawing. Today `$D0`
   advances by 2 per glyph unconditionally. Under VWF it advances by 2 only when
   the pixel pen crosses a cell boundary.

`$D1` bit 7 selects an alternate, wider path at `$C1:8560` that doubles each row
— both paths need the same treatment.

## What runtime VWF therefore costs

- a pixel pen beside `$18`/`$D0`,
- a shift-and-OR in place of the two `STA $7F80xx,X` stores, spilling into the
  next tile when a glyph straddles a cell,
- `$D0` bumped on cell crossings only,
- the advance read from the P3 attribute table at `$C1:8456` instead of the
  constant 2.

No new DMA path, no new VRAM budget, no vblank risk beyond what the engine
already carries — which removes the plan's single biggest stated risk.

## Advance decision — `$C1:8456` (hook `glyph_width_1`)

```
$C1:8456  STA $26            ; keep the glyph index
          CMP #$0100
          BCS $846B
          LDA $28            ; $28 = space left on the line
          BMI $848E
          SEC : SBC #$0002   ; half-width glyph costs 2
          STA $28
          BCS $848E
          BRA $8476
$C1:846B  LDA $28
          BMI $848E
          SBC #$0003         ; full-width glyph costs 3
          STA $28
          BCS $848E
$C1:8476  JSL $818A19        ; out of room -> wrap
```

The second copy of the whole engine lives around `$C1:9200`; `glyph_width_2`
hooks `$C1:9219`. Both must be patched together — that is why every hook in the
build report is doubled.

## How the current build patches it

The sub-pixel work described below as pending has since been written: the
ordinary and battle copies live at `$FF:6000` and `$FF:6A00`, are assembled by
`tools/thai_renderer.py`, and
`docs/rendering.md` is its documentation. This section stays because the
width hook is a separate thing from the renderer, and it still reads the way it
did when it was the whole of the mechanism.

`$C1:8456` becomes `JML $FF0400` (5 bytes, padded with `NOP`), landing in
`thai_width_1`:

```
$FF:0400  STA $26
          CMP #$0700 / CMP #$07EC     ; Thai weapon/menu page
          CMP #$08EC / CMP #$08F0     ; Thai menu specials
          CMP #$0900 / CMP #$09EC     ; Thai name/status page
          CMP #$0B00 / CMP #$0E00     ; VWF packed-cell pages
$FF:042A  CMP #$0100                  ; not Thai: reproduce the original test
          JML $81845B
$FF:0431  CLC                         ; Thai: take the cheap (half-width) branch
          JML $81845B
```

"Thai is one cell wide" is expressed by forcing the carry, nothing more; the
line-budget subtraction the hook exists for still counts whole cells. Real
sub-pixel positioning happens later, inside the renderer, which keeps its own
pen and writes the tilemap word itself.

The `$0700`, `$08EC` and `$0900` ranges tested above are dead. They were the
three-page design this replaced; one page at `$0A00`-`$0AEC` carries every
translated field now, and only the `COMBINING_BASE`/`COMBINING_LIMIT` pair at
the end of the chain can match. They are harmless — no code emits a byte in
those ranges — but nothing keeps them correct either.

## The `FB` handler — resolved

`$C1:8DBA`. It pushes the current source pointer onto a 3-byte-stride stack at
`$0DFD,X` (index in `$14`), reads the two operand bytes, and branches on the
16-bit value:

| operand | behaviour |
|---|---|
| `< $8000` | index × 3 into the pointer table at `$C9:00D8` |
| `$8000`-`$81FF` | index into the 24-bit pointer table at **`$C1:8E6E`** — this is the dynamic-name path |
| `$8200`-`$8FFF` | indirect through `$C9:00EA`, indexed by `(operand & $1FF) × 2` |
| `>= $9000` | `(operand - $9000) >> 8`, × 3, into the script master table at `$E8:0000` |

The `$C1:8E6E` table resolves to WRAM: pilot names on a **7-byte stride** from
`$00:1008`, unit names on an **11-byte stride** from `$00:1032`, each a plain
`$FF`-terminated string. Full table and consequences in
`docs/measurements.md` section D.

## Stock-font passthrough, and why a field can need it

The weapon panel's morale and EN fields are `( <value> )`, written in the JP
script as `3C F8 83 3D` at `0x0CA64E` and `0x0CA65D`. `F8 83` is the engine's
own dynamic value: it draws through the half-cell cursor `$18` and never
touches the renderer's pending VWF run. Encoding the two parentheses onto the
Thai page therefore put both of them in the *same* cell behind the digits —
`(` advances 4px, which crosses no cell boundary, so its run stayed pending
until `)` was appended to it. On screen that is one blob that exists in no
font: rows `28 44 44 82 82 82 44 44 28`, which is `(` OR `)` shifted 4.

The digits were worse and had been wrong for longer: the value's own bytes
reach the classifier tagged for this page as well, and `$30-$39` are blank
there, so the number never drew at all. The panel had been rendering
`---()` where the JP build renders `---(100)`.

Fixed by sending both back to the stock font. `JP_PASSTHROUGH` in
`tools/build_thai_weapons.py` lists page-code ranges and the stock glyph each
maps to — `$30-$39` to `'0'-'9'`, and `$EA`/`$EB` to `'('`/`')'`. The
classifier biases the code into stock range and hands it to the stock
renderer; the width hook charges it a whole cell. The fields are then drawn by
exactly the code and exactly the `$18` arithmetic the JP build used, and they
land on the same pixel columns as the clean ROM — `(` at 91-93, `)` at 121-123
in the morale box — with only the Thai label to the left differing.

Getting a clean-ROM reference needs the input, not just the state: loading a
save state into the clean ROM shows the *translated* screen it was saved with,
because the state carries the composed VRAM. Backing out of the panel and
re-entering (`--press 8:10:b --press 40:42:a`) makes the JP script re-run and
is what produced the comparison above.

Two things this cost a full rebuild each to learn:

- **The parentheses cannot live in `$30-$39`.** They arrive at the classifier
  tagged just like any page code, so a `(` there is indistinguishable from a
  runtime `0` — the field drew five parentheses. They sit at
  `PASSTHROUGH_BASE` (`$EA`) instead, in the tail of the below-mark block,
  where eight slots are still spare.
- **Only the classifier may substitute.** The width hook runs first;
  substituting there left a bare `$3C` in `A`, which is under the internal
  base, so the classifier's raw-byte route read it as a page index and drew
  `เ`. The width hook only charges the cell and passes the code through.

## Stock runs inside Thai text

Static Latin designations no longer consume duplicate glyphs on the Thai page.
`tools/stock_text.py` stores runs such as `HP`, `AI`, `GP-03S`, `mkII`, `ν` and
`Ⅱ` in free bank `$FB`, encoded with the untouched font at `$EE:8000`.  Thai
strings insert them through the game's existing `$FB` nesting mechanism, then
the normal `$FF` return resumes the Thai source.

Operands `$FE00-$FEFF` index a 24-bit table at `$FB:0000`; a narrow hook at
`$C1:8DF3` handles only that previously unused range and reproduces the original
dispatch for every other operand.  The hook lives at `$FC:0000`.  The static
validator rebuilds and compares the table, strings and hook so a translation
catalogue change cannot silently leave mismatched IDs in a second-stage build.

Digits and ordinary punctuation deliberately remain on the proportional Thai
page when they are not part of a Latin designation.  Sending all of them to the
fixed 8px stock font would widen dialogue and create line-wrap regressions for
little page-space gain.

## Still to resolve

- **The `$D1` wide path** at `$C1:8560`, which doubles each row. No translated
  field reaches it, so it has never been given the Thai treatment.
- **Where `$7F:8000` is DMA'd, and when `$D0` resets.** The renderer works by
  parking `$D0` past the cells it holds open rather than by knowing the reset
  point, which has been enough so far; the run detection in `$EA`/`$B6` is what
  notices anyone else moving it.

Settled since: vblank cost was never an issue — the composited path draws one
glyph per call like the original, and `tools/check_combining.py` runs it inside
Mesen without a timing failure.

## Anchors worth keeping

| what | where |
|---|---|
| resource pointer table (24-bit entries, index × 3) | `$CE:0000` — `$EE8000` direct font, `$EE0000` kanji low, `$E24000` kanji high, … |
| resource loader reading that table | `$C2:817A`, `$C2:CA08` |
| decompressor called by the loader | `JSL $80F93D`, source in `$10`-`$12`, destination in `$13`-`$15` |
| control-byte jump table | `($9071,X)`, indexed by the low nibble × 2 |
| runtime name pool (ROM template) | `0x1288ED`-`0x12897D`, packed, `$FF`-terminated |
| live name copy (WRAM) | `$7E:100C`-`$7E:104F`, bounded by the pilot roster at `$7E:1088` |
