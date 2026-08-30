"""Compile one catalog's variable-length records into a single-bank pool.

The stock catalog reader fetches a 16-bit offset from its descriptor's pointer
table and keeps the descriptor bank.  A migrated catalog must therefore keep
its table and every record in one bank, and must supply every slot—including
empty and duplicate ones.  This module enforces that mechanical contract
before a ROM write is considered.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contract import TERMINATORS
from .rom import RomError


@dataclass(frozen=True)
class CatalogRecord:
    """One compiled stream, shared by every slot listed in ``slots``."""

    source: str
    slots: tuple[int, ...]
    stream: bytes


@dataclass(frozen=True)
class CatalogPool:
    """A complete pointer table followed by its variable-length records."""

    bank: int
    address: int
    slots: int
    payload: bytes
    slot_pointers: tuple[int, ...]
    records: tuple[tuple[str, int, int], ...]

    @property
    def end_address(self) -> int:
        return self.address + len(self.payload)


def compile_pool(*, bank: int, address: int, slots: int, records: list[CatalogRecord]) -> CatalogPool:
    """Make a complete variable-length catalog without crossing a bank.

    ``address`` is the CPU address of the pointer table.  Every record must
    include its engine terminator.  The function intentionally refuses missing
    slots: preserving them from the stock table would create a mixed catalog
    after its descriptor is repointed.
    """
    if not 0 <= bank <= 0xFF:
        raise RomError(f"catalog bank out of range: {bank:#x}")
    if not 0 <= address <= 0xFFFF:
        raise RomError(f"catalog address out of range: {address:#x}")
    if slots <= 0:
        raise RomError(f"catalog slot count must be positive, got {slots}")

    table_bytes = slots * 2
    if address + table_bytes > 0x10000:
        raise RomError("catalog pointer table crosses its bank")

    pointers: list[int | None] = [None] * slots
    payload = bytearray(table_bytes)
    report: list[tuple[str, int, int]] = []
    for record in records:
        if not record.slots:
            raise RomError(f"catalog record {record.source!r} has no slots")
        if not record.stream or record.stream[-1] not in TERMINATORS:
            raise RomError(f"catalog record {record.source!r} has no engine terminator")
        pointer = address + len(payload)
        if pointer > 0xFFFF or pointer + len(record.stream) > 0x10000:
            raise RomError(f"catalog record {record.source!r} crosses bank ${bank:02X}")
        for slot in record.slots:
            if not 0 <= slot < slots:
                raise RomError(f"catalog record {record.source!r} uses slot {slot}, outside 0..{slots - 1}")
            if pointers[slot] is not None:
                raise RomError(f"catalog slot {slot} is assigned more than once")
            pointers[slot] = pointer
        payload.extend(record.stream)
        report.append((record.source, pointer, len(record.stream)))

    missing = [slot for slot, pointer in enumerate(pointers) if pointer is None]
    if missing:
        preview = ", ".join(map(str, missing[:8]))
        suffix = "..." if len(missing) > 8 else ""
        raise RomError(f"catalog has {len(missing)} unassigned slot(s): {preview}{suffix}")

    for slot, pointer in enumerate(pointers):
        assert pointer is not None
        payload[slot * 2:slot * 2 + 2] = pointer.to_bytes(2, "little")
    return CatalogPool(bank, address, slots, bytes(payload), tuple(pointers), tuple(report))
