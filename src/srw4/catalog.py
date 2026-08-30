"""The catalog side of the game's text: nineteen tables, read from the ROM.

Almost everything outside the story script is reached the same way. A master
table of nineteen 24-bit pointers at `$C9:00D8` names a table of 16-bit
pointers; each of those names a record in the same bank, terminated by `$FF`
(sometimes `$F7`).

How many slots a table has is not written down anywhere, but it does not have
to be guessed: the first pointer is where the records start, so

    slots = (first pointer - the table's own address) / 2

Three things about these tables have cost time before and are checked here
rather than remembered:

  * one table can have several descriptors. Entries 5, 9, 10 and 16 are not
    tables of their own -- they are windows onto entries 4, 8 and 13 starting
    at slot 256 or 512. Repointing the first and forgetting the window leaves
    a screen in Japanese while the report says the catalog moved.
  * several slots often name one record, so a record has to be found from any
    slot that names it, not the first.
  * a slot that looks empty is not spare room. It points at a lone `$FF`, and
    putting a record there makes an empty field start drawing text.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contract import TERMINATORS
from .rom import RomError
from .script import cpu_to_pc

MASTER_TABLE = 0x0900D8        # $C9:00D8
MASTER_SLOTS = 19
ENTRY_BYTES = 3


@dataclass(frozen=True)
class Descriptor:
    """One of the nineteen entries: where a pointer table lives, and how big."""

    index: int
    bank: int
    address: int
    slots: int
    first_record: int          # the offset the records start at
    window_of: int | None = None   # the entry this one is a view of
    from_slot: int = 0             # where in that entry the view starts

    @property
    def pc(self) -> int:
        return cpu_to_pc(self.bank, self.address)

    @property
    def is_null(self) -> bool:
        return self.bank == 0 and self.address == 0


def read_master(rom: bytes) -> list[tuple[int, int]]:
    """The nineteen entries as (bank, address). A null slot reads as (0, 0)."""
    out = []
    for index in range(MASTER_SLOTS):
        at = MASTER_TABLE + index * ENTRY_BYTES
        out.append((rom[at + 2], rom[at] | rom[at + 1] << 8))
    return out


def describe(rom: bytes, index: int, bank: int, address: int) -> Descriptor:
    """Measure a pointer table from its own first entry."""
    at = cpu_to_pc(bank, address)
    first = rom[at] | rom[at + 1] << 8
    if first <= address:
        raise RomError(
            f"catalog {index}: the first pointer ${first:04X} is not past the "
            f"table at ${bank:02X}:{address:04X}"
        )
    span = first - address
    if span % 2:
        raise RomError(f"catalog {index}: the table is {span} bytes, not a whole number of slots")
    return Descriptor(index, bank, address, span // 2, first)


def load(rom: bytes) -> list[Descriptor]:
    """Every catalog the master table names, with windows resolved.

    A window's address lands inside another entry's pointer table, so its own
    first pointer says nothing about how many slots it has -- that comes from
    the parent. Measuring the real tables first and then placing the rest
    inside them is what tells the two apart, without a list to maintain.
    """
    master = read_master(rom)
    real: list[Descriptor] = []
    for index, (bank, address) in enumerate(master):
        if bank == 0 and address == 0:
            continue
        try:
            real.append(describe(rom, index, bank, address))
        except RomError:
            continue                        # a window, or entry 18's graphics

    inside = {entry.index: entry for entry in real}
    found: list[Descriptor] = []
    for index, (bank, address) in enumerate(master):
        if bank == 0 and address == 0:
            continue
        if index in inside:
            entry = inside[index]
            parent = next(
                (
                    other
                    for other in real
                    if other.index != index
                    and other.bank == bank
                    and other.address < address < other.first_record
                ),
                None,
            )
            if parent is None:
                found.append(entry)
                continue
        else:
            parent = next(
                (
                    other
                    for other in real
                    if other.bank == bank and other.address < address < other.first_record
                ),
                None,
            )
            if parent is None:
                continue                    # entry 18: not a string table at all
        offset = address - parent.address
        found.append(
            Descriptor(
                index,
                bank,
                address,
                parent.slots - offset // 2,
                parent.first_record,
                window_of=parent.index,
                from_slot=offset // 2,
            )
        )
    return sorted(found, key=lambda entry: entry.index)


def read_slots(rom: bytes, entry: Descriptor) -> list[int]:
    return [
        rom[entry.pc + slot * 2] | rom[entry.pc + slot * 2 + 1] << 8
        for slot in range(entry.slots)
    ]


def record_at(rom: bytes, bank: int, address: int, limit: int = 512) -> bytes | None:
    """The bytes of one record, terminator included, or None if there is none.

    A pointer past the end of a pool is not a record: it is a slot the game
    never follows, and the bytes there belong to whatever comes next.
    """
    at = cpu_to_pc(bank, address)
    for length in range(limit):
        if rom[at + length] in TERMINATORS:
            return rom[at : at + length + 1]
    return None
