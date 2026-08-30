"""Verified fixed-label builder for the weapon list/detail page."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from .catalogs import Write
from .text.stock import encode_stock


BADGES = {
    "air": "Ai",
    "land": "La",
    "sea": "Wa",
    "space": "Sp",
}


def _number(value: str) -> int:
    return int(value, 0)


def build_weapon_detail_data(
    root: Path, clean: bytes, *, translation_dir: Path | None = None
) -> tuple[list[Write], dict[str, object]]:
    """Replace only asserted fixed fields; retain the stock page renderer."""
    translations = translation_dir or root / "translations"
    text = json.loads((translations / "weapon-detail.th.json").read_text(encoding="utf-8"))
    geometry = text["_layout"]
    layout = json.loads((root / "font/encoding.json").read_text(encoding="utf-8"))
    codes = layout["codes"]
    script = geometry["script"]
    script_start = _number(str(script["address"]))
    script_end = _number(str(script["end"]))
    actual_hash = sha256(clean[script_start:script_end]).hexdigest()
    expected_hash = str(script["source_sha256"])
    if actual_hash != expected_hash:
        raise ValueError(
            f"weapon-detail script hash mismatch: {actual_hash} != {expected_hash}"
        )

    entries = {str(item["key"]): item for item in text["fixed_labels"]}
    fields = geometry["fields"]
    if set(entries) != set(fields):
        raise ValueError("weapon-detail labels and field geometry do not match")

    blank = encode_stock(" ")
    writes: list[Write] = []
    routes: list[list[int]] = []
    report: list[dict[str, object]] = []
    for key, item in fields.items():
        start = _number(str(item["address"]))
        end = _number(str(item["end"]))
        expected = bytes.fromhex(str(item["source_hex"]))
        if len(expected) != end - start:
            raise ValueError(f"weapon-detail:{key} source span has the wrong size")
        if clean[start:end] != expected:
            raise ValueError(f"weapon-detail:{key} source mismatch at {start:#x}")

        translation = str(entries[key]["translation"])
        badge = BADGES.get(key)
        if badge is None:
            payload = encode_stock(translation)
            font = "stock"
        else:
            tokens = tuple(part + ">" for part in translation.split(">") if part)
            payload = bytes(int(codes[token]) for token in tokens)
            font = "thai_vwf"
        capacity = end - start
        if len(payload) > capacity:
            raise ValueError(
                f"weapon-detail:{key} needs {len(payload)} cells; holds {capacity}"
            )
        replacement = payload + blank * (capacity - len(payload))
        writes.append(Write(start, replacement, f"weapon-detail:{key}", False))
        if badge is not None:
            routes.append([(start + 1) & 0xFFFF, (start + len(payload) + 1) & 0xFFFF])
        report.append({
            "key": key,
            "source": entries[key]["source"],
            "translation": badge or translation,
            "pc": f"0x{start:06X}",
            "cells": len(payload),
            "capacity": capacity,
            "font": font,
        })

    return writes, {
        "script_start": f"0x{script_start:06X}",
        "script_end": f"0x{script_end:06X}",
        "fixed_fields": report,
        "source_routes": {"0xCC": routes},
    }
