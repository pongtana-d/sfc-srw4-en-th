"""Verified Thai VWF builder for main and system menu screens."""

from __future__ import annotations

import json
from pathlib import Path

from .catalogs import Write
from .text.encoding import advance_table, encode
from .text.stock import encode_stock, mixed_segments


LINE_BREAK = 0xF6


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


def _encode_text(
    value: str, layout: dict[str, object], advances: bytes
) -> tuple[bytes, list[bool], list[int]]:
    payload = bytearray()
    flags: list[bool] = []
    widths: list[int] = []
    lines = value.split("\n")
    for line_index, line in enumerate(lines):
        width = 0
        for stock, part in mixed_segments(line):
            if stock:
                encoded = encode_stock(part)
                payload.extend(encoded)
                flags.extend([False] * len(encoded))
                width += len(part) * 8
            else:
                encoded = encode(
                    part, layout["codes"], layout.get("shorthand"), layout.get("phrases")
                )
                payload.extend(encoded)
                flags.extend([True] * len(encoded))
                width += sum(advances[code] for code in encoded)
        widths.append(width)
        if line_index + 1 < len(lines):
            payload.append(LINE_BREAK)
            flags.append(False)
    return bytes(payload), flags, widths


def build_main_menu_data(
    root: Path, clean: bytes, *, translation_dir: Path | None = None
) -> tuple[list[Write], dict[str, object]]:
    translations = translation_dir or root / "translations"
    data = json.loads((translations / "main-menu-screens.th.json").read_text(encoding="utf-8"))
    model = json.loads((root / "font/thai.json").read_text(encoding="utf-8"))
    layout = json.loads((root / "font/encoding.json").read_text(encoding="utf-8"))
    advances = advance_table(model, layout)
    pad = int(layout["codes"]["<Pad>"])

    writes: list[Write] = []
    fields: list[dict[str, object]] = []
    routes: dict[int, list[tuple[int, int]]] = {}
    seen: set[tuple[int, int]] = set()
    for entry in data["fields"]:
        start = int(str(entry["address"]), 0)
        end = int(str(entry["end"]), 0)
        expected = bytes.fromhex(str(entry["source_hex"]))
        if len(expected) != end - start or clean[start:end] != expected:
            raise ValueError(f"main-menu source mismatch at {start:#x}")
        if (start, end) in seen:
            raise ValueError(f"duplicate main-menu field at {start:#x}")
        seen.add((start, end))

        encoded, flags, widths = _encode_text(str(entry["translation"]), layout, advances)
        capacity = end - start
        if len(encoded) > capacity:
            raise ValueError(
                f"main-menu {entry['key']} needs {len(encoded)} bytes; holds {capacity}"
            )
        padding = capacity - len(encoded)
        payload = encoded + bytes((pad,)) * padding
        flags.extend([True] * padding)
        writes.append(Write(start, payload, f"main-menu:{entry['key']}", False))
        bank = 0xC0 + (start >> 16)
        routes.setdefault(bank, []).extend(_route_runs(start, flags))
        fields.append({
            "key": entry["key"], "screen": entry["screen"],
            "source": entry["source"], "translation": entry["translation"],
            "pc_start": f"0x{start:06X}", "pc_end": f"0x{end:06X}",
            "encoded_bytes": len(encoded), "capacity": capacity,
            "padding": padding, "line_widths_px": widths,
            "lines": len(widths), "stock_encoding": "direct",
        })
    return writes, {
        "fields": fields,
        "source_routes": {
            f"0x{bank:02X}": [[start, end] for start, end in sorted(bank_routes)]
            for bank, bank_routes in sorted(routes.items())
        },
    }
