# Sizing measurements behind the design

Measured against the precomposed font this project has since replaced;
the numbers are kept because they are what set the shape of the rewrite.
See `docs/rendering.md` for what shipped. (Raw numbers landed in
`build/p0-measurements.json`). Everything below comes from data already in the
repo plus the Mesen save states, which live in `saves/` now.

## A. Combining glyph budget — comfortable

| | |
|---|---|
| Base glyphs already standalone | 91 (43 Thai consonants + vowels + Latin/digits) |
| Legacy precomposed clusters | 259 |
| Combining marks recovered by subtraction | 12 / 12 |
| Clusters that failed to resolve | 0 |

Every mark the project uses (`ั ิ ี ึ ื ุ ู ็ ่ ้ ๊ ์`) exists **only** inside
precomposed clusters today, but all 12 are recoverable by subtracting the base
bitmap. The hand-tuned pixel work is therefore reusable.

After restricting the subtraction to the mark's own vertical band (rows 0–7 for
above marks, 11–15 for below marks), one dominant shape covers most clusters:

| mark | clusters | distinct shapes | dominant |
|---|---|---|---|
| `่` | 20 | 2 | 95% |
| `ั` | 28 | 4 | 89% |
| `็` | 17 | 3 | 88% |
| `ื` | 7 | 2 | 85% |
| `้` | 21 | 4 | 85% |
| `ิ` | 25 | 4 | 72% |
| `ี` | 21 | 6 | 61% |
| `ู` | 22 | 3 | 45% |
| `ุ` | 18 | 3 | 38% |
| `ึ` | 6 | 5 | 33% |
| `๊` | 2 | 2 | — (too few samples) |
| `์` | 20 | 17 | 15% |

The residual shapes differ for two reasons, both benign:

- **Positional nudging.** Below marks (`ุ ู`) sit under the base's ink centre, so
  their x offset varies per base. This is an *attribute*, not a new glyph.
- **Ink erosion.** Where a mark overlaps a tall base (`ป ฟ ฬ ล ษ`), subtraction
  removes the shared pixels and the residual looks different. The canonical
  shape is the dominant one.

`์`, `๊` and `ึ` do not have enough clean samples and will need hand work in the
editor.

**Page budget:** even the pessimistic reading — bake every observed variant as
its own glyph — lands at **177 of 236 usable byte codes** (`$00`–`$EB`, since
`$EC`–`$FF` are already claimed by icons, kanji pages, line break, terminators
and the `FB`/`FC` macros). Storing position as a per-base attribute instead
brings it nearer 110–130. **No escape page is needed.** This resolves decision
#5 from the plan.

## B. VWF saving on real Thai text — much smaller than assumed

Measured across all 1,097 finished Thai strings (10,747 clusters) in
`translations/`:

| glyph advance cap | mean advance | cells | saving |
|---|---|---|---|
| 8px (honest ink+1) | 7.02px | 10747 → 9925 | **7.6%** |
| 7px | 6.60px | 10747 → 9354 | 13.0% |
| 6px | 5.82px | 10747 → 8228 | 23.4% |
| 5px | 4.91px | 10747 → 7087 | 34.1% |

Mean base-consonant ink width is **6.67px of an 8px cell** — the legacy glyphs
were drawn to fill a fixed cell, so there is almost nothing for VWF to reclaim.

**This is the most important P0 result and it revises the plan's premise.**
Runtime VWF on the current glyph shapes buys ~7%, which will not rescue a Thai
line that overflows. The saving comes from *redrawing the bases narrower*; VWF
is only the mechanism that lets a narrower drawing pay off. The two must ship
together.

The 5px row is not hypothetical — the current build already forces a 5px cap on
weapon and name fields, accepting overlap. Redrawn bases would reach the same
compression honestly.

Combining marks are what make the redraw affordable: ~130 glyphs to redraw
instead of 2,000 precomposed clusters.

## C. Line-width budget — from the Japanese source

16,188 lines parsed from `translations/script.source.json`, counting a kanji as
two cells and everything else as one:

| p50 | p90 | p99 | max |
|---|---|---|---|
| 25 | 32 | 35 | 45 |

Messages are 1 line (4,886), 2 lines (3,017) or 3 lines (1,229); longer ones are
rare and likely non-dialogue blocks.

**Working budget: 32 cells per line.** Thai renders longer than Japanese for the
same content, so a 23–34% VWF saving (cap 6px / 5px) is roughly what is needed
to hold parity — consistent with the conclusion in B.

## D. Player-name buffer — RESOLVED

> Superseded during P4: the `FB` handler was disassembled and settles this. The
> original static-only reasoning is kept below for the record.

`FB aa bb` dispatches through `$C1:8DBA`. For an operand in `$8000`-`$81FF` —
which covers every dynamic name slot — it does:

```
$C1:8E18  AND #$00FF : TAX
$C1:8E1C  LDA $818E6E,X -> $1A      ; 24-bit pointer table at $C1:8E6E,
$C1:8E22  LDA $818E6F,X -> $1B      ; read as two overlapping 16-bit loads
$C1:8E28  JMP $83FB                 ; carry on reading text from there
```

So the operand is an **index into a table of 24-bit pointers**, stride 3 — which
is exactly the stride observed in the catalogs. Reading that table:

| slot | target | field |
|---|---|---|
| `$8000 $8006 $800C` | `$00:1032 $00:103D $00:1048` | unit names, **stride 11** |
| `$8012 $8018 $801E $8024 $802A $8030` | `$00:1008 $00:100F $00:1016 $00:101D $00:1024 $00:102B` | pilot names, **stride 7** |
| `$8003 $8009 $800F` | `$00:1FD1 $00:1FDC $00:1FE7` | second copy, stride 11 |
| `$8015 $801B $8021 $8027 $802D` | `$00:1FA7 $00:1FAE $00:1FB5 $00:1FBC $00:1FC3` | second copy, stride 7 |

Bank `$00` mirrors WRAM, so these are the `$7E:1000` names dumped from the save
state — and the strings line up exactly: `ライクリング` (6 chars + `$FF` = 7) fills
a pilot slot at `$00:100F`, `ヒュッケバイン` (7 + `$FF` = 8) sits in an 11-byte unit
slot at `$00:1032`.

**Capacity, therefore:**

- **pilot name field: 7 bytes → 6 characters plus the `$FF` terminator**
- **unit name field: 11 bytes → 10 characters plus the `$FF` terminator**

Under the combining model a Thai cluster costs 1–3 bytes, so a Thai pilot name
holds roughly 2–4 visible clusters and a unit name 4–7. Tight, but real.
Decision #6 stands as recommended: **cap the naming screen by bytes, do not
expand the buffer** — the second copy at `$1FAx`/`$1FDx` shows these fields are
copied around, so widening them would ripple.

## D (original static reasoning, superseded)

The dynamic name slots are visible in the extracted catalogs as `FB aa bb`
macros (`kind: "dynamic_name"`):

- **Units** (`translations/units.source.json`, IDs 1–8): `$8000 $8003 $8006
  $8009 $800C $800F`
- **Pilots** (`translations/pilots.source.json`, IDs 248–251): rendered as
  `<NAME:A>＝<NAME:B>` from `$8012 $8015 $8018 $801B $8024 $8027 $802A $802D`

**Stride is exactly 3 bytes across all 14 slots.** Two readings fit:

1. Inline text, 3 bytes per name — brutally tight, and Thai player names would
   be impossible without expanding the buffer.
2. A table of 24-bit pointers to name buffers elsewhere — the more likely
   reading, and it leaves the actual name length unconstrained here.

Neither save state has player-defined units (`cart.saveRam` holds
only the `Sirius Works 009JS` header, no save game), and `$7E:8000` / `$7F:8000`
contain unrelated data in both, so the bank the `FB` handler reads from is not
resolvable statically.

**Resolution: disassemble the `FB` handler during P4.** The text renderer has to
be located there anyway, and the handler sits immediately beside it. Until then
decision #6 stands as recommended: treat the existing buffer as a byte budget
and do not expand it.

Also recovered: the ROM's runtime name pool at `0x1288ED`–`0x12897D` (packed,
`$FF`-terminated) and the live copy at WRAM `$7E:100C`–`$7E:104F`, bounded above
by the pilot roster at `$7E:1088` that `tools/patch_mesen_roster.py` already
uses.

## Consequences for the plan

1. **P2 gains a deliverable:** narrower base consonants, not just mark
   extraction. Target ~5–6px ink so VWF returns 23–34% instead of 7%.
2. **Decision #5 is closed** — one 256-code page, no escape page.
3. **Decision #6 stays open** until the `FB` handler is read in P4; P7 is the
   only phase that depends on it.
4. Seven translated clusters have no glyph yet (`ฟื้ นึ่ อึ ฝั ซึ่` and `%`,
   `O`) — they disappear once marks compose freely, which is itself a small
   proof of the combining model's value.
