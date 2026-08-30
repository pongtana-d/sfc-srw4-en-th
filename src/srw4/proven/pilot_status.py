"""Verified data builder for pilot status, spirit names and pilot skills."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from .catalogs import CatalogEncoder, Write
from .text.encoding import advance_table
from .text.stock import StockCatalog, encode_stock, mixed_segments


LINE_BREAK = 0xF6
SPIRIT_ENTRY_BYTES = 6
SPIRIT_VISIBLE_PX = 4 * 8
SKILL_VISIBLE_PX = 9 * 8
BANK_D2_END = 0x130000


def _number(value: str) -> int:
    return int(value, 0)


def _assert_hash(clean: bytes, item: dict[str, object], owner: str) -> None:
    start, end = _number(str(item["address"])), _number(str(item["end"]))
    actual = sha256(clean[start:end]).hexdigest()
    expected = str(item["source_sha256"])
    if actual != expected:
        raise ValueError(f"source hash mismatch for {owner}: {actual} != {expected}")


def _span(item: dict[str, object]) -> tuple[int, int, bytes]:
    start, end = _number(str(item["address"])), _number(str(item["end"]))
    expected = bytes.fromhex(str(item["source_hex"]))
    if len(expected) != end - start:
        raise ValueError(f"pilot-status source span at {start:#x} has the wrong size")
    return start, end, expected


def _route_runs(start: int, flags: list[bool]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(flags):
        if not flags[cursor]:
            cursor += 1
            continue
        run = cursor
        while cursor < len(flags) and flags[cursor]:
            cursor += 1
        result.append(((start + run + 1) & 0xFFFF, (start + cursor + 1) & 0xFFFF))
    return result


def _fixed_screen(
    clean: bytes,
    text: dict[str, object],
    layout: dict[str, object],
    encoder: CatalogEncoder,
) -> tuple[list[Write], list[tuple[int, int]], list[dict[str, object]]]:
    geometry = text["_layout"]
    _assert_hash(clean, geometry["script"], "pilot-status script")
    pad = int(layout["codes"]["<Pad>"])
    gap = int(layout["codes"]["<Gap>"])
    fixed = {str(entry["key"]): entry for entry in text["fixed_labels"]}
    writes: list[Write] = []
    routes: list[tuple[int, int]] = []
    report: list[dict[str, object]] = []

    for key, item in geometry["fields"].items():
        entry = fixed[key]
        value = str(entry["translation"])
        if mixed_segments(value) == [(True, value)]:
            payload = bytearray(encode_stock(value))
            flags = [False] * len(payload)
            width = len(value) * 8
            font = "stock"
        else:
            encoded, width = encoder.visible(value)
            payload = bytearray(encoded)
            flags = [True] * len(payload)
            font = "thai_vwf"

        target_cells = int(item["visible_cells"])
        visible_padding = 0
        if item.get("visible_pad"):
            visible_padding = max(0, target_cells - ((width + 7) // 8))
            payload.extend(bytes((gap,)) * visible_padding)
            flags.extend([True] * visible_padding)

        start, end, expected = _span(item)
        if clean[start:end] != expected:
            raise ValueError(f"source mismatch for pilot-status:{key}")
        capacity = end - start
        if len(payload) > capacity:
            raise ValueError(f"pilot-status:{key} needs {len(payload)} bytes; holds {capacity}")
        zero_padding = capacity - len(payload)
        payload.extend(bytes((pad,)) * zero_padding)
        flags.extend([True] * zero_padding)
        writes.append(Write(start, bytes(payload), f"pilot-status:{key}", False))
        routes.extend(_route_runs(start, flags))
        report.append({
            "key": key, "translation": value, "font": font,
            "width_px": width, "target_cells": target_cells,
            "visible_padding_cells": visible_padding,
            "zero_width_padding": zero_padding, "capacity": capacity,
        })

    codes = layout["codes"]
    badges = (
        ("<AiL>", "<AiR>"), ("<LaL>", "<a>"),
        ("<WaL>", "<a>"), ("<SpL>", "<SpR>"),
    )
    terrain = bytearray()
    for index, pair in enumerate(badges):
        if index:
            terrain.append(LINE_BREAK)
        terrain.extend(int(codes[token]) for token in pair)
    terrain_item = geometry["terrain_box"]
    start, end, expected = _span(terrain_item)
    if clean[start:end] != expected or len(terrain) != end - start:
        raise ValueError("pilot-status terrain source or size mismatch")
    writes.append(Write(start, bytes(terrain), "pilot-status:terrain-box", False))
    routes.extend(_route_runs(start, [True] * len(terrain)))
    return writes, routes, report


def _trailing_spill(payload: bytes, advances: bytes, control_base: int) -> bool:
    pen = 0
    result = False
    for code in payload:
        if code >= control_base:
            continue
        step = advances[code]
        if not step:
            continue
        pen += step
        crossed = False
        while pen >= 8:
            pen -= 8
            crossed = True
        result = crossed and bool(pen)
    return result


def _spirit_data(
    clean: bytes,
    text: dict[str, object],
    layout: dict[str, object],
    encoder: CatalogEncoder,
    overflow_start: int,
) -> tuple[list[Write], list[dict[str, object]], list[dict[str, object]], int]:
    geometry = text["_layout"]
    pointer_item, pool_item = geometry["spirit_pointers"], geometry["spirit_pool"]
    _assert_hash(clean, pointer_item, "spirit pointer table")
    _assert_hash(clean, pool_item, "spirit string pool")
    pool_start, pool_end = _number(pool_item["address"]), _number(pool_item["end"])
    pad = int(layout["codes"]["<Pad>"])
    spirits = sorted(text["spirits"], key=lambda entry: int(entry["id"]))
    if [int(entry["id"]) for entry in spirits] != list(range(1, 31)):
        raise ValueError("pilot spirits must cover IDs 1-30")

    primary = bytearray()
    overflow = bytearray()
    pointers: list[int] = []
    report: list[dict[str, object]] = []
    for entry in spirits:
        encoded, width = encoder.visible(str(entry["translation"]))
        if len(encoded) > SPIRIT_ENTRY_BYTES:
            raise ValueError(
                f"spirit {entry['translation']!r} needs {len(encoded)} bytes; "
                f"record holds {SPIRIT_ENTRY_BYTES}"
            )
        record = encoded + bytes((pad,)) * (SPIRIT_ENTRY_BYTES - len(encoded)) + b"\xFF"
        if len(primary) + len(record) <= pool_end - pool_start:
            target = pool_start + len(primary)
            primary.extend(record)
            destination = "original_pool"
        else:
            target = overflow_start + len(overflow)
            overflow.extend(record)
            destination = "overflow"
        pointers.append(target & 0xFFFF)
        report.append({
            "id": entry["id"], "source": entry["source"],
            "translation": entry["translation"], "target_pc": f"0x{target:06X}",
            "encoded_bytes": len(encoded), "record_bytes": SPIRIT_ENTRY_BYTES,
            "width_px": width, "over_width": width > SPIRIT_VISIBLE_PX,
            "destination": destination,
        })

    if len(primary) != pool_end - pool_start:
        raise ValueError("24 fixed spirit records must fill the original pool exactly")
    if overflow_start + len(overflow) > BANK_D2_END:
        raise ValueError("spirit overflow exceeds the bank D2 tail")
    if clean[overflow_start:overflow_start + len(overflow)] != b"\xFF" * len(overflow):
        raise ValueError("spirit overflow target is not FF-filled")
    pointer_start = _number(pointer_item["address"])
    pointer_payload = b"".join(pointer.to_bytes(2, "big") for pointer in pointers)
    writes = [
        Write(pool_start, bytes(primary), "pilot-spirit-pool", False),
        Write(pointer_start, pointer_payload, "pilot-spirit-pointers", False),
    ]
    if overflow:
        writes.append(Write(overflow_start, bytes(overflow), "pilot-spirit-overflow", True))
    pools = [
        {
            "name": "pilot_spirit_pool", "start": f"0x{pool_start:06X}",
            "end": f"0x{pool_end:06X}", "capacity": pool_end - pool_start,
            "used": len(primary),
        },
        {
            "name": "pilot_spirit_overflow", "start": f"0x{overflow_start:06X}",
            "end": f"0x{BANK_D2_END:06X}", "capacity": BANK_D2_END - overflow_start,
            "used": len(overflow),
        },
    ]
    return writes, pools, report, overflow_start + len(overflow)


def _skill_data(
    clean: bytes,
    text: dict[str, object],
    layout: dict[str, object],
    encoder: CatalogEncoder,
    stock: StockCatalog,
    advances: bytes,
) -> tuple[list[Write], dict[str, object], list[dict[str, object]]]:
    geometry = text["_layout"]
    pool_item = geometry["skill_pool"]
    _assert_hash(clean, pool_item, "pilot skill pool")
    for index, item in enumerate(geometry["skill_pointer_tables"]):
        _assert_hash(clean, item, f"pilot skill pointer table {index}")
    by_id: dict[int, dict[str, object]] = {}
    for entry in text["skills"]:
        for skill_id in entry["ids"]:
            by_id[int(skill_id)] = entry
    required = set(range(32, 51)) | {62, 63}
    if set(by_id) != required:
        raise ValueError("pilot skills have incomplete ID coverage")

    pool_start, pool_end = _number(pool_item["address"]), _number(pool_item["end"])
    control_base = int(layout["blocks"]["control_base"])
    space = int(layout["codes"][" "])
    payload = bytearray()
    pointers: dict[int, int] = {}
    report: list[dict[str, object]] = []
    for skill_id in range(32, 64):
        entry = by_id.get(skill_id)
        if entry is None:
            continue
        target = pool_start + len(payload)
        encoded, width = encoder.visible(str(entry["translation"]))
        value = bytearray(encoded)
        guard = False
        if 32 <= skill_id <= 47:
            guard = _trailing_spill(encoded, advances, control_base)
            if guard:
                value.append(space)
                width += advances[space]
            value.extend(stock.control(str(1 + ((skill_id - 32) % 8))))
            width += 8
        value.append(0xFF)
        pointers[skill_id] = target & 0xFFFF
        payload.extend(value)
        report.append({
            "id": skill_id, "source": entry["source"],
            "translation": entry["translation"], "target_pc": f"0x{target:06X}",
            "bytes": len(value) - 1, "width_px": width,
            "over_width": width > SKILL_VISIBLE_PX, "tail_guard": guard,
        })

    empty_pointer = (pool_start + len(payload)) & 0xFFFF
    payload.append(0xFF)
    for skill_id in range(51, 62):
        pointers[skill_id] = empty_pointer
    if len(payload) > pool_end - pool_start:
        raise ValueError(f"pilot skills need {len(payload)} bytes; pool holds {pool_end-pool_start}")
    replacement = bytes(payload) + b"\xFF" * (pool_end - pool_start - len(payload))
    pointer_payload = b"".join(pointers[skill_id].to_bytes(2, "big") for skill_id in range(32, 64))
    writes = [Write(pool_start, replacement, "pilot-skill-pool", False)]
    for index, item in enumerate(geometry["skill_pointer_tables"]):
        writes.append(Write(
            _number(item["address"]), pointer_payload,
            f"pilot-skill-pointers:{index}", False,
        ))
    return writes, {
        "name": "pilot_skill_pool", "start": f"0x{pool_start:06X}",
        "end": f"0x{pool_end:06X}", "capacity": pool_end - pool_start,
        "used": len(payload),
    }, report


def build_pilot_status_data(
    root: Path,
    clean: bytes,
    *,
    overflow_start: int,
    translation_dir: Path | None = None,
) -> tuple[list[Write], dict[str, object]]:
    """Build pilot-status writes after the preceding D2-tail allocation."""
    if not 0x12FF83 <= overflow_start <= BANK_D2_END:
        raise ValueError(f"invalid pilot-status overflow start {overflow_start:#x}")
    translations = translation_dir or root / "translations"
    text = json.loads((translations / "pilot-status.th.json").read_text(encoding="utf-8"))
    layout = json.loads((root / "font/encoding.json").read_text(encoding="utf-8"))
    model = json.loads((root / "font/thai.json").read_text(encoding="utf-8"))
    stock = StockCatalog.locked()
    encoder = CatalogEncoder(model, layout, stock)
    advances = advance_table(model, layout)

    writes, fixed_routes, fixed_report = _fixed_screen(clean, text, layout, encoder)
    spirit_writes, spirit_pools, spirits, overflow_end = _spirit_data(
        clean, text, layout, encoder, overflow_start
    )
    skill_writes, skill_pool, skills = _skill_data(
        clean, text, layout, encoder, stock, advances
    )
    writes.extend(spirit_writes)
    writes.extend(skill_writes)
    return writes, {
        "fixed_fields": fixed_report,
        "source_routes": {"0xCC": [[start, end] for start, end in fixed_routes]},
        "pools": [*spirit_pools, skill_pool],
        "spirits": spirits,
        "skills": skills,
        "overflow_start": f"0x{overflow_start:06X}",
        "overflow_end": f"0x{overflow_end:06X}",
        "overflow_bytes": overflow_end - overflow_start,
    }
