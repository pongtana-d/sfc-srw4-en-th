# Traps

Every entry here cost real debugging time at least once. Most of them share a
shape: something that looks like a rendering fault is arithmetic, and something
that looks like proof is a stale picture.

## Measurement traps

### A save state shows you the screen it was saved on

Loading a state and screenshotting it tells you nothing. The state carries a
composed screen, and unless the game redraws, you photograph whatever build
made the state.

The tell is brutal and worth remembering: **load the state on the clean
Japanese ROM and you will get the same Thai screen back, byte-identical PNG.**
If that happens, nothing you are looking at came from your build.

A single button press is usually not enough. Leave the screen and come back:

```bash
python3 tools/run_mesen.py build/SRW4-FULL.sfc --state saves/SRW4-FULL_2.mss \
    --frames 300 --press 30:34:b --press 60:64:a --watch 0xFF6000
```

`--watch 0xFF6000` is the receipt for ordinary screens; use `$FF:6A00` for
battle dialogue. A non-zero hit count means the renderer actually ran. Zero
hits means the screenshot is a fossil. Button names are lowercase, and the
flag is `FIRST:LAST:BUTTON`, not a bare button name.

### `--watch` names the wrong caller

The exec watch reads the return address off the stack. Handlers reached by
`JMP` through a dispatch table never pushed one, so the "caller" it prints is
whatever stale frame was underneath. Chasing those addresses is how the `F6`
line-break theory survived as long as it did.

Use `--watch-write LO[:HI]` when you want to know who moved a value. There the
PC *is* the writer, and it is not a guess. `--watch-write 0x18:0x19` over the
spirit grid answered in one run what disassembly had got wrong twice.

### `check_combining --sheet` renders from boot when its state is missing

It needs `build/SRW4-TH_1-fixed.mss`, which is not in the repo. Without it, it
does not fail — it renders from boot and reports every row as differing,
usually all shifted 8px. A total failure means a missing state far more often
than a broken renderer.

## Arithmetic traps

### Routed ranges are quoted one past the text

The font classifier is handed a source pointer the parser has **already
advanced** past the byte it is asking about. Routing the literal at address `A`
needs the range to contain `A + 1`, so a block is `[start + 1, end + 1)`.

Getting this wrong is silent — the affected bytes simply draw from the stock
font. `UNIT_SHIELD_TARGET_RANGES` was written at the two string starts and lost
a byte at each end of the arithmetic: the tone mark of `ไม่มีโล่` came out as a
stray glyph one space to the right, and `มีโล่` would have been garbage end to
end. It reads exactly like a mark-placement bug, and it is not.

Derive ranges from the block constants with `+ 1` rather than typing bounds.

### A fixed source record is a number of bytes, not a pixel width

This is the single most expensive misconception in the project. The grid's
source traversal and the VWF's pixel pen are separate contracts. A source byte
can expand into several Thai pieces, while `<Pad>` is swallowed before drawing
and exists only to keep a fixed record full.

- The spirit-search grid positions each cell with `FD`, columns `$0C` apart,
  and a cell is **six bytes**. A longer name bleeds into the next cell, which
  the next `FD` recovers — except on a row's last cell, where the text runs off
  the row, wraps, and names stale tiles. That was the garbage band.
- The unit command menu drifts for the same reason, which is why it is still
  spelled in the stock font.

The fix is never to shorten the translation blindly. Fill a verified fixed
record with `<Pad>`; it allocates no tile and advances no VWF pen. If encoded
text will not fit, point the cluster shorthand at it.

### The name-bank chain is a ladder, not a set of tests

In `source_range_checks`, the bank `$D2` chain leaves for the original path the
moment the pointer is below a range start. Every range must therefore appear in
**ascending order**. A range appended at the end is dead code — it will never
run, and nothing will tell you.

The bank `$CC` chain is different: its early entries are true two-sided tests
and their order does not matter. Do not generalise from one to the other.

### `$D2` pointer tables start on odd addresses

The label pool's first pointer is one byte before where you would guess. Assert
the index you resolve rather than trusting the base.

## State traps

### The dialogue compositor already places its tilemap

The second text engine is not just the first engine with a different width
counter. It composes both speaker windows itself. Letting the VWF also write
columns through the ordinary `$18`/`DP_COL` path produces a ghost copy over the
map; reused dynamic tiles then make it look like random tile corruption.

Keep the proportional pen and Thai rasterization, but use the tile pair and
tilemap placement supplied by the dialogue compositor. Restoring `「」` does not
help: those bytes are ordinary glyphs, and a raw-byte emulator test left the
fault unchanged.

### A source-byte boundary can overwrite the previous Thai spill

The ordinary menu/status engine prepares its next tilemap word between source
bytes. If the previous Thai glyph spills into that next cell, the prepared word
can replace the spill even though the renderer drew every glyph correctly.
This made `ใช่` lose `ช่`, and made `เลเวลถัดไป` lose its final `ป` when the
stock level number followed it.

Use the narrow fix that matches the boundary:

- Keep a spilling base plus its mark in one renderer call with phrase or
  cluster shorthand. `ช่` is reserved for this reason.
- When a fixed Thai label is followed immediately by stock digits, add one real
  spacing glyph as a guard. `<Pad>` cannot guard pixels because the parser
  consumes it before the renderer. Levelled pilot skill `โล่1` is another
  measured case: the stock `1` erased the spilled tail of `ล`.
- Apply the same guard when a weapon name ends in a real spill immediately
  before a stock MAP/B/P attribute. Without it, the attribute's prepared write
  can overwrite the final base; `บีมไรเฟิล<B>` was the measured case.
- Do not remove the renderer's pending-write redirection globally. Dead guard
  columns are reused by other menus and will turn into gaps or stray glyphs.

Verify these cases from the real save state and compare the rendered pixels,
not just the encoded bytes: the encoder can be correct while the following
engine write still destroys the tail.

### Map spirit help does not wrap itself

The help box used by the map spirit selector is 240px wide and two lines high.
Its Japanese records contain explicit `$F6` line breaks; replacing the whole
record with a continuous Thai string removes those controls, so a long line
crosses the right frame and wraps into the frame's left edge. The build now
requires every translated line to measure at most 240px, allows no more than
two lines, writes `$F6` explicitly, and keeps that control on the stock parser
route. `พลีชีพ` and `ตรึง` are the two descriptions that require two lines.

### The direct page is not scratch

Three separate bytes have bitten this project, and `tools/dp_census.py` missed
all three because it was only ever walked over `$C1:8300`-`$C1:9400` — the text
engine's own range.

- `$F0`-`$FB` holds four 24-bit map-renderer source pointers that must survive a
  menu transition. Parking renderer state there filled the map with menu tiles.
- `$D6` is the **event script** engine's condition register (`$83:B035`,
  `$83:B10D`, `$83:B3F8` write it; `$83:9388` reads `$D6 & 7`). Borrowing it
  made one line of dialogue index past a jump table and run into the `STP` at
  `$80:EFF6` — the machine stops with the picture still up. That was the
  "press A and it hangs" freeze.
- `$EE` is written by something outside the text engine, and a stale value
  restarted a glyph run mid-word.

`$7E:F000-$F3FF` is not a solution either: battle uses it for line and geometry
tables, which become active during the attack-hit transition. Renderer state
there causes dialogue, tiles and the battle layout to fail together.

Renderer-owned state now lives only in the reserved `$7E:FFA0-$FFFF` block and
is always reached with 24-bit operands. Ordinary and battle keep separate
persistent halves; only temporary per-call work is shared. The generator rejects
non-interface direct-page accesses and overlap with known stock WRAM. Do not
move the block based on zero-filled snapshots alone: prove ownership with cold
boot and scenario write watches first.

A freeze captured while an old build had the map pointers clobbered **cannot be
migrated**. Writing the constants back at load time still leaves the buffers
behind them destroyed. Replace the state.

## Build traps

### Battle records are bytecode, not overlapping 16-bit words

Blocks 20-26 store battle-quote selectors as a command stream. `FA nn` and
`FC 07` carry message pointers; `FC 08` carries eight record-local branch
targets. Never scan the area one byte at a time looking for values that happen
to equal a message offset. A window such as `07 56` can coincidentally form
`$5607`; rewriting it changes command 07, sends the interpreter outside its
jump table, and ends at the `$80:EFF6` stop trap after confirming an attack.

`jp_script.record_references()` is the single structural parser used by the
extractor, repacker, validator, and targeted repair mode.

### Battle dialogue has its own `FB` interpreter

The private `FB $FExx` operands used to insert stock-font Latin runs are not
automatically shared by the two text engines. The ordinary hook at `$C1:8DF3`
does not run for battle dialogue; that engine handles `FB` at `$C1:9381`.
Sending a battle short name such as `AI` through the ordinary-only scheme makes
the battle handler treat `$FE1C` as a runtime name. It then reads three bytes
past the shared queue, and the next reward window runs away while expanding its
dynamic numbers. Keep the paired battle hook in `tools/stock_text.py`, and
always replay through the reward window when changing battle-name encoding.

The first Thai glyph can also begin after a stock-font battle name.  On that
transition `$D0` is ahead of `$D2` because the Latin tiles are waiting for DMA.
Do not treat every backwards reset relative to the previous Thai run as an
empty queue: rebase `$D2` only when it is numerically ahead of the new `$D0`.
Rebasing it for `AIกรรรรรร!!` advances the text correctly but drops the `AI`
tiles, leaving two convincing blank cells before the Thai quote.

### Byte counts are not constants

`tools/build_shorthand.py` re-picks the cluster shorthand from the translations
on **every** rebuild. Adding a glyph, or changing one string, changes how every
other string encodes. Never hard-code a byte length you measured once.

This cuts both ways, and the good direction is useful: a string that is one
byte over can often be rescued by making the shorthand spend a code on it,
rather than by rewriting the Thai.

### Regenerate `encoding.json` after re-picking

`tools/build_shorthand.py` writes `font/shorthand.json`, but the builders read
`font/encoding.json`. Run `tools/thai_encoding.py` in between or you will build
against a stale page and spend an hour explaining impossible output.

### Do not `git checkout` a tool file to "reset" it

Uncommitted renderer work was destroyed exactly once this way and had to be
reconstructed and then byte-compared against a baseline ROM to prove it was
back. Check `git status` and `git diff` first; commit or stash before
discarding.

### Full ROMs are build artifacts

They must not be distributed. Release patches are BPS/IPS against the clean
SHA-256 in the README.

## Verification that actually holds

A change is verified when all of these agree, not when one of them does:

1. `tools/validate_thai_build.py` and `tools/validate_script_build.py` pass.
2. A rebuild from scratch reproduces the ROM byte for byte.
3. A byte diff against the previous build shows **only** the spans you meant to
   touch, plus the checksum and any hook block that legitimately grew.
4. A Mesen screenshot taken after a confirmed redraw — non-zero `--watch` count
   — matches the Japanese layout where it should.
