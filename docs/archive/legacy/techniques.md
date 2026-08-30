# The techniques this project uses

A short catalogue of how Thai gets into this ROM, and — more usefully — which
technique applies to which kind of text. Picking the wrong one is most of how
time gets lost. `docs/rendering.md` is the deep reference for the page and the
renderer; this file is the map above it.

The governing constraint: **the clean ROM is never modified, and the original
banks are full.** Pointers inside them are 16-bit, so a string physically
cannot leave its bank. Everything below is a way around that.

## 1. One combining code page

One byte per character, one glyph per character, and marks that carry no
advance. 57 Thai bases and 13 marks cover the language where the precomposed
page this replaced needed 213 and 228 glyphs across two pages and still could
not spell everything.

`$30`-`$39` must stay on the stock digits — the menu writes runtime numbers by
poking those codes directly.

## 2. Cluster shorthand

Spare codes in the spacing block each stand for a base plus one or two marks,
expanded by the renderer at draw time. Nothing else in the system knows.

This exists purely to buy **bytes**, not pixels. It is re-picked from the
translations on every build, measured against the constraints that are actually
still over — the `$CC` and `$D2` pools, per-string spirit descriptions,
per-span status labels, and per-cell spirit names.

Because it is re-picked, it is also a *tool*: when one string is a byte or two
over its hole, spending shorthand codes on that string is the fix, not
rewriting the Thai. The spirit-cell work is the worked example — four names
needed a seventh byte and got six codes instead of six shorter names.

Priority matters. Pool overflow stops the build with a message; a spirit name
that overflows its cell says nothing and tears the screen at runtime. The
silent failure gets the codes first.

## 3. A runtime sub-pixel renderer

`tools/thai_renderer.py` assembles context-isolated rasterizers at `$FF:6000`
and `$FF:6A00`. Each keeps its own persistent pen/cell state, so a glyph can
start partway through a cell without the ordinary and battle engines resetting
one another. The 65816 has no variable shift, so both directions come out of
tables.

Most of its code is about staying out of the engine's way — see
`docs/rendering.md`. The important architectural point is that it holds state
between glyphs, which is what makes run boundaries and cursor arithmetic the
recurring source of bugs.

## 4. Source-address routing

The ordinary font classifiers decide, per byte, whether to draw from the Thai
page or the stock font, and they decide **by where the text came from**. Battle
dialogue has a separate call-site dispatcher because it has a different cursor
and compositor contract. Two source-routing shapes:

| shape | when | cost |
|---|---|---|
| range compare | the whole span is translated text | a few bytes of code |
| per-byte route table | literals and runtime values are interleaved | one byte of table per script byte |

The pilot-status, unit-status, weapon-menu and map-spirit spans need tables
because stock labels, Thai values, numbers, `+`, `/` and runtime controls are
interleaved. The repacked story banks need only a range compare — every byte of
them is translated.

Control operands are consumed by the parser rather than classified, so a range
may span a block containing `FD`s without harming their positioning.

**Ranges are quoted one past the text.** See `docs/pitfalls.md`.

## 5. Repointing indexed pools

Where the game reaches a string through a pointer table, a string that outgrows
its slot is moved to the bank tail and its pointer rewritten — the unit
commands, the `$D2` type values and series names, and the spirit names that did
not fit their own block all work this way. The new location needs its own entry
in the routing chain.

## 6. In-place fixed-span replacement

Where a string is *not* pointed at — inline script labels, the spirit
descriptions — it has to be overwritten where it lies, in exactly the bytes the
Japanese occupied. Short translations are padded with the zero-width status
pad, which fills the span without drawing anything.

This is why some labels look arbitrarily constrained: `レベル`/`気力` share an
eight-byte span with a line break between them, and every neighbouring label in
the same message is already filled to the byte. The unit-status build uses the
compact stock labels `LV` and `WILL`, so the payload fits without moving the
following dynamic controls.

## 7. Byte padding to a fixed source-record count

Where a grid or inline script traverses fixed source spans, every entry must
occupy the same number of source bytes even though the VWF advances by pixels.
`SPIRIT_ENTRY_BYTES = 6` is the shipped example.

Fill the unused bytes with `<Pad>`. The parser consumes it before the renderer,
so it has zero width and zero tile cost. Never shorten the translation merely
to remove padding.

## 8. Script repack into expanded banks

The 47 story blocks are rebuilt from `$F0:0000` and the 52-entry master table
is repointed. Inside a block the pointer table and command-record area keep
their original layout, so only messages move, and every reference — pointer
table, command records, and the eight-way `FC 08` branch stored inside message
bodies — is remapped.

## 9. Hooks and trampolines in expanded space

The classifier and width hooks live in the `$3F0000` PC region, one block per
call site. Branch reach is the binding constraint as chains grow, which is why
`source_route_trampolines` is emitted *between* the two range lists rather than
after both. The assembler raises rather than emitting an out-of-range branch.

Blocks are laid out on fixed strides; the tightest currently uses 422 bytes of
512. Adding routing arms is not free.

## 10. Verification

Four independent checks, described in `docs/pitfalls.md`. The two that catch
the most are the byte diff against the previous build — which shows anything
you touched by accident — and the deterministic rebuild, which proves the
pipeline has no hidden state.

The Python reference renderer (`tools/thai_render.py`) is the specification for
glyph placement, and `tools/check_combining.py` runs the ROM routine against it
row for row.
