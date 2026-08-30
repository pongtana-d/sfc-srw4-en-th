"""65816 adapters for deterministic stock-font runs embedded in Thai text."""

from __future__ import annotations

from .renderer65816 import (
    BATTLE_STATE_BASE,
    ORDINARY_STATE_BASE,
    STATE_SIGNATURE,
    Asm,
    pc_to_cpu,
    renderer_memory,
)


ORDINARY_HOOK_SITE = 0x018DF3
ORDINARY_HOOK_EXPECTED = bytes.fromhex("A5 00 30 17 EB")
BATTLE_HOOK_SITE = 0x019386
BATTLE_HOOK_EXPECTED = bytes.fromhex("85 00 30 09 EB")
# The stock battle width path at CPU $C1:921E advances this compositor column.
BATTLE_CURSOR = 0x0E2A


def _jml(asm: Asm, cpu: int) -> None:
    asm.emit(0x5C, cpu & 0xFF, (cpu >> 8) & 0xFF, cpu >> 16)


def _emit_ordinary_thai_to_stock_guard(asm: Asm) -> None:
    """Keep a nested stock run off the open tail of an active Thai run.

    The ordinary renderer parks the stock cursor immediately after its current
    cell.  That is correct for another Thai glyph, which resumes the private
    pen, but an ``FB`` stock string owns a whole 8-pixel cell and can rename the
    Thai tail's tilemap column.  Move that one transition by a cell only when
    the renderer signature, tile counter and cursor prove that the ``FB``
    follows the same Thai run and its proportional pen is still open.
    """
    memory = renderer_memory(ORDINARY_STATE_BASE)
    asm.long_index(0xAF, memory.initialized)   # LDA long
    asm.emit(0xC9, STATE_SIGNATURE & 0xFF, STATE_SIGNATURE >> 8)
    asm.branch(0xD0, "thai_stock_guard_done")
    asm.emit(0xA5, 0xD0)
    asm.long_index(0xCF, memory.expect)        # CMP long
    asm.branch(0xD0, "thai_stock_guard_done")
    # FB nesting is resolved before the engine performs the prepared stock
    # tilemap write.  At this point $18 still names the renderer's current
    # column; EXPECT_COL is the value only after that write has completed.
    asm.emit(0xA5, 0x18)
    asm.long_index(0xCF, memory.col)           # CMP long
    asm.branch(0xD0, "thai_stock_guard_done")
    asm.long_index(0xAF, memory.pen)
    asm.branch(0xF0, "thai_stock_guard_done")
    asm.emit(0xA5, 0x18, 0x18, 0x69, 0x02, 0x00, 0x85, 0x18)
    asm.label("thai_stock_guard_done")


def _emit_battle_thai_to_stock_guard(asm: Asm) -> None:
    """Advance the dialogue compositor past an active proportional tail."""
    memory = renderer_memory(BATTLE_STATE_BASE)
    asm.long_index(0xAF, memory.initialized)   # LDA long
    asm.emit(0xC9, STATE_SIGNATURE & 0xFF, STATE_SIGNATURE >> 8)
    asm.branch(0xD0, "battle_thai_stock_guard_done")
    asm.emit(0xA5, 0xD0)
    asm.long_index(0xCF, memory.expect)        # CMP long
    asm.branch(0xD0, "battle_thai_stock_guard_done")
    asm.long_index(0xAF, memory.pen)
    asm.branch(0xF0, "battle_thai_stock_guard_done")
    asm.emit(
        0xAD, BATTLE_CURSOR & 0xFF, BATTLE_CURSOR >> 8,
        0x18, 0x69, 0x02, 0x00,
        0x8D, BATTLE_CURSOR & 0xFF, BATTLE_CURSOR >> 8,
    )
    asm.label("battle_thai_stock_guard_done")


def build_ordinary_stock_fb(origin: int, pointer_table_pc: int) -> bytes:
    """Resolve private ``FB xx FE`` operands in the ordinary interpreter."""
    asm = Asm(origin)
    asm.emit(0xA5, 0x00)                       # LDA $00: FB operand
    asm.emit(0xC9, 0x00, 0xFE)
    asm.branch(0x90, "normal")                 # below private range
    asm.emit(0xC9, 0x00, 0xFF)
    asm.branch(0xB0, "normal")
    _emit_ordinary_thai_to_stock_guard(asm)
    asm.emit(0xA5, 0x00)                       # reload after guard scratch work
    asm.emit(0x29, 0xFF, 0x00, 0xAA)           # X = id
    asm.emit(0x0A, 0x85, 0x1A, 0x8A, 0x18, 0x65, 0x1A, 0xAA)  # X = id * 3
    table = pc_to_cpu(pointer_table_pc)
    asm.long_index(0xBF, table)
    asm.emit(0x85, 0x1A)
    asm.long_index(0xBF, table + 1)
    asm.emit(0x85, 0x1B)
    _jml(asm, 0x8183FB)

    asm.label("normal")
    asm.emit(0xA5, 0x00)                       # displaced LDA $00
    asm.branch(0x30, "negative")               # displaced BMI
    asm.emit(0xEB)                             # displaced XBA
    _jml(asm, 0x818DF8)
    asm.label("negative")
    _jml(asm, 0x818E0E)
    return asm.finish()


def build_battle_stock_fb(origin: int, pointer_table_pc: int) -> bytes:
    """Resolve private stock strings in the battle dialogue interpreter."""
    asm = Asm(origin)
    asm.emit(0x85, 0x00)                       # displaced STA $00
    asm.emit(0xC9, 0x00, 0xFE)
    asm.branch(0x90, "normal")
    asm.emit(0xC9, 0x00, 0xFF)
    asm.branch(0xB0, "normal")
    _emit_battle_thai_to_stock_guard(asm)

    # Inline the stock $C1:9746 return-stack operation.  Its RTS contract
    # prevents calling it safely from an expanded-ROM bank.
    asm.emit(0xE2, 0x30)
    asm.emit(0xAD, 0x26, 0x0E)
    asm.emit(0x18, 0x69, 0x03, 0x8D, 0x26, 0x0E, 0xAA)
    asm.emit(0xA5, 0xCD, 0x9D, 0x19, 0x0E)
    asm.emit(0xC2, 0x20)
    asm.emit(0xA5, 0xCB, 0x1A, 0x1A)
    asm.emit(0x9D, 0x17, 0x0E)
    asm.emit(0xC2, 0x30)

    asm.emit(0xA5, 0x00, 0x29, 0xFF, 0x00, 0x85, 0x00)
    asm.emit(0x0A, 0x18, 0x65, 0x00, 0xAA)     # X = id * 3
    table = pc_to_cpu(pointer_table_pc)
    asm.long_index(0xBF, table)
    asm.emit(0x85, 0xCB)
    asm.long_index(0xBF, table + 1)
    asm.emit(0x85, 0xCC)
    _jml(asm, 0x8191E3)

    asm.label("normal")
    asm.emit(0xA5, 0x00)
    asm.branch(0x30, "negative")
    _jml(asm, 0x81938A)
    asm.label("negative")
    _jml(asm, 0x819393)
    return asm.finish()


def hook_jump(target_pc: int) -> bytes:
    cpu = pc_to_cpu(target_pc)
    return bytes((0x5C, cpu & 0xFF, (cpu >> 8) & 0xFF, cpu >> 16, 0xEA))
