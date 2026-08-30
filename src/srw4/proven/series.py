"""Thai series titles for the encyclopedia's FROM field.

The titles live in catalog ``$D2:8103``, which the unit-status adapter already
patches in place, so the catalog stays where it is and only these records move.
Thai needs more bytes than the Japanese it replaces, and bank ``$D2`` had 33
bytes free, so the records are written into the pools the relocated terrain and
scenario catalogs left behind in the same bank.

A record can be reached from more than one slot of the pointer table, so every
slot that addressed it is repointed.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from .catalogs import CatalogEncoder, Write
from .text.stock import StockCatalog


POINTER_TABLE_PC = 0x128103
POINTER_TABLE_ENTRIES = 370
BANK_PC = 0x120000


def _number(value: str) -> int:
    return int(value, 0)


def build_series_data(
    root: Path, clean: bytes, released: list[tuple[int, int]],
    *, translation_dir: Path | None = None,
) -> tuple[list[Write], dict[str, object]]:
    """Rewrite the series-title records inside bank $D2."""
    translations = translation_dir or root / "translations"
    text = json.loads((translations / "series-names.th.json").read_text(encoding="utf-8"))
    codes = json.loads((root / "font/encoding.json").read_text(encoding="utf-8"))
    model = json.loads((root / "font/thai.json").read_text(encoding="utf-8"))
    encoder = CatalogEncoder(model, codes, StockCatalog.locked())

    layout = text["_layout"]
    table = layout["pointer_table"]
    table_pc = _number(str(table["address"]))
    entries = int(table["entries"])
    if (table_pc, entries) != (POINTER_TABLE_PC, POINTER_TABLE_ENTRIES):
        raise ValueError("series pointer table declaration changed")
    actual = sha256(clean[table_pc:table_pc + entries * 2]).hexdigest()
    if actual != str(table["source_sha256"]):
        raise ValueError(f"series pointer table hash mismatch: {actual}")
    max_width = int(layout["max_width_px"])

    pools = [
        {"start": start, "end": end, "cursor": start}
        for start, end in sorted(released)
        if (start >> 16) == (POINTER_TABLE_PC >> 16)
    ]
    if not pools:
        raise ValueError("series titles need a released pool in bank $D2")
    for pool in pools:
        if clean[pool["start"]:pool["end"]] == b"\xFF" * (pool["end"] - pool["start"]):
            raise ValueError("a released pool should hold the catalog it replaced")

    writes: list[Write] = []
    report_records: list[dict[str, object]] = []
    route_ranges: list[tuple[int, int]] = []
    for record in text["records"]:
        pointer = _number(str(record["pointer"]))
        source = bytes.fromhex(str(record["source_hex"]))
        start = BANK_PC + pointer
        if clean[start:start + len(source)] != source:
            raise ValueError(f"series source mismatch at {start:#08x}")
        if start + len(source) != _number(str(record["source_end"])):
            raise ValueError(f"series record {pointer:#06x} has the wrong extent")
        if source[-1] != 0xFF:
            raise ValueError(f"series record {pointer:#06x} has no terminator")

        payload, width = encoder.visible(str(record["translation"]))
        if width > max_width:
            raise ValueError(
                f"series {record['translation']!r} is {width}px; the field holds {max_width}px"
            )
        payload += b"\xFF"

        for pool in pools:
            if pool["end"] - pool["cursor"] >= len(payload):
                pc = int(pool["cursor"])
                pool["cursor"] = pc + len(payload)
                break
        else:
            raise ValueError(f"series record {pointer:#06x} has nowhere to live")

        writes.append(Write(pc, payload, f"series-record-{pointer:04X}", False))
        slots = [int(slot) for slot in record["slots"]]
        for slot in slots:
            slot_pc = table_pc + slot * 2
            if clean[slot_pc] | (clean[slot_pc + 1] << 8) != pointer:
                raise ValueError(f"series slot {slot} does not address {pointer:#06x}")
            writes.append(
                Write(
                    slot_pc,
                    (pc & 0xFFFF).to_bytes(2, "little"),
                    f"series-slot-{slot}",
                    False,
                )
            )
        # Route the terminator too: it closes the pending VWF run. Ranges are
        # quoted one past the text because the engine has already advanced the
        # source pointer when the classifier sees a byte.
        route_ranges.append(((pc & 0xFFFF) + 1, (pc & 0xFFFF) + len(payload) + 1))
        report_records.append(
            {
                "pointer": record["pointer"],
                "pc": f"0x{pc:06X}",
                "source": record["source"],
                "translation": record["translation"],
                "slots": slots,
                "source_bytes": len(source),
                "bytes": len(payload),
                "width_px": width,
            }
        )

    return writes, {
        "pointer_table": f"0x{table_pc:06X}",
        "records": report_records,
        "pools": [
            {
                "start": f"0x{int(pool['start']):06X}",
                "end": f"0x{int(pool['end']):06X}",
                "capacity": int(pool["end"]) - int(pool["start"]),
                "used": int(pool["cursor"]) - int(pool["start"]),
            }
            for pool in pools
        ],
        "source_routes": {"0xD2": [[start, end] for start, end in sorted(route_ranges)]},
    }
