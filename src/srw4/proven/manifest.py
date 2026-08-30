"""Load and validate the central ROM map."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..rom import cpu_to_pc


def parse_address(value: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise ValueError(f"address must use 0x notation: {value!r}")
    return int(value, 16)


def load_rom_map(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported ROM map schema")
    rom = data.get("rom", {})
    for key in ("input_size", "expanded_size", "sha256", "mapper"):
        if key not in rom:
            raise ValueError(f"ROM map is missing rom.{key}")
    validate_ranges(data)
    return data


def load_hooks(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported hook registry schema")
    seen: set[str] = set()
    for hook in data.get("hooks", []):
        hook_id = str(hook["id"])
        if hook_id in seen:
            raise ValueError(f"duplicate hook id: {hook_id}")
        seen.add(hook_id)
        pc = parse_address(hook["pc"])
        cpu_text = str(hook["cpu"])
        bank_text, address_text = cpu_text.removeprefix("$").split(":", 1)
        cpu = (int(bank_text, 16) << 16) | int(address_text, 16)
        if cpu_to_pc(cpu >> 16, cpu & 0xFFFF) != pc:
            raise ValueError(f"CPU/PC mismatch in hook {hook_id}")
        expected = bytes.fromhex(str(hook["expected"]))
        replacement = bytes.fromhex(str(hook["legacy_replacement"]))
        if len(expected) != len(replacement):
            raise ValueError(f"hook length mismatch in {hook_id}")
        active = hook.get("active_replacement")
        if active is not None and len(bytes.fromhex(str(active))) != len(expected):
            raise ValueError(f"active hook length mismatch in {hook_id}")
    return data


def validate_ranges(data: dict[str, Any]) -> None:
    """Validate shape and bounds; legacy pools may intentionally be non-contiguous."""
    limit = int(data["rom"]["expanded_size"])
    for section in ("pointer_tables", "legacy_string_pools"):
        seen: set[str] = set()
        for item in data.get(section, []):
            item_id = str(item["id"])
            if item_id in seen:
                raise ValueError(f"duplicate {section} id: {item_id}")
            seen.add(item_id)
            start = parse_address(item["start"])
            end = parse_address(item["end"])
            if not 0 <= start < end <= limit:
                raise ValueError(f"invalid {section} range {item_id}: {start:#x}-{end:#x}")

            entries = item.get("entries")
            entry_bytes = item.get("entry_bytes")
            if entries is not None and entry_bytes is not None:
                if end - start != int(entries) * int(entry_bytes):
                    raise ValueError(f"size mismatch in {section} range {item_id}")
