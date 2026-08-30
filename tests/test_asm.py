"""Tests for the 65816 assembler: encodings, sizing, and the errors it raises."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.asm65816 import AsmError, assemble  # noqa: E402


def code(source: str, origin: int = 0x008000, **constants) -> bytes:
    return assemble(source, origin, constants or None).code


# --- encodings --------------------------------------------------------------


def test_implied_instructions():
    assert code("clc\nsec\nxce\nrtl\nrts\nnop") == bytes([0x18, 0x38, 0xFB, 0x6B, 0x60, 0xEA])


def test_the_accumulator_is_the_default_operand_for_shifts():
    assert code("asl\nlsr a\nrol a\nror") == bytes([0x0A, 0x4A, 0x2A, 0x6A])


def test_addressing_modes_pick_their_own_opcodes():
    assert code(".a16\nlda #$1234") == bytes([0xA9, 0x34, 0x12])
    assert code("lda $12") == bytes([0xA5, 0x12])
    assert code("lda $1234") == bytes([0xAD, 0x34, 0x12])
    assert code("lda $7E1234") == bytes([0xAF, 0x34, 0x12, 0x7E])
    assert code("lda $1234,x") == bytes([0xBD, 0x34, 0x12])
    assert code("lda $7E1234,x") == bytes([0xBF, 0x34, 0x12, 0x7E])
    assert code("lda ($12),y") == bytes([0xB1, 0x12])
    assert code("lda [$12],y") == bytes([0xB7, 0x12])
    assert code("lda ($12,x)") == bytes([0xA1, 0x12])
    assert code("lda $12,s") == bytes([0xA3, 0x12])


def test_test_and_reset_bits_supports_the_displaced_menu_instruction():
    assert code("trb $12\ntrb $1234\ntsb $12\ntsb $1234") == bytes(
        [0x14, 0x12, 0x1C, 0x34, 0x12, 0x04, 0x12, 0x0C, 0x34, 0x12]
    )


def test_an_explicit_width_overrides_the_value():
    assert code("lda.w $12") == bytes([0xAD, 0x12, 0x00])
    assert code("lda.l $12") == bytes([0xAF, 0x12, 0x00, 0x00])


def test_block_moves_take_their_banks_the_right_way_round():
    # The opcode carries the destination bank first.
    assert code("mvn $7E,$7F") == bytes([0x54, 0x7F, 0x7E])


# --- register widths --------------------------------------------------------


def test_an_immediate_follows_the_declared_accumulator_width():
    assert code(".a8\nlda #$12") == bytes([0xA9, 0x12])
    assert code(".a16\nlda #$12") == bytes([0xA9, 0x12, 0x00])


def test_index_and_accumulator_widths_are_tracked_apart():
    assert code(".a8\n.i16\nlda #$12\nldx #$12") == bytes([0xA9, 0x12, 0xA2, 0x12, 0x00])


def test_sep_and_rep_are_followed_so_the_source_need_not_repeat_itself():
    assert code("rep #$30\nlda #$1234\nsep #$20\nlda #$12") == bytes(
        [0xC2, 0x30, 0xA9, 0x34, 0x12, 0xE2, 0x20, 0xA9, 0x12]
    )


def test_an_immediate_with_no_declared_width_is_refused():
    with pytest.raises(AsmError, match="width"):
        code("lda #$12")


# --- labels -----------------------------------------------------------------


def test_a_backward_branch_reaches_its_label():
    assert code("here:\nnop\nbra here") == bytes([0xEA, 0x80, 0xFD])


def test_a_forward_reference_settles_to_the_short_form():
    assert code("bra ahead\nnop\nahead:\nnop") == bytes([0x80, 0x01, 0xEA, 0xEA])


def test_a_same_bank_label_loses_its_bank_where_there_is_no_long_form():
    assembled = assemble("jsr target\ntarget:\nrts", 0x018000)
    assert assembled.code == bytes([0x20, 0x03, 0x80, 0x60])


def test_a_branch_too_far_is_an_error_not_a_wrap():
    with pytest.raises(AsmError, match="out of range"):
        code("bra ahead\n.res 200\nahead:\nnop")


def test_a_label_defined_twice_is_refused():
    with pytest.raises(AsmError, match="twice"):
        code("here:\nnop\nhere:\nnop")


def test_build_constants_can_be_used_as_symbols():
    assert code("lda CANVAS,x", CANVAS=0xC5C0) == bytes([0xBD, 0xC0, 0xC5])


def test_a_constant_cannot_be_redefined_by_the_source():
    with pytest.raises(AsmError, match="already a constant"):
        code("CANVAS:\nnop", CANVAS=0xC5C0)


# --- directives and errors --------------------------------------------------


def test_data_directives_emit_little_endian():
    assert code(".db $12,$34\n.dw $1234\n.dl $123456") == bytes(
        [0x12, 0x34, 0x34, 0x12, 0x56, 0x34, 0x12]
    )


def test_org_sets_where_the_block_starts():
    assembled = assemble(".org $018000\nhere:\nnop", 0x000000)
    assert assembled.labels["here"] == 0x018000


def test_an_unknown_instruction_names_the_line():
    with pytest.raises(AsmError, match="line 2"):
        code("nop\nfoo $1234")


def test_an_unknown_symbol_is_refused():
    with pytest.raises(AsmError, match="unknown symbol"):
        code("lda missing")


def test_an_addressing_mode_the_instruction_lacks_is_refused():
    with pytest.raises(AsmError, match="addressing mode"):
        code("stx $1234,x")
