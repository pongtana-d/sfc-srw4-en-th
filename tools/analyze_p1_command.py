#!/usr/bin/env python3
"""Summarise the reproducible en unit-command-menu capture.

The live capture is produced by tools/lua/p1-command-probe.lua.  This tool
turns its before/after WRAM tilemap dumps into coordinate evidence, rather
than relying on a visual estimate from a screenshot.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


TILEMAP_START = 0x2000  # Offset of the 32x32 BG tilemap inside the 7E:8000 dump.
ROW_BYTES = 0x40        # 32 little-endian tile entries.
MENU_LABELS = {
    # $F0:E045 is entered beginning at the second byte below.  Keep the
    # leading byte: it is required for the visible initial M/A/S glyph.
    "Move": 0x3ED85C,    # CPU $FE:D85C, byte stream ends at FF.
    "Attack": 0x3ED864,  # CPU $FE:D864
    "Spirit": 0x3ED892,  # CPU $FE:D892
    "Status": 0x3ED8C6,  # CPU $FE:D8C6
}


def hirom_pc(cpu: int) -> int:
    bank, offset = cpu >> 16, cpu & 0xFFFF
    if not 0xC0 <= bank <= 0xFF or offset < 0x8000:
        raise ValueError(f"not a HiROM address: ${bank:02X}:{offset:04X}")
    return (bank - 0xC0) * 0x10000 + offset


def cpu_bytes(rom: bytes, cpu: int, length: int) -> str:
    start = hirom_pc(cpu)
    return rom[start : start + length].hex(" ")


def changed_cells(before: bytes, after: bytes) -> set[tuple[int, int]]:
    if len(before) != len(after):
        raise ValueError("tilemap dumps have different sizes")
    changed = set()
    for offset in range(0, len(before), 2):
        if before[offset : offset + 2] == after[offset : offset + 2]:
            continue
        relative = offset - TILEMAP_START
        if relative < 0 or relative >= 32 * ROW_BYTES:
            continue
        changed.add(((relative % ROW_BYTES) // 2, relative // ROW_BYTES))
    return changed


def components(cells: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    remaining = set(cells)
    found = []
    while remaining:
        component = {remaining.pop()}
        frontier = list(component)
        while frontier:
            x, y = frontier.pop()
            for neighbour in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    component.add(neighbour)
                    frontier.append(neighbour)
        found.append(component)
    return sorted(found, key=lambda group: (-len(group), min(group)))


def rect(cells: set[tuple[int, int]]) -> dict[str, int]:
    xs, ys = zip(*cells)
    left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
    return {
        "x_tiles": left,
        "y_tiles": top,
        "width_tiles": right - left + 1,
        "height_tiles": bottom - top + 1,
        "x_pixels": left * 8,
        "y_pixels": top * 8,
        "width_pixels": (right - left + 1) * 8,
        "height_pixels": (bottom - top + 1) * 8,
    }


def read_labels(rom: bytes) -> dict[str, dict[str, str]]:
    result = {}
    for label, offset in MENU_LABELS.items():
        end = rom.index(0xFF, offset)
        result[label] = {
            "cpu_start": f"$FE:{offset - 0x3E0000:04X}",
            "encoded_hex": rom[offset:end].hex(" "),
        }
    return result


def renderer_path(en: bytes, clean: bytes) -> dict[str, object]:
    hooks = (0xC184E4, 0xC19238)
    return {
        "shared_parser": {
            "cpu_range": "$C1:83C7-$C1:84E4",
            "pointer_table_read": "$C9:00D8,X / $C9:00D9,X",
            "runtime_pointer": "$00:1A-$00:1C",
            "en_bytes": cpu_bytes(en, 0xC183C7, 0x22),
            "clean_bytes": cpu_bytes(clean, 0xC183C7, 0x22),
        },
        "raster_hooks": [
            {
                "cpu": f"${cpu >> 16:02X}:{cpu & 0xFFFF:04X}",
                "clean": cpu_bytes(clean, cpu, 4),
                "en": cpu_bytes(en, cpu, 4),
            }
            for cpu in hooks
        ],
        "interpretation": (
            "en preserves the stock parser/pointer contract and replaces only "
            "the raster call with JSL $F0:E045."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--clean", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    cells = changed_cells(args.before.read_bytes(), args.after.read_bytes())
    groups = components(cells)
    if not groups:
        raise SystemExit("no changed BG tilemap cells")
    main_group = groups[0]
    payload = {
        "capture": {
            "before": str(args.before),
            "after": str(args.after),
            "tilemap_dump_base": "$7E:8000",
            "bg_tilemap_base": "$7E:A000",
            "row_tiles": 32,
        },
        "changed_cells": len(cells),
        "components": [
            {"changed_cells": len(group), "bounds": rect(group)} for group in groups
        ],
        "command_menu_component": {"changed_cells": len(main_group), "bounds": rect(main_group)},
        "labels": read_labels(args.rom.read_bytes()),
        "renderer_path": renderer_path(args.rom.read_bytes(), args.clean.read_bytes()),
    }
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
