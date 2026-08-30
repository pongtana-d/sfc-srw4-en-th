"""Verified data builder for the unit-status screen and its value pools."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .catalogs import CatalogEncoder, Write
from .text.encoding import advance_table
from .text.stock import StockCatalog, encode_stock, mixed_segments


LINE_BREAK = 0xF6
TAIL_POOL = (0x12FF83, 0x130000)
TYPE_MAX_WIDTH = 48
SERIES_MAX_WIDTH = 96


@dataclass(frozen=True)
class _Pool:
    start: int
    end: int
    pointer_start: int | None
    pointer_end: int | None
    aligned_scan: bool = False


def _number(value: str) -> int:
    return int(value, 0)


def _assert_hash(clean: bytes, item: dict[str, object], owner: str) -> None:
    start, end = _number(str(item["address"])), _number(str(item["end"]))
    actual = sha256(clean[start:end]).hexdigest()
    expected = str(item["source_sha256"])
    if actual != expected:
        raise ValueError(f"source hash mismatch for {owner}: {actual} != {expected}")


def _layout_span(item: dict[str, object]) -> tuple[int, int, bytes]:
    start, end = _number(str(item["address"])), _number(str(item["end"]))
    expected = bytes.fromhex(str(item["source_hex"]))
    if len(expected) != end - start:
        raise ValueError(f"fixed unit-status span at {start:#x} has the wrong size")
    return start, end, expected


def _route_runs(start: int, flags: list[bool]) -> list[tuple[int, int]]:
    """Convert byte flags to ranges of the engine's already-advanced pointer."""
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
    _assert_hash(clean, geometry["script"], "unit-status script")
    pad = int(layout["codes"]["<Pad>"])
    writes: list[Write] = []
    routes: list[tuple[int, int]] = []
    report: list[dict[str, object]] = []

    def literal(value: str) -> tuple[bytes, list[bool], str, int]:
        if mixed_segments(value) == [(True, value)]:
            return encode_stock(value), [False] * len(value), "stock", len(value) * 8
        payload, width = encoder.visible(value)
        return payload, [True] * len(payload), "thai_vwf", width

    def fill(item: dict[str, object], payload: bytes, flags: list[bool], owner: str) -> None:
        start, end, expected = _layout_span(item)
        capacity = end - start
        if len(payload) > capacity:
            raise ValueError(f"{owner} needs {len(payload)} bytes; field holds {capacity}")
        padding = capacity - len(payload)
        replacement = payload + bytes((pad,)) * padding
        full_flags = flags + [True] * padding
        writes.append(Write(start, replacement, owner, False))
        routes.extend(_route_runs(start, full_flags))
        if clean[start:end] != expected:
            raise ValueError(f"source mismatch for {owner} at {start:#x}")

    stats_payload = bytearray()
    stats_flags: list[bool] = []
    for index, entry in enumerate(text["stat_column"]):
        if index:
            stats_payload.append(LINE_BREAK)
            stats_flags.append(False)
        payload, flags, font, width = literal(str(entry["translation"]))
        stats_payload.extend(payload)
        stats_flags.extend(flags)
        report.append({
            "key": entry["key"], "translation": entry["translation"],
            "font": font, "bytes": len(payload), "width_px": width,
        })
    fill(geometry["stat_column"], bytes(stats_payload), stats_flags, "unit-status:stats")

    inline = text["inline_labels"]["level_morale"]
    lines = str(inline["translation"]).split("\n")
    if len(lines) != 2:
        raise ValueError("level/morale label must contain exactly two lines")
    inline_payload = bytearray()
    inline_flags: list[bool] = []
    widths = []
    for index, line in enumerate(lines):
        if index:
            inline_payload.append(LINE_BREAK)
            inline_flags.append(False)
        payload, flags, _, width = literal(line)
        inline_payload.extend(payload)
        inline_flags.extend(flags)
        widths.append(width)
    fill(
        geometry["level_morale"], bytes(inline_payload), inline_flags,
        "unit-status:level-morale",
    )
    report.append({
        "key": "level_morale", "translation": inline["translation"],
        "font": "stock", "bytes": len(inline_payload), "width_px": widths,
    })

    fixed = {str(entry["key"]): entry for entry in text["fixed_labels"]}
    for key, item in geometry["fields"].items():
        entry = fixed[key]
        payload, flags, font, width = literal(str(entry["translation"]))
        fill(item, payload, flags, f"unit-status:{key}")
        report.append({
            "key": key, "translation": entry["translation"], "font": font,
            "bytes": len(payload), "width_px": width,
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
    for index, item in enumerate(geometry["terrain_boxes"]):
        fill(item, bytes(terrain), [True] * len(terrain), f"unit-status:terrain-box-{index}")

    return writes, routes, report


def _pack_group(
    clean: bytes,
    entries: list[dict[str, object]],
    pool: _Pool,
    encoder: CatalogEncoder,
    tail: bytearray,
    *,
    key: str,
    max_width: int | None = None,
    space_code: int,
    space_width: int,
) -> tuple[list[Write], dict[str, object], list[dict[str, object]]]:
    payload = bytearray()
    pointer_writes: list[Write] = []
    records: list[dict[str, object]] = []
    for index, entry in enumerate(entries):
        visible, width = encoder.visible(str(entry["translation"]))
        if max_width is not None and width > max_width:
            raise ValueError(
                f"{key} {entry['translation']!r} is {width}px; field holds {max_width}px"
            )
        pad = ((max_width - width) // space_width) if max_width and entry.get("align") else 0
        encoded = bytes((space_code,)) * pad + visible + b"\xFF"
        if len(payload) + len(encoded) <= pool.end - pool.start:
            target = pool.start + len(payload)
            payload.extend(encoded)
            destination = "original_pool"
        else:
            target = TAIL_POOL[0] + len(tail)
            tail.extend(encoded)
            destination = "overflow"

        source = _number(str(entry["address"]))
        old = (source & 0xFFFF).to_bytes(2, "little")
        new = (target & 0xFFFF).to_bytes(2, "little")
        if pool.aligned_scan:
            assert pool.pointer_start is not None and pool.pointer_end is not None
            slots = [
                at for at in range(pool.pointer_start, pool.pointer_end, 2)
                if clean[at:at + 2] == old
            ]
        else:
            assert pool.pointer_start is not None
            at = pool.pointer_start + index * 2
            if clean[at:at + 2] != old:
                raise ValueError(f"{key} pointer {index} does not match {source:#x}")
            slots = [at]
        if not slots:
            raise ValueError(f"no pointer found for {key} entry at {source:#x}")
        for at in slots:
            pointer_writes.append(Write(at, new, f"{key}-pointer:{index}", False))
        records.append({
            "source": entry["source"], "translation": entry["translation"],
            "source_pc": f"0x{source:06X}", "target_pc": f"0x{target:06X}",
            "bytes": len(encoded) - 1, "width_px": width, "left_pad": pad,
            "destination": destination, "pointer_slots": len(slots),
        })

    replacement = bytes(payload) + b"\xFF" * (pool.end - pool.start - len(payload))
    writes = [Write(pool.start, replacement, f"{key}-pool", False), *pointer_writes]
    pool_report = {
        "name": key, "start": f"0x{pool.start:06X}", "end": f"0x{pool.end:06X}",
        "capacity": pool.end - pool.start, "used": len(payload),
    }
    return writes, pool_report, records


def build_unit_status_data(
    root: Path, clean: bytes, *, translation_dir: Path | None = None
) -> tuple[list[Write], dict[str, object]]:
    """Build all asserted writes and source routes for one complete status screen."""
    translations = translation_dir or root / "translations"
    text = json.loads((translations / "unit-status.th.json").read_text(encoding="utf-8"))
    abilities = json.loads(
        (translations / "unit-abilities.th.json").read_text(encoding="utf-8")
    )
    layout = json.loads((root / "font/encoding.json").read_text(encoding="utf-8"))
    model = json.loads((root / "font/thai.json").read_text(encoding="utf-8"))
    stock = StockCatalog.locked()
    encoder = CatalogEncoder(model, layout, stock)
    advances = advance_table(model, layout)
    space_code = int(layout["codes"][" "])
    space_width = advances[space_code]

    geometry = text["_layout"]
    ability_geometry = abilities["_layout"]
    for owner, item in (
        ("unit type pointers", geometry["type_pointers"]),
        ("unit type pool", geometry["type_pool"]),
        ("unit series pointers", geometry["series_pointers"]),
        ("unit series pool", geometry["series_pool"]),
        ("unit ability pointers", ability_geometry["pointer_scan"]),
        ("unit ability pool", ability_geometry["pool"]),
    ):
        _assert_hash(clean, item, owner)

    writes, fixed_routes, fixed_report = _fixed_screen(clean, text, layout, encoder)
    tail = bytearray()
    pools: list[dict[str, object]] = []
    entries: dict[str, list[dict[str, object]]] = {}
    groups = (
        (
            "unit_abilities", list(abilities["abilities"]),
            _Pool(0x1286F0, 0x128729, 0x12823B, 0x1282A8, True), None,
        ),
        (
            "unit_type_values", list(text["type_values"]),
            _Pool(0x1283FD, 0x128472, 0x128109, 0x128123), TYPE_MAX_WIDTH,
        ),
        (
            "unit_series_names", list(text["series_names"]),
            _Pool(0x12847E, 0x1284CB, 0x128143, 0x128155), SERIES_MAX_WIDTH,
        ),
    )
    for key, source_entries, pool, max_width in groups:
        group_writes, pool_report, records = _pack_group(
            clean, source_entries, pool, encoder, tail, key=key,
            max_width=max_width, space_code=space_code, space_width=space_width,
        )
        writes.extend(group_writes)
        pools.append(pool_report)
        entries[key] = records

    if TAIL_POOL[0] + len(tail) > TAIL_POOL[1]:
        raise ValueError("unit-status overflow exceeds the verified bank D2 tail")
    if tail:
        if clean[TAIL_POOL[0]:TAIL_POOL[0] + len(tail)] != b"\xFF" * len(tail):
            raise ValueError("unit-status overflow pool is not FF-filled")
        writes.append(Write(TAIL_POOL[0], bytes(tail), "unit-status-overflow", True))
    pools.append({
        "name": "unit_status_overflow", "start": f"0x{TAIL_POOL[0]:06X}",
        "end": f"0x{TAIL_POOL[1]:06X}", "capacity": TAIL_POOL[1] - TAIL_POOL[0],
        "used": len(tail),
    })

    return writes, {
        "fixed_fields": fixed_report,
        "source_routes": {"0xCC": [[start, end] for start, end in fixed_routes]},
        "pools": pools,
        "entries": entries,
        "overflow_bytes": len(tail),
        "overflow_end": f"0x{TAIL_POOL[0] + len(tail):06X}",
    }
