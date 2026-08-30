"""Build the variable-length payload for catalog 13 without patching a ROM.

Catalog 13 and its window descriptor 16 share one pointer table.  This module
turns the current translation sources into one complete, catalog-tokenised
pool.  A build integration may only repoint the descriptors after the runtime
adapter for this pool is enabled.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .catalog import load, read_slots
from .catalog_pool import CatalogPool, CatalogRecord, compile_pool
from .pipeline import Pipeline
from .rom import RomError
from .text import Tokenizer, load_stock_codes

CATALOG_INDEX = 13
POOL_BANK = 0xFA
# The catalog-pool allocation begins at PC $3A:0000, which is CPU $FA:0000
# under this project's HiROM mapping.  Catalog pointers are 16-bit offsets,
# so the table and its records may validly occupy the lower half of this bank.
POOL_ADDRESS = 0x0000
_D2_PC_START = 0x120000
_D2_PC_END = 0x130000


@dataclass(frozen=True)
class Catalog13Build:
    pool: CatalogPool
    report: dict


def _number(value: object) -> int | None:
    try:
        return int(value, 0) if isinstance(value, str) else int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _owns_catalog_13(document: object) -> bool:
    if not isinstance(document, dict):
        return False
    layout = document.get("_layout")
    if not isinstance(layout, dict):
        return False
    table = layout.get("pointer_table")
    return isinstance(table, dict) and (
        table.get("cpu") == "$D2:8103" or table.get("address") == "0x128103"
    )


def _walk_records(value: object):
    if isinstance(value, dict):
        if "translation" in value:
            yield value
        for child in value.values():
            yield from _walk_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_records(child)


def _assign(
    targets: dict[int, tuple[str, str, int]],
    slots: set[int],
    translation: str,
    source: str,
    priority: int,
) -> None:
    for slot in slots:
        existing = targets.get(slot)
        if existing is None or priority > existing[2]:
            targets[slot] = (translation, source, priority)
        elif priority == existing[2] and translation != existing[0]:
            raise RomError(
                f"catalog 13 slot {slot} has conflicting translations "
                f"{existing[0]!r} ({existing[1]}) / {translation!r} ({source})"
            )


def _pilot_status_overrides(root: Path, targets: dict[int, tuple[str, str, int]]) -> None:
    document = json.loads((root / "data/translations/pilot-status.th.json").read_text())
    spirits = document.get("spirits", [])
    if tuple(item.get("id") for item in spirits) != tuple(range(1, 31)):
        raise RomError("pilot-status spirit ids no longer match catalog 13")
    for slot, item in zip(range(50, 80), spirits):
        _assign(targets, {slot}, str(item["translation"]), "pilot-status:spirit", 2)

    skills = document.get("skills", [])
    expected = (
        tuple(range(32, 40)), tuple(range(40, 48)), (48,), (49,), (50,), (62,), (63,),
    )
    if tuple(tuple(item.get("ids", ())) for item in skills) != expected:
        raise RomError("pilot-status skill ids no longer match catalog 13")
    for item, slots in zip(
        skills,
        (
            tuple(range(224, 232)) + tuple(range(256, 264)),
            tuple(range(232, 240)) + tuple(range(264, 272)),
            (240, 272), (241, 273), (242, 274), (254, 286), (255, 287),
        ),
    ):
        _assign(targets, set(slots), str(item["translation"]), "pilot-status:skill", 2)
    _assign(targets, set(range(243, 254)) | set(range(275, 286)), "", "pilot-status:blank", 2)


def _main_menu_overrides(root: Path, targets: dict[int, tuple[str, str, int]]) -> None:
    document = json.loads((root / "data/translations/main-menu-screens.th.json").read_text())
    values = {
        item.get("key"): str(item["translation"])
        for item in document.get("fields", [])
        if isinstance(item, dict) and item.get("key") in {"mono_value", "stereo_value", "none_value"}
    }
    if set(values) != {"mono_value", "stereo_value", "none_value"}:
        raise RomError("main-menu padded values no longer match catalog 13")
    for slot, key in ((94, "mono_value"), (95, "stereo_value"), (98, "none_value")):
        _assign(targets, {slot}, values[key], f"main-menu:{key}", 2)


def build(root: Path, clean: bytes, pipeline: Pipeline, *, bank: int = POOL_BANK, address: int = POOL_ADDRESS) -> Catalog13Build:
    """Compile all catalog-13 slots and return an uninstalled variable pool."""
    entry = next(item for item in load(clean) if item.index == CATALOG_INDEX)
    pointer_slots: dict[int, set[int]] = defaultdict(set)
    for slot, pointer in enumerate(read_slots(clean, entry)):
        pointer_slots[pointer].add(slot)

    targets: dict[int, tuple[str, str, int]] = {}
    translations = root / "data/translations"
    for path in sorted(translations.glob("*.json")):
        try:
            document = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        for record in _walk_records(document):
            translation = str(record["translation"])
            source = path.name
            if _owns_catalog_13(document) and isinstance(record.get("slots"), list):
                _assign(targets, {int(slot) for slot in record["slots"]}, translation, source, 3)
            for field in ("address", "source_pc"):
                pc = _number(record.get(field))
                if pc is not None and _D2_PC_START <= pc < _D2_PC_END:
                    _assign(targets, pointer_slots.get(pc & 0xFFFF, set()), translation, source, 1)

    _pilot_status_overrides(root, targets)
    _main_menu_overrides(root, targets)
    missing = sorted(set(range(entry.slots)) - set(targets))
    if missing:
        raise RomError(f"catalog 13 translation map misses {len(missing)} slots: {missing[:8]}")

    tokenizer = Tokenizer(
        set(json.loads((root / "data/font/renewal-icons.json").read_text())["glyphs"]),
        load_stock_codes(root / "data/font/renewal-stock.json"),
        engine="catalog",
    )
    grouped: dict[tuple[str, bytes], list[int]] = defaultdict(list)
    rows = []
    for slot in range(entry.slots):
        translation, source, _priority = targets[slot]
        text = translation if translation.endswith(("<ENDFF>", "<ENDF7>")) else translation + "<ENDFF>"
        tokenised = tokenizer.tokenize(text, where=f"catalog13[{slot}]")
        from .stream import encode  # local: avoids widening this module's public surface

        stream = encode(tokenised.pieces, pipeline.token_map).data
        grouped[(translation, stream)].append(slot)
        layout = pipeline.renderer.render(stream)
        rows.append({
            "slot": slot,
            "source": source,
            "translation": translation,
            "bytes": len(stream),
            "width_px": layout.lines[0].width if layout.lines else 0,
            "overflow_px": layout.lines[0].canvas.overflow if layout.lines else 0,
        })
    records = [
        CatalogRecord(translation, tuple(slots), stream)
        for (translation, stream), slots in grouped.items()
    ]
    pool = compile_pool(bank=bank, address=address, slots=entry.slots, records=records)
    return Catalog13Build(pool, {
        "catalog": CATALOG_INDEX,
        "stock": {"bank": f"${entry.bank:02X}", "address": f"${entry.address:04X}", "slots": entry.slots},
        "destination": {"bank": f"${bank:02X}", "address": f"${address:04X}", "end": f"${pool.end_address:04X}"},
        "records": rows,
        "unique_records": len(records),
        "bytes": len(pool.payload),
    })
