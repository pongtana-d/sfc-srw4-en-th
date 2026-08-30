"""Variable-length catalog pool contracts."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.catalog_pool import CatalogRecord, compile_pool  # noqa: E402
from srw4.rom import RomError  # noqa: E402


def test_pool_keeps_duplicate_slots_on_one_variable_length_record():
    pool = compile_pool(
        bank=0xFA,
        address=0x8000,
        slots=3,
        records=[
            CatalogRecord("blank", (0, 2), b"\xff"),
            CatalogRecord("long", (1,), b"\x10\x11\x12\xff"),
        ],
    )
    assert pool.slot_pointers == (0x8006, 0x8007, 0x8006)
    assert pool.payload[:6] == bytes((0x06, 0x80, 0x07, 0x80, 0x06, 0x80))
    assert pool.payload[6:] == b"\xff\x10\x11\x12\xff"
    assert pool.records == (("blank", 0x8006, 1), ("long", 0x8007, 4))


@pytest.mark.parametrize(
    "records, message",
    [
        ([CatalogRecord("only", (0,), b"\xff")], "unassigned"),
        ([CatalogRecord("one", (0,), b"\xff"), CatalogRecord("two", (0, 1), b"\xff")], "more than once"),
        ([CatalogRecord("unterminated", (0, 1), b"\x10")], "terminator"),
    ],
)
def test_pool_rejects_incomplete_or_ambiguous_slot_maps(records, message):
    with pytest.raises(RomError, match=message):
        compile_pool(bank=0xFA, address=0x8000, slots=2, records=records)


def test_pool_refuses_a_record_that_would_cross_its_bank():
    with pytest.raises(RomError, match="crosses bank"):
        compile_pool(
            bank=0xFA,
            address=0xFFFC,
            slots=1,
            records=[CatalogRecord("too-long", (0,), b"\x10\x11\xff")],
        )
