"""Repack the current audited story corpus into the proven cumulative ROM."""
from __future__ import annotations

import json
from pathlib import Path

from .proven.catalog_router import build_route_tables
from .proven.story import build_story_data
from .rom import Rom, sha256


ROOT = Path(__file__).resolve().parents[2]
CLEAN = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
SOURCE = ROOT / "data" / "translations" / "script.source.json"
TRANSLATION = ROOT / "data" / "translations" / "script.th.json"
LAYOUT = ROOT / "data" / "proven" / "font" / "encoding.json"
TRANSLATIONS = ROOT / "data" / "translations"
MEMORY_MAP = ROOT / "data" / "proven" / "config" / "memory-map.json"
ROUTE_TABLE_PC = 0x3C0000
ROUTE_TABLE_CAPACITY = 0x10000


def _routes(rows: dict[str, list[list[str | int]]]) -> dict[int, list[tuple[int, int]]]:
    return {
        int(bank, 16): [
            (int(start, 16) if isinstance(start, str) else int(start),
             int(end, 16) if isinstance(end, str) else int(end))
            for start, end in ranges
        ]
        for bank, ranges in rows.items()
    }


def apply(image: bytes, cumulative_report: dict) -> tuple[bytes, dict]:
    """Replace pinned story data/routes with the current source and translation."""
    clean = CLEAN.read_bytes()
    writes, story = build_story_data(
        ROOT,
        clean,
        source_path=SOURCE,
        translation_path=TRANSLATION,
        layout_path=LAYOUT,
        translation_dir=TRANSLATIONS,
        allocation_path=MEMORY_MAP,
    )
    payload = bytearray(image)
    for write in writes:
        payload[write.pc:write.pc + len(write.payload)] = write.payload

    routes = _routes(cumulative_report["catalog_routes"])
    current_story_routes = _routes(story["source_routes"])
    for bank in tuple(routes):
        if 0xF0 <= bank <= 0xF9:
            del routes[bank]
    routes.update(current_story_routes)
    fixed_routes = _routes(cumulative_report["fixed_routes"])
    route_table = build_route_tables(routes, fixed_routes)
    if len(route_table) > ROUTE_TABLE_CAPACITY:
        raise ValueError("current story route table exceeds bank $FC")
    payload[ROUTE_TABLE_PC:ROUTE_TABLE_PC + ROUTE_TABLE_CAPACITY] = bytes(
        (0xFF,)
    ) * ROUTE_TABLE_CAPACITY
    payload[ROUTE_TABLE_PC:ROUTE_TABLE_PC + len(route_table)] = route_table

    rom = Rom(payload)
    checksum = rom.fix_checksum()
    final = rom.to_bytes()
    report = {
        "story": story,
        "route_table": {
            "pc": f"0x{ROUTE_TABLE_PC:06X}",
            "bytes": len(route_table),
            "capacity": ROUTE_TABLE_CAPACITY,
        },
        "output": {
            "bytes": len(final),
            "sha256": sha256(final),
            "checksum": f"0x{checksum:04X}",
        },
    }
    return final, report
