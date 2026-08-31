"""EN battle dispatch records must repoint their quote pointers."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_story_build import (  # noqa: E402
    _dispatch_records,
    _merge_ranges,
    quote_fields,
    replace_en_quote_separators,
)
from srw4.en_dialogue_font import BATTLE_QUOTE_PADDING  # noqa: E402


def test_quote_fields_accepts_english_battle_dispatch_header():
    # EN records add `$AB $43` before the shared `$FA` quote selector.
    record = bytes.fromhex("FC 01 AB 43 FA 02 34 12 78 56 FF")
    assert quote_fields(record) == (6, 8)


def test_quote_fields_keeps_the_japanese_header_for_reference_data():
    record = bytes.fromhex("FC 01 FA 02 34 12 78 56 FF")
    assert quote_fields(record) == (4, 6)


def test_quote_fields_relocates_english_direct_quote_pointer():
    record = bytes.fromhex("FC 01 AB 43 FC 07 79 7B")
    assert quote_fields(record) == (6,)


def test_quote_fields_relocates_japanese_direct_quote_pointer():
    record = bytes.fromhex("FC 01 FC 07 87 7A")
    assert quote_fields(record) == (4,)


def test_english_quote_separator_becomes_zero_advance_thai_padding_in_place():
    record = bytearray.fromhex("FC 01 AB 43 FA 02 34 12 78 56 FF")
    assert replace_en_quote_separators(record) == 1
    assert record == bytearray(
        b"\xFC\x01" + BATTLE_QUOTE_PADDING
        + bytes.fromhex("FA 02 34 12 78 56 FF")
    )


def test_dispatch_records_aligns_table_and_direct_quote_pointers():
    english = bytes.fromhex(
        "FC 01 AB 43 FA 02 34 12 78 56 "
        "FC 01 AB 43 FC 07 CE 7E"
    )
    japanese = bytes.fromhex(
        "FC 01 FA 02 80 51 88 51 "
        "FC 01 FC 07 8C 56"
    )
    assert _dispatch_records(english, bytes.fromhex("FC 01 AB 43")) == [
        [(6, 0x1234), (8, 0x5678)],
        [(16, 0x7ECE)],
    ]
    assert _dispatch_records(japanese, bytes.fromhex("FC 01")) == [
        [(4, 0x5180), (6, 0x5188)],
        [(12, 0x568C)],
    ]


def test_character_archive_route_ranges_merge_only_when_contiguous():
    assert _merge_ranges([(0x1200, 0x1300), (0x1100, 0x1200), (0x1400, 0x1500)]) == [
        (0x1100, 0x1300),
        (0x1400, 0x1500),
    ]
