"""Verified builder for the map unit-command menu and shield labels."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from .catalogs import CatalogEncoder, Write
from .text.stock import StockCatalog, encode_stock, mixed_segments


TERMINATOR = 0xFF


def _number(value: str) -> int:
    return int(value, 0)


def _assert_hash(clean: bytes, item: dict[str, object], owner: str) -> tuple[int, int]:
    start = _number(str(item["address"]))
    end = _number(str(item["end"]))
    actual = sha256(clean[start:end]).hexdigest()
    expected = str(item["source_sha256"])
    if actual != expected:
        raise ValueError(f"source hash mismatch for {owner}: {actual} != {expected}")
    return start, end


def _source(entry: dict[str, object], clean: bytes) -> tuple[int, bytes]:
    start = _number(str(entry["address"]))
    expected = bytes.fromhex(str(entry["source_hex"]))
    if not expected or expected[-1] != TERMINATOR:
        raise ValueError(f"unit-command source at {start:#x} has no terminator")
    if clean[start:start + len(expected)] != expected:
        raise ValueError(f"unit-command source mismatch at {start:#x}")
    return start, expected


def build_unit_commands_data(
    root: Path, clean: bytes, *, font_dir: Path | None = None,
) -> tuple[list[Write], dict[str, object]]:
    """Patch every label in its original slot; no pointer relocation is needed."""
    text = json.loads(
        (root / "translations/unit-commands.th.json").read_text(encoding="utf-8")
    )
    layout_info = text["_layout"]
    command_start, command_end = _assert_hash(
        clean, layout_info["command_block"], "unit-command block"
    )
    shield_start, shield_end = _assert_hash(
        clean, layout_info["shield_block"], "unit-shield block"
    )

    fonts = font_dir or root / "font"
    model = json.loads((fonts / "thai.json").read_text(encoding="utf-8"))
    layout = json.loads((fonts / "encoding.json").read_text(encoding="utf-8"))
    encoder = CatalogEncoder(model, layout, StockCatalog.locked())
    command_layout = layout_info["command_block"]
    visible_limit = int(command_layout.get(
        "legacy_visible_width_px", command_layout.get("visible_width_px", 0)
    ))
    if visible_limit <= 0:
        raise ValueError("unit-command compatibility width is not declared")

    writes: list[Write] = []
    command_report: list[dict[str, object]] = []
    cursor = command_start
    for entry in text["commands"]:
        start, expected = _source(entry, clean)
        if start != cursor:
            raise ValueError(f"unit-command block has an unexpected gap at {cursor:#x}")
        value = str(entry.get("legacy_translation", entry["translation"]))
        if mixed_segments(value) != [(True, value)]:
            raise ValueError(f"unit command {value!r} must use the stock font")
        encoded = encode_stock(value)
        width = len(value) * 8
        capacity = len(expected) - 1
        if len(encoded) > capacity or width > visible_limit:
            raise ValueError(
                f"unit command {value!r} needs {len(encoded)} bytes/{width}px; "
                f"slot holds {capacity} bytes/{visible_limit}px"
            )
        replacement = encoded + bytes((TERMINATOR,)) * (len(expected) - len(encoded))
        writes.append(Write(start, replacement, f"unit-command:{value}", False))
        command_report.append({
            "source": entry["source"], "translation": value,
            "pc": f"0x{start:06X}", "encoded_bytes": len(encoded),
            "slot_bytes": len(expected), "width_px": width,
            "font": "stock_direct", "pointer_relocated": False,
        })
        cursor += len(expected)
    if cursor != command_end:
        raise ValueError(f"unit-command block ends at {cursor:#x}; expected {command_end:#x}")

    shield_report: list[dict[str, object]] = []
    cursor = shield_start
    for entry in text["shield"]:
        start, expected = _source(entry, clean)
        if start != cursor:
            raise ValueError(f"unit-shield block has an unexpected gap at {cursor:#x}")
        value = str(entry["translation"])
        if mixed_segments(value) == [(True, value)]:
            raise ValueError(f"unit shield {value!r} must use Thai VWF")
        encoded, width = encoder.visible(value)
        capacity = len(expected) - 1
        if len(encoded) > capacity:
            raise ValueError(
                f"unit shield {value!r} needs {len(encoded)} bytes; slot holds {capacity}"
            )
        replacement = encoded + bytes((TERMINATOR,)) * (len(expected) - len(encoded))
        writes.append(Write(start, replacement, f"unit-shield:{value}", False))
        shield_report.append({
            "source": entry["source"], "translation": value,
            "pc": f"0x{start:06X}", "encoded_bytes": len(encoded),
            "slot_bytes": len(expected), "width_px": width,
            "font": "thai_vwf", "pointer_relocated": False,
        })
        cursor += len(expected)
    if cursor != shield_end:
        raise ValueError(f"unit-shield block ends at {cursor:#x}; expected {shield_end:#x}")

    return writes, {
        "commands": command_report,
        "shield": shield_report,
        "pointer_relocations": 0,
        "visible_command_owner": "p7-current-overlay",
        "legacy_command_owner": str(root / "translations/unit-commands.th.json"),
        "shield_owner": str(root / "translations/unit-commands.th.json"),
        "source_routes": {
            "0xD2": [[(shield_start & 0xFFFF) + 1, (shield_end & 0xFFFF) + 1]]
        },
    }
