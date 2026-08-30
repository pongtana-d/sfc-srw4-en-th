"""EN battle dispatch records must repoint their quote pointers."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_story_build import quote_fields, replace_en_quote_separators  # noqa: E402


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
    assert replace_en_quote_separators(record, bytes.fromhex("C1 03")) == 1
    assert record == bytearray.fromhex("FC 01 C1 03 FA 02 34 12 78 56 FF")
