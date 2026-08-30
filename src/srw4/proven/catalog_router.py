"""Catalog-only parser, width and renderer routing adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .renderer65816 import (
    Asm,
    BATTLE_STATE_BASE,
    ORDINARY_STATE_BASE,
    STATE_SIGNATURE,
    pc_to_cpu,
    renderer_memory,
)


INTERNAL_BASE = 0x0A00
INTERNAL_LIMIT = 0x0AEC
FIXED_BASE = 0x0B00
FIXED_LIMIT = 0x0BEC
CONTROL_BASE = 0xEC


def _jml(asm: Asm, cpu: int) -> None:
    asm.emit(0x5C, cpu & 0xFF, (cpu >> 8) & 0xFF, cpu >> 16)


DESC_STRIDE = 8
PAGE_TABLE_BYTES = 512
PAGE_BITMAP_BYTES = 32
ROUTE_ORIGINAL = 0x0000
ROUTE_THAI = 0x0001
ROUTE_FIXED = 0x0002
ROUTE_MIXED = 0x8000
ROUTE_OFFSET_MASK = 0x7FFF
ROUTE_BLOCK_LIMIT = 0x10000


def build_route_tables(
    ranges: Mapping[int, Sequence[tuple[int, int]]],
    fixed_ranges: Mapping[int, Sequence[tuple[int, int]]] | None = None,
    *,
    capacity: int = ROUTE_BLOCK_LIMIT,
) -> bytes:
    """Constant-cost routing tables for the shared source router.

    A byte's route used to be decided by walking every declared range, so the
    per-byte cost grew with the catalogs.  Past roughly twenty comparisons the
    battle text path missed its timing budget and the battle sequence never
    resumed.  Here the source bank indexes a descriptor, the address' high byte
    indexes that bank's page table, and only a page that mixes routed and
    unrouted bytes falls back to a 32-byte bitmap.

    The block is one blob: descriptors, then page tables, then page bitmaps.
    Every stored offset is relative to its start, so all three levels are read
    through one 24-bit base with a 16-bit index.
    """
    fixed_ranges = fixed_ranges or {}
    banks = sorted(set(ranges) | set(fixed_ranges))
    descriptors = bytearray(256 * DESC_STRIDE)
    tables = bytearray()
    bitmaps = bytearray()
    mixed_entries: list[tuple[int, int]] = []
    table_base = len(descriptors)

    def word(buffer: bytearray, at: int, value: int) -> None:
        buffer[at:at + 2] = (value & 0xFFFF).to_bytes(2, "little")

    for bank in banks:
        thai = tuple(sorted(ranges.get(bank, ())))
        fixed = tuple(sorted(fixed_ranges.get(bank, ())))
        if not thai and not fixed:
            continue
        marks = bytearray(0x10000)
        for kind, entries in ((1, thai), (2, fixed)):
            for start_address, end_address in entries:
                if end_address > 0x10000:
                    raise ValueError(f"route range past the bank end: {end_address:#06x}")
                for address in range(start_address, end_address):
                    if marks[address] not in (0, kind):
                        raise ValueError(f"conflicting routes at {bank:02X}:{address:04X}")
                    marks[address] = kind
        table = bytearray(PAGE_TABLE_BYTES)
        pending: list[tuple[int, bytes]] = []
        for page in range(256):
            span = marks[page * 256:(page + 1) * 256]
            kinds = set(span)
            if kinds == {0}:
                continue
            if kinds == {1}:
                word(table, page * 2, ROUTE_THAI)
                continue
            if kinds == {2}:
                word(table, page * 2, ROUTE_FIXED)
                continue
            # A mixed page carries both bitmaps back to back: Thai first, then
            # fixed-width.  Pages that mix the two do exist ($CC:AB).
            bits = bytearray(PAGE_BITMAP_BYTES * 2)
            for index, value in enumerate(span):
                if value:
                    bits[(index >> 3) + (value - 1) * PAGE_BITMAP_BYTES] |= 1 << (index & 7)
            pending.append((page, bytes(bits)))
            word(table, page * 2, ROUTE_MIXED)
        descriptors[bank * DESC_STRIDE:bank * DESC_STRIDE + 2] = (
            (table_base + len(tables)).to_bytes(2, "little")
        )
        for page, bits in pending:
            # Patched below, once the page tables are sized: a mixed entry
            # carries the bitmap's offset from the start of the whole block.
            word(table, page * 2, ROUTE_MIXED | len(bitmaps))
            bitmaps.extend(bits)
        mixed_entries.extend(
            (len(tables) + page * 2, page) for page, _ in pending
        )
        tables.extend(table)

    offset_base = len(descriptors) + len(tables)
    for at, _page in mixed_entries:
        entry = int.from_bytes(tables[at:at + 2], "little")
        word(tables, at, ROUTE_MIXED | (entry & ROUTE_OFFSET_MASK) + offset_base)
    block = bytes(descriptors) + bytes(tables) + bytes(bitmaps)
    if offset_base + len(bitmaps) > capacity or len(bitmaps) > ROUTE_OFFSET_MASK:
        raise ValueError(f"route tables need {len(block)} bytes, capacity is {capacity}")
    if table_base + len(tables) > 0xFFFF:
        raise ValueError("route page tables outrun a 16-bit offset")
    return block


def _emit_source_route(
    asm: Asm,
    pointer_dp: int,
    tables: int,
    thai: str,
    fixed: str,
    original: str,
    prefix: str,
    cursor_left_pointers: Mapping[int, Sequence[int]] | None = None,
    *,
    use_fixed: bool = True,
) -> None:
    """Route by the already-advanced 24-bit source pointer.

    Two indexed loads answer for a whole page; only a page that mixes routed
    and unrouted bytes reads a bitmap.  See `build_route_tables` for why the
    old range walk had to go.
    """
    asm.emit(0x48)                              # preserve raw source byte
    cursor_left_pointers = cursor_left_pointers or {}
    if cursor_left_pointers:
        asm.emit(0xA5, pointer_dp + 2, 0x29, 0xFF, 0x00)
        for bank_index, (bank, pointers) in enumerate(sorted(cursor_left_pointers.items())):
            asm.emit(0xC9, bank & 0xFF, bank >> 8)
            asm.branch(0xD0, f"{prefix}_cursor_next_bank_{bank_index}")
            asm.emit(0xA5, pointer_dp)
            for pointer in pointers:
                asm.emit(0xC9, pointer & 0xFF, pointer >> 8)
                asm.branch(0xF0, f"{prefix}_cursor_left")
            asm.brl(f"{prefix}_cursor_checks_done")
            asm.label(f"{prefix}_cursor_next_bank_{bank_index}")
        asm.brl(f"{prefix}_cursor_checks_done")
        asm.label(f"{prefix}_cursor_left")
        # $18 counts half-cells here; two decrements move the F8 value 8px.
        asm.emit(0xC6, 0x18, 0xC6, 0x18)
        asm.brl(original)
        asm.label(f"{prefix}_cursor_checks_done")

    inverse = {0xF0: 0xD0, 0xD0: 0xF0, 0x90: 0xB0, 0xB0: 0x90}
    far_count = [0]

    def far(opcode: int, name: str) -> None:
        """A conditional branch that may outrun its 8-bit displacement."""
        far_count[0] += 1
        skip = f"{prefix}_far_{far_count[0]}"
        asm.branch(inverse[opcode], skip)
        asm.brl(name)
        asm.label(skip)

    asm.emit(0x08)                              # PHP
    asm.emit(0xC2, 0x30)                        # REP #$30
    asm.emit(0xDA)                              # PHX
    asm.emit(0xA5, pointer_dp + 2, 0x29, 0xFF, 0x00)
    asm.emit(0x0A, 0x0A, 0x0A)                  # bank * DESC_STRIDE
    asm.emit(0xAA)                              # TAX
    asm.long_index(0xBF, tables)                # LDA tables,X -- page-table offset
    far(0xF0, f"{prefix}_original_exit")
    asm.emit(0xA5, pointer_dp)                  # source address
    asm.emit(0xEB)                              # XBA -- high byte to the low half
    asm.emit(0x29, 0xFF, 0x00)
    asm.emit(0x0A)                              # page * 2
    asm.emit(0x18)                              # CLC
    asm.long_index(0x7F, tables)                # + this bank's page table
    asm.emit(0xAA)                              # TAX
    asm.long_index(0xBF, tables)                # LDA tables,X -- page entry
    far(0xF0, f"{prefix}_original_exit")
    asm.emit(0xC9, ROUTE_THAI & 0xFF, ROUTE_THAI >> 8)
    far(0xF0, f"{prefix}_thai_exit")
    asm.emit(0xC9, ROUTE_FIXED & 0xFF, ROUTE_FIXED >> 8)
    # The second parser never saw the fixed-width ranges, so it keeps sending
    # them down the original path.
    far(0xF0, f"{prefix}_fixed_exit" if use_fixed else f"{prefix}_original_exit")

    # Mixed page: one bit per byte, Thai bitmap first and fixed-width second.
    # The offset and the caller's Y live on the stack -- every spare byte of
    # bank $7E is either the renderer's or the game's battle line tables.
    asm.emit(0x29, ROUTE_OFFSET_MASK & 0xFF, ROUTE_OFFSET_MASK >> 8)
    asm.emit(0x48)                              # PHA -- bitmap offset
    asm.emit(0x5A)                              # PHY
    asm.emit(0xA5, pointer_dp, 0x29, 0x07, 0x00)
    asm.emit(0xA8)                              # TAY -- bit index
    asm.emit(0xA5, pointer_dp, 0x29, 0xFF, 0x00)
    asm.emit(0x4A, 0x4A, 0x4A)                  # byte index inside the page bitmap
    asm.emit(0x18, 0x63, 0x03)                  # CLC : ADC $03,S -- bitmap offset
    asm.emit(0xAA)                              # TAX
    asm.emit(0xE2, 0x20)                        # SEP #$20
    asm.long_index(0xBF, tables)
    asm.label(f"{prefix}_shift")
    asm.emit(0xC0, 0x00, 0x00)                  # CPY #$0000
    asm.branch(0xF0, f"{prefix}_tested")
    asm.emit(0x4A)                              # LSR A
    asm.emit(0x88)                              # DEY
    asm.branch(0x80, f"{prefix}_shift")
    asm.label(f"{prefix}_tested")
    asm.emit(0x29, 0x01)                        # AND #$01
    asm.branch(0xD0, f"{prefix}_mixed_thai")

    if not use_fixed:
        asm.emit(0xC2, 0x20)                    # REP #$20
        asm.emit(0x7A, 0x68)                    # PLY : PLA
        asm.brl(f"{prefix}_original_exit")
    asm.emit(0xC2, 0x20)                        # REP #$20
    asm.emit(0x8A)                              # TXA
    asm.emit(0x18, 0x69, PAGE_BITMAP_BYTES, 0x00)
    asm.emit(0xAA)                              # TAX -- the fixed-width half
    asm.emit(0xA5, pointer_dp, 0x29, 0x07, 0x00)
    asm.emit(0xA8)                              # TAY -- the first probe counted Y down
    asm.emit(0xE2, 0x20)                        # SEP #$20
    asm.long_index(0xBF, tables)
    asm.label(f"{prefix}_shift_fixed")
    asm.emit(0xC0, 0x00, 0x00)
    asm.branch(0xF0, f"{prefix}_tested_fixed")
    asm.emit(0x4A)
    asm.emit(0x88)
    asm.branch(0x80, f"{prefix}_shift_fixed")
    asm.label(f"{prefix}_tested_fixed")
    asm.emit(0x29, 0x01)
    asm.branch(0xD0, f"{prefix}_mixed_fixed")
    asm.emit(0xC2, 0x20)                        # REP #$20
    asm.emit(0x7A, 0x68)                        # PLY : PLA
    asm.brl(f"{prefix}_original_exit")

    asm.label(f"{prefix}_mixed_thai")
    asm.emit(0xC2, 0x20)
    asm.emit(0x7A, 0x68)
    asm.brl(f"{prefix}_thai_exit")
    asm.label(f"{prefix}_mixed_fixed")
    asm.emit(0xC2, 0x20)
    asm.emit(0x7A, 0x68)
    asm.brl(f"{prefix}_fixed_exit")

    # The walk this replaced always fell into its Thai and fixed-width targets
    # straight off a successful range compare, so both ran with carry clear.
    asm.label(f"{prefix}_thai_exit")
    asm.emit(0xFA, 0x28, 0x18)                  # PLX PLP CLC
    asm.brl(thai)
    asm.label(f"{prefix}_original_exit")
    asm.emit(0xFA, 0x28)
    asm.brl(original)
    asm.label(f"{prefix}_fixed_exit")
    asm.emit(0xFA, 0x28, 0x18)
    asm.brl(fixed)


def build_parser_1(
    origin: int,
    tables: int,
    cursor_left_pointers: Mapping[int, Sequence[int]] | None = None,
) -> bytes:
    asm = Asm(origin)
    _emit_source_route(
        asm, 0x1A, tables, "thai", "fixed", "original", "p1",
        cursor_left_pointers,
    )
    asm.label("original")
    asm.emit(0x68, 0xC9, 0xF0, 0x00)
    asm.branch(0x90, "direct_original")
    _jml(asm, 0x818407)
    asm.label("direct_original")
    _jml(asm, 0x81842A)
    asm.label("thai")
    asm.emit(0x68, 0xC9, CONTROL_BASE, 0x00)
    asm.branch(0x90, "primary")
    _jml(asm, 0x818407)
    asm.label("primary")
    asm.emit(0x09, INTERNAL_BASE & 0xFF, INTERNAL_BASE >> 8)
    _jml(asm, 0x818456)
    asm.label("fixed")
    asm.emit(0x68, 0xC9, CONTROL_BASE, 0x00)
    asm.branch(0xB0, "original_fixed_control")
    asm.emit(0x09, FIXED_BASE & 0xFF, FIXED_BASE >> 8)
    _jml(asm, 0x818456)
    asm.label("original_fixed_control")
    _jml(asm, 0x818407)
    return asm.finish()


def build_parser_1_alt(
    origin: int,
    tables: int,
    cursor_left_pointers: Mapping[int, Sequence[int]] | None = None,
) -> bytes:
    asm = Asm(origin)
    _emit_source_route(
        asm, 0x1A, tables, "thai", "fixed", "original", "p1a",
        cursor_left_pointers,
    )
    asm.label("original")
    asm.emit(0x68, 0xC9, 0xF6, 0x00)
    asm.branch(0x90, "direct_original")
    _jml(asm, 0x818407)
    asm.label("direct_original")
    _jml(asm, 0x818414)
    asm.label("thai")
    asm.emit(0x68, 0xC9, CONTROL_BASE, 0x00)
    asm.branch(0x90, "primary")
    _jml(asm, 0x818407)
    asm.label("primary")
    asm.emit(0x09, INTERNAL_BASE & 0xFF, INTERNAL_BASE >> 8)
    _jml(asm, 0x818456)
    asm.label("fixed")
    asm.emit(0x68, 0xC9, CONTROL_BASE, 0x00)
    asm.branch(0xB0, "original_fixed_control")
    asm.emit(0x09, FIXED_BASE & 0xFF, FIXED_BASE >> 8)
    _jml(asm, 0x818456)
    asm.label("original_fixed_control")
    _jml(asm, 0x818407)
    return asm.finish()


def build_parser_2(origin: int, tables: int) -> bytes:
    asm = Asm(origin)
    _emit_source_route(
        asm, 0xCB, tables, "thai", "fixed", "original", "p2"
    )
    asm.label("thai")
    asm.emit(0x68, 0xC9, CONTROL_BASE, 0x00)
    asm.branch(0x90, "primary")
    asm.emit(0xC9, 0xF6, 0x00)
    asm.branch(0x90, "secondary")
    _jml(asm, 0x81923F)
    asm.label("secondary")
    _jml(asm, 0x81920B)
    asm.label("primary")
    asm.emit(0x09, INTERNAL_BASE & 0xFF, INTERNAL_BASE >> 8)
    _jml(asm, 0x819219)

    asm.label("original")
    asm.emit(0x68, 0xC9, CONTROL_BASE, 0x00)
    asm.branch(0x90, "direct_original")
    asm.emit(0xC9, 0xF0, 0x00)
    asm.branch(0x90, "attribute_original")
    asm.emit(0xC9, 0xF6, 0x00)
    asm.branch(0xB0, "control_original")
    _jml(asm, 0x81920B)
    asm.label("direct_original")
    _jml(asm, 0x819219)
    asm.label("control_original")
    _jml(asm, 0x81923F)
    asm.label("attribute_original")
    _jml(asm, 0x819247)
    asm.label("fixed")
    asm.emit(0x68, 0xC9, CONTROL_BASE, 0x00)
    asm.branch(0xB0, "fixed_control")
    asm.emit(0x09, FIXED_BASE & 0xFF, FIXED_BASE >> 8)
    _jml(asm, 0x819219)
    asm.label("fixed_control")
    _jml(asm, 0x81923F)
    return asm.finish()


def build_classifier(
    origin: int,
    pointer_dp: int,
    continuation: int,
    renderer_pc: int,
    tables: int,
    *,
    fixed_renderer_pc: int | None = None,
    special_renderers: Sequence[tuple[int, int, int, int]] = (),
) -> bytes:
    asm = Asm(origin)
    asm.emit(0x85, 0x00)                       # displaced STA $00
    asm.emit(0xC9, INTERNAL_BASE & 0xFF, INTERNAL_BASE >> 8)
    asm.branch(0x90, "raw")
    asm.emit(0xC9, INTERNAL_LIMIT & 0xFF, INTERNAL_LIMIT >> 8)
    asm.branch(0x90, "internal")
    if fixed_renderer_pc is not None:
        asm.emit(0xC9, FIXED_BASE & 0xFF, FIXED_BASE >> 8)
        asm.branch(0x90, "tagged_original")
        asm.emit(0xC9, FIXED_LIMIT & 0xFF, FIXED_LIMIT >> 8)
        asm.branch(0x90, "fixed_internal")
        asm.label("tagged_original")
    asm.emit(0xC9, 0x00, 0x01)
    _jml(asm, continuation)
    asm.label("internal")
    asm.emit(0x38, 0xE9, INTERNAL_BASE & 0xFF, INTERNAL_BASE >> 8)
    if special_renderers:
        asm.emit(0x48)                          # preserve decoded glyph index
        for index, (bank, start, end, special_pc) in enumerate(special_renderers):
            miss = f"special_miss_{index}"
            asm.emit(0xA5, pointer_dp + 2, 0x29, 0xFF, 0x00)
            asm.emit(0xC9, bank & 0xFF, bank >> 8)
            asm.branch(0xD0, miss)
            asm.emit(0xA5, pointer_dp)
            asm.emit(0xC9, start & 0xFF, start >> 8)
            asm.branch(0x90, miss)
            asm.emit(0xC9, end & 0xFF, end >> 8)
            asm.branch(0xB0, miss)
            asm.emit(0x68)
            _jml(asm, pc_to_cpu(special_pc))
            asm.label(miss)
        asm.emit(0x68)
    _jml(asm, pc_to_cpu(renderer_pc))

    if fixed_renderer_pc is not None:
        asm.label("fixed_internal")
        asm.emit(0x38, 0xE9, FIXED_BASE & 0xFF, FIXED_BASE >> 8)
        _jml(asm, pc_to_cpu(fixed_renderer_pc))

    asm.label("raw")
    asm.emit(0xC9, CONTROL_BASE, 0x00)
    asm.branch(0x90, "raw_source")
    asm.emit(0xC9, 0x00, 0x01)
    _jml(asm, continuation)
    asm.label("raw_source")
    _emit_source_route(
        asm,
        pointer_dp,
        tables,
        "raw_thai",
        "raw_fixed",
        "raw_original",
        "class",
    )
    asm.label("raw_thai")
    asm.emit(0x68)
    _jml(asm, pc_to_cpu(renderer_pc))
    asm.label("raw_original")
    asm.emit(0x68)
    asm.emit(0xC9, 0x00, 0x01)
    _jml(asm, continuation)
    asm.label("raw_fixed")
    asm.emit(0x68)
    if fixed_renderer_pc is None:
        asm.emit(0xC9, 0x00, 0x01)
        _jml(asm, continuation)
    else:
        _jml(asm, pc_to_cpu(fixed_renderer_pc))
    return asm.finish()


def build_width(
    origin: int,
    dp: int,
    continuation: int,
    free: int,
    advance_pc: int,
    *,
    state_base: int,
    battle: bool,
    fixed_advance_pc: int | None = None,
) -> bytes:
    if battle != (state_base == BATTLE_STATE_BASE):
        raise ValueError("width hook context and private state disagree")
    memory = renderer_memory(state_base)
    asm = Asm(origin)
    asm.emit(0x85, dp)
    asm.emit(0xC9, INTERNAL_BASE & 0xFF, INTERNAL_BASE >> 8)
    asm.branch(0x90, "original_jump")
    asm.emit(0xC9, INTERNAL_LIMIT & 0xFF, INTERNAL_LIMIT >> 8)
    asm.branch(0x90, "thai")
    if fixed_advance_pc is not None:
        asm.emit(0xC9, FIXED_BASE & 0xFF, FIXED_BASE >> 8)
        asm.branch(0x90, "original_jump")
        asm.emit(0xC9, FIXED_LIMIT & 0xFF, FIXED_LIMIT >> 8)
        asm.branch(0x90, "fixed")
    asm.branch(0x80, "original_jump")
    asm.label("original_jump")
    asm.brl("original")

    def emit_width_path(label: str, prefix: str, base: int, table_pc: int) -> None:
        asm.label(label)
        asm.emit(0x38, 0xE9, base & 0xFF, base >> 8)
        asm.emit(0x29, 0xFF, 0x00, 0xAA)
        asm.long_index(0xAF, memory.initialized)
        asm.emit(0xC9, STATE_SIGNATURE & 0xFF, STATE_SIGNATURE >> 8)
        asm.branch(0xD0, f"{prefix}_fresh")
        asm.emit(0xA5, 0xD0)
        asm.long_index(0xCF, memory.expect)
        asm.branch(0xD0, f"{prefix}_fresh")
        if not battle:
            asm.emit(0xA5, 0x18)
            asm.long_index(0xCF, memory.expect_col)
            asm.branch(0xD0, f"{prefix}_fresh")
        asm.emit(0xE2, 0x20)
        asm.long_index(0xAF, memory.pen)
        asm.branch(0x80, f"{prefix}_pen")
        asm.label(f"{prefix}_fresh")
        asm.emit(0xE2, 0x20, 0xA9, 0x00)
        asm.label(f"{prefix}_pen")
        asm.emit(0x18)
        asm.long_index(0x7F, pc_to_cpu(table_pc))
        asm.emit(0xC9, 0x08, 0xC2, 0x20)
        asm.branch(0x90, f"{prefix}_free")
        asm.emit(0x18)
        _jml(asm, continuation)
        asm.label(f"{prefix}_free")
        _jml(asm, free)

    emit_width_path("thai", "thai", INTERNAL_BASE, advance_pc)
    if fixed_advance_pc is not None:
        emit_width_path("fixed", "fixed", FIXED_BASE, fixed_advance_pc)
    asm.label("original")
    asm.emit(0xC9, 0x00, 0x01)
    _jml(asm, continuation)
    return asm.finish()


def build_en_cluster_width(
    origin: int, dp: int, continuation: int, *, include_fixed: bool = False
) -> bytes:
    """Strip either private catalog-page tag before the ordinary width path."""
    asm = Asm(origin)
    asm.emit(0x85, dp)
    asm.emit(0xC9, INTERNAL_BASE & 0xFF, INTERNAL_BASE >> 8)
    asm.branch(0x90, "fixed" if include_fixed else "original")
    asm.emit(0xC9, INTERNAL_LIMIT & 0xFF, INTERNAL_LIMIT >> 8)
    asm.branch(0xB0, "fixed" if include_fixed else "original")
    asm.emit(0x38, 0xE9, INTERNAL_BASE & 0xFF, INTERNAL_BASE >> 8)
    asm.emit(0x85, dp)
    asm.branch(0x80, "original")
    if include_fixed:
        asm.label("fixed")
        asm.emit(0xC9, FIXED_BASE & 0xFF, FIXED_BASE >> 8)
        asm.branch(0x90, "original")
        asm.emit(0xC9, FIXED_LIMIT & 0xFF, FIXED_LIMIT >> 8)
        asm.branch(0xB0, "original")
        asm.emit(0x38, 0xE9, FIXED_BASE & 0xFF, FIXED_BASE >> 8)
        asm.emit(0x85, dp)
    asm.label("original")
    asm.emit(0xC9, 0x00, 0x01)
    _jml(asm, continuation)
    return asm.finish()


def build_halfwidth(origin: int, original_wide: int, done: int) -> bytes:
    asm = Asm(origin)
    asm.emit(0xC0, INTERNAL_BASE & 0xFF, INTERNAL_BASE >> 8)
    asm.branch(0x90, "original")
    asm.emit(0xC0, INTERNAL_LIMIT & 0xFF, INTERNAL_LIMIT >> 8)
    asm.branch(0x90, "done")
    asm.emit(0xC0, FIXED_BASE & 0xFF, FIXED_BASE >> 8)
    asm.branch(0x90, "original")
    asm.emit(0xC0, FIXED_LIMIT & 0xFF, FIXED_LIMIT >> 8)
    asm.branch(0x90, "done")
    asm.label("original")
    asm.emit(0xC0, 0x00, 0x01)
    asm.branch(0x90, "done")
    _jml(asm, original_wide)
    asm.label("done")
    _jml(asm, done)
    return asm.finish()


def build_battle_dispatch(origin: int, battle_renderer_pc: int) -> bytes:
    asm = Asm(origin)
    asm.emit(0xC9, INTERNAL_BASE & 0xFF, INTERNAL_BASE >> 8)
    asm.branch(0x90, "stock")
    asm.emit(0xC9, INTERNAL_LIMIT & 0xFF, INTERNAL_LIMIT >> 8)
    asm.branch(0xB0, "stock")
    asm.emit(0x38, 0xE9, INTERNAL_BASE & 0xFF, INTERNAL_BASE >> 8)
    _jml(asm, pc_to_cpu(battle_renderer_pc))
    asm.label("stock")
    asm.emit(0x22, 0xEB, 0x84, 0x81, 0x6B)
    return asm.finish()


def build_ordinary_dispatch(
    origin: int,
    ordinary_renderer_pc: int,
    tables: int,
    *,
    stock_renderer_cpu: int,
    fixed_renderer_pc: int | None = None,
) -> bytes:
    """Dispatch the EN ordinary VWF callsite to Thai or its stock renderer.

    The English patch bypasses the stock classifier at $81:84F2 and calls its
    VWF directly from $81:84E4.  Check both parser-tagged glyphs and the live
    source pointer here so catalog strings still reach the Thai renderer.
    """
    asm = Asm(origin)
    asm.emit(0xC9, INTERNAL_BASE & 0xFF, INTERNAL_BASE >> 8)
    asm.branch(0x90, "raw")
    asm.emit(0xC9, INTERNAL_LIMIT & 0xFF, INTERNAL_LIMIT >> 8)
    asm.branch(0x90, "internal")
    if fixed_renderer_pc is not None:
        asm.emit(0xC9, FIXED_BASE & 0xFF, FIXED_BASE >> 8)
        asm.branch(0x90, "tagged_stock")
        asm.emit(0xC9, FIXED_LIMIT & 0xFF, FIXED_LIMIT >> 8)
        asm.branch(0x90, "fixed_internal")
        asm.label("tagged_stock")
    asm.brl("stock")
    asm.label("internal")
    asm.emit(0x38, 0xE9, INTERNAL_BASE & 0xFF, INTERNAL_BASE >> 8)
    _jml(asm, pc_to_cpu(ordinary_renderer_pc))
    if fixed_renderer_pc is not None:
        asm.label("fixed_internal")
        asm.emit(0x38, 0xE9, FIXED_BASE & 0xFF, FIXED_BASE >> 8)
        _jml(asm, pc_to_cpu(fixed_renderer_pc))

    asm.label("raw")
    asm.emit(0xC9, CONTROL_BASE, 0x00)
    asm.branch(0x90, "raw_route")
    asm.brl("stock")
    asm.label("raw_route")
    _emit_source_route(
        asm, 0x1A, tables, "raw_thai", "raw_fixed", "raw_stock",
        "ordinary_dispatch", use_fixed=fixed_renderer_pc is not None,
    )
    asm.label("raw_thai")
    asm.emit(0x68)
    _jml(asm, pc_to_cpu(ordinary_renderer_pc))
    if fixed_renderer_pc is not None:
        asm.label("raw_fixed")
        asm.emit(0x68)
        _jml(asm, pc_to_cpu(fixed_renderer_pc))
    asm.label("raw_stock")
    asm.emit(0x68)

    asm.label("stock")
    _jml(asm, stock_renderer_cpu)
    return asm.finish()


def hook_jml(target_pc: int) -> bytes:
    cpu = pc_to_cpu(target_pc)
    return bytes((0x5C, cpu & 0xFF, (cpu >> 8) & 0xFF, cpu >> 16, 0xEA))


def hook_jsl(target_pc: int) -> bytes:
    cpu = pc_to_cpu(target_pc)
    return bytes((0x22, cpu & 0xFF, (cpu >> 8) & 0xFF, cpu >> 16))
