"""Thai labels and modifiers for the terrain-information window."""

from __future__ import annotations

import json
from pathlib import Path

from .catalogs import CatalogEncoder, Write
from .text.stock import StockCatalog, encode_stock


def _number(value: str) -> int:
    return int(value, 0)


def build_terrain_effect_data(
    root: Path, clean: bytes, *, translation_dir: Path | None = None
) -> tuple[list[Write], dict[str, object]]:
    """Replace the terrain window's labels without changing its runtime value."""
    translations = translation_dir or root / "translations"
    text = json.loads((translations / "terrain-effects.th.json").read_text(encoding="utf-8"))
    layout = json.loads((root / "font" / "encoding.json").read_text(encoding="utf-8"))
    model = json.loads((root / "font" / "thai.json").read_text(encoding="utf-8"))
    encoder = CatalogEncoder(model, layout, StockCatalog.locked())
    pad = int(layout["codes"]["<Pad>"])

    writes: list[Write] = []
    routes: list[tuple[int, int]] = []
    report: list[dict[str, object]] = []
    for entry in text["entries"]:
        start, end = _number(entry["address"]), _number(entry["end"])
        expected = bytes.fromhex(entry["source_hex"])
        if clean[start:end] != expected:
            raise ValueError(f"terrain effect source mismatch at {start:#08x}")
        kind = entry["kind"]
        if kind == "stock":
            payload = encode_stock(str(entry["translation"]))
            payload += b"\x00" * (len(expected) - len(payload))
        elif kind == "modifier":
            # The original's leading control bytes draw the live percentage.
            # Keep them first, then replace only the Japanese suffix.
            payload = expected[:3] + encode_stock(str(entry["translation"]))
            payload += b"\x00" * (len(expected) - len(payload) - 1) + b"\xFF"
        elif kind == "thai":
            encoded, width = encoder.visible(str(entry["translation"]))
            payload = encoded + bytes((pad,)) * (len(expected) - len(encoded) - 1) + b"\xFF"
            routes.append(((start + 1) & 0xFFFF, (start + len(payload) + 1) & 0xFFFF))
        else:
            raise ValueError(f"unknown terrain effect kind {kind!r}")
        if len(payload) != len(expected):
            raise ValueError(f"terrain effect {entry['translation']!r} does not fit")
        writes.append(Write(start, payload, f"terrain-effect:{entry['key']}", False))
        report.append({
            "key": entry["key"], "translation": entry["translation"],
            "bytes": len(payload),
            **({"width_px": width} if kind == "thai" else {}),
        })
    return writes, {"source_routes": {"0xD2": routes}, "entries": report}
