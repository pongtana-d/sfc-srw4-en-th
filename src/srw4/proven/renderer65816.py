#!/usr/bin/env python3
"""The 65816 rasterizer for the combining Thai page, assembled from Python.

One routine draws every piece of Thai text in the game.  It is a sub-pixel
renderer: it keeps its own pen, its own cell and its own tilemap column, so a
glyph can start partway through a cell and the next one can carry on where it
left off.  `srw4th.text.renderer` is the specification it is checked against,
and the isolated renderer fixture runs that check inside the emulator.

Three shapes go through it:

    a base       advances the pen, opens or fills a cell, and leaves an anchor
    a mark       advances nothing; placed against the anchor the base left
    a shorthand  one byte the prologue expands into the two or three codes it
                 stands for, each drawn as if it had been written out
    an upper stack keeps normal vowel+tone bytes but places the tone from one
                 of 30 precomputed pair records anchored to the lifted vowel

There is no full-cluster page to choose.  The small upper-stack table avoids the
combinatorial glyph pages this replaced while making the fragile second layer
deterministic.  What the renderer does have to
live with is the engine, which hands out tiles through a single counter and
writes its own tilemap column before every glyph — most of the bookkeeping
below is about staying out of the way of that.

The deterministic Core builder calls `build_renderer()` and places the result
inside the declared `$FF` Core region before any hook is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .assembler import Asm, pc_to_cpu

ROOT = Path(__file__).resolve().parents[3]

# Fixed table slots inside the new `$FF` Core region.  The allocator
# reserves these addresses and tests fail if preceding artifacts grow into them.
SHR_TABLE = 0x3F2000  # CPU $FF:2000 — byte >> pen, indexed pen*256 + byte
SHL_TABLE = 0x3F2800  # CPU $FF:2800 — byte << (8-pen)
BATTLE_BG_GUARD = 0x3D0000  # CPU $FD:0000, reserved for the battle adapter
BATTLE_BG_ENTRY = 0x01E5D8  # CPU $C1:E5D8 / $81:E5D8 mirror

# Renderer-owned memory is deliberately outside the direct page.  Earlier
# versions moved state from one apparently-unused DP range to another and each
# move collided with a different subsystem: event bytecode, map pointers, then
# battle geometry.  The last 96 bytes of bank $7E are cleared by the stock boot
# loop at $80:EFCB and had no post-boot writer in cold-boot plus save-state
# write-watch runs.  Two independent persistent blocks prevent the synchronous
# menu engine and the per-frame dialogue engine from resetting one another;
# the scratch block is live only while a renderer call is on the CPU.
PRIVATE_WRAM_START = 0x7EFFA0
PRIVATE_WRAM_END = 0x7F0000
STATE_BLOCK_SIZE = 0x20
SCRATCH_BLOCK_SIZE = 0x20
ORDINARY_STATE_BASE = 0x7EFFA0
BATTLE_STATE_BASE = 0x7EFFC0
RENDERER_SCRATCH_BASE = 0x7EFFE0
STATE_SIGNATURE = 0xA55A


@dataclass(frozen=True)
class RendererMemory:
    """Absolute-long addresses owned by one context-isolated renderer."""

    initialized: int
    pen: int
    expect: int
    cleared: int
    cell: int
    col: int
    expect_col: int
    run_cell: int
    base_left: int
    base_ink: int
    base_cell: int
    has_vowel: int
    upper_x: int
    upper_top: int
    rows: int
    tile: int
    glyph: int
    index: int
    temp: int
    glyph_id: int
    tilebase: int
    lift_q: int
    lift_a: int
    lift_b: int
    internal_base: int
    mark_top: int
    mark_x: int
    tail_ink: int
    stack_index: int


def renderer_memory(state_base: int) -> RendererMemory:
    """Return one persistent state block plus the shared private scratch block."""
    persistent = {
        "initialized": 0x00, "pen": 0x02, "expect": 0x04,
        "cleared": 0x06, "cell": 0x08, "col": 0x0A,
        "expect_col": 0x0C, "run_cell": 0x0E, "base_left": 0x10,
        "base_ink": 0x12, "base_cell": 0x14, "has_vowel": 0x16,
        "upper_x": 0x18, "upper_top": 0x1A,
    }
    scratch = {
        "rows": 0x00, "tile": 0x02, "glyph": 0x04, "index": 0x06,
        "temp": 0x08, "glyph_id": 0x0A, "tilebase": 0x0C,
        "lift_q": 0x0E, "lift_a": 0x10, "lift_b": 0x12,
        "internal_base": 0x14, "mark_top": 0x16, "mark_x": 0x18,
        "tail_ink": 0x1A,
        "stack_index": 0x1C,
    }
    return RendererMemory(
        **{name: state_base + offset for name, offset in persistent.items()},
        **{name: RENDERER_SCRATCH_BASE + offset for name, offset in scratch.items()},
    )


def emit_redirect_stock_tilemap_write(
    asm: "Asm", memory: RendererMemory, done: str, external_tilemap: bool
) -> None:
    """Make the engine's next placement repeat our current cell, not a guard.

    Ordinary text placement is prepared outside the renderer.  Keeping the
    cursor on the current cell prevents a parked dynamic tile from remaining
    in an otherwise unused column and later reappearing as stray text.  Fields
    that end in a spill before stock text use an explicit spacing guard, while
    a base plus combining mark that crosses a cell is kept inside one renderer
    call by shorthand.
    """
    asm.emit(0xC2, 0x30)                       # 16-bit A and X
    if external_tilemap:
        # This surface's stock compositor owns the visible destination.  Give
        # it the renderer's tile word directly without writing a ghost column
        # through the ordinary engine's unrelated $18 cursor.
        asm.var(0xA5, memory.cell)
        asm.emit(0x18)
        asm.var(0x65, memory.tilebase)
        asm.emit(0x29, 0xFF, 0x03)
        asm.emit(0x18, 0x65, 0x2E)
    else:
        asm.var_to_x(memory.col)
        asm.long_index(0xBF, 0x7E8000)         # word carry_on installed
    asm.emit(0x85, 0x00)                       # stock writer repeats that word
    asm.emit(0x8A)                             # TXA: current tilemap column
    asm.emit(0x85, 0x18)
    asm.emit(0x1A, 0x1A)                       # cursor after the stock write
    asm.var(0x85, memory.expect_col)
    asm.label(done)


def emit_renderer_return(asm: "Asm", exit_op: int) -> None:
    """Reproduce the stock rasterizer's observable return state.

    The stock path leaves M/X at 16 bit, A equal to the parked tile counter and
    PLB as its final flag-affecting instruction.  Keeping PLB immediately before
    RTS/RTL avoids leaking flags from private-state cleanup into either caller.
    """
    asm.emit(0xC2, 0x30)
    asm.emit(0xA5, 0xD0)
    asm.emit(0xAB)                             # PLB — last flag-changing opcode
    asm.emit(exit_op)


def emit_tilemap_preserve(
    asm: "Asm", spec: dict[str, int], *, restore: bool
) -> None:
    """Snapshot or restore a persistent tilemap rectangle around a popup draw."""
    pointer = spec["last_pointer"] if restore else spec["first_pointer"]
    done = "preserve_restore_done" if restore else "preserve_snapshot_done"
    asm.emit(0xA5, spec["pointer_dp"])
    asm.emit(0xC9, pointer & 0xFF, (pointer >> 8) & 0xFF)
    asm.branch(0xD0, done)
    for row in range(spec["rows"]):
        loop = f"{'restore' if restore else 'snapshot'}_row_{row}"
        source = spec["backup"] + row * spec["row_bytes"] if restore else (
            spec["source"] + row * spec["stride"]
        )
        target = spec["source"] + row * spec["stride"] if restore else (
            spec["backup"] + row * spec["row_bytes"]
        )
        asm.emit(0xA2, 0x00, 0x00)             # LDX #$0000
        asm.label(loop)
        asm.long_index(0xBF, source)
        asm.long_index(0x9F, target)
        asm.emit(0xE8, 0xE8)                   # INX / INX
        asm.emit(0xE0, spec["row_bytes"] & 0xFF, spec["row_bytes"] >> 8)
        asm.branch(0xD0, loop)
    asm.label(done)


def validate_renderer_scratch() -> None:
    """Check the three private blocks and known stock WRAM ownership ranges."""
    blocks = (
        (ORDINARY_STATE_BASE, ORDINARY_STATE_BASE + STATE_BLOCK_SIZE, "ordinary"),
        (BATTLE_STATE_BASE, BATTLE_STATE_BASE + STATE_BLOCK_SIZE, "battle"),
        (RENDERER_SCRATCH_BASE, RENDERER_SCRATCH_BASE + SCRATCH_BLOCK_SIZE, "scratch"),
    )
    if blocks[0][0] != PRIVATE_WRAM_START or blocks[-1][1] != PRIVATE_WRAM_END:
        raise ValueError("renderer private WRAM does not fill its declared reservation")
    for index, (start, end, name) in enumerate(blocks):
        if not (0x7E0000 <= start < end <= 0x7F0000):
            raise ValueError(f"{name} renderer state is outside bank $7E")
        for other_start, other_end, other_name in blocks[index + 1:]:
            if start < other_end and other_start < end:
                raise ValueError(f"{name} renderer state overlaps {other_name}")

    # These are the stock ranges that exposed earlier false "free WRAM" claims.
    # Keep them explicit so moving the reservation back into one fails at build.
    stock_owned = (
        (0x7E8000, 0x7EC000, "tilemap buffers"),
        (0x7ED400, 0x7EDA03, "map source pointers"),
        (0x7EF000, 0x7EF400, "battle line tables"),
        (0x7F8000, 0x800000, "dynamic tile shadow"),
    )
    for start, end, name in blocks:
        for stock_start, stock_end, stock_name in stock_owned:
            if start < stock_end and stock_start < end:
                raise ValueError(f"{name} renderer state overlaps {stock_name}")

    for state_base in (ORDINARY_STATE_BASE, BATTLE_STATE_BASE):
        memory = renderer_memory(state_base)
        persistent = (
            memory.initialized, memory.pen, memory.expect, memory.cleared,
            memory.cell, memory.col, memory.expect_col, memory.run_cell,
            memory.base_left, memory.base_ink, memory.base_cell, memory.has_vowel,
            memory.upper_x, memory.upper_top,
        )
        if any(not state_base <= address < state_base + STATE_BLOCK_SIZE
               for address in persistent):
            raise ValueError("persistent renderer variable escaped its state block")
        scratch = (
            memory.rows, memory.tile, memory.glyph, memory.index, memory.temp,
            memory.glyph_id, memory.tilebase, memory.lift_q, memory.lift_a,
            memory.lift_b, memory.internal_base, memory.mark_top, memory.mark_x,
            memory.tail_ink,
            memory.stack_index,
        )
        if any(not RENDERER_SCRATCH_BASE <= address < PRIVATE_WRAM_END
               for address in scratch):
            raise ValueError("renderer scratch variable escaped its private block")


def validate_renderer_code(
    code: bytes, extra_direct_page: frozenset[int] = frozenset()
) -> None:
    """Reject generated code that uses DP outside the caller-owned contract.

    This is a small 65816 walk using the project's disassembler table. It
    tracks M/X width because a 16-bit access touches two bytes.  The renderer
    may touch only the text engine's documented interface: tilemap word/cursor,
    tile counters, and colour planes.  Every renderer-owned value must use the
    private absolute-long blocks above.
    """
    validate_renderer_scratch()
    try:
        from . import disasm65816 as dis
    except ImportError:
        import disasm65816 as dis

    direct_page_modes = {
        dis.DP, dis.DPX, dis.DPY, dis.IDP, dis.IDPX, dis.IDPY,
        dis.IDPL, dis.IDPLY,
    }
    m_width_ops = {
        "LDA", "STA", "ADC", "SBC", "AND", "ORA", "EOR", "CMP",
        "BIT", "ASL", "LSR", "ROL", "ROR", "INC", "DEC", "STZ",
        "TSB", "TRB",
    }
    x_width_ops = {"LDX", "LDY", "STX", "STY", "CPX", "CPY"}
    pointer_ops = {"PEI"}
    allowed = {
        0x00, 0x01,             # stock tilemap word
        0x18, 0x19,             # ordinary text cursor
        0x2E, 0x2F,             # tilemap attribute
        0xD0, 0xD1, 0xD2, 0xD3, # engine tile/DMA counters
        0xFD, 0xFE, 0xFF,       # colour planes
    } | set(extra_direct_page)

    m16 = True
    x16 = True
    pc = 0
    while pc < len(code):
        opcode = code[pc]
        entry = dis.OPS.get(opcode)
        if entry is None:
            raise ValueError(f"unknown opcode ${opcode:02X} in renderer at +{pc:#x}")
        name, mode = entry
        if mode == dis.IMM_M:
            operand_size = 2 if m16 else 1
        elif mode == dis.IMM_X:
            operand_size = 2 if x16 else 1
        else:
            operand_size = dis.MODE_LEN[mode]
        end = pc + 1 + operand_size
        if end > len(code):
            raise ValueError(f"truncated opcode ${opcode:02X} in renderer at +{pc:#x}")

        if mode in direct_page_modes:
            operand = code[pc + 1]
            span = 1
            if mode in (dis.IDP, dis.IDPX, dis.IDPY):
                span = 2
            elif mode in (dis.IDPL, dis.IDPLY):
                span = 3
            elif name in pointer_ops:
                span = 2
            elif name in m_width_ops and m16:
                span = 2
            elif name in x_width_ops and x16:
                span = 2
            touched = {(operand + offset) & 0xFF for offset in range(span)}
            outside = sorted(touched - allowed)
            if outside:
                values = ", ".join(f"${value:02X}" for value in outside)
                raise ValueError(
                    f"renderer accesses non-contract direct-page {values} at +{pc:#x}"
                )

        if opcode == 0xC2:  # REP
            if code[pc + 1] & 0x20:
                m16 = True
            if code[pc + 1] & 0x10:
                x16 = True
        elif opcode == 0xE2:  # SEP
            if code[pc + 1] & 0x20:
                m16 = False
            if code[pc + 1] & 0x10:
                x16 = False
        pc = end


def shift_tables() -> tuple[bytes, bytes]:
    shr = bytearray(8 * 256)
    shl = bytearray(8 * 256)
    for pen in range(8):
        for byte in range(256):
            shr[pen * 256 + byte] = (byte >> pen) & 0xFF
            shl[pen * 256 + byte] = (byte << (8 - pen)) & 0xFF if pen else 0
    return bytes(shr), bytes(shl)


def battle_bg_guard() -> bytes:
    """Recreate the battle line-table bound before its per-frame update.

    The engine initializes $E3 to $0200 for the two half-size buffers and to
    $0400 for the two full-size buffers. Text rasterizers reuse $E3/$E4, so a
    line ending in stock punctuation can leave a glyph offset there. $80 bit 1
    is already the selector used by the displaced entry code and identifies
    which buffer layout is active without reserving another byte of WRAM.
    """
    return bytes((
        0xA5, 0x80,             # LDA $80
        0x89, 0x02, 0x00,       # BIT #$0002
        0xF0, 0x05,             # BEQ half_size
        0xA9, 0x00, 0x04,       # LDA #$0400
        0x80, 0x03,             # BRA store
        0xA9, 0x00, 0x02,       # half_size: LDA #$0200
        0x85, 0xE3,             # store: STA $E3
        0xA5, 0x80,             # reproduce displaced LDA/BIT for caller's BEQ
        0x89, 0x02, 0x00,
        0x6B,                   # RTL
    ))


def emit_shorthand_prologue(
    asm: "Asm", tables: dict[str, int], memory: RendererMemory
) -> None:
    """Turn one shorthand byte into the two or three draws it stands for.

    The combining page spends a byte per character, which is what killed the
    merged-word glyphs — but it also made every name longer, and the banks the
    game reads names out of are 16-bit addressed and full.  The spacing block
    had a hundred codes spare, so the commonest clusters each took one.

    Nothing below this point knows.  A shorthand expands into exactly the codes
    a translator would have written by hand, goes down the same base and mark
    paths, and leaves the same pen and cell state behind.  Which is why the
    expansion lives here and not in the parser: the run bookkeeping is per
    glyph, and splitting a byte into three of them has to happen inside one
    call or the engine's cursor gets in between.

    Component one doubles as the test — it is zero for every code that is not a
    shorthand.  That costs a table but no range compare, and nothing has to be
    kept in step when a newly drawn consonant pushes the block along.
    """
    asm.emit(0xAA)                             # TAX — the code indexes all three
    asm.emit(0xE2, 0x20)                       # SEP #$20
    asm.long_index(0xBF, pc_to_cpu(tables["first"]))
    asm.emit(0xC2, 0x20)                       # REP #$20
    asm.emit(0x29, 0xFF, 0x00)                 # AND #$00FF — drop the stale high byte
    asm.branch(0xD0, "expand")
    asm.emit(0xA9, 0x00, 0x00)                 # stale save-state WRAM is unsafe
    asm.var(0x85, memory.internal_base)
    asm.emit(0x8A)                             # TXA — an ordinary code, drawn as is
    asm.emit(0x20, 0x00, 0x00)
    asm.fixups_abs.append((len(asm.code) - 2, "draw"))
    asm.emit(0x6B)                             # RTL

    asm.label("expand")
    asm.emit(0x48)                             # preserve component one
    asm.emit(0xA9, 0x00, 0x00)
    asm.var(0x85, memory.internal_base)
    asm.emit(0x68)
    for slot, last in (("second", False), ("third", True)):
        asm.emit(0xDA)                         # PHX — draw clobbers X
        asm.emit(0x20, 0x00, 0x00)
        asm.fixups_abs.append((len(asm.code) - 2, "draw"))
        asm.emit(0xFA)                         # PLX
        asm.emit(0xE2, 0x20)                   # SEP #$20
        asm.long_index(0xBF, pc_to_cpu(tables[slot]))
        asm.emit(0xC2, 0x20)                   # REP #$20
        asm.emit(0x29, 0xFF, 0x00)
        if last:
            # Two-character clusters store zero here and stop; three-character
            # ones fall through to one more draw.
            asm.branch(0xF0, "expand_done")
        # The next component is drawn inside this same renderer call, so a base
        # must not go through the outer engine's run guard: the engine has not
        # performed its normal post-call cursor step yet.  Mark components
        # already bypass that guard and must retain the base anchor unchanged.
        asm.emit(0xC9, 0xD0, 0x00)             # CMP #MARK_ABOVE_BASE
        asm.branch(0xB0, f"expand_no_sync_{slot}")
        asm.emit(0x48)                          # preserve the next component
        asm.emit(0xA9, 0x01, 0x00)
        asm.var(0x85, memory.internal_base)
        asm.emit(0x68)
        asm.label(f"expand_no_sync_{slot}")
    asm.emit(0x20, 0x00, 0x00)
    asm.fixups_abs.append((len(asm.code) - 2, "draw"))
    asm.label("expand_done")
    asm.emit(0x6B)                             # RTL

    asm.label("draw")


def build_renderer(origin: int, source_base: int, advance: int,
                   lock: int,
                   combining: dict[str, int] | None = None,
                   shorthand: dict[str, int] | None = None,
                   upper_stacks: dict[str, int] | None = None,
                   preview_ranges: tuple[tuple[int, int], ...] = (),
                   *, state_base: int = ORDINARY_STATE_BASE,
                   battle: bool = False,
                   external_tilemap: bool = False,
                   dialogue_tail_counter_step: bool = False,
                   tilemap_preserve: dict[str, int] | None = None,
                   source_page_state: int | None = None,
                   alternate_advance: tuple[int, int] | None = None,
                   caller_reuses_cell_cursor: bool = False,
                   entry_cursor_is_cell: bool = False,
                   compact_grid: bool = False,
                   shift_tables_base: tuple[int, int] = (SHR_TABLE, SHL_TABLE),
                   source_bank: int = 0xFF) -> bytes:
    """Context-isolated sub-pixel renderer.

    The engine hands out tiles through a single counter, `$D0`, and derives the
    tilemap's tile number from it *before* calling the renderer.  A cell held
    open across several glyphs therefore cannot leave `$D0` pointing at itself:
    the next Latin glyph or digit goes through the stock rasterizer, takes
    `$D0`, and overwrites the pair being filled.

    Persistent state lives in a private 32-byte WRAM block, never in direct
    page.  The ordinary variant writes the menu/status tilemap itself; the
    battle variant leaves placement to the dialogue compositor.

    `$D0` is parked past both the open cell and the pair its spill lands in, so
    whatever draws next always gets untouched tiles.

    Grid-locked codes — the paired terrain and ammo icons, and the dynamic digit
    slots the menu positions by column — take none of this.  They go down a
    verbatim copy of the stock rasterizer, leaving the engine's own tilemap
    write and cursor step alone, because the engine names their tiles itself
    (the `$84A2` wide path uses `$D0+2`/`$D0+3`) and compressing them would slide
    artwork off the grid it was drawn for.
    """
    if battle != (state_base == BATTLE_STATE_BASE):
        raise ValueError("renderer context and private state block disagree")
    if battle and external_tilemap:
        raise ValueError("battle already uses its compositor-owned tilemap path")
    if dialogue_tail_counter_step and not battle:
        raise ValueError("dialogue-tail counter compensation requires battle mode")
    if not 0 <= source_bank <= 0xFF:
        raise ValueError("renderer source bank must fit one byte")
    if combining and source_bank != 0xFF:
        raise ValueError("non-$FF combining pages are not supported")
    if (source_page_state is None) != (alternate_advance is None):
        raise ValueError(
            "dynamic source page state and alternate advance must be supplied together"
        )
    if source_page_state is not None:
        alternate_page, _alternate_advance_pc = alternate_advance
        if source_base != 0:
            raise ValueError("dynamic source pages require a zero renderer source base")
        if alternate_page & 0x0FFF:
            raise ValueError("dynamic renderer source pages must be 4 KiB aligned")
    if caller_reuses_cell_cursor or entry_cursor_is_cell:
        if battle or external_tilemap:
            raise ValueError("cell-cursor contracts are ordinary internal-tilemap only")
    if compact_grid and (battle or external_tilemap or not entry_cursor_is_cell):
        raise ValueError("compact grid requires an ordinary cell-cursor renderer")
    if tilemap_preserve:
        row_bytes = tilemap_preserve["row_bytes"]
        rows = tilemap_preserve["rows"]
        stride = tilemap_preserve["stride"]
        source = tilemap_preserve["source"]
        backup = tilemap_preserve["backup"]
        if row_bytes <= 0 or row_bytes & 1 or rows <= 0 or stride < row_bytes:
            raise ValueError("invalid renderer tilemap-preserve geometry")
        source_end = source + (rows - 1) * stride + row_bytes
        backup_end = backup + rows * row_bytes
        if not (0x7E8000 <= source < source_end <= 0x7EC000):
            raise ValueError(
                "renderer tilemap-preserve source is outside the shadow tilemap"
            )
        if not (0x7F8000 <= backup < backup_end <= 0x800000):
            raise ValueError(
                "renderer tilemap-preserve backup is outside the shadow arena"
            )
    if (upper_stacks is None) != (combining is None):
        raise ValueError("combining-mark and upper-stack tables must be supplied together")
    memory = renderer_memory(state_base)
    shift_right, shift_left = shift_tables_base
    if shift_right & 0x7FF or shift_left & 0x7FF:
        raise ValueError("renderer shift tables must be 2 KiB aligned")
    if (shift_right & 0xFF0000) != (origin & 0xFF0000) or (
        shift_left & 0xFF0000
    ) != (origin & 0xFF0000):
        raise ValueError("renderer shift tables must share its ROM bank")
    asm = Asm(origin)
    asm.fixups_abs = []
    # With shorthand in play the body becomes a subroutine the prologue calls
    # once per component, so every exit returns to it rather than to the engine.
    exit_op = 0x60 if shorthand else 0x6B      # RTS / RTL
    if shorthand:
        emit_shorthand_prologue(asm, shorthand, memory)

    # --- entry: A = page-relative glyph index, M=16, X=16, DB = the engine's ---
    asm.var(0x85, memory.glyph_id)
    if tilemap_preserve:
        emit_tilemap_preserve(asm, tilemap_preserve, restore=False)
    asm.emit(0xAD, 0x18, 0x0E)                 # LDA $0E18 (engine's tile offset)
    asm.var(0x85, memory.tilebase)              # keep it before DB changes

    # Grid-locked?  The table lives in bank $FF and DB is still the engine's.
    asm.var_to_x(memory.glyph_id)               # LDX glyph index
    asm.emit(0xE2, 0x20)                       # SEP #$20
    asm.long_index(0xBF, pc_to_cpu(lock))      # LDA long,X
    asm.branch(0xF0, "unlocked")
    asm.brl("locked")
    asm.label("unlocked")
    if combining:
        # The fixed-width name picker owns a few otherwise-unused mark-block
        # codes containing dotted-circle previews.  In that renderer alone
        # they are ordinary spacing glyphs, not marks waiting for an anchor.
        for index, (first, limit) in enumerate(preview_ranges):
            miss = f"preview_miss_{index}"
            asm.var(0xA5, memory.glyph_id)
            asm.emit(0xC9, first)
            asm.branch(0x90, miss)
            asm.emit(0xC9, limit)
            asm.branch(0x90, "not_mark")
            asm.label(miss)
        # Marks are a contiguous block above every spacing code, so one compare
        # separates them.  They carry no advance and open no cell — they are
        # placed against the base already drawn — so they leave the run
        # bookkeeping below completely alone.
        asm.var(0xA5, memory.glyph_id)
        asm.emit(0xC9, 0xD0)
        asm.branch(0x90, "not_mark")
        asm.brl("mark")
        asm.label("not_mark")
    asm.emit(0xC2, 0x20)                       # REP #$20

    asm.var(0xA5, memory.glyph_id)
    asm.emit(0x0A, 0x0A, 0x0A, 0x0A)           # ASL x4
    if source_page_state is not None:
        asm.emit(0x18)                         # page base + glyph * 16
        asm.var(0x65, source_page_state)
    asm.emit(0xA8)                             # TAY
    asm.var(0x85, memory.glyph)

    if shorthand:
        # A second or third spacing component expanded from the same source
        # byte belongs to the run already in progress.  Testing the engine's
        # cursor here would always see the pre-return value and restart the run,
        # leaving only fragments of `เลเวล`, `กำลังใจ`, and `กำแพง` visible.
        # Consume the one-shot flag and continue with the existing pen/cell.
        asm.var(0xA5, memory.internal_base)
        asm.branch(0xF0, "outer_component")
        asm.emit(0xA9, 0x00, 0x00)
        asm.var(0x85, memory.internal_base)
        asm.brl("carry_on")
        asm.label("outer_component")

    # Did anything else move the tile counter or jump the cursor?
    #
    # There used to be a third test here, against a byte at $EE saying which
    # glyph page drew last — three pages needed telling apart.  There is one
    # page now, and $EE turned out not to be free: something outside the text
    # engine writes it, which restarted the run mid-word and left a cell's worth
    # of ink in a tile the tilemap no longer pointed at.  The counter and the cursor
    # are the real guards, and both have to match exactly.
    asm.var(0xA5, memory.initialized)
    asm.emit(0xC9, STATE_SIGNATURE & 0xFF, STATE_SIGNATURE >> 8)
    asm.branch(0xD0, "restart_uninitialized")
    asm.emit(0xA5, 0xD0)
    asm.var(0xC5, memory.expect)
    asm.branch(0xD0, "restart")
    # The cursor check is what keeps one field's open cell from following the
    # engine into the next one.  $18 is reset per field without $D0 necessarily
    # moving, and a stale $F2 would then drag that field's text back to the
    # previous field's column.
    if not battle and not external_tilemap:
        asm.emit(0xA5, 0x18)
        asm.var(0xC5, memory.expect_col)
        asm.branch(0xD0, "restart")
    asm.brl("carry_on")

    asm.label("restart_uninitialized")
    if battle:
        # Old save states contain no signature and can retain a stale DMA base.
        # Rebase only for that first isolated call; ordinary forward transitions
        # still let the stock engine upload any glyph it drew before Thai.
        asm.emit(0xA5, 0xD0)
        asm.emit(0x85, 0xD2)
    asm.brl("restart_initialize")

    asm.label("restart")
    # The dialogue engine resets $D0 at the start of a new message, but leaves
    # $D2 at the end of the previous dynamic-tile upload until after the first
    # glyph.  The VWF parks $D0 ahead while drawing that glyph, so the engine's
    # subsequent `D0 - D2` DMA calculation underflows and copies past the
    # $7F:8000 shadow tiles into the tilemap buffer.  That data lands in VRAM
    # as corrupt graphics.  Rebase the pending upload only on a backwards
    # dialogue reset with D2 still ahead of D0.  A stock-font prefix such as
    # the battle name `AI` advances D0 before the first Thai glyph while D2
    # remains behind it; preserving that forward range is what uploads the
    # Latin tiles instead of leaving two blank cells.
    if battle:
        asm.emit(0xA5, 0xD0)
        asm.var(0xC5, memory.expect)
        asm.branch(0xB0, "restart_dma_done")
        asm.emit(0xC5, 0xD2)                   # pending stock upload is forward
        asm.branch(0xB0, "restart_dma_done")
        asm.emit(0x85, 0xD2)
        asm.label("restart_dma_done")
    asm.label("restart_initialize")
    asm.emit(0xA9, STATE_SIGNATURE & 0xFF, STATE_SIGNATURE >> 8)
    asm.var(0x85, memory.initialized)
    # Start a fresh run one pair past where $D0 sits.  The run that
    # just ended left a dead tilemap column naming exactly the pair `park` left
    # $D0 on — the engine writes that column for a glyph that then turns out to
    # be somewhere else, and nothing ever rewrites it.  `park` blanks the pair so
    # the dead column shows nothing, which works right up until the next run
    # claims the same pair and draws into it: the ink then reappears in the old
    # string's trailing cell.  That is the stray glyph after `ฮึดสู้` on the
    # pilot-status screen.
    asm.emit(0xA5, 0xD0)
    if not battle and not external_tilemap and not compact_grid:
        asm.emit(0x1A, 0x1A)                   # ordinary guard pair
    asm.emit(0x29, 0xFF, 0x03)                 # AND #$03FF
    asm.var(0x85, memory.cell)
    asm.var(0x85, memory.run_cell)              # the run's left edge, for marks
    if not battle:
        asm.emit(0xA5, 0x18)
        if not entry_cursor_is_cell:
            asm.emit(0x3A, 0x3A)               # ordinary cursor follows the cell
        asm.var(0x85, memory.col)
    # `clear_pair` skips a pair it just cleared, which is what stops a spill from
    # being wiped.  At the start of a run that guard is holding a value from the
    # previous run (or from nothing at all), and if it happens to match the first
    # pair, that pair keeps whatever the last screen left in it.  Poisoning the
    # guard here costs two instructions and makes the first clear unconditional.
    asm.emit(0xA9, 0xFF, 0xFF)
    asm.var(0x85, memory.cleared)

    # A fresh run clears its own cell plus the two ahead of it; from then on
    # every glyph clears the pair $D0 is parked on, so each pair is cleared
    # exactly once, before either ink or a stray column can reach it.
    clear_offsets = (0x0000, 0x0002) if compact_grid else (0x0000, 0x0002, 0x0004)
    for offset in clear_offsets:
        asm.var(0xA5, memory.cell)
        if offset:
            asm.emit(0x18)
            asm.emit(0x69, offset, 0x00)
        asm.emit(0x0A, 0x0A, 0x0A, 0x0A, 0x0A)
        asm.var(0x85, memory.tile)
        asm.emit(0x20, 0x00, 0x00)
        asm.fixups_abs.append((len(asm.code) - 2, "clear_pair"))
    asm.clear_var(memory.pen)                   # pen restarts at 0

    asm.label("carry_on")
    # Dialogue has already placed the tilemap word through its own compositor.
    # Writing a second column through $18 creates a ghost copy on the scene.
    if not battle and not external_tilemap:
        # Write this cell's tilemap column ourselves, then put the cursor back so
        # the engine's own write for the next glyph lands where we expect.
        asm.var(0xA5, memory.cell)
        asm.emit(0x18)
        asm.var(0x65, memory.tilebase)
        asm.emit(0x29, 0xFF, 0x03)             # AND #$03FF
        asm.emit(0x18)
        asm.emit(0x65, 0x2E)                   # ADC $2E
        asm.var_to_x_preserving_a(memory.col)
        asm.long_index(0x9F, 0x7E8000)         # top row of the column
        asm.emit(0x1A)                         # INC
        asm.long_index(0x9F, 0x7E8040)         # bottom row
        asm.var(0xA5, memory.col)
        asm.emit(0x1A, 0x1A)                   # INC / INC
        asm.emit(0x85, 0x18)                   # cursor = column + 2
        asm.emit(0x1A, 0x1A)                   # the engine adds 2 more of its own
        asm.var(0x85, memory.expect_col)

    asm.var(0xA5, memory.cell)
    asm.emit(0x0A, 0x0A, 0x0A, 0x0A, 0x0A)
    asm.var(0x85, memory.tile)                  # draw into our own cell

    if combining:
        # Anchor for any marks that follow: where this base starts, how wide its
        # ink is, and which cell it went into.  Captured before the advance, so
        # a mark is placed against the base rather than against the next glyph.
        asm.var(0xA5, memory.cell)
        asm.var(0x85, memory.base_cell)
        asm.emit(0xE2, 0x20)                   # SEP #$20
        asm.var(0xA5, memory.pen)
        asm.var(0x85, memory.base_left)
        asm.var_to_x_from_m8(memory.glyph_id)
        asm.long_index(0xBF, pc_to_cpu(combining["base_ink"]))
        asm.var(0x85, memory.base_ink)
        asm.emit(0xA9, 0x00)                   # no STZ long; A is dead here
        asm.var(0x85, memory.has_vowel)
        asm.emit(0xC2, 0x20)                   # REP #$20

    asm.emit(0xE2, 0x20)
    asm.var(0xA5, memory.pen)
    asm.emit(0xEB)                             # XBA
    asm.emit(0xA9, 0x00)
    asm.emit(0xC2, 0x20)
    asm.var(0x85, memory.index)                 # pen * 256

    asm.emit(0xE2, 0x20)
    asm.emit(0x8B)                             # PHB
    asm.emit(0xA9, source_bank)
    asm.emit(0x48, 0xAB)
    asm.emit(0xA9, 0x08)
    asm.var(0x85, memory.rows)
    asm.emit(0xA9, 0x00)
    asm.var(0x85, memory.tail_ink)

    asm.label("row")
    emit_row(asm, memory, source_base, 0x0000, 0x0040,
             shift_right, shift_left)
    emit_row(asm, memory, source_base + 8, 0x0020, 0x0060,
             shift_right, shift_left)

    asm.emit(0xA5, 0xFD)
    asm.var_to_x_from_m8(memory.tile)
    asm.long_index(0x9F, 0x7F8001)
    asm.long_index(0x9F, 0x7F8021)
    asm.long_index(0x9F, 0x7F8041)
    asm.long_index(0x9F, 0x7F8061)
    asm.emit(0xC2, 0x20)
    asm.emit(0xA5, 0xFE)
    asm.long_index(0x9F, 0x7F8010)
    asm.long_index(0x9F, 0x7F8030)
    asm.long_index(0x9F, 0x7F8050)
    asm.long_index(0x9F, 0x7F8070)
    asm.emit(0xE2, 0x20)

    asm.emit(0xC8)                             # INY
    asm.emit(0xC2, 0x20)                       # tile offset is 16-bit
    asm.var(0xA5, memory.tile)
    asm.emit(0x1A, 0x1A)
    asm.var(0x85, memory.tile)
    asm.emit(0xE2, 0x20)
    asm.var(0xA5, memory.rows)
    asm.emit(0x3A)
    asm.var(0x85, memory.rows)
    asm.branch(0xF0, "rows_done")
    asm.brl("row")
    asm.label("rows_done")

    # --- advance the pen, and move our cell on when it wraps ---
    asm.emit(0xC2, 0x10)                       # REP #$10
    asm.var_to_x_from_m8(memory.glyph_id)
    if source_page_state is None:
        asm.emit(0xBD, advance & 0xFF, (advance >> 8) & 0xFF)
    else:
        alternate_page, alternate_advance_pc = alternate_advance
        asm.var(0xA5, source_page_state + 1)
        asm.emit(0xC9, alternate_page >> 8)
        asm.branch(0xF0, "alternate_advance")
        asm.emit(0xBD, advance & 0xFF, (advance >> 8) & 0xFF)
        asm.branch(0x80, "advance_ready")
        asm.label("alternate_advance")
        asm.emit(
            0xBD,
            alternate_advance_pc & 0xFF,
            (alternate_advance_pc >> 8) & 0xFF,
        )
        asm.label("advance_ready")
    asm.emit(0x18)
    asm.var(0x65, memory.pen)
    asm.emit(0x48)                             # PHA — hold the new pen

    # Name the pair beyond the open cell only when a shifted bitmap row actually
    # put ink there.  The old test was merely `pen != 0`, which claimed a blank
    # pair after any glyph drawn between cell boundaries.  At the right edge of
    # the spirit grid that blank pair replaced the frame after `กำแพง`.  The row
    # loop ORs every real spill byte into the private tail_ink word, so bearings and
    # other empty shifted columns no longer create tilemap entries.
    if not battle and not external_tilemap:
        asm.var(0xA5, memory.tail_ink)
        asm.branch(0xF0, "no_tail")
        asm.emit(0xC2, 0x20)                   # REP #$20
        asm.var(0xA5, memory.col)
        asm.emit(0x1A, 0x1A)
        asm.var(0x85, memory.index)             # the tail's column
        asm.var(0xA5, memory.cell)
        asm.emit(0x18)
        asm.emit(0x69, 0x02, 0x00)
        asm.emit(0x18)
        asm.var(0x65, memory.tilebase)
        asm.emit(0x29, 0xFF, 0x03)             # AND #$03FF
        asm.emit(0x18)
        asm.emit(0x65, 0x2E)                   # ADC $2E
        asm.var_to_x_preserving_a(memory.index)
        asm.long_index(0x9F, 0x7E8000)
        asm.emit(0x1A)                         # INC
        asm.long_index(0x9F, 0x7E8040)
        asm.emit(0xE2, 0x20)                   # SEP #$20
        asm.label("no_tail")

    asm.emit(0x68)                             # PLA — the new pen
    asm.emit(0xC9, 0x08)
    asm.branch(0x90, "same_cell")

    asm.emit(0xE9, 0x08)
    asm.var(0x85, memory.pen)
    asm.emit(0xC2, 0x20)
    asm.var(0xA5, memory.cell)                  # the spill pair becomes our cell
    asm.emit(0x1A, 0x1A)
    asm.emit(0x29, 0xFF, 0x03)
    asm.var(0x85, memory.cell)
    if not battle:
        asm.var(0xA5, memory.col)
        asm.emit(0x1A, 0x1A)
        asm.var(0x85, memory.col)
    # The cell just moved on.  If the glyph that moved it spilled — the new pen
    # is not zero — its tail is sitting in that new cell, and `carry_on` left
    # the cursor pointing straight at it.  A Thai glyph next would rewrite the
    # column and never notice, but anything on the stock path writes its own
    # column first and renames the tail's cell out from under it: which is how
    # every status label that abuts a value lost its last letter.  Step the
    # cursor past it so whoever draws next starts clear.
    #
    # Only when there is a tail.  A glyph whose advance lands exactly on the
    # boundary moves the cell without leaving anything in it, and stepping there
    # skips a column the next glyph wanted — an 8px hole in the middle of a word.
    if not battle:
        asm.emit(0xE2, 0x20)                   # SEP #$20
        asm.var(0xA5, memory.pen)
        asm.branch(0xF0, "no_step")
        asm.emit(0xC2, 0x20)                   # REP #$20
        asm.emit(0xA5, 0x18)
        asm.emit(0x1A, 0x1A)
        asm.emit(0x85, 0x18)
        asm.var(0xA5, memory.expect_col)
        asm.emit(0x1A, 0x1A)
        asm.var(0x85, memory.expect_col)
        asm.emit(0xE2, 0x20)                   # SEP #$20
        asm.label("no_step")
    asm.emit(0xC2, 0x20)                       # REP #$20
    if dialogue_tail_counter_step:
        # The EN-hack VWF tail advances $D0 by one pair after a pixel-cell
        # crossing.  This renderer already moved its private cell, so predict
        # that external step in EXPECT without moving $D0 a second time here.
        asm.emit(0xA9, 0x01, 0x00)
        asm.var(0x85, memory.temp)
    asm.branch(0x80, "park")

    asm.label("same_cell")
    asm.var(0x85, memory.pen)
    asm.emit(0xC2, 0x20)
    if dialogue_tail_counter_step:
        asm.emit(0xA9, 0x00, 0x00)
        asm.var(0x85, memory.temp)

    asm.label("park")
    # Repeat the current cell on the engine's next placement instead of leaving
    # a parked guard tile named in a dead column.  A field boundary that needs
    # to protect a real spill supplies a spacing guard in its script.
    if not battle:
        emit_redirect_stock_tilemap_write(
            asm, memory, "base_stock_write_ready", external_tilemap
        )
        if caller_reuses_cell_cursor:
            # The catalog caller keeps the cursor returned by this renderer;
            # its next glyph is in the same field iff it names our live cell.
            asm.var(0xA5, memory.col)
            asm.var(0x85, memory.expect_col)

    # Park $D0 past our cell and past the pair its spill uses, so a Latin glyph
    # or digit drawn next can never land on either. The parked pairs still have
    # to be blank because stock glyphs allocate from them, but they no longer
    # need a sacrificial tilemap column of their own.
    asm.var(0xA5, memory.cell)
    asm.emit(0x18)
    park = 0x0002 if compact_grid else 0x0004
    asm.emit(0x69, park & 0xFF, park >> 8)
    asm.emit(0x29, 0xFF, 0x03)
    asm.emit(0x85, 0xD0)
    if dialogue_tail_counter_step:
        asm.var(0xA5, memory.temp)
        asm.branch(0xF0, "expect_after_dialogue_tail")
        asm.emit(0xA5, 0xD0)
        asm.emit(0x18)
        asm.emit(0x69, 0x02, 0x00)
        asm.emit(0x29, 0xFF, 0x03)
        asm.branch(0x80, "store_expect")
        asm.label("expect_after_dialogue_tail")
        asm.emit(0xA5, 0xD0)
        asm.label("store_expect")
    asm.var(0x85, memory.expect)
    # Blank both the parked pair and the one after it: the wide path names tiles
    # $D0+2/$D0+3, so its stray column can reach a pair beyond the parked one.
    park_clear_offsets = (0x0000,) if compact_grid else (0x0000, 0x0002)
    for offset in park_clear_offsets:
        asm.emit(0xA5, 0xD0)
        if offset:
            asm.emit(0x18)
            asm.emit(0x69, offset, 0x00)
        asm.emit(0x0A, 0x0A, 0x0A, 0x0A, 0x0A)
        asm.var(0x85, memory.tile)
        asm.emit(0x20, 0x00, 0x00)
        asm.fixups_abs.append((len(asm.code) - 2, "clear_pair"))
    if tilemap_preserve:
        emit_tilemap_preserve(asm, tilemap_preserve, restore=True)
    emit_renderer_return(asm, exit_op)          # RTS under shorthand, else RTL

    # --- grid-locked: the stock rasterizer, byte for byte -----------------
    asm.label("locked")
    # Poisoning the expected counter ends the current run, so the next Thai
    # glyph restarts from wherever the engine has left $D0 and $18.
    asm.emit(0xC2, 0x20)                       # REP #$20
    asm.emit(0xA9, 0xFF, 0xFF)
    asm.var(0x85, memory.expect)
    asm.var(0xA5, memory.glyph_id)
    asm.emit(0x0A, 0x0A, 0x0A, 0x0A)           # Y = glyph * 16
    if source_page_state is not None:
        asm.emit(0x18)
        asm.var(0x65, source_page_state)
    asm.emit(0xA8)
    asm.emit(0xA5, 0xD0)
    asm.emit(0x0A, 0x0A, 0x0A, 0x0A, 0x0A)     # X = tile counter * 32
    asm.emit(0xAA)
    asm.emit(0xE2, 0x20)                       # SEP #$20
    asm.emit(0x8B)                             # PHB
    asm.emit(0xA9, source_bank)
    asm.emit(0x48, 0xAB)                       # PHA / PLB
    asm.emit(0xA9, 0x08)
    asm.var(0x85, memory.rows)

    asm.label("locked_row")
    asm.emit(0xB9, source_base & 0xFF, (source_base >> 8) & 0xFF)
    asm.long_index(0x9F, 0x7F8000)             # plane 0, top tile
    asm.emit(0xB9, (source_base + 8) & 0xFF, ((source_base + 8) >> 8) & 0xFF)
    asm.long_index(0x9F, 0x7F8020)             # plane 0, bottom tile
    asm.emit(0xA5, 0xFD)
    asm.long_index(0x9F, 0x7F8001)
    asm.long_index(0x9F, 0x7F8021)
    asm.emit(0xA5, 0xFE)
    asm.long_index(0x9F, 0x7F8010)
    asm.long_index(0x9F, 0x7F8030)
    asm.emit(0xC8)                             # INY
    asm.emit(0xE8, 0xE8)                       # INX / INX
    asm.var(0xA5, memory.rows)
    asm.emit(0x3A)
    asm.var(0x85, memory.rows)
    asm.branch(0xD0, "locked_row")

    asm.emit(0xC2, 0x20)                       # REP #$20
    asm.emit(0xA5, 0xD0)
    asm.emit(0x1A, 0x1A)
    asm.emit(0x29, 0xFF, 0x03)
    asm.emit(0x85, 0xD0)
    emit_renderer_return(asm, exit_op)

    if combining:
        emit_mark_path(
            asm,
            memory,
            source_base,
            combining,
            upper_stacks,
            battle,
            exit_op,
            external_tilemap,
            shift_right,
            shift_left,
        )

    # --- subroutine: zero plane 0 of the pair whose byte offset is in $E0 ---
    asm.label("clear_pair")
    asm.emit(0x08)                             # PHP
    asm.emit(0xC2, 0x20)
    asm.var(0xA5, memory.tile)
    asm.var(0xC5, memory.cleared)
    asm.branch(0xD0, "do_clear")
    asm.emit(0x28)
    asm.emit(0x60)
    asm.label("do_clear")
    asm.var(0xA5, memory.tile)
    asm.var(0x85, memory.cleared)
    asm.emit(0xE2, 0x20)
    asm.emit(0xDA)                             # PHX
    asm.emit(0x5A)                             # PHY
    asm.var_to_x_from_m8(memory.tile)
    asm.emit(0xA9, 0x00)
    asm.emit(0xA0, 0x08, 0x00)
    asm.label("clear_loop")
    asm.long_index(0x9F, 0x7F8000)
    asm.long_index(0x9F, 0x7F8020)
    asm.emit(0xE8, 0xE8)
    asm.emit(0x88)
    asm.branch(0xD0, "clear_loop")
    asm.emit(0x7A)                             # PLY
    asm.emit(0xFA)                             # PLX
    asm.emit(0x28)                             # PLP
    asm.emit(0x60)                             # RTS

    code = bytearray(asm.finish())
    for at, name in asm.fixups_abs:
        target = (origin & 0xFFFF) + asm.labels[name]
        code[at : at + 2] = target.to_bytes(2, "little")
    extra_dp = frozenset()
    if tilemap_preserve:
        pointer_dp = tilemap_preserve["pointer_dp"]
        extra_dp = frozenset((pointer_dp, (pointer_dp + 1) & 0xFF))
    validate_renderer_code(bytes(code), extra_dp)
    return bytes(code)


def emit_mark_path(
    asm: "Asm", memory: RendererMemory, source_base: int,
    tables: dict[str, int], upper_stacks: dict[str, int],
    battle: bool, exit_op: int = 0x6B, external_tilemap: bool = False,
    shift_right: int = SHR_TABLE, shift_left: int = SHL_TABLE,
) -> None:
    """Place a combining mark against the base already drawn.

    `srw4th.text.renderer` is the specification; this is the same arithmetic with
    the divisions turned into shifts.  The mark is right-aligned to the base's
    ink and nudged by its own `dx`, drawn at an absolute row, and given no
    advance — so the pen, the cell and the tilemap columns are untouched and the
    run carries on as if the mark were not there. Before returning, the stock
    tilemap write is redirected just like the base path; marks are separate
    engine glyphs even though they advance no pixels.
    """
    asm.label("mark")
    # A save made by an older renderer can resume on the mark after its base,
    # while the new private block has no anchor. Dropping that one orphan mark
    # is safe; using zero/stale cell state would draw into an unrelated tile.
    asm.emit(0xC2, 0x20)
    asm.var(0xA5, memory.initialized)
    asm.emit(0xC9, STATE_SIGNATURE & 0xFF, STATE_SIGNATURE >> 8)
    asm.branch(0xF0, "mark_has_anchor")
    asm.emit(0xA5, 0xD0)
    asm.emit(exit_op)
    asm.label("mark_has_anchor")
    asm.emit(0xE2, 0x20)
    asm.emit(0x8B)                             # PHB
    asm.emit(0xA9, 0xFF)
    asm.emit(0x48, 0xAB)                       # PHA / PLB — DB = $FF
    asm.var_to_x_from_m8(memory.glyph_id)

    # A tone following one of the six upper vowels uses one of 30 precomputed
    # pair records. Text/save bytes remain base+vowel+tone; only the second
    # layer's geometry changes. $FF means this mark follows the generic path.
    asm.emit(0xA9, 0xFF)
    asm.var(0x85, memory.stack_index)
    asm.emit(0xA9, 0x00)
    asm.var(0x85, memory.stack_index + 1)       # zero-extend for 16-bit X loads
    asm.var(0xA5, memory.glyph_id)
    asm.emit(0xC9, 0xDA)
    asm.branch(0x90, "stack_classified")
    asm.emit(0xC9, 0xDF)
    asm.branch(0xB0, "stack_classified")
    asm.var(0xA5, memory.has_vowel)
    asm.emit(0xC9, 0xD0)
    asm.branch(0x90, "stack_classified")
    asm.emit(0xC9, 0xD6)
    asm.branch(0xB0, "stack_classified")
    asm.emit(0x38, 0xE9, 0xD0)                 # upper-vowel index 0..5
    asm.var(0x85, memory.temp)
    asm.emit(0x0A, 0x0A)                       # index * 4
    asm.emit(0x18)
    asm.var(0x65, memory.temp)                  # index * 5
    asm.var(0x85, memory.temp)
    asm.var(0xA5, memory.glyph_id)
    asm.emit(0x38, 0xE9, 0xDA)                 # tone index 0..4
    asm.emit(0x18)
    asm.var(0x65, memory.temp)
    asm.var(0x85, memory.stack_index)
    asm.label("stack_classified")

    # Width and height live in private scratch, never battle geometry DP.
    asm.var(0xA5, memory.stack_index)
    asm.emit(0xC9, 0xFF)
    asm.branch(0xF0, "mark_regular_size")
    asm.var_to_x_from_m8(memory.stack_index)
    asm.emit(
        0xBD,
        upper_stacks["size"] & 0xFF,
        (upper_stacks["size"] >> 8) & 0xFF,
    )
    asm.branch(0x80, "mark_size_loaded")
    asm.label("mark_regular_size")
    asm.var_to_x_from_m8(memory.glyph_id)
    asm.emit(0xBD, tables["mark_size"] & 0xFF, (tables["mark_size"] >> 8) & 0xFF)
    asm.label("mark_size_loaded")
    asm.emit(0x48)                             # PHA
    asm.emit(0x29, 0x0F)
    asm.var(0x85, memory.temp)
    asm.emit(0x68)                             # PLA
    asm.emit(0x4A, 0x4A, 0x4A, 0x4A)           # LSR x4
    asm.var(0x85, memory.rows)

    # A precomposed second layer follows the final position of its vowel.  Its
    # signed dx/dy were generated from the pair, so no collision probe or
    # independently chosen raised row can separate the two layers.
    asm.var(0xA5, memory.stack_index)
    asm.emit(0xC9, 0xFF)
    asm.branch(0xF0, "mark_regular_position")
    asm.var_to_x_from_m8(memory.stack_index)
    asm.var(0xA5, memory.upper_x)
    asm.emit(0x18)
    asm.emit(
        0x7D,
        upper_stacks["dx"] & 0xFF,
        (upper_stacks["dx"] >> 8) & 0xFF,
    )
    asm.var(0x85, memory.mark_x)
    asm.var(0xA5, memory.upper_top)
    asm.emit(0x18)
    asm.emit(
        0x7D,
        upper_stacks["dy"] & 0xFF,
        (upper_stacks["dy"] >> 8) & 0xFF,
    )
    asm.branch(0x10, "stack_top_in_bounds")    # BPL: signed result >= 0
    asm.emit(0xA9, 0x00)
    asm.label("stack_top_in_bounds")
    asm.var(0x85, memory.mark_top)
    asm.branch(0x80, "mark_classify")

    asm.label("mark_regular_position")
    asm.var_to_x_from_m8(memory.glyph_id)
    # column = base_left + base_ink - width + dx, biased by 8 so the cell index
    # stays unsigned: `ึ` is 7px wide with dx +1 and starts left of a narrow base.
    asm.var(0xA5, memory.base_left)
    asm.emit(0x18)
    asm.var(0x65, memory.base_ink)
    asm.emit(0x38)
    asm.var(0xE5, memory.temp)
    asm.emit(0x18)
    asm.emit(0x7D, tables["mark_dx"] & 0xFF, (tables["mark_dx"] >> 8) & 0xFF)
    asm.emit(0x18)
    asm.emit(0x69, 0x08)
    asm.var(0x85, memory.mark_x)

    # Generic resting row. Upper-stack tones never enter this path.
    asm.emit(0xBD, tables["mark_y"] & 0xFF, (tables["mark_y"] >> 8) & 0xFF)
    asm.var(0x85, memory.mark_top)
    asm.label("mark_classify")
    asm.var(0xA5, memory.glyph_id)
    asm.emit(0xC9, 0xDA)
    asm.branch(0x90, "mark_vowel")             # below $DA: an above vowel
    asm.emit(0xC9, 0xE0)
    asm.branch(0xB0, "mark_below")
    asm.branch(0x80, "mark_place")

    asm.label("mark_vowel")
    asm.var(0xA5, memory.glyph_id)
    asm.var(0x85, memory.has_vowel)
    asm.branch(0x80, "mark_place")

    asm.label("mark_below")
    asm.emit(0xA9, 0x00)
    asm.var(0x85, memory.has_vowel)

    asm.label("mark_place")
    # A mark wider than its base's ink hangs left of the pen — `ก` is 5px of ink
    # and `ั` is 5px with dx -1, so it starts one pixel before the base does.
    # Mid-word that pixel belongs in the previous pair, which is why MARK_X is
    # biased by 8 and the cell index can come out at -2.  On the run's first
    # base there is no previous pair: the index would land on whatever tile the
    # engine last handed to someone else and smear the mark's left edge across
    # an unrelated glyph.  Clamp to the run's own cell there, which shifts the
    # mark right by a pixel or two rather than dropping it.  The reference renderer
    # does the same by clamping x at 0, since its surface starts at the string.
    asm.var(0xA5, memory.mark_x)
    asm.emit(0xC9, 0x08)
    asm.branch(0xB0, "mark_placed")
    asm.emit(0xC2, 0x20)                       # REP #$20
    asm.var(0xA5, memory.base_cell)
    asm.var(0xC5, memory.run_cell)
    asm.emit(0xE2, 0x20)                       # SEP #$20
    asm.branch(0xD0, "mark_placed")
    asm.emit(0xA9, 0x08)
    asm.var(0x85, memory.mark_x)

    asm.label("mark_placed")
    # $E0 = byte offset of the pair the mark starts in.  The bias makes the
    # divide a plain shift; subtracting 2 afterwards takes it back out.
    asm.var(0xA5, memory.mark_x)
    asm.emit(0x4A, 0x4A, 0x4A)                 # LSR x3
    asm.emit(0x0A)                             # ASL — cells step by two
    asm.emit(0xC2, 0x20)                       # REP #$20
    asm.emit(0x29, 0xFF, 0x00)
    asm.emit(0x38)
    asm.emit(0xE9, 0x02, 0x00)
    asm.emit(0x18)
    asm.var(0x65, memory.base_cell)
    asm.emit(0x29, 0xFF, 0x03)                 # AND #$03FF
    asm.emit(0x0A, 0x0A, 0x0A, 0x0A, 0x0A)
    asm.var(0x85, memory.tile)
    asm.var(0xA5, memory.stack_index)
    asm.emit(0xC9, 0xFF, 0x00)                 # M=16 here after tile arithmetic
    asm.branch(0xF0, "mark_regular_source")
    asm.var(0xA5, memory.stack_index)
    asm.emit(0x0A, 0x0A, 0x0A, 0x0A)           # Y = pair index * 16
    asm.emit(0xA8)
    asm.branch(0x80, "mark_source_ready")
    asm.label("mark_regular_source")
    asm.var(0xA5, memory.glyph_id)
    asm.emit(0x0A, 0x0A, 0x0A, 0x0A)           # Y = code * 16
    asm.emit(0xA8)
    asm.label("mark_source_ready")
    asm.emit(0xE2, 0x20)                       # SEP #$20
    asm.var(0xA5, memory.mark_x)
    asm.emit(0x29, 0x07)
    asm.emit(0xEB)                             # XBA
    asm.emit(0xA9, 0x00)
    asm.emit(0xC2, 0x20)                       # REP #$20
    asm.var(0x85, memory.index)                 # sub-pixel column * 256
    asm.emit(0xE2, 0x20)                       # SEP #$20

    asm.var(0xA5, memory.stack_index)
    asm.emit(0xC9, 0xFF)
    asm.branch(0xF0, "mark_generic_lift")
    asm.brl("mark_lift_done")                  # precomposed pair: never re-solve
    asm.label("mark_generic_lift")
    emit_mark_lift(asm, memory, source_base, shift_right, shift_left)
    asm.label("mark_lift_done")

    # Remember the upper vowel only after its collision lift is final. The
    # collision routine reuses glyph_id as scratch, so has_vowel is the stable
    # class/code record here.
    asm.var(0xA5, memory.stack_index)
    asm.emit(0xC9, 0xFF)
    asm.branch(0xD0, "mark_anchor_ready")
    asm.var(0xA5, memory.has_vowel)
    asm.emit(0xC9, 0xD0)
    asm.branch(0x90, "mark_anchor_ready")
    asm.emit(0xC9, 0xD6)
    asm.branch(0xB0, "mark_anchor_ready")
    asm.var(0xA5, memory.mark_x)
    asm.var(0x85, memory.upper_x)
    asm.var(0xA5, memory.mark_top)
    asm.var(0x85, memory.upper_top)
    asm.label("mark_anchor_ready")

    asm.label("mark_row")
    asm.var(0xA5, memory.mark_top)
    asm.emit(0xC9, 0x10)
    asm.branch(0x90, "mark_in_bounds")
    asm.brl("mark_done")                       # off the bottom of the cell
    asm.label("mark_in_bounds")
    # byte offset inside the pair: row * 2, plus 16 once the bottom tile starts
    asm.emit(0x0A)
    asm.emit(0xC9, 0x10)
    asm.branch(0x90, "mark_top_tile")
    asm.emit(0x18)
    asm.emit(0x69, 0x10)
    asm.label("mark_top_tile")
    asm.emit(0xC2, 0x20)                       # REP #$20
    asm.emit(0x29, 0xFF, 0x00)
    asm.emit(0x18)
    asm.var(0x65, memory.tile)
    asm.var(0x85, memory.glyph)                 # where this row lands
    asm.emit(0xE2, 0x20)                       # SEP #$20

    for table, spill in ((shift_right, 0x0000), (shift_left, 0x0040)):
        source_regular = f"mark_regular_row_source_{spill:04X}"
        source_ready = f"mark_row_source_ready_{spill:04X}"
        asm.var(0xA5, memory.stack_index)
        asm.emit(0xC9, 0xFF)
        asm.branch(0xF0, source_regular)
        asm.emit(
            0xB9,
            upper_stacks["overlay"] & 0xFF,
            (upper_stacks["overlay"] >> 8) & 0xFF,
        )
        asm.branch(0x80, source_ready)
        asm.label(source_regular)
        asm.emit(0xB9, source_base & 0xFF, (source_base >> 8) & 0xFF)
        asm.label(source_ready)
        asm.emit(0xC2, 0x20)
        asm.emit(0x29, 0xFF, 0x00)
        asm.emit(0x18)
        asm.var(0x65, memory.index)
        asm.emit(0xAA)
        asm.emit(0xE2, 0x20)
        asm.emit(0xBD, table & 0xFF, (table >> 8) & 0xFF)
        asm.var(0x85, memory.temp)
        asm.var_to_x_from_m8(memory.glyph)
        asm.var(0xA5, memory.temp)
        asm.long_index(0x1F, 0x7F8000 + spill)
        asm.long_index(0x9F, 0x7F8000 + spill)

    asm.emit(0xC8)                             # INY
    asm.var(0xA5, memory.mark_top)              # no INC long; A is dead here
    asm.emit(0x1A)
    asm.var(0x85, memory.mark_top)
    asm.var(0xA5, memory.rows)
    asm.emit(0x3A)
    asm.var(0x85, memory.rows)
    asm.branch(0xF0, "mark_done")
    asm.brl("mark_row")

    asm.label("mark_done")
    asm.emit(0xC2, 0x20)                       # REP #$20
    # The engine steps the cursor once per source byte, marks included, but a
    # mark occupies no cell. Repeat the renderer-owned cell and keep the open
    # run aligned. Marks that share a spill with their base are expanded inside
    # one source byte, so no engine placement occurs between them.
    if not battle:
        emit_redirect_stock_tilemap_write(
            asm, memory, "mark_stock_write_ready", external_tilemap
        )
    emit_renderer_return(asm, exit_op)


def emit_mark_lift(
    asm: "Asm", memory: RendererMemory, source_base: int,
    shift_right: int = SHR_TABLE, shift_left: int = SHL_TABLE,
) -> None:
    """Raise an above mark until it stops touching ink already in the buffer.

    Thai stacks marks over tall consonants — `ป ฟ ฬ ล ษ` — and over an already
    stacked vowel, so a fixed row is not enough.  The test is per pixel, against
    what has actually been drawn, which is what makes it independent of which
    base or which combination turned up.

    Reading eight pixels at an arbitrary column means combining two bytes:
    `A << sub` from the pair the mark starts in, and `B >> (8 - sub)` from the
    next one.  The shift tables cover 0..7, so with `q = 8 - sub` those are
    `SHL[q][A]` and `SHR[q][B]` — except at `sub == 0`, where `q` would be 8 and
    the answer is simply `A`.
    """
    asm.var(0xA5, memory.glyph_id)
    asm.emit(0xC9, 0xE0)
    asm.branch(0xB0, "lift_done")              # below marks never lift

    asm.var(0xA5, memory.mark_x)
    asm.emit(0x29, 0x07)
    asm.var(0x85, memory.lift_q)
    asm.emit(0xA9, 0x08)
    asm.emit(0x38)
    asm.var(0xE5, memory.lift_q)
    asm.var(0x85, memory.lift_q)                # q = 8 - sub
    asm.emit(0xEB)                             # XBA
    asm.emit(0xA9, 0x00)
    asm.emit(0xC2, 0x20)                       # REP #$20
    asm.var(0x85, memory.glyph)                 # q * 256
    asm.emit(0xE2, 0x20)                       # SEP #$20

    asm.label("lift_loop")
    asm.var(0xA5, memory.mark_top)
    asm.branch(0xF0, "lift_done")              # already at the top of the cell
    asm.emit(0x20, 0x00, 0x00)
    asm.fixups_abs.append((len(asm.code) - 2, "mark_collides"))
    asm.branch(0xF0, "lift_done")              # clear: stop here
    asm.var(0xA5, memory.mark_top)              # no DEC long; A is dead here
    asm.emit(0x3A)
    asm.var(0x85, memory.mark_top)
    asm.branch(0x80, "lift_loop")
    asm.label("lift_done")
    asm.brl("lift_exit")

    # --- returns Z set when the mark clears everything already drawn ---
    asm.label("mark_collides")
    asm.emit(0x5A)                             # PHY
    asm.var(0xA5, memory.rows)
    asm.var(0x85, memory.glyph_id)              # rows left; glyph id is dead here
    asm.var(0xA5, memory.mark_top)
    asm.var(0x85, memory.temp)                  # row being tested

    asm.label("col_row")
    asm.var(0xA5, memory.temp)
    asm.emit(0xC9, 0x10)
    asm.branch(0xB0, "col_next")               # past the bottom: nothing to hit
    asm.emit(0x0A)                             # row * 2
    asm.emit(0xC9, 0x10)
    asm.branch(0x90, "col_top_tile")
    asm.emit(0x18)
    asm.emit(0x69, 0x10)                       # bottom tile starts 16 bytes on
    asm.label("col_top_tile")
    asm.emit(0xC2, 0x20)                       # REP #$20
    asm.emit(0x29, 0xFF, 0x00)
    asm.emit(0x18)
    asm.var(0x65, memory.tile)
    asm.emit(0xAA)                             # TAX
    asm.emit(0xE2, 0x20)                       # SEP #$20
    asm.long_index(0xBF, 0x7F8000)
    asm.var(0x85, memory.lift_a)
    asm.long_index(0xBF, 0x7F8040)
    asm.var(0x85, memory.lift_b)

    asm.var(0xA5, memory.lift_q)
    asm.emit(0xC9, 0x08)
    asm.branch(0xF0, "col_aligned")            # sub == 0: the byte as it stands
    asm.var(0xA5, memory.lift_a)
    asm.emit(0xC2, 0x20)
    asm.emit(0x29, 0xFF, 0x00)
    asm.emit(0x18)
    asm.var(0x65, memory.glyph)
    asm.emit(0xAA)
    asm.emit(0xE2, 0x20)
    asm.emit(0xBD, shift_left & 0xFF, (shift_left >> 8) & 0xFF)
    asm.var(0x85, memory.lift_a)
    asm.var(0xA5, memory.lift_b)
    asm.emit(0xC2, 0x20)
    asm.emit(0x29, 0xFF, 0x00)
    asm.emit(0x18)
    asm.var(0x65, memory.glyph)
    asm.emit(0xAA)
    asm.emit(0xE2, 0x20)
    asm.emit(0xBD, shift_right & 0xFF, (shift_right >> 8) & 0xFF)
    asm.var(0x05, memory.lift_a)                # ORA — the eight pixels at x
    asm.branch(0x80, "col_test")

    asm.label("col_aligned")
    asm.var(0xA5, memory.lift_a)

    asm.label("col_test")
    asm.emit(0x39, source_base & 0xFF, (source_base >> 8) & 0xFF)  # AND page,Y
    asm.branch(0xD0, "col_hit")

    asm.label("col_next")
    asm.emit(0xC8)                             # INY
    asm.var(0xA5, memory.temp)
    asm.emit(0x1A)
    asm.var(0x85, memory.temp)
    asm.var(0xA5, memory.glyph_id)
    asm.emit(0x3A)
    asm.var(0x85, memory.glyph_id)
    asm.branch(0xF0, "col_clear")
    asm.brl("col_row")
    asm.label("col_clear")
    asm.emit(0x7A)                             # PLY
    asm.emit(0xA9, 0x00)                       # Z set: clear
    asm.emit(0x60)                             # RTS

    asm.label("col_hit")
    asm.emit(0x7A)                             # PLY
    asm.emit(0xA9, 0x01)                       # Z clear: something is in the way
    asm.emit(0x60)                             # RTS

    asm.label("lift_exit")


def emit_row(
    asm: "Asm", memory: RendererMemory, source: int, target: int, spill: int,
    shift_right: int = SHR_TABLE, shift_left: int = SHL_TABLE,
) -> None:
    """One glyph row: shift into the current pair, carry the rest to the next."""
    for table, offset, merge in ((shift_right, target, True), (shift_left, spill, True)):
        asm.emit(0xB9, source & 0xFF, (source >> 8) & 0xFF)  # LDA $8000,Y
        asm.emit(0xC2, 0x20)
        asm.emit(0x29, 0xFF, 0x00)
        asm.emit(0x18)
        asm.var(0x65, memory.index)
        asm.emit(0xAA)                                       # TAX = pen*256 + byte
        asm.emit(0xE2, 0x20)
        asm.emit(0xBD, table & 0xFF, (table >> 8) & 0xFF)    # LDA table,X
        asm.var(0x85, memory.temp)
        if table == shift_left:
            asm.var(0x05, memory.tail_ink)                  # ORA actual spill flag
            asm.var(0x85, memory.tail_ink)
        asm.var_to_x_from_m8(memory.tile)
        asm.var(0xA5, memory.temp)
        asm.long_index(0x1F, 0x7F8000 + offset)              # ORA long,X
        asm.long_index(0x9F, 0x7F8000 + offset)              # STA long,X
