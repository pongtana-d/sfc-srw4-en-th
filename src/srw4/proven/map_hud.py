"""Verified mixed-font builder for map HUD labels and value alignment."""

from __future__ import annotations

import json
from pathlib import Path

from .catalogs import Write
from .text.encoding import advance_table, encode
from .text.stock import encode_stock, mixed_segments


def build_map_hud_data(
    root: Path, clean: bytes, *, translation_dir: Path | None = None
) -> tuple[list[Write], dict[str, object]]:
    translations = translation_dir or root / "translations"
    data = json.loads(
        (translations / "map-hud.th.json").read_text(encoding="utf-8")
    )
    model = json.loads((root / "font/thai.json").read_text(encoding="utf-8"))
    layout = json.loads((root / "font/encoding.json").read_text(encoding="utf-8"))
    advances = advance_table(model, layout)
    pad = int(layout["codes"]["<Pad>"])
    writes: list[Write] = []
    labels: list[dict[str, object]] = []
    routes: dict[int, list[list[int]]] = {}
    for entry in data["labels"]:
        start = int(str(entry["address"]), 0)
        end = int(str(entry["end"]), 0)
        expected = bytes.fromhex(str(entry["source_hex"]))
        if len(expected) != end - start or clean[start:end] != expected:
            raise ValueError(f"map-HUD source mismatch at {start:#x}")
        value = str(entry["translation"])
        stock_only = mixed_segments(value) == [(True, value)]
        if stock_only:
            encoded = encode_stock(value)
            width = len(value) * 8
            font = "stock_direct"
        else:
            encoded = encode(
                value, layout["codes"], layout.get("shorthand"), layout.get("phrases")
            )
            width = sum(advances[code] for code in encoded)
            font = "thai_vwf"
        if len(encoded) > len(expected):
            raise ValueError(f"map-HUD label {value!r} does not fit its field")
        padding = len(expected) - len(encoded)
        payload = encoded + (
            encode_stock(" " * padding) if stock_only else bytes((pad,)) * padding
        )
        if not stock_only:
            bank = 0xC0 + (start >> 16)
            routes.setdefault(bank, []).append([
                ((start + 1) & 0xFFFF), ((end + 1) & 0xFFFF)
            ])
        writes.append(Write(start, payload, f"map-hud:{value}", False))
        labels.append({
            "source": entry["source"], "translation": value,
            "pc_start": f"0x{start:06X}", "pc_end": f"0x{end:06X}",
            "encoded_bytes": len(encoded), "capacity": len(expected),
            "padding": padding, "width_px": width,
            "font": font,
        })

    cursor_left: dict[int, list[int]] = {}
    values: list[dict[str, object]] = []
    for entry in data["_layout"]["dynamic_values"]:
        pc = int(str(entry["address"]), 0)
        expected = bytes.fromhex(str(entry["source_hex"]))
        if clean[pc:pc + len(expected)] != expected:
            raise ValueError(f"map-HUD dynamic control mismatch at {pc:#x}")
        pointer = int(str(entry["post_read_pointer"]), 0)
        if pointer != ((pc & 0xFFFF) + len(expected)):
            raise ValueError(f"map-HUD post-read pointer mismatch for {entry['name']}")
        pixels = int(entry["cursor_left_px"])
        if pixels != 8:
            raise ValueError("map-HUD Core adapter supports the verified 8px shift only")
        bank = 0xC0 + (pc >> 16)
        cursor_left.setdefault(bank, []).append(pointer)
        values.append({
            "name": entry["name"], "pc": f"0x{pc:06X}",
            "post_read_pointer": f"0x{pointer:04X}", "cursor_left_px": pixels,
        })
    return writes, {
        "labels": labels,
        "translation_source": str(translations / "map-hud.th.json"),
        "dynamic_values": values,
        "cursor_left_pointers": {
            f"0x{bank:02X}": pointers for bank, pointers in sorted(cursor_left.items())
        },
        "source_routes": {
            f"0x{bank:02X}": bank_routes for bank, bank_routes in sorted(routes.items())
        },
    }
