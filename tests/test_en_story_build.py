"""EN battle dispatch records must repoint their quote pointers."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_story_build import (  # noqa: E402
    _dispatch_records,
    _merge_ranges,
    _relocated_dispatch_target,
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


def test_quote_fields_relocates_english_eight_way_branch_table():
    record = bytes.fromhex(
        "FC 01 AB 43 FC 08 "
        "10 70 20 70 30 70 40 70 50 70 60 70 70 70 80 70"
    )
    assert quote_fields(record) == (6, 8, 10, 12, 14, 16, 18, 20)


def test_quote_fields_relocates_japanese_eight_way_branch_table():
    record = bytes.fromhex(
        "FC 01 FC 08 "
        "10 50 20 50 30 50 40 50 50 50 60 50 70 50 80 50"
    )
    assert quote_fields(record) == (4, 6, 8, 10, 12, 14, 16, 18)


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


def test_dispatch_records_aligns_eight_way_branch_pointers():
    english = bytes.fromhex(
        "FC 01 AB 43 FC 08 "
        "10 70 20 70 30 70 40 70 50 70 60 70 70 70 80 70"
    )
    japanese = bytes.fromhex(
        "FC 01 FC 08 "
        "10 50 20 50 30 50 40 50 50 50 60 50 70 50 80 50"
    )
    assert _dispatch_records(english, bytes.fromhex("FC 01 AB 43")) == [[
        (6, 0x7010), (8, 0x7020), (10, 0x7030), (12, 0x7040),
        (14, 0x7050), (16, 0x7060), (18, 0x7070), (20, 0x7080),
    ]]
    assert _dispatch_records(japanese, bytes.fromhex("FC 01")) == [[
        (4, 0x5010), (6, 0x5020), (8, 0x5030), (10, 0x5040),
        (12, 0x5050), (14, 0x5060), (16, 0x5070), (18, 0x5080),
    ]]


def test_dispatch_records_walks_nested_fa_selector_from_fc08_branch():
    english = bytes.fromhex(
        "FC 01 AB 43 FC 08 "
        "16 42 16 42 16 42 16 42 16 42 16 42 16 42 16 42 "
        "FA 02 10 70 20 70"
    )
    japanese = bytes.fromhex(
        "FC 01 FC 08 "
        "14 50 14 50 14 50 14 50 14 50 14 50 14 50 14 50 "
        "FA 02 10 60 20 60"
    )
    assert _dispatch_records(
        english,
        bytes.fromhex("FC 01 AB 43"),
        dispatch_start=0x4200,
    ) == [[
        (6, 0x4216), (8, 0x4216), (10, 0x4216), (12, 0x4216),
        (14, 0x4216), (16, 0x4216), (18, 0x4216), (20, 0x4216),
        (24, 0x7010), (26, 0x7020),
    ]]
    assert _dispatch_records(
        japanese,
        bytes.fromhex("FC 01"),
        dispatch_start=0x5000,
    ) == [[
        (4, 0x5014), (6, 0x5014), (8, 0x5014), (10, 0x5014),
        (12, 0x5014), (14, 0x5014), (16, 0x5014), (18, 0x5014),
        (22, 0x6010), (24, 0x6020),
    ]]


def test_dispatch_target_rebases_nested_dispatch_before_text_mapping():
    assert _relocated_dispatch_target(
        0x4280,
        source_dispatch_start=0x4200,
        source_dispatch_end=0x4800,
        destination_dispatch_start=0x5200,
        source_by_target={},
        starts={},
    ) == 0x5280


def test_dispatch_target_maps_external_quote_to_translated_record_start():
    assert _relocated_dispatch_target(
        0x75BB,
        source_dispatch_start=0x4200,
        source_dispatch_end=0x4800,
        destination_dispatch_start=0x5200,
        source_by_target={0x75BB: 0x76BF},
        starts={0x76BF: 0x75A9},
    ) == 0x75A9


def test_character_archive_route_ranges_merge_only_when_contiguous():
    assert _merge_ranges([(0x1200, 0x1300), (0x1100, 0x1200), (0x1400, 0x1500)]) == [
        (0x1100, 0x1300),
        (0x1400, 0x1500),
    ]
