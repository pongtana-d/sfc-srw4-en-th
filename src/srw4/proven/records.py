"""Rebuild individual catalog records in place of a whole-catalog move.

Some catalogs cannot relocate: the intro overlay recognises its crawl pages by
their ``$CC`` source pointers, and other adapters already patch records inside
the same pools.  For those, the adapter rebuilds one record at a time, keeping
every byte except the visible Japanese words, and repoints only that record's
slot in the pointer table.

Replacement text is longer than the Japanese it replaces, so records move into
free space in the same bank.  Two kinds of space are used: a verified ``FF``
run, and the span a record vacates the moment its own pointer moves.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from collections.abc import Callable

from .catalogs import Write
from .text.encoding import advance_table, encode
from .text.stock import StockCatalog, encode_stock, mixed_segments


LabelEncoder = Callable[[str], tuple[list[tuple[bytes, bool]], int]]


def _number(value: str) -> int:
    return int(value, 0)


def _encode_label(
    text: str, codes: dict, advances: bytes, stock: StockCatalog
) -> tuple[list[tuple[bytes, bool]], int]:
    """Encode one label as runs of ``(bytes, needs_thai_routing)``.

    Text with no Thai at all is written as direct stock bytes, the way the
    Japanese it replaces was.  Mixed text keeps its Latin parts on the stock
    font through the FB run mechanism, so only the Thai bytes are routed.
    """
    segments = mixed_segments(text)
    if all(is_stock for is_stock, _ in segments):
        encoded = encode_stock(text)
        return [(encoded, False)], len(encoded) * 8
    runs: list[tuple[bytes, bool]] = []
    width = 0
    for is_stock, part in segments:
        if is_stock:
            runs.append((stock.control(part), False))
            width += len(part) * 8
            continue
        encoded = encode(part, codes["codes"], codes.get("shorthand"), codes.get("phrases"))
        runs.append((encoded, True))
        width += sum(advances[code] for code in encoded)
    return runs, width


def measure_label(text: str, codes: dict, advances: bytes, stock: StockCatalog) -> int:
    """Pixel width of a replacement, counting stock runs the way the build does."""
    return _encode_label(text, codes, advances, stock)[1]


def rebuild_record(
    source: bytes,
    labels: list[dict],
    codes: dict,
    advances: bytes,
    stock: StockCatalog,
    default_width: int,
    owner: str,
    label_encoder: LabelEncoder | None = None,
) -> tuple[bytes, list[tuple[int, int]], list[dict[str, object]]]:
    """Replace the declared labels inside one record, keeping every other byte.

    Returns the rebuilt payload, the Thai run ranges relative to the record's
    own start, and one report row per label.  Callers add the record's address
    to the ranges once they know where the record lands.
    """
    payload = bytearray()
    report: list[dict[str, object]] = []
    routes: list[tuple[int, int]] = []
    read = 0
    for label in sorted(labels, key=lambda item: int(item["offset"])):
        offset = int(label["offset"])
        length = int(label["length"])
        expected = bytes.fromhex(str(label["source_hex"]))
        if offset < read:
            raise ValueError(f"{owner}: labels overlap")
        if len(expected) != length or source[offset:offset + length] != expected:
            raise ValueError(f"{owner}: label {label['source']!r} is not at offset {offset}")
        replacement = str(label["text"])
        runs, width = (
            label_encoder(replacement)
            if label_encoder is not None
            else _encode_label(replacement, codes, advances, stock)
        )
        limit = int(label.get("max_width_px", default_width))
        if width > limit:
            raise ValueError(f"{owner}: {replacement!r} is {width}px; the field holds {limit}px")
        payload.extend(source[read:offset])
        encoded_bytes = 0
        for encoded, thai in runs:
            if thai:
                # Ranges are quoted one past the text because the engine has
                # already advanced the source pointer when the classifier runs.
                run_start = len(payload)
                routes.append((run_start + 1, run_start + len(encoded) + 1))
            payload.extend(encoded)
            encoded_bytes += len(encoded)
        read = offset + length
        report.append(
            {
                "source": label["source"],
                "text": replacement,
                "encoding": "-".join(
                    sorted({"thai-vwf" if thai else "stock-english" for _, thai in runs})
                ),
                "width_px": width,
                "max_width_px": limit,
                "byte_delta": encoded_bytes - length,
            }
        )
    payload.extend(source[read:])
    return bytes(payload), routes, report


def build_record_patches(
    root: Path,
    clean: bytes,
    translation: str,
    owner: str,
    pools: list[dict],
) -> tuple[list[Write], dict[str, object]]:
    """Rebuild the declared records of one catalog and repoint their slots."""
    text = json.loads((root / translation).read_text(encoding="utf-8"))
    return build_record_config_patches(root, clean, text, owner, pools)


def build_record_config_patches(
    root: Path,
    clean: bytes,
    text: dict,
    owner: str,
    pools: list[dict],
    *,
    label_encoder: LabelEncoder | None = None,
) -> tuple[list[Write], dict[str, object]]:
    """Rebuild records declared by an already-loaded translation document."""
    codes = json.loads((root / "font/encoding.json").read_text(encoding="utf-8"))
    model = json.loads((root / "font/thai.json").read_text(encoding="utf-8"))
    advances = advance_table(model, codes)
    stock = StockCatalog.locked()

    layout = text["_layout"]
    table = layout["pointer_table"]
    table_pc = _number(str(table["address"]))
    entries = int(table["entries"])
    actual = sha256(clean[table_pc:table_pc + entries * 2]).hexdigest()
    if actual != str(table["source_sha256"]):
        raise ValueError(f"{owner}: pointer table hash mismatch: {actual}")
    bank_pc = table_pc & 0xFF0000
    default_width = int(layout["max_width_px"])

    built: list[dict] = []
    if len({int(record["slot"]) for record in text["records"]}) != len(text["records"]):
        raise ValueError(f"{owner}: a slot is declared twice")
    for record in text["records"]:
        slot = int(record["slot"])
        pointer = _number(str(record["pointer"]))
        source = bytes.fromhex(str(record["source_hex"]))
        record_pc = bank_pc + pointer
        if clean[record_pc:record_pc + len(source)] != source:
            raise ValueError(f"{owner}: source mismatch at {record_pc:#08x}")
        if record_pc + len(source) != _number(str(record["source_end"])):
            raise ValueError(f"{owner}: record {slot} has the wrong extent")
        # $FE takes an operand, so the first $FF inside a record can be that
        # operand rather than the terminator; a record runs to the next pointer
        # and must still end on a real terminator.
        if source[-1] != 0xFF:
            raise ValueError(f"{owner}: record {slot} does not end on a terminator")
        slot_pc = table_pc + slot * 2
        if clean[slot_pc] | (clean[slot_pc + 1] << 8) != pointer:
            raise ValueError(f"{owner}: slot {slot} does not address {pointer:#06x}")

        # Rebuild left to right so each label's new offset is known: Thai runs
        # have to be routed to the VWF renderer at their new address.
        payload, routes, labels = rebuild_record(
            source, record["labels"], codes, advances, stock, default_width,
            f"{owner}: record {slot}", label_encoder,
        )

        built.append(
            {
                "slot": slot,
                "slot_pc": slot_pc,
                "source_pc": record_pc,
                "source": source,
                "payload": bytes(payload),
                "labels": labels,
                "routes": routes,
                "pointer": record["pointer"],
            }
        )

    # A record's own span becomes dead as soon as its pointer moves, so the
    # vacated spans join the declared pools as places to put rebuilt records.
    allocation = [dict(pool) for pool in pools]
    allocation.extend(
        {"start": item["source_pc"], "end": item["source_pc"] + len(item["source"]),
         "kind": "vacated-record"}
        for item in sorted(built, key=lambda item: item["source_pc"])
    )

    for item in built:
        for pool in allocation:
            if pool["end"] - pool["start"] < len(item["payload"]):
                continue
            item["pc"] = pool["start"]
            item["pool"] = pool["kind"]
            pool["start"] += len(item["payload"])
            break
        else:
            raise ValueError(f"{owner}: record {item['slot']} has nowhere to live")

    writes: list[Write] = []
    report_records: list[dict[str, object]] = []
    route_ranges: list[tuple[int, int]] = []
    bank = 0xC0 + (bank_pc >> 16)
    for item in built:
        pc = int(item["pc"])
        payload = item["payload"]
        free = item["pool"].endswith("ff")
        if free and clean[pc:pc + len(payload)] != b"\xFF" * len(payload):
            raise ValueError(f"{owner}: target {pc:#08x} is not free")
        writes.append(Write(pc, payload, f"{owner}-record-{item['slot']}", free))
        new_pointer = pc & 0xFFFF
        writes.append(
            Write(
                int(item["slot_pc"]),
                new_pointer.to_bytes(2, "little"),
                f"{owner}-slot-{item['slot']}",
                False,
            )
        )
        base = pc & 0xFFFF
        for run_start, run_end in item["routes"]:
            route_ranges.append((base + run_start, base + run_end))
        report_records.append(
            {
                "slot": item["slot"],
                "source_pointer": item["pointer"],
                "pointer": f"0x{new_pointer:04X}",
                "pc": f"0x{pc:06X}",
                "pool": item["pool"],
                "source_bytes": len(item["source"]),
                "bytes": len(payload),
                "labels": item["labels"],
            }
        )

    return writes, {
        "pointer_table": f"0x{table_pc:06X}",
        "records": report_records,
        "pools": [
            {
                "kind": str(pool["kind"]),
                "start": f"0x{int(pool['start']):06X}",
                "end": f"0x{int(pool['end']):06X}",
            }
            for pool in allocation
        ],
        "source_routes": {f"0x{bank:02X}": [[start, end] for start, end in sorted(route_ranges)]},
    }
