"""The nineteen catalogs, measured from the ROM rather than remembered."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.catalog import load, read_slots, record_at  # noqa: E402

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"


@pytest.fixture(scope="module")
def rom() -> bytes:
    return CLEAN_ROM.read_bytes()


@pytest.fixture(scope="module")
def catalogs(rom):
    return load(rom)


def test_every_entry_that_is_a_table_is_found(catalogs):
    # Entry 3 is null and entry 18 points at graphics; the other seventeen are
    # string tables.
    assert [entry.index for entry in catalogs] == [
        0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17
    ]


def test_the_windows_are_recognised_as_views_of_another_table(catalogs):
    view = {e.index: (e.window_of, e.from_slot) for e in catalogs if e.window_of is not None}
    assert view == {5: (4, 256), 9: (8, 256), 10: (8, 512), 16: (13, 224)}


def test_a_window_covers_what_is_left_of_its_parent(catalogs):
    by_index = {entry.index: entry for entry in catalogs}
    for entry in catalogs:
        if entry.window_of is None:
            continue
        parent = by_index[entry.window_of]
        assert entry.slots == parent.slots - entry.from_slot
        assert entry.first_record == parent.first_record


def test_slot_counts_come_from_each_table_s_own_first_pointer(rom, catalogs):
    for entry in catalogs:
        if entry.window_of is not None:
            continue
        assert entry.address + entry.slots * 2 == entry.first_record


def test_a_slot_that_looks_empty_names_a_lone_terminator(rom, catalogs):
    """Not spare room -- putting a record there makes an empty field draw text."""
    blank = 0
    for entry in catalogs:
        for pointer in read_slots(rom, entry):
            if pointer and pointer >= entry.first_record:
                if record_at(rom, entry.bank, pointer) == b"\xff":
                    blank += 1
    assert blank > 0


def test_the_top_of_a_pool_is_where_the_next_table_starts(rom, catalogs):
    """A slot naming that address is not a record -- it is one past the end.

    Searching for a terminator would not tell you: the table that begins
    there holds `$C1FF` as a pointer, and its low byte reads as one.
    """
    by_index = {entry.index: entry for entry in catalogs}
    weapons, screens = by_index[8], by_index[0]
    assert weapons.bank == screens.bank == 0xCC
    highest = max(p for p in read_slots(rom, weapons) if p >= weapons.first_record)
    assert highest == screens.address
