"""Verified text data for the protagonist setup and naming flow."""

from __future__ import annotations

import json
from pathlib import Path

from .catalogs import Write
from .text.encoding import advance_table, encode
from .text.stock import encode_stock, mixed_segments


TERMINATOR = 0xFF


def _route_runs(start: int, flags: list[bool]) -> list[tuple[int, int]]:
    routes: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(flags):
        if not flags[cursor]:
            cursor += 1
            continue
        first = cursor
        while cursor < len(flags) and flags[cursor]:
            cursor += 1
        routes.append(((start + first + 1) & 0xFFFF, (start + cursor + 1) & 0xFFFF))
    return routes


def _encode_text(
    value: str, layout: dict[str, object], advances: bytes
) -> tuple[bytes, list[bool], int]:
    payload = bytearray()
    flags: list[bool] = []
    width = 0
    for stock, part in mixed_segments(value):
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
    return bytes(payload), flags, width


def build_protagonist_data(
    root: Path, clean: bytes, *, translation_dir: Path | None = None
) -> tuple[list[Write], dict[str, object]]:
    translations = translation_dir or root / "translations"
    data = json.loads(
        (translations / "protagonist-settings.th.json").read_text(
            encoding="utf-8"
        )
    )
    layout = json.loads((root / "font" / "encoding.json").read_text(encoding="utf-8"))
    model = json.loads((root / "font" / "thai.json").read_text(encoding="utf-8"))
    advances = advance_table(model, layout)
    pad = int(layout["codes"]["<Pad>"])
    writes: list[Write] = []
    report_items: list[dict[str, object]] = []
    routes: dict[int, list[tuple[int, int]]] = {}
    seen: set[tuple[int, int]] = set()

    for kind in ("fields", "records"):
        for entry in data[kind]:
            start = int(str(entry["address"]), 0)
            end = int(str(entry["end"]), 0)
            expected = bytes.fromhex(str(entry["source_hex"]))
            if (start, end) in seen:
                raise ValueError(f"duplicate protagonist field at {start:#x}")
            seen.add((start, end))
            if len(expected) != end - start or clean[start:end] != expected:
                raise ValueError(f"protagonist source mismatch at {start:#x}")
            encoded, flags, width = _encode_text(
                str(entry["translation"]), layout, advances
            )
            capacity = end - start
            if kind == "records":
                if len(encoded) + 1 > capacity:
                    raise ValueError(
                        f"protagonist {entry['key']} needs {len(encoded) + 1} bytes; "
                        f"holds {capacity}"
                    )
                payload = encoded + bytes((TERMINATOR,))
                flags.append(False)
                payload += bytes((TERMINATOR,)) * (capacity - len(payload))
                flags.extend([False] * (capacity - len(flags)))
            else:
                if len(encoded) > capacity:
                    raise ValueError(
                        f"protagonist {entry['key']} needs {len(encoded)} bytes; "
                        f"holds {capacity}"
                    )
                payload = encoded + bytes((pad,)) * (capacity - len(encoded))
                flags.extend([True] * (capacity - len(flags)))
            writes.append(Write(start, payload, f"protagonist:{entry['key']}", False))
            bank = 0xC0 + (start >> 16)
            routes.setdefault(bank, []).extend(_route_runs(start, flags))
            report_items.append({
                "key": entry["key"],
                "kind": kind[:-1],
                "source": entry["source"],
                "translation": entry["translation"],
                "pc_start": f"0x{start:06X}",
                "pc_end": f"0x{end:06X}",
                "encoded_bytes": len(encoded),
                "capacity": capacity,
                "width_px": width,
                "source_hex": expected.hex(" ").upper(),
            })

    return writes, {
        "items": report_items,
        "source_routes": {
            f"0x{bank:02X}": [[start, end] for start, end in sorted(bank_routes)]
            for bank, bank_routes in sorted(routes.items())
        },
    }
