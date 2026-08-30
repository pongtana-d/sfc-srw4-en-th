# Editing the glyphs

The worklist this file used to carry is done. Every base it listed as missing
(`ฌ ฤ ฦ ฯ ๅ`) is on the page, `๋` has been drawn, and the derived marks have all
been through the editor. What remains is how to keep editing them.

## Edit them here

`python3 tools/font_glyph_editor.py` edits `font/thai.json` directly through its
**thai-bases** and **thai-marks** sources, and `font/icons.json` through
**icons**. Marks are shown at the row they rest on rather than floating at the
top of an empty cell, so they can be judged against the base they sit over.
Everything the canvas can change is measured back off the pixels on save — ink
width, height, resting row, advance. `dx` and the raised tone rows are placement
decisions no bitmap implies, and are left alone.

Saving and pressing build re-picks the cluster shorthand and re-lays the page
before it rebuilds the ROM, because adding a glyph takes a code the shorthand
was using and changes how every string encodes.

Check the result without an emulator:

```bash
python3 tools/preview_combining.py --limit 8 --scale 5 \
    --out build/marks-preview.png "กิ กี กึ กื กุ กู" "ปิ ปี ปึ ปื ปั ป็"
```

`tools/check_combining.py --sheet` is the stronger check, and it passes: all 37
rows agree. The ten that used to differ were fixed on 2026-08-16 — they were two
real placement faults, not the driver artefact this file used to claim. The
*Checking it* section of `docs/rendering.md` says what they were.

It needs `build/SRW4-TH_1-fixed.mss`, which is not in the repo, and **renders
from boot rather than failing when the state is missing** — every row differs,
all shifted 8px. A total failure means a missing state far more often than it
means a broken renderer.

## Where the shapes came from

The marks were originally derived by subtracting bases from the precomposed
clusters, which reproduced 99 of 207 single-mark clusters exactly. Both the
derivation tool and the cluster data it read are gone; the marks are maintained
in the editor now. `docs/measurements.md` section A has the sample counts that
derivation produced, which is still the best guide to which marks rest on the
least evidence — `์`, `๊` and `ึ` were the thin ones.

## Still worth an eye

- **Below marks ignore descenders.** `ญ ฎ ฏ ฐ` have ink in rows 11-14 and `ุ ู`
  sit at 13-15, so they overlap. Deliberately left alone: those consonants do
  not take a below vowel in normal Thai, and `ญู` is rare enough to spell
  around. Fixing it properly means a downward lift in the renderer or four
  redrawn tails.
- **Narrow ink is what pays.** `docs/measurements.md` section B is the reason the
  bases are drawn tight: VWF over cell-filling glyphs returns ~7%, over narrower
  drawings 23-34%. The build report prints the saving per field
  (`tools/build_thai_font.py`), currently 15.6% on weapons and 22.0% on the
  script.
