"""Read the English story corpus without relying on JP byte offsets.

The JP summary supplies only stable structure: master-slot meaning, pointer
count, and battle-dispatch size.  Every EN address, record byte and interval
is read from the locked English ROM.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from .rom import RomError
from .script import BANK_SIZE, MASTER_SLOTS, cpu_to_pc, read_master_table


def _rows_by_slot(summary: Iterable[dict]) -> dict[int, dict]:
    rows = list(summary)
    if len(rows) != MASTER_SLOTS:
        raise RomError(f"story summary has {len(rows)} slots, expected {MASTER_SLOTS}")
    by_slot = {int(row["slot"]): row for row in rows}
    if set(by_slot) != set(range(MASTER_SLOTS)):
        raise RomError("story summary slots are not exactly 0..51")
    return by_slot


def _intervals(rom: bytes, by_slot: dict[int, dict]) -> dict[int, tuple[int, int, int]]:
    """Return ``slot -> (bank, start, end)`` bounded by EN peer entries."""
    master = read_master_table(rom)
    grouped: dict[int, list[tuple[int, int]]] = {}
    for slot, (bank, start) in enumerate(master):
        unused = by_slot[slot].get("kind") == "unused"
        if unused:
            if (bank, start) != (0, 0):
                raise RomError(f"EN story slot {slot}: unused slot is not null")
            continue
        if (bank, start) == (0, 0):
            raise RomError(f"EN story slot {slot}: used slot is null")
        grouped.setdefault(bank, []).append((start, slot))

    spans: dict[int, tuple[int, int, int]] = {}
    for bank, entries in grouped.items():
        entries.sort()
        starts = [start for start, _ in entries]
        if len(starts) != len(set(starts)):
            raise RomError(f"EN story bank ${bank:02X} has duplicate master starts")
        for index, (start, slot) in enumerate(entries):
            end = entries[index + 1][0] if index + 1 < len(entries) else BANK_SIZE
            if start >= end:
                raise RomError(f"EN story slot {slot}: invalid interval ${bank:02X}:{start:04X}-${end:04X}")
            spans[slot] = (bank, start, end)
    return spans


def extract_story(rom: bytes, summary: Iterable[dict]) -> dict[str, object]:
    """Extract every EN story pointer and unique record into JSON-ready data."""
    by_slot = _rows_by_slot(summary)
    source_summary_records = sum(int(row.get("messages", 0)) for row in by_slot.values())
    spans = _intervals(rom, by_slot)
    blocks: list[dict[str, object]] = []
    occurrences: list[dict[str, object]] = []
    records: dict[str, dict[str, object]] = {}
    null_slots = 0

    for slot in range(MASTER_SLOTS):
        row = by_slot[slot]
        if row.get("kind") == "unused":
            continue
        bank, start, end = spans[slot]
        pointer_count = int(row["pointers"])
        table_end = start + pointer_count * 2
        dispatch_bytes = int(row.get("record_bytes", 0))
        dispatch_end = table_end + dispatch_bytes
        if dispatch_end > end:
            raise RomError(f"EN story slot {slot}: table/dispatch exceeds its interval")

        blocks.append(
            {
                "slot": slot,
                "kind": row["kind"],
                "bank": f"${bank:02X}",
                "table_address": f"${start:04X}",
                "interval_end": f"${end:04X}",
                "pc": f"0x{cpu_to_pc(bank, start):06X}",
                "pointer_slots": pointer_count,
                "pointer_table_bytes": pointer_count * 2,
                "dispatch_bytes": dispatch_bytes,
                "dispatch_sha256": hashlib.sha256(
                    rom[cpu_to_pc(bank, table_end) : cpu_to_pc(bank, dispatch_end)]
                ).hexdigest(),
            }
        )

        base = cpu_to_pc(bank, start)
        for index in range(pointer_count):
            address = rom[base + index * 2] | rom[base + index * 2 + 1] << 8
            occurrence: dict[str, object] = {
                "slot": slot,
                "pointer_index": index,
                "address": f"${address:04X}",
            }
            if address == 0:
                occurrence["record"] = None
                null_slots += 1
                occurrences.append(occurrence)
                continue
            if not start <= address < end:
                raise RomError(
                    f"EN story slot {slot}, pointer {index}: ${address:04X} outside "
                    f"${start:04X}-${end:04X}"
                )
            identity = f"{slot:02d}_{address:04X}"
            occurrence["record"] = identity
            occurrences.append(occurrence)
            current = records.get(identity)
            if current is None:
                records[identity] = {
                    "slot": slot,
                    "bank": f"${bank:02X}",
                    "address": f"${address:04X}",
                    "pc": f"0x{cpu_to_pc(bank, address):06X}",
                    "boundary": "unresolved: EN stream grammar requires P2 runtime/disassembly evidence",
                }

    aliases: dict[str, list[str]] = {}
    for occurrence in occurrences:
        record = occurrence["record"]
        if record is not None:
            aliases.setdefault(str(record), []).append(
                f"{int(occurrence['slot']):02d}:{int(occurrence['pointer_index']):03d}"
            )

    return {
        "schema": "srw4.en-story.source.v2",
        "authority": "English ROM addresses and pointer topology; JP summary supplies structure only.",
        "master_table": {"cpu": "$E8:0000", "slots": MASTER_SLOTS},
        "blocks": blocks,
        "occurrences": occurrences,
        "records": records,
        "aliases": aliases,
        "record_boundary_policy": (
            "Do not infer EN record boundaries from F7/FF: runtime evidence proves "
            "F7 can occur inside an active EN battle payload."
        ),
        "summary": {
            "text_blocks": sum(block["kind"] == "text" for block in blocks),
            "record_blocks": sum(block["kind"] == "record" for block in blocks),
            "pointer_slots": len(occurrences),
            "null_pointer_slots": null_slots,
            "pointer_reachable_records": len(records),
            "aliased_pointer_slots": sum(len(rows) - 1 for rows in aliases.values()),
            "source_summary_records": source_summary_records,
            "source_minus_reachable_records": source_summary_records - len(records),
        },
    }
