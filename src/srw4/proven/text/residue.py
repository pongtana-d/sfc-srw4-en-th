"""Static discovery of catalog text that is still Japanese in a built ROM.

The clean ROM keeps every catalog behind one master table of 24-bit pointers at
``$C9:00D8``.  The ``FB`` handler indexes that table, so the table is the
game's own list of catalog pointer tables and is a complete, evidence-backed
starting point for the ``unknown.discovery`` surface.

Each entry points at a table of 16-bit pointers inside the same bank; the first
pointer marks the start of that table's string pool, which gives the entry
count without guessing.  Some entries are windows into a table that another
entry already owns (an ascending ladder of alternate bases); those are reported
as windows rather than as separate catalogs.

A string counts as translated when the built ROM changed its bytes or when the
owning adapter repointed it.  Everything left untouched is still the original
Japanese and is reported for triage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .japanese import DIRECT, CatalogDecoder


MASTER_TABLE_CPU = (0xC9, 0x00D8)
MASTER_TABLE_ENTRIES = 19
MASTER_TABLE_EXPECTED = bytes.fromhex(
    "888ecc" "ffc1cc" "bde9cc" "000000" "5060d2" "5062d2" "346bd2" "2b77d2"
    "6077cc" "6079cc" "607bcc" "037fd2" "8993d2" "0381d2" "0990d2" "8a8bd2"
    "c382d2" "7c66cb" "6302a2"
)

CONTROL_NAMES = {
    0xF6: "<BR>",
    0xF7: "<F7>",
    0xF8: "<VAL>",
    0xF9: "<F9>",
    0xFA: "<FA>",
    0xFB: "<REF>",
    0xFC: "<FC>",
    0xFD: "<FD>",
    0xFE: "<FE>",
}

# Entry 3 is the null slot; entry 18 addresses bank $A2 graphics data rather
# than a catalog pointer table, so neither is scanned for text.
SKIPPED_ENTRIES = {3: "null-slot", 18: "not-a-catalog-pointer-table"}

MAX_POOL_STRING = 512


def cpu_to_pc(bank: int, address: int) -> int:
    return ((bank & 0x3F) << 16) | address


def lenient_decode(decoder: CatalogDecoder, payload: bytes) -> str:
    """Decode a catalog string, naming controls instead of failing on them."""
    out: list[str] = []
    cursor = 0
    while cursor < len(payload):
        value = payload[cursor]
        cursor += 1
        if 0xF0 <= value <= 0xF5 and cursor < len(payload):
            index = (value - 0xF0) * 0x100 + payload[cursor]
            cursor += 1
            out.append(decoder.kanji.get(index, f"<K{index:04X}>"))
        elif value == 0xFF:
            break
        elif value in CONTROL_NAMES:
            out.append(CONTROL_NAMES[value])
        else:
            out.append(DIRECT.get(value, f"<{value:02X}>"))
    return "".join(out)


def read_string(rom: bytes, bank_pc: int, pointer: int) -> bytes:
    """Read one ``FF``-terminated record, keeping multi-byte operands intact."""
    cursor = bank_pc + pointer
    payload = bytearray()
    while len(payload) < MAX_POOL_STRING:
        value = rom[cursor]
        payload.append(value)
        cursor += 1
        if value == 0xFF:
            return bytes(payload)
        if 0xF0 <= value <= 0xF5:
            payload.append(rom[cursor])
            cursor += 1
        elif value == 0xFB:
            payload.extend(rom[cursor:cursor + 2])
            cursor += 2
    raise ValueError(f"unterminated catalog string at pointer {pointer:#06x}")


@dataclass
class CatalogGroup:
    index: int
    bank: int
    table: int
    entries: int
    pool: int
    window_of: int | None = None
    records: list[dict] = field(default_factory=list)

    @property
    def cpu(self) -> str:
        return f"${self.bank:02X}:{self.table:04X}"


def read_master_table(clean: bytes) -> list[tuple[int, int, int]]:
    """Return ``(index, bank, address)`` for every master-table entry."""
    base = cpu_to_pc(*MASTER_TABLE_CPU)
    raw = clean[base:base + MASTER_TABLE_ENTRIES * 3]
    if raw != MASTER_TABLE_EXPECTED:
        raise ValueError("master catalog table does not match the clean ROM")
    entries: list[tuple[int, int, int]] = []
    for index in range(MASTER_TABLE_ENTRIES):
        low, high, bank = raw[index * 3:index * 3 + 3]
        entries.append((index, bank, low | (high << 8)))
    return entries


def _group_bounds(clean: bytes, bank: int, table: int) -> tuple[int, int]:
    base = cpu_to_pc(bank, table)
    pool = clean[base] | (clean[base + 1] << 8)
    if pool <= table:
        raise ValueError(f"catalog table ${bank:02X}:{table:04X} has no ascending pool")
    return (pool - table) // 2, pool


def scan_catalogs(clean: bytes, built: bytes, kanji_path: Path) -> dict:
    """Compare every catalog record in the master table against the build."""
    decoder = CatalogDecoder(kanji_path)
    groups: list[CatalogGroup] = []
    skipped: list[dict] = []

    for index, bank, table in read_master_table(clean):
        if index in SKIPPED_ENTRIES:
            skipped.append(
                {
                    "index": index,
                    "cpu": f"${bank:02X}:{table:04X}",
                    "reason": SKIPPED_ENTRIES[index],
                }
            )
            continue
        entries, pool = _group_bounds(clean, bank, table)
        groups.append(CatalogGroup(index, bank, table, entries, pool))

    # An entry whose table starts inside an earlier table of the same bank is a
    # shifted base into that table, not a catalog of its own.
    owners = {(group.bank, group.table): group for group in groups}
    for group in groups:
        for other in groups:
            if other is group or other.bank != group.bank:
                continue
            span = other.table + other.entries * 2
            if other.table < group.table < span:
                group.window_of = other.index
                break
    del owners

    report_groups: list[dict] = []
    master_pc = cpu_to_pc(*MASTER_TABLE_CPU)
    for group in groups:
        entry_pc = master_pc + group.index * 3
        moved = built[entry_pc:entry_pc + 3]
        if moved != clean[entry_pc:entry_pc + 3]:
            # The adapter rebuilt this catalog somewhere else; the clean-ROM
            # copy it left behind is no longer reachable.
            report_groups.append(
                {
                    "index": group.index,
                    "cpu": group.cpu,
                    "relocated_to": f"${moved[2]:02X}:{(moved[1] << 8) | moved[0]:04X}",
                    "entries": group.entries,
                    "untouched": 0,
                }
            )
            continue
        if group.window_of is not None:
            report_groups.append(
                {
                    "index": group.index,
                    "cpu": group.cpu,
                    "window_of": group.window_of,
                    "entries": group.entries,
                }
            )
            continue

        bank_pc = cpu_to_pc(group.bank, 0)
        seen: set[int] = set()
        untouched: list[dict] = []
        translated = 0
        for slot in range(group.entries):
            offset = cpu_to_pc(group.bank, group.table) + slot * 2
            pointer = clean[offset] | (clean[offset + 1] << 8)
            if pointer in seen:
                continue
            seen.add(pointer)
            try:
                payload = read_string(clean, bank_pc, pointer)
            except ValueError:
                continue
            start = bank_pc + pointer
            built_pointer = built[offset] | (built[offset + 1] << 8)
            same_bytes = clean[start:start + len(payload)] == built[start:start + len(payload)]
            if built_pointer != pointer or not same_bytes:
                translated += 1
                continue
            untouched.append(
                {
                    "slot": slot,
                    "pointer": f"${group.bank:02X}:{pointer:04X}",
                    "pc": f"0x{start:06X}",
                    "bytes": len(payload),
                    "text": lenient_decode(decoder, payload),
                }
            )
        report_groups.append(
            {
                "index": group.index,
                "cpu": group.cpu,
                "pool": f"${group.bank:02X}:{group.pool:04X}",
                "entries": group.entries,
                "unique_records": len(untouched) + translated,
                "translated": translated,
                "untouched": len(untouched),
                "records": untouched,
            }
        )

    total_untouched = sum(item.get("untouched", 0) for item in report_groups)
    return {
        "master_table": f"${MASTER_TABLE_CPU[0]:02X}:{MASTER_TABLE_CPU[1]:04X}",
        "master_entries": MASTER_TABLE_ENTRIES,
        "skipped": skipped,
        "groups": report_groups,
        "total_untouched_records": total_untouched,
    }


def write_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
