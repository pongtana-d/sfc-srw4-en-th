"""Move a whole catalog out of its cramped bank and fill it with Thai.

Every catalog the game can print sits behind the master table of 24-bit
pointers at ``$C9:00D8``.  The ``FB`` handler loads a whole entry into
``$1A-$1C``, so a catalog's strings are read from the bank of its own pointer
table.  When a catalog is referenced from the master table alone, the table and
its pool can therefore move together into an expansion bank and only the
three-byte master entry changes.

A translation file describes one catalog: which master entry owns it, the
clean-ROM table and pool with their hashes, the field's pixel budget, and one
record per unique pointer with its source bytes.  This module turns that into
writes plus the source ranges the Thai renderer must route.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from .catalogs import CatalogEncoder, Write
from .records import rebuild_record
from .text.encoding import advance_table
from .text.stock import StockCatalog


MASTER_TABLE_PC = 0x0900D8
TEXT_DATA_END = 0x3C0000


def _number(value: str) -> int:
    return int(value, 0)


def build_relocated_catalog(
    root: Path, clean: bytes, text_cursor: int, translation: str, owner: str,
    *, translation_path: Path | None = None,
) -> tuple[list[Write], dict[str, object]]:
    """Rebuild one master-table catalog in the ``text_data`` region."""
    layout_codes = json.loads((root / "font/encoding.json").read_text(encoding="utf-8"))
    model = json.loads((root / "font/thai.json").read_text(encoding="utf-8"))
    encoder = CatalogEncoder(
        model, layout_codes, StockCatalog.locked()
    )
    source_path = translation_path or root / translation
    text = json.loads(source_path.read_text(encoding="utf-8"))
    layout = text["_layout"]

    entry_index = int(layout["master_entry"])
    entry_pc = MASTER_TABLE_PC + entry_index * 3
    entry_source = bytes.fromhex(str(layout["master_entry_hex"]))
    if entry_pc != _number(str(layout["master_entry_pc"])):
        raise ValueError(f"{owner}: master entry index and address disagree")
    if clean[entry_pc:entry_pc + 3] != entry_source:
        raise ValueError(f"{owner}: master-table entry source mismatch")

    table = layout["pointer_table"]
    table_pc = _number(str(table["address"]))
    entries = int(table["entries"])
    if entry_source != (
        (table_pc & 0xFFFF).to_bytes(2, "little") + bytes((0xC0 + (table_pc >> 16),))
    ):
        raise ValueError(f"{owner}: master entry does not address the declared table")
    actual = sha256(clean[table_pc:table_pc + entries * 2]).hexdigest()
    if actual != str(table["source_sha256"]):
        raise ValueError(f"{owner}: pointer table hash mismatch: {actual}")

    pool = layout["pool"]
    pool_pc = _number(str(pool["address"]))
    pool_end = _number(str(pool["end"]))
    actual = sha256(clean[pool_pc:pool_end]).hexdigest()
    if actual != str(pool["source_sha256"]):
        raise ValueError(f"{owner}: pool hash mismatch: {actual}")

    max_width = int(layout["max_width_px"])
    bank_pc = table_pc & 0xFF0000

    payloads: dict[int, bytes] = {}
    thai: dict[int, bool] = {}
    report_records: list[dict[str, object]] = []
    for record in text["records"]:
        pointer = _number(str(record["pointer"]))
        expected = bytes.fromhex(str(record["source_hex"]))
        start = bank_pc + pointer
        if clean[start:start + len(expected)] != expected:
            raise ValueError(f"{owner}: source mismatch at {start:#08x}")
        value = record["translation"]
        if value is None:
            # A record the adapter carries across untouched: screen scripts
            # whose control bytes are not yet reverse engineered, and pages an
            # overlay already covers. It keeps the original bytes and is not
            # routed to the Thai renderer.
            payloads[pointer] = expected
            thai[pointer] = False
            report_records.append(
                {
                    "pointer": record["pointer"],
                    "source": record["source"],
                    "translation": None,
                    "bytes": len(expected),
                    "width_px": None,
                    "slots": len(record["slots"]),
                }
            )
            continue
        translation_text = str(value)
        if translation_text:
            payload, width = encoder.visible(translation_text)
        else:
            payload, width = b"", 0
        if width > max_width:
            raise ValueError(
                f"{owner}: {translation_text!r} is {width}px; the field holds {max_width}px"
            )
        payloads[pointer] = payload + b"\xFF"
        thai[pointer] = True
        report_records.append(
            {
                "pointer": record["pointer"],
                "source": record["source"],
                "translation": translation_text,
                "bytes": len(payload) + 1,
                "width_px": width,
                "slots": len(record["slots"]),
            }
        )

    declared_slots = sorted(slot for record in text["records"] for slot in record["slots"])
    if declared_slots != list(range(entries)):
        raise ValueError(f"{owner}: slots must cover the pointer table exactly")

    block_pc = (text_cursor + 0xFF) & ~0xFF
    new_pool = bytearray()
    offsets: dict[int, int] = {}
    routes: list[tuple[int, int]] = []
    pool_start = (block_pc & 0xFFFF) + entries * 2
    for record in text["records"]:
        pointer = _number(str(record["pointer"]))
        offsets[pointer] = pool_start + len(new_pool)
        payload = payloads[pointer]
        if thai[pointer]:
            # Route the terminator too: it closes the pending VWF run. Ranges
            # are quoted one past the text because the engine has already
            # advanced the source pointer when the classifier sees a byte.
            start = pool_start + len(new_pool) + 1
            routes.append((start, start + len(payload)))
        new_pool.extend(payload)
    new_table = bytearray()
    for slot in range(entries):
        source = clean[table_pc + slot * 2] | (clean[table_pc + slot * 2 + 1] << 8)
        new_table.extend(offsets[source].to_bytes(2, "little"))

    block = bytes(new_table) + bytes(new_pool)
    block_end = block_pc + len(block)
    if block_end > TEXT_DATA_END:
        raise ValueError(f"{owner}: catalog exceeds the text_data region")
    if (block_pc >> 16) != ((block_end - 1) >> 16):
        raise ValueError(f"{owner}: catalog must not cross a bank boundary")

    bank = 0xC0 + (block_pc >> 16)
    table_cpu = block_pc & 0xFFFF
    writes = [
        Write(block_pc, block, f"{owner}-catalog", True),
        Write(
            entry_pc,
            table_cpu.to_bytes(2, "little") + bytes((bank,)),
            f"{owner}-master-entry",
            False,
        ),
    ]

    merged: list[list[int]] = []
    for start, end in sorted(routes):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return writes, {
        "master_entry": entry_index,
        "master_entry_pc": f"0x{entry_pc:06X}",
        "catalog_pc": f"0x{block_pc:06X}",
        "catalog_cpu": f"${bank:02X}:{table_cpu:04X}",
        "entries": entries,
        "records": report_records,
        "table_bytes": len(new_table),
        "pool_bytes": len(new_pool),
        "released_pool": {
            "pc": f"0x{pool_pc:06X}-0x{pool_end:06X}",
            "bytes": pool_end - pool_pc,
            "state": "unreferenced-after-relocation",
        },
        "translated_records": sum(1 for value in thai.values() if value),
        "kept_records": sum(1 for value in thai.values() if not value),
        "source_routes": {f"0x{bank:02X}": merged},
    }


def build_relocated_script_catalog(
    root: Path,
    clean: bytes,
    current: bytes,
    text_cursor: int,
    translation: str,
    owner: str,
    *,
    translation_path: Path | None = None,
) -> tuple[list[Write], dict[str, object]]:
    """Move a catalog of screen scripts and translate the words inside them.

    Unlike a catalog of plain strings, these records carry window control bytes
    that are not reverse engineered, so a record is rebuilt around its declared
    labels rather than re-encoded.  Records are read from ``current`` rather
    than ``clean``: other adapters patch fields inside this catalog, and their
    bytes have to travel with it.  ``clean`` still backs every source
    assertion, so the labels are proven to be the ones they were cut from.
    """
    codes = json.loads((root / "font/encoding.json").read_text(encoding="utf-8"))
    model = json.loads((root / "font/thai.json").read_text(encoding="utf-8"))
    advances = advance_table(model, codes)
    stock = StockCatalog.locked()

    source_path = translation_path or root / translation
    text = json.loads(source_path.read_text(encoding="utf-8"))
    layout = text["_layout"]
    entry_index = int(layout["master_entry"])
    entry_pc = MASTER_TABLE_PC + entry_index * 3
    entry_source = bytes.fromhex(str(layout["master_entry_hex"]))
    if entry_pc != _number(str(layout["master_entry_pc"])):
        raise ValueError(f"{owner}: master entry index and address disagree")
    if clean[entry_pc:entry_pc + 3] != entry_source:
        raise ValueError(f"{owner}: master-table entry source mismatch")

    table = layout["pointer_table"]
    table_pc = _number(str(table["address"]))
    entries = int(table["entries"])
    if entry_source != (
        (table_pc & 0xFFFF).to_bytes(2, "little") + bytes((0xC0 + (table_pc >> 16),))
    ):
        raise ValueError(f"{owner}: master entry does not address the declared table")
    if sha256(clean[table_pc:table_pc + entries * 2]).hexdigest() != str(table["source_sha256"]):
        raise ValueError(f"{owner}: pointer table hash mismatch")

    pool = layout["pool"]
    pool_pc = _number(str(pool["address"]))
    pool_end = _number(str(pool["end"]))
    if sha256(clean[pool_pc:pool_end]).hexdigest() != str(pool["source_sha256"]):
        raise ValueError(f"{owner}: pool hash mismatch")

    bank_pc = table_pc & 0xFF0000
    default_width = int(layout["max_width_px"])

    declared = sorted(slot for record in text["records"] for slot in record["slots"])
    if declared != list(range(entries)):
        raise ValueError(f"{owner}: slots must cover the pointer table exactly")

    built: list[dict[str, object]] = []
    for record in text["records"]:
        pointer = _number(str(record["pointer"]))
        source = bytes.fromhex(str(record["source_hex"]))
        start = bank_pc + pointer
        if clean[start:start + len(source)] != source:
            raise ValueError(f"{owner}: source mismatch at {start:#08x}")
        if start + len(source) != _number(str(record["source_end"])):
            raise ValueError(f"{owner}: record {record['pointer']} has the wrong extent")
        for slot in record["slots"]:
            slot_pc = table_pc + slot * 2
            if clean[slot_pc] | (clean[slot_pc + 1] << 8) != pointer:
                raise ValueError(f"{owner}: slot {slot} does not address {pointer:#06x}")

        carried = current[start:start + len(source)]
        if "labels" in record:
            # Surgery runs on the carried bytes, not the clean ones: another
            # adapter may already own other fields in this same record.  Each
            # label still has to find its Japanese there, so a field two
            # adapters both claim fails loudly instead of losing one of them.
            payload, routes, labels = rebuild_record(
                carried, record["labels"], codes, advances, stock, default_width,
                f"{owner}: record {record['pointer']}",
            )
        else:
            payload, routes, labels = carried, [], []
        built.append(
            {
                "pointer": pointer,
                "source_pc": start,
                "source_bytes": len(source),
                "payload": payload,
                "routes": routes,
                "labels": labels,
                "slots": list(record["slots"]),
                "patched_elsewhere": carried != source,
            }
        )

    block_pc = (text_cursor + 0xFF) & ~0xFF
    pool_start = (block_pc & 0xFFFF) + entries * 2
    new_pool = bytearray()
    offsets: dict[int, int] = {}
    routes: list[tuple[int, int]] = []
    moves: list[dict[str, object]] = []
    for item in built:
        base = pool_start + len(new_pool)
        offsets[int(item["pointer"])] = base
        for run_start, run_end in item["routes"]:
            routes.append((base + run_start, base + run_end))
        moves.append(
            {
                "from": f"0x{int(item['source_pc']):06X}",
                "bytes": int(item["source_bytes"]),
                "to_cpu": base,
            }
        )
        new_pool.extend(item["payload"])

    new_table = bytearray()
    for slot in range(entries):
        source_pointer = clean[table_pc + slot * 2] | (clean[table_pc + slot * 2 + 1] << 8)
        new_table.extend(offsets[source_pointer].to_bytes(2, "little"))

    block = bytes(new_table) + bytes(new_pool)
    block_end = block_pc + len(block)
    if block_end > TEXT_DATA_END:
        raise ValueError(f"{owner}: catalog exceeds the text_data region")
    if (block_pc >> 16) != ((block_end - 1) >> 16):
        raise ValueError(f"{owner}: catalog must not cross a bank boundary")

    bank = 0xC0 + (block_pc >> 16)
    table_cpu = block_pc & 0xFFFF
    writes = [
        Write(block_pc, block, f"{owner}-catalog", True),
        Write(
            entry_pc,
            table_cpu.to_bytes(2, "little") + bytes((bank,)),
            f"{owner}-master-entry",
            False,
        ),
    ]

    merged: list[list[int]] = []
    for start, end in sorted(routes):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    return writes, {
        "master_entry": entry_index,
        "master_entry_pc": f"0x{entry_pc:06X}",
        "catalog_pc": f"0x{block_pc:06X}",
        "catalog_cpu": f"${bank:02X}:{table_cpu:04X}",
        "entries": entries,
        "records": len(built),
        "rebuilt_records": sum(1 for item in built if item["labels"]),
        "carried_records": sum(1 for item in built if not item["labels"]),
        "records_patched_elsewhere": sum(1 for item in built if item["patched_elsewhere"]),
        "labels": [label for item in built for label in item["labels"]],
        "table_bytes": len(new_table),
        "pool_bytes": len(new_pool),
        "released_pool": {
            "pc": f"0x{pool_pc:06X}-0x{pool_end:06X}",
            "bytes": pool_end - pool_pc,
            "state": "unreferenced-after-relocation",
        },
        # Where each record's bytes ended up, so a route another adapter
        # emitted into the old bank can be moved with the bytes it describes.
        "moved_records": moves,
        "moved_from_bank": f"0x{0xC0 + (bank_pc >> 16):02X}",
        "source_routes": {f"0x{bank:02X}": merged},
    }
