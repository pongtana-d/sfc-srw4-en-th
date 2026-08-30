"""Verified mixed-font builder for the battle-map command menu."""

from __future__ import annotations

import json
from pathlib import Path

from .catalogs import Write
from .text.encoding import advance_table, encode
from .text.stock import encode_stock, mixed_segments


HEADER_BYTES = 4
LINE_BREAK = 0xF6
TERMINATOR = 0xF7
LABEL_COUNT = 8


def _route(start: int, length: int) -> list[int]:
    """Source-pointer range for bytes handled by the Thai renderer."""
    return [((start + 1) & 0xFFFF), ((start + length + 1) & 0xFFFF)]


def build_map_menu_data(
    root: Path, clean: bytes, *, translation_dir: Path | None = None
) -> tuple[list[Write], dict[str, object]]:
    """Replace the eight labels without changing the inline script footprint."""
    translations = translation_dir or root / "translations"
    data = json.loads(
        (translations / "map-menu.th.json").read_text(encoding="utf-8")
    )
    start = int(str(data["address"]), 0)
    end = int(str(data["end"]), 0)
    expected = bytes.fromhex(str(data["source_hex"]))
    if len(expected) != end - start or clean[start:end] != expected:
        raise ValueError(f"map-menu source mismatch at {start:#x}")

    model = json.loads((root / "font/thai.json").read_text(encoding="utf-8"))
    layout = json.loads((root / "font/encoding.json").read_text(encoding="utf-8"))
    advances = advance_table(model, layout)
    max_width = int(data.get("max_width_px", 8 * 8))
    external_tilemap = bool(data.get("external_tilemap", False))
    preserve = data.get("preserve_tilemap")

    labels = list(data["labels"])
    if len(labels) != LABEL_COUNT:
        raise ValueError(f"expected {LABEL_COUNT} map-menu labels")
    payload = bytearray(expected[:HEADER_BYTES])
    report: list[dict[str, object]] = []
    routes: list[list[int]] = []
    for index, entry in enumerate(labels):
        value = str(entry["translation"])
        stock_only = mixed_segments(value) == [(True, value)]
        if stock_only:
            encoded = encode_stock(value)
            width = len(value) * 8
            font = "stock_direct"
        else:
            encoded = encode(
                value,
                layout["codes"],
                layout.get("shorthand"),
                layout.get("phrases"),
            )
            width = sum(advances[code] for code in encoded)
            routes.append(_route(start + len(payload), len(encoded)))
            font = "thai_vwf"
        if width > max_width:
            raise ValueError(
                f"map-menu label {value!r} is {width}px; the field holds {max_width}px"
            )
        payload.extend(encoded)
        if index + 1 < len(labels):
            payload.append(LINE_BREAK)
        report.append({
            "source": entry["source"], "translation": value,
            "encoded_bytes": len(encoded), "width_px": width,
            "max_width_px": max_width, "font": font,
        })
    payload.append(TERMINATOR)
    used = len(payload)
    if used > len(expected):
        raise ValueError(f"map-menu script needs {used} bytes; holds {len(expected)}")
    payload.extend(bytes((TERMINATOR,)) * (len(expected) - used))
    preserve_report = None
    if preserve is not None:
        preserve_report = {
            "first_post_read_pointer": int(str(preserve["first_post_read_pointer"]), 0),
            "last_post_read_pointer": int(str(preserve["last_post_read_pointer"]), 0),
            "source_address": int(str(preserve["source_address"]), 0),
            "backup_address": int(str(preserve["backup_address"]), 0),
            "row_bytes": int(preserve["row_bytes"]),
            "rows": int(preserve["rows"]),
            "stride": int(preserve["stride"]),
        }
        if preserve_report["first_post_read_pointer"] != routes[0][0]:
            raise ValueError("map-menu tilemap snapshot does not start on the first Thai byte")
        if preserve_report["last_post_read_pointer"] != routes[-1][1] - 1:
            raise ValueError("map-menu tilemap restore does not follow the last Thai byte")
    return [Write(start, bytes(payload), "map-command-menu", False)], {
        "pc_start": f"0x{start:06X}", "pc_end": f"0x{end:06X}",
        "encoded_bytes": used, "capacity": len(expected),
        "padding": len(expected) - used, "labels": report,
        "translation_source": str(translations / "map-menu.th.json"),
        "source_routes": (
            {f"0x{0xC0 + (start >> 16):02X}": routes} if routes else {}
        ),
        "renderer_route": ({
            "bank": f"0x{0xC0 + (start >> 16):02X}",
            "start": routes[0][0], "end": routes[-1][1],
            "external_tilemap": external_tilemap,
            "preserve_tilemap": preserve_report,
        } if routes else None),
    }
