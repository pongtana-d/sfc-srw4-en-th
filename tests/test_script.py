"""P6 tests: finding the story blocks, and moving them without breaking them."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from srw4.rom import Rom, RomError  # noqa: E402
from srw4.script import (  # noqa: E402
    BANK_SIZE,
    ENTRY_BYTES,
    MASTER_SLOTS,
    MASTER_TABLE_PC,
    Block,
    Move,
    cpu_to_pc,
    load_blocks,
    load_summary,
    pc_to_cpu,
    plan_mirror,
    read_master_table,
    read_pointers,
)

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
SOURCE = ROOT / "data" / "translations" / "script.source.json"


@pytest.fixture(scope="module")
def rom() -> bytes:
    return Rom.load_clean(CLEAN_ROM).to_bytes()


@pytest.fixture(scope="module")
def blocks(rom) -> list[Block]:
    return load_blocks(rom, load_summary(SOURCE))


# --- reading the tables -----------------------------------------------------


def test_the_master_table_holds_one_entry_per_slot(rom):
    assert len(read_master_table(rom)) == MASTER_SLOTS


def test_every_block_matches_the_master_table(blocks):
    # load_blocks raises if they disagree, so reaching here is the assertion.
    assert len(blocks) == 47


def test_unused_slots_are_empty(rom):
    table = read_master_table(rom)
    used = {block.slot for block in load_blocks(rom, load_summary(SOURCE))}
    for slot, (bank, address) in enumerate(table):
        if slot not in used:
            assert (bank, address) == (0, 0), f"slot {slot} looks used after all"


def test_the_master_table_sits_just_before_the_first_block(rom, blocks):
    first = min(blocks, key=lambda block: block.pc)
    assert first.pc == MASTER_TABLE_PC + MASTER_SLOTS * ENTRY_BYTES


def test_a_block_starts_with_its_own_pointer_table(rom, blocks):
    for block in blocks:
        assert block.size >= block.table_bytes


def test_block_pointers_are_absolute_inside_their_bank(rom, blocks):
    for block in blocks:
        for pointer in read_pointers(rom, block):
            if pointer == 0:
                continue
            assert block.start <= pointer <= block.end, (
                f"block {block.slot}: {pointer:#06x} is outside "
                f"{block.start:#06x}-{block.end:#06x}"
            )


def test_addresses_convert_both_ways():
    assert cpu_to_pc(0xE8, 0x009C) == 0x28009C
    assert pc_to_cpu(0x28009C) == (0xE8, 0x009C)


# --- planning a move --------------------------------------------------------


def test_a_mirror_keeps_every_offset_where_it_was(blocks):
    for move in plan_mirror(blocks, first_bank=0xF0):
        assert move.shift == 0
        assert move.to_start == move.block.start


def test_a_mirror_maps_each_source_bank_to_one_destination(blocks):
    moves = plan_mirror(blocks, first_bank=0xF0)
    mapping = {move.block.bank: move.to_bank for move in moves}
    assert len(set(mapping.values())) == len(mapping)
    assert sorted(mapping.values()) == list(range(0xF0, 0xF0 + len(mapping)))


def test_a_mirror_that_would_run_past_the_last_bank_is_refused(blocks):
    with pytest.raises(RomError, match="too high"):
        plan_mirror(blocks, first_bank=0xFE)


# --- rebasing pointers ------------------------------------------------------


def make_move(shift: int) -> Move:
    block = Block(slot=0, bank=0xE8, start=0x1000, end=0x2000, pointers=4)
    return Move(block, to_bank=0xF0, to_start=0x1000 + shift)


def test_a_pointer_inside_the_block_moves_with_it():
    assert make_move(0x500).rebase(0x1234) == 0x1734


def test_the_address_one_past_the_block_is_a_legal_target():
    # Ranges in this project are quoted one byte past the text, and empty
    # table slots point there.
    assert make_move(0x500).rebase(0x2000) == 0x2500


def test_a_pointer_outside_the_block_is_reported_not_moved():
    assert make_move(0x500).rebase(0x0FFF) is None
    assert make_move(0x500).rebase(0x2001) is None


def test_a_move_that_would_leave_the_bank_is_refused():
    with pytest.raises(RomError, match="leaves the bank"):
        make_move(0xF000).rebase(0x1234)


# --- moving for real --------------------------------------------------------


def test_mirroring_copies_whole_banks_and_repoints_the_table():
    from build import build as build_rom  # tools/build.py

    plain, plain_report = build_rom("none")
    moved, moved_report = build_rom("mirror")

    # Only the master table's bank bytes and the checksum may differ below 3 MB.
    changed = {int(address, 16) for address in moved_report["stock_bytes_changed"]}
    banks = {
        MASTER_TABLE_PC + entry["slot"] * ENTRY_BYTES + 2
        for entry in moved_report["script"]["blocks"]
    }
    assert banks <= changed
    assert len(changed - banks) == 4      # the checksum and its complement

    # And the moved banks must hold an exact copy of the originals.
    for source_bank, destination in moved_report["script"]["whole_banks"].items():
        start = cpu_to_pc(int(source_bank[1:], 16), 0)
        to = cpu_to_pc(int(destination[1:], 16), 0)
        assert moved[to : to + BANK_SIZE] == plain[start : start + BANK_SIZE]


def test_relocation_is_reproducible():
    from build import build as build_rom

    assert build_rom("mirror")[0] == build_rom("mirror")[0]
