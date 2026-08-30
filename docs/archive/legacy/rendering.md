# How Thai text is stored and drawn

Every translated string in the game — weapons, unit and pilot names, the weapon
menu, the pilot-status screen, spirit commands, skills, the spirit descriptions
on the map — goes through one code page and one rasterizer. This document is
the state of that system as it ships. `docs/text-engine.md` is the
clean-ROM reading of the engine it hooks into, and `docs/measurements.md` the
measurements that set the shape of it.

## The page

One byte per character, one glyph per character.

| range | contents |
|---|---|
| `$00` | space, 4px |
| `$01`-`$80` | 119 spacing glyphs: consonants, side vowels, Latin, digits, punctuation, the seven terrain-badge halves |
| `$81` | the zero-width status pad |
| `$82`-`$CF` | 78 cluster shorthand codes |
| `$D0`-`$D5` | above vowels |
| `$DA`-`$DE` | tone marks |
| `$E0`-`$E1` | below vowels |
| `$EC`-`$FF` | the game's own icons and controls, untouched |

133 codes are spoken for and 25 are free: `$30`-`$39`, `$D6`-`$D9`, `$DF` and
`$E2`-`$EB`. Nothing here is a constant in the source — `tools/thai_encoding.py`
lays the page out from `font/thai.json` and `font/icons.json` and
`tools/build_shorthand.py` decides how much of it the shorthand takes, so every
boundary above moves when a glyph is added. `$30`-`$39` are the exception that
is deliberate: the menu writes runtime numbers by poking those codes directly,
so whatever page is active has to keep the stock digits there.

Marks carry no advance. They are placed against the base already drawn —
right-aligned to its ink, nudged by their own `dx`, and lifted at runtime until
they clear whatever is underneath — so a cluster costs exactly the pixels its
base does. That is the whole reason the page fits: 13 marks and 57 Thai bases
cover the language, where the precomposed page this replaced needed 213 and 228
glyphs across two pages and still could not spell everything. The other 54 bases
are Latin, digits and punctuation, which the page has to carry because a
translated field is drawn entirely from it.

`font/thai.json` holds the letters, `font/icons.json` the artwork that is not a
letter, and `tools/thai_encoding.py` lays both out over the page into
`font/encoding.json`.

## The cluster shorthand

One byte per character costs bytes. Every place the game reads text from is
full, and none of it can move: the pointers are 16-bit, so a string physically
cannot leave its bank, and the spirit descriptions are not pointed to at all and
have to be overwritten where they lie. Encoding one byte per character overran
those by about 1100 bytes in total.

The spacing block had about a hundred codes nobody was using. Each one now
stands for a whole cluster — a base plus one or two marks — and the renderer
expands it at draw time into exactly the codes a translator would have written
out. Nothing else in the system knows: the components go down the same base and
mark paths and leave the same pen and cell state behind.

Which clusters get a code is decided by `tools/build_shorthand.py`, from the
translations themselves, because the constraints are unrelated to each other:

| constraint | kind | shape |
|---|---|---|
| bank `$CC` | pool | every weapon string against 5820 bytes in three pools |
| bank `$D2` | pool | every unit, pilot, and battle short name against 6732 bytes in five pools |
| spirit descriptions | per string | each against the hole its Japanese original left |
| pilot-status labels | per string | each against its fixed span in the script |

Ranking clusters by overall frequency satisfies none of these in particular, so
each round measures what is actually still over and spends the next code on
that. Adding a base takes a code from this block, which is why the editor
re-picks the shorthand before it rebuilds.

Battle dialogue reads a second 320-entry pilot table at `0x12772B`, not the
full pilot-name table used by menus. Its short strings occupy
`0x1279AB`-`0x127F03`; the build repoints all 320 entries to Thai short names
and routes that pool through the same combining renderer. The speaker strip
already supplies its own spacing, so these names contain no appended colon.

Latin runs inside those names still use the project's private `FB $FExx`
stock-font insertion (for example `AI`). Battle dialogue has a separate `FB`
interpreter from ordinary text, so `tools/stock_text.py` hooks both engines.
The battle hook preserves its three-byte return stack and opens the same
deterministic stock-string pool; without it, `$FExx` is mistaken for a runtime
name and consumes bytes reserved for the post-battle reward fields.

## The renderer

`tools/thai_renderer.py` assembles two context-specific copies. Ordinary text
(menus, status and map labels) enters `$FF:6000` through the two font
classifiers. Battle dialogue is split at its own stock rasterizer call at
`$C1:9238` and enters `$FF:6A00`; digits, parentheses and other stock glyphs
still fall back to `$81:84EB`. Both are sub-pixel renderers and share the same
glyph and shift tables at `$FF:3000` and `$FF:3800`, but they do not share
persistent state.

Most of its bookkeeping is about staying out of the engine's way. The engine
hands out tiles through a single counter, `$D0`, and derives the tilemap's tile
number from it *before* calling the rasterizer — so a cell held open across
several glyphs cannot leave `$D0` pointing at itself. The renderer parks `$D0`
past both the open cell and the pair its spill lands in, and writes the tilemap
word itself.

| work RAM | owner | lifetime |
|---|---|---|
| `$7E:FFA0-$FFBF` | ordinary renderer | persistent across ordinary glyphs |
| `$7E:FFC0-$FFDF` | battle renderer | persistent across battle glyphs |
| `$7E:FFE0-$FFFF` | both renderers | temporary during one call only |

Every renderer-owned access uses a 24-bit address. Generated code is rejected
if it touches direct page outside the engine interface: `$00-$01`, `$18-$19`,
`$2E-$2F`, `$D0-$D3` and `$FD-$FF`. The battle copy does not use ordinary
cursor `$18`. Each persistent block starts with signature `$A55A`; loading an
old save in the middle of a combining mark therefore drops that orphan mark
instead of drawing it against stale state.

The last 96 bytes of bank `$7E` are cleared by the stock boot loop at
`$80:EFCB`. Write-watch runs from cold boot and the supplied battle/menu states
found no later stock writer. The build also rejects any reservation overlapping
known tilemap buffers, map pointers, battle line tables or the dynamic-tile
shadow. This is the ownership evidence for the reservation; it is stronger
than merely finding bytes that happen to be zero in one save.

Earlier versions borrowed direct-page bytes. `$F0-$FB` are map-renderer source
pointers and `$D6` is the event engine's condition register. Corrupting the
former filled the map with menu tiles; corrupting the latter indexed past an
event jump table and eventually reached the `STP` at `$80:EFF6`.

A freeze taken while the old build had those pointers overwritten cannot be
repaired by loading it on a fixed ROM: writing the four constants back at load
time still leaves the buffers behind them destroyed, so such a state has to be
replaced, not migrated.

The next attempted home, `$7E:F000`, was also owned: the battle engine uses
`$7E:F000-$F3FF` as its line/geometry tables. The attack-hit transition is where
that ownership becomes live. A shared renderer state there could be overwritten
by battle setup and could overwrite battle geometry in return, explaining the
simultaneous dialogue, tile and combat-screen corruption. The current build
explicitly rejects that range and keeps ordinary and battle state separate.

The dialogue compositor also owns its tilemap placement. It stages the two
speaker windows through a different cursor from the ordinary menu path and
writes the final tilemap words itself. On this path the Thai renderer keeps the
compositor's `$D0` tile pair and only rasterizes glyph data; emitting the usual
`$7E:8000+DP_COL` column as well creates a second copy of the lower speaker over
the map and makes reused glyph tiles look like random graphics corruption.
Menus and status screens still use the renderer-owned tilemap path.

Run detection compares the caller's `$D0` against the matching private expected
value. The ordinary copy additionally compares `$18`; the battle copy has no
ordinary cursor contract. This compile-time split replaces the old heuristic
that tried to guess which engine was calling from a shared direct-page byte.

Tail handling has two separate tests. First, a tail tile is named only when a
shifted bitmap row actually put a pixel in it. Testing only `pen != 0` was too
broad: `กำแพง` ends at 31px, so its final `ง` leaves the pen between cell
boundaries but puts no pixel in a fifth cell. The old test still named that
blank fifth pair and replaced the spirit window's right frame.

Second, the ordinary engine prepares one tilemap write around every rasterizer
call using a word it computed from `$D0`. During a VWF run `$D0` is parked on a
blank guard pair, so leaving that word named in an unused column makes later
tile reuse appear as stray text. Before returning, the renderer replaces the
pending word with the current cell's word and points `$18` back at that same
column. A trailing base-plus-mark that crosses a cell is encoded as one
shorthand call, and a fixed label followed by stock digits uses a blank spacing
guard; both keep the repeated write away from real tail ink. The dialogue
compositor is excluded because it owns its own tilemap placement.

The parked pairs are still required. They protect the open cell and its spill
from a stock digit, icon, or Latin glyph that allocates through the shared
`$D0` counter. They are transient pairs in the `$400`-tile circular shadow
buffer, cleared and reused after the run; they are not permanent ROM tiles and
not spare storage another feature can safely claim. `restart` also begins one
pair past the previous guard so a later run cannot make old ink reappear in a
dead column, the former stray glyph after `ฮึดสู้`.

Where a run stops is the other thing that matters, and it is why one screen
deliberately does not use this renderer at all. Spell the unit command menu
proportionally and each line starts a cell further off than the one above it,
until the drift is a whole row. Padding every entry back to a common
stopping point works, but the only point available is three cells of ink
spilling into a fourth: three *and* a spill, never four cells flat, because
claiming the fourth cell outright writes over the frame's right edge. That
leaves three usable cells for a four-cell box.

So the menu is spelled with the stock 8x16 font instead, and its block is absent
from the classifier chain in `source_range_checks`. One cell per glyph means a
fixed letter count stops in a fixed place, with no padding and no arithmetic.

The count is three. The box is 24 pixels wide — measure the green highlight
band, which sits at x 208-231 in the post-move menu and is the same 24px in the
clean ROM. The kanji this menu was built for are 12px, not 16, so two of them
fill it exactly; so do three 8px letters. A fourth letter is drawn at x 232-239,
which is the frame's own column, and eats the border: `WAIT` put a bare stem
where the box edge should be. `encode_stock_menu` in
`tools/build_thai_weapons.py` refuses a fourth letter rather than let it
truncate, and the page only carries `A`-`Z`, `0`-`9` and space, so the entries
are three uppercase letters. The shield line next door does not drift and stays
on the Thai page.

**The explanation this section used to give was wrong, and the real one is a
cell that overflows.** It said the engine implements `F6` as a constant added to
wherever the cursor stopped. Measured 2026-08-17 against the clean ROM, it does
not: the handler the `$81:9071` table sends `F6` to is `$81:8CE8`, and it
computes `$16 + $0040` — the *line origin* plus a row, stored to both `$18` and
`$16`. `FD` at `$81:8EF4` is absolute as well. Neither can drift.

What actually happens, from `--watch-write 0x18:0x19` over the spirit-search
grid: the grid repositions with `FD` once per cell, columns `$0C` apart, and
between those the stock path steps `$18` two bytes per byte drawn at
`$81:8449`. A cell is six bytes. A name longer than that keeps drawing into the
next cell, and the next `FD` pulls the following cell back into place — so a
long name in the middle of a row costs only the cell beside it. On the row's
*last* cell there is no `FD` left before the row ends: the text runs off the end,
wraps, and lands half a row down, and because it is past the run's end it names
stale tiles. That is the band of stock-font garbage under `เร่ง` and `กำแพง`.

So the invariant is per cell, not per line: **every spirit-name record contains
exactly `SPIRIT_ENTRY_BYTES` = 6 source bytes before its terminator**, padded
with `<Pad>` by `install_pilot_status`. `<Pad>` is intercepted by the parser and
never reaches the renderer: it draws no pixel, advances no VWF pen and allocates
no tile. Its job is to preserve the grid's fixed source-record traversal. Six
is measured — padding to seven leaves one stray glyph after `เดือด`; terminating
all records at their natural encoded length tears and shifts the grid.
Four names did not fit six, so `tools/build_shorthand.py` now spends its first
codes on the spirit cells before any pool: a pool that overshoots stops the
build with a message, and a spirit name that overshoots tears the grid at
runtime. Six codes close it and no name is spelled shorter to suit the engine.

The unit command menu drifts for the same reason, and the same padding would
hold it still. Measured 2026-08-17, a Thai entry there has to clear two
ceilings, not one: 24px of ink *and* four bytes, the four being what the
cursor counts. Eleven of the fifteen commands have a natural Thai word inside
both — `เดิน` `ซ่อม` `แปลง` `แยก` `เติม` `รวม` `จิต` `รอ` `พาร์ท` and the
terrain set `ใต้ น้ำ บก ฟ้า`, which is the vocabulary the type values already
use. `ข้อมูล` is 24px but five bytes, and would need the shorthand pointed at
it the way the spirit cells were. `โจมตี` misses both at 25px and five bytes
and has no rescue; `ตี` or `ยิง` is the honest substitute.

The four-byte figure is read off `UNIT_COMMAND_CURSOR_CELLS` and the comment
beside it, **not** off a write-watch. Measure it before spending work on the
menu: this document has already been wrong twice about cursor arithmetic.

Measure this kind of box off the highlight, not off the frame. The frame is
drawn wider than the text field, so counting its cells says four and reading the
highlight says three.

The other thing that reaches the stock path is the MAP/B/P attribute a weapon
name can end with, `$EC`-`$EF`. It is an ordinary 8x16 glyph — `$EC` is the MAP
box, `$EE` the circled B — so the parser hooks hand the byte over untouched:
parsers 1 and `1_alt` to the rasterizer at `$81:8456`, parser 2 to that engine's
own attribute handler at `$81:9247`, which is exactly where each parser's
`original_body` sends the same byte for an untranslated name. Both addresses are
the target of the branch the stock code takes for the same byte — `$81:9204`'s
`BCC` lands on `$9247`, and `$9248` is the middle of the `JMP $94DC` sitting
there. A `JML` one byte late executes `JMP [$94DC]` instead, and the wild jump
ends in the ROM's `SEI : JML *` trap at `$80:EFF1`: pressing A to attack froze
on a black screen. Tagging it with
`ORA #$0800` first, the way translated names used to, forces it down the 16x16
path and reads `$22A000 + code * 32` — past the end of that font — so every name
carrying an attribute drew two cells of unrelated ROM bytes after it.

## Checking it

`tools/thai_render.py` is the specification — a Python renderer that draws the
same page by the same rules. `tools/check_combining.py` runs the ROM routine
inside Mesen against an isolated driver and compares the result row for row. It
also places a `$201C` frame word immediately after the last cell and emulates
the engine's post-render tilemap write; any blank or unnecessary tail that
claims the frame fails the same test:

```bash
python3 tools/check_combining.py --sheet
```

The sheet is chosen so that a pass means something: every mark on a plain base,
then the four things the placement rules exist for — marks over tall consonants,
two-level stacks, tone marks that rise when a vowel is already there, below
marks under the descenders they collide with — and real corpus strings, because
a rule can be right in isolation and wrong in the middle of a word.

All 40 sheet rows agree with the reference renderer.

Ten of them did not until 2026-08-16, and the reading that they were an
artefact of the driver was wrong — both shapes were real, and both were
visible in the game:

- the **raised second mark** of a two-level stack landed at an arbitrary column
  (`ลื่`, `ฟื้`, `ซื้`, `ตื่`, `นึ่`, `อึ๊`, and `งั้น` on screen). The
  collision probe was reusing the base anchor — then at `$D6`-`$D9` — on the grounds
  that it is dead once the mark's tile and column are known. It is dead for
  that mark and not for the next one, and a second mark on the same base read
  shift-table leftovers. The probe has its own bytes now.
- the mark on the row's **first** cluster was missing (`อัศจรรย์`,
  `กักิกีกึกื`, `เครื่องยนต์`). A mark wider than its base's ink starts left of
  the pen — `ก` is 5px of ink and `ั` is 5px with `dx` -1 — and mid-word that
  pixel belongs in the previous pair, which is what the 8px bias on `MARK_X`
  is for. On the first base of a run there is no previous pair, so it went to
  a tile the engine had given to someone else. Both sides clamp to the run's
  own cell now, which shifts the mark right by a pixel rather than losing it.

To look at text without an emulator at all:

```bash
python3 tools/preview_combining.py --spirits
```

To watch the engine draw:

```bash
python3 tools/run_mesen.py build/SRW4-TH.sfc --state saves/SRW4-TH_11.mss \
    --frames 200 --out build/mesen/run --watch 0xFF6000 --press 40:70:b
```

A loaded save state has its screen already composed, so the rasterizer never
runs without replayed input — `--press` is not optional. `--watch` counts
executions and traces the first 160, which is how the pilot-status screen was
confirmed to route all 171 of its glyphs through this renderer.

## Known gaps

- All weapon names now fit the 15-cell field together with their fixed
  `MAP`/`B` attribute badges. IDs 355 and 474 use the approved shorter Thai
  names; `build/SRW4-TH-overlong.md` reports zero overruns.
- The `精神検索` spirit-search grid is fixed, and the reading that it was "half
  routed" was wrong — it was routed all along. Fixed-size six-byte records stop
  row tearing; separately, actual-pixel tail detection plus the harmless stock
  tilemap rewrite preserves the right frame beside `กำแพง`. At tilemap offset
  `$233C` the Thai redraw now has `$201C`, identical to the Japanese layout.
- 5 of the 30 spirit commands are wider than the 4-cell selector, and all five
  by 1-3px: `แม่นยำ`, `ข่มขวัญ`, `เดินซ้ำ`, `ซ่อนตัว`, `วิญญาณ`
  (`tools/preview_combining.py --spirits` prints the count). A shorter spelling
  for any of them is a translator's call, not a renderer change.
- The ユニット能力 unit-ability screen and its shared tab bar use stable
  English labels, while unit abilities, values and the map unit-command menu
  remain Thai — `translations/unit-status.th.json` and
  `translations/unit-commands.th.json`.
- Below marks still collide with the descenders of `ญ ฎ ฏ ฐ`, because the lift
  only works upward. Left alone deliberately: those consonants do not take a
  below vowel in normal Thai. `ญู` is the exception, and rare enough to spell
  around.

## The map command menu

The menu the map pops up on A — `ターン終了 / 部隊表 / 全体マップ / 精神検索 /
命令 / システム / 作戦目的 / セーブ`. The data and display are now both
covered by the build.

The block is one script at `0x0C95EA`-`0x0C9625` (CPU `$CC:95EA`): a four-byte
header `40 FC 01 EF`, eight labels separated by `$F6`, `$F7` at the end. The
next block starts immediately at `$CC:9625`, so the translated labels get exactly the
47 bytes the Japanese ones had — 59 less the header, the seven separators and
the terminator. The narrow box safely holds at most eight stock Latin
characters. The approved short forms are `END` and `OBJ`; both byte length and
visible width are enforced by regression tests.
The English labels use direct stock glyphs so opening this menu does not allocate
dynamic text or disturb the `TURN` / `FND` HUD. They use 35 of the 47
available payload bytes, leaving twelve padding terminators after the first `$F7`:

| Japanese | English | bytes | cells |
|---|---|---|---|
| ターン終了 | END | 3 | 3 |
| 部隊表 | UNITS | 5 | 5 |
| 全体マップ | MAP | 3 | 3 |
| 精神検索 | SEARCH | 6 | 6 |
| 命令 | ORDER | 5 | 5 |
| システム | SYSTEM | 6 | 6 |
| 作戦目的 | OBJ | 3 | 3 |
| セーブ | SAVE | 4 | 4 |

The builder patches the block and leaves it on the original stock-font path. On
a genuine redraw in Mesen, all eight labels are visible at the intended columns.
The saved map-menu state was checked with:

```bash
python3 tools/run_mesen.py build/SRW4-FULL.sfc --state saves/SRW4-FULL_1.mss \
    --frames 300 --out build/mesen/mapmenu --watch 0xFF6000 \
    --press 30:34:b --press 70:74:b --press 110:114:left --press 150:154:a
```

The two `b` presses close the pilot and unit screens, `left` moves the cursor
off the selected unit, and `a` opens the map-command menu on that empty tile.
Without a genuine redraw the screenshot is only the frame captured in the state.

## The map HUD

The two static labels in the top-right corner are separate inline records beside
the dynamic counters: `ターン数` becomes `TURN`, and `資金` becomes `FND`.
`TURN` uses four of its seven bytes and fills the remaining three with stock
spaces; `FND` uses three bytes and keeps one trailing guard space. Both labels and their dynamic
numbers remain on the stock path. The stock `$F8` controls retain their full
three- and seven-digit fields, while the parser moves their starting cursor one
8px cell left so the last digit clears the right frame. A Mesen redraw confirms
them together with the command menu.
