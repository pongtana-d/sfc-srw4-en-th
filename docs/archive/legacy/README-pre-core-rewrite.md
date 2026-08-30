# SRW4 Thai localization

This project builds from the unheadered Japanese Rev 1 ROM without modifying the clean input.

- Expected SHA-256: `efd72094b2727c4903924cf9296b3946b95a354f639b600e1d76d9ec6b9ca18b`
- Mapper: HiROM + FastROM
- Clean size: 3 MiB, build size: 4 MiB
- Thai font: linear 1bpp, 8x16 pixels, 16 bytes per glyph, one glyph per character
- Thai encoding: one combining page `$00-$EB`, drawn by isolated ordinary/battle sub-pixel renderers at `$FF:6000` and `$FF:6A00`

Full ROM files are build artifacts and must not be distributed; release patches
should use BPS/IPS against the exact clean hash above.

## Where to read next

| document | what it answers |
|---|---|
| `docs/status.md` | what is translated, what is left, and which open items are decisions rather than work |
| `docs/techniques.md` | the catalogue of methods, and which one applies to which kind of text |
| `docs/pitfalls.md` | **the traps.** Read this before debugging anything that looks like a rendering fault |
| `docs/rendering.md` | the page, the cluster shorthand, the renderer, and how it is checked |
| `docs/text-engine.md` | the clean-ROM disassembly this all hooks into |
| `docs/measurements.md` | the sizing evidence behind the design |
| `docs/glyph-editing.md` | editing the glyphs themselves |

## Design invariants

These hold across every screen and are the ones most easily broken by accident:

- Original dynamic digit slots `$30-$39` stay on the stock digits — the menu writes runtime numbers by poking those codes directly
- Thai glyph codes are true one-cell 8x16 characters to both the cursor and tilemap placement, so the engine does not emit the extra right-half tile it reserves for kanji
- Font routing marks only literal translated byte ranges; numbers, spacing, `+`, `/` and other runtime-control output stays on the stock font page
- Weapon-menu labels occupy shared-cache tiles `$108-$17D`; dynamic weapon text appends after them and stays below the unit artwork in the `$300+` tile range
- Japanese name separators `＝` and `・` are rendered as Thai word spaces
- Non-text sentinels preserved: weapon IDs 653-655

## Build and validate

Build the weapon, menu, unit-name, pilot-name, and pilot-status base patch:

```bash
python3 tools/build_thai_weapons.py \
  --input "rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc" \
  --output "build/SRW4-TH.sfc" \
  --report "build/SRW4-TH.json"
```

Run static validation after building:

```bash
python3 tools/validate_thai_build.py \
  --input "rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc" \
  --output "build/SRW4-TH.sfc" \
  --report "build/SRW4-TH.json"
```

Patch the pre-rendered title resource after the main build. This changes the
four menu rows to `START / LOAD / CONTINUE / OPTION` and retains the stock logo
and space/Earth background unchanged:

```bash
python3 tools/patch_title_screen.py \
  --input "build/SRW4-FULL.sfc" \
  --output "build/SRW4-FULL-title.sfc" \
  --report "build/SRW4-FULL-title.json"
```

The title patch decodes stock resource `$16`, redraws only its OBJ tiles,
repoints the rebuilt resource into checked expansion space at `$FB:1000`, and
repairs the ROM checksum. The input is never modified.

Edit the Thai glyphs in a local visual editor:

```bash
python3 tools/font_glyph_editor.py
```

Its three sources are the whole font. `thai-bases` and `thai-marks` edit the
combining model in `font/thai.json` — marks are shown at the row they rest on,
and every metric is measured back off the pixels on save. `icons` edits
`font/icons.json`, the four terrain badges and the zero-width status pad, which
are the only things on the page that are not letters. Saving and pressing build
re-picks the cluster shorthand, re-lays the page and rebuilds the ROM, because
adding a glyph takes a code the shorthand was using and changes how every string
encodes. The editor opens a browser at an available `127.0.0.1` port; stop it
with `Ctrl+C`.

Preview the result without an emulator. `tools/thai_render.py` is the reference
renderer and `check_combining` runs it against the ROM routine inside Mesen,
row for row. All 37 sheet rows agree, as do 40 lines sampled from the
translated script; the *Checking it* section of `docs/rendering.md` says
what the last ten used to be and why:

```bash
python3 tools/preview_combining.py --spirits
python3 tools/check_combining.py --sheet
```

## How Thai is stored

One page, one byte per character, one glyph per character:

| range | contents |
| --- | --- |
| `$00` | space |
| `$01`-`$80` | spacing glyphs: consonants, side vowels, Latin, digits, punctuation, badge halves |
| `$81` | the zero-width status pad |
| `$82`-`$CF` | cluster shorthand — one byte the renderer expands into two or three of the codes above |
| `$D0`-`$D5` | above vowels |
| `$DA`-`$DE` | tone marks |
| `$E0`-`$E1` | below vowels |
| `$EC`-`$FF` | the game's own icons and controls, untouched |

`$30`-`$39` stay on the stock digits: the menu pokes those codes directly.
`$D6`-`$D9`, `$DF` and `$E2`-`$EB` are free. The boundaries are not hard-coded —
`tools/thai_encoding.py` lays the page out from `font/thai.json` and
`font/icons.json`, so adding a glyph moves them.

Marks carry no advance — they are placed against the base already drawn, lifted
at runtime until they clear it — so a cluster costs exactly the cells its base
does. The shorthand exists because that costs bytes: the banks the game reads
names out of are 16-bit addressed and full, and one byte per character overran
them by about 1100. `tools/build_shorthand.py` measures what is over and spends
the spare codes on the clusters that close the gap, so nothing had to be
precomposed and every glyph is still one character you can open in the editor.

The build preserves the Japanese font and control codes, installs the combining
page, its attribute tables and its renderer in expanded bank `$FF`, repacks
translated weapons across three verified pools in bank `$CC` and translated
names across four in bank `$D2`, translates the menu and status screens listed
in `docs/status.md`, and repairs the SNES checksum. Identical encoded names
share one target string, and player-defined unit/pilot controls remain
lossless.

Pool occupancy as of the last rebuild — `build/SRW4-TH.json` is the live
figure, not this table:

| bank | capacity | used |
|---|---|---|
| `$CC` weapons, three pools | 5,820 | 5,736 |
| `$D2` names, four pools | 5,380 | 5,343 |

Generated build artifacts:

- `build/SRW4-TH.json` — pointer, allocation, checksum, glyph, and translation report,
  including the separate short pilot names used by battle dialogue
- `build/SRW4-TH-overlong.md` — weapon names wider than the 15-cell field
- `build/SRW4-TH-names-overlong.md` — unit/pilot names wider than the 15-cell field (currently empty)

Static validation covers all pointers, source-byte assertions, encoded-string
round trips, pool boundaries, checksum/complement, and deterministic rebuilds.
Emulator display QA uses Mesen save states after a full menu redraw, repeated menu
entry, weapon-list navigation, and repeated `L/R` page switching through
pilot/unit screens. Legacy freezes must be redrawn once (or migrated) because an
emulator restores their old WRAM/VRAM cache contents verbatim.

## Story script

The story script is separate from the menu catalogs above. A 52-entry master
table of 24-bit pointers at `0x280000` selects 47 script blocks spread across
HiROM banks `$E8-$EF`; each block holds its own table of bank-relative 16-bit
pointers, optionally a command-record area (`FC 01 FA nn` headers used by the
battle-quote blocks), then the `$FF`/`$F7` terminated messages. Text reuses the
menu code page: direct glyphs `0x00-0xEB` match the 8x16 font at `$EE:8000`,
`0xF0-0xF5` are kanji pages into the 16x16 font at `0x2E0000` (pages `$F0-$F3`)
and `0x224000` (pages `$F4-$F5`), `0xF6` is a line break, `0xFB aaaa` inserts a
runtime name and `0xFC nn` a runtime macro such as the speaking pilot or the
active weapon.

Extract every message for translation:

```bash
python3 tools/extract_script.py \
  --rom "rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc" \
  --output translations/script.source.json \
  --markdown build/script-source.md
```

Build the two glossary layers before reviewing or synchronising names:

```bash
python3 tools/build_script_glossary.py
```

- `translations/glossary.th.json` is the canonical, full-name reference.
- `translations/rom-glossary.th.json` contains only names proven too wide for
  their actual ROM field.
- `build/glossary.reference.json` is the complete merged reference catalog.
- `build/glossary.rom.json` is the complete map used by ROM fields.
- `build/glossary.script.json` contains only terms found in the story script.

The unit, pilot and battle-speaker tables resolve through the ROM layer. A
short battle label still follows the Japanese label itself (`キース` → `คีธ`),
not the first word of the pilot's full Thai name.

- 9,400 messages across 47 blocks, each with its id, block, PC address, raw
  hex, and decoded text
- `font/jp-kanji.json` holds 1,496 readings for the 16x16 font, transcribed
  from the ROM glyphs, cross-checked against the weapon and name catalogs, and
  confirmed against the words the script builds from them; two shapes the
  script never uses stay unmapped and would decode as `<K0xxx>` index tokens
- extraction fails if any message does not decode and re-encode byte-for-byte

Regenerate the labelled font sheets used for that transcription:

```bash
python3 tools/render_kanji_sheets.py \
  --rom "rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc" \
  --output build/kanji
```

Repack the script, with or without translations from
`translations/script.th.json`:

```bash
python3 tools/build_thai_script.py \
  --input "rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc" \
  --output build/SRW4-script.sfc \
  --translation translations/script.th.json \
  --report build/SRW4-script.json
```

Because the original banks are full, every block is rebuilt in the expanded
area from `$F0:0000` (PC `0x300000`, 417 KiB used, `$FB` upward left free for
the existing fonts and code) and the master table is repointed. Inside a block
the pointer table and command-record area keep their original layout, so only
messages move; message references in both the pointer table and the command
records are remapped, and the SNES checksum is repaired.

Battle-quote blocks are 20–26 (770 messages). They use the same Thai combining
page as the menus; parser 2 tags the repacked story banks `$F0`–`$FA`, and the
battle call-site dispatcher routes Thai glyphs to `$FF:6A00`.

Validate the repack against the clean ROM:

```bash
python3 tools/validate_script_build.py \
  --input "rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc" \
  --output build/SRW4-script.sfc \
  --translation translations/script.th.json
```

This checks block and message counts, per-message bytes (translated messages
against their re-encoded text, untouched ones against the original), that every
pointer and command-record reference still selects the same text, and that the
checksum pairs. With no translations the repack reproduces all 9,400 messages
byte-for-byte and rebuilds deterministically.

Three things make that comparison less literal than it sounds, and the validator
has to know all three:

- Translations encode through `ThaiCodec`, the same combining-page codec the
  repacker uses. The plain Japanese codec cannot spell Thai at all.
- A record block does not store where its text begins; `parse_block` normally
  finds it by looking for a message that opens with `「` or a name macro, which
  no Thai line does. The validator takes the offset from the clean ROM instead,
  because the repack keeps the pointer table and record area exactly their
  original size.
- References move on purpose — pointers, structurally parsed battle-record
  operands, and the eight-way
  `FC 08` personality branch stored inside a message body — so those are checked
  by which message they select, not by their bytes.

Translated lines must keep their trailing `<ENDFF>`/`<ENDF7>` terminator and any
`<FB:aaaa>`/`<FC:nn>` macros.

The repack writes text only. Layer it onto the menu build to get every patched
byte in one ROM:

```bash
python3 tools/build_thai_script.py \
  --input build/SRW4-TH.sfc \
  --output build/SRW4-FULL.sfc \
  --translation translations/script.th.json \
  --report build/SRW4-FULL.json
```

Menus and the story window use two separately assembled renderers. The ordinary
path is `$FF:6000`; battle dialogue is dispatched at `$C1:9238` to `$FF:6A00`.
They share glyph tables but not persistent state: ordinary state is
`$7E:FFA0-$FFBF`, battle state is `$7E:FFC0-$FFDF`, and renderer-only temporary
work is `$7E:FFE0-$FFFF`. No renderer-owned value lives in direct page or in the
battle line tables at `$7E:F000-$F3FF`.

Watching `$FF:6000` counts ordinary calls; watching `$FF:6A00` counts battle
dialogue calls. A save state has its screen already composed, so this needs
`--press`; without it the count is zero and the screenshot is the frame the
state was taken on, not the frame this build would draw.

The supplied states are `saves/SRW4-FULL_1.mss` … `_4.mss`. One press is often
not enough to make a menu redraw — leave the screen and come back, and check
the hit count before believing the screenshot:

```bash
python3 tools/run_mesen.py build/SRW4-FULL.sfc \
  --state saves/SRW4-FULL_2.mss \
  --frames 300 \
  --press 30:34:b \
  --press 60:64:a \
  --out build/mesen/status \
  --watch 0xFF6000
```

A zero hit count means you photographed the frame the state was captured on.
`docs/pitfalls.md` has the test that catches this every time.
