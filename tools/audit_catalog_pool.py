#!/usr/bin/env python3
"""Audit whether catalog-13 sources cover every slot before migration.

This does not write a ROM.  It resolves a record's slots from the clean
pointer table when a legacy translation file only gives its original address,
which lets the migration gate reject a descriptor repoint with hidden holes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.catalog import load, read_slots  # noqa: E402

CLEAN = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
TRANSLATIONS = ROOT / "data" / "translations"


def number(value: object) -> int | None:
    try:
        return int(value, 0) if isinstance(value, str) else int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def slots_for(
    value: object,
    pointer_slots: dict[int, list[int]],
    d2_pc_start: int,
    d2_pc_end: int,
    *,
    accepts_direct_slots: bool,
) -> set[int]:
    """Find translated records whose declared source lies in catalog 13's bank.

    A bare ``source_pointer`` has no bank and occurs in unrelated catalogs
    (weapons are the common case), so it is deliberately ignored.  ``address``
    and ``source_pc`` are absolute PC offsets and are unambiguous.
    """
    found: set[int] = set()

    def visit(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, dict):
            return
        if "translation" in node:
            direct = node.get("slots")
            if accepts_direct_slots and isinstance(direct, list):
                found.update(int(slot) for slot in direct)
            for key in ("address", "source_pc"):
                pc = number(node.get(key))
                if pc is not None and d2_pc_start <= pc < d2_pc_end:
                    found.update(pointer_slots.get(pc & 0xFFFF, []))
        for child in node.values():
            visit(child)

    visit(value)
    return found


def owns_catalog_13(document: object) -> bool:
    """Whether a document's local ``slots`` fields belong to catalog 13."""
    if not isinstance(document, dict):
        return False
    layout = document.get("_layout")
    if not isinstance(layout, dict):
        return False
    table = layout.get("pointer_table")
    if not isinstance(table, dict):
        return False
    return table.get("cpu") == "$D2:8103" or table.get("address") == "0x128103"


def pilot_skill_slots(document: dict) -> set[int]:
    """Resolve the two catalog-13 windows onto pilot-status skill ids.

    Catalog 13 slots 224--287 are the same 32 special-skill ids twice: the
    second window changes only leading layout padding.  The pilot-status source
    declares the semantic ids, while its pool declaration proves their record
    order starts at `$D2:880E`.  Keep this mapping explicit so a changed source
    file cannot silently claim that the migration is complete.
    """
    expected = (
        tuple(range(32, 40)), tuple(range(40, 48)), (48,), (49,), (50,), (62,), (63,),
    )
    actual = tuple(tuple(item.get("ids", ())) for item in document.get("skills", ()))
    if actual != expected:
        raise SystemExit("pilot-status skill ids no longer match catalog-13 mapping")
    # IDs 51--61 are ten blank entries plus one blank alias in each window.
    translated = set(range(224, 243)) | {254, 255}
    translated |= set(range(256, 275)) | {286, 287}
    blanks = set(range(243, 254)) | set(range(275, 286))
    return translated | blanks


def pilot_spirit_slots(document: dict) -> set[int]:
    """Resolve the documented thirty spirit ids to catalog-13 slots 50--79."""
    ids = tuple(item.get("id") for item in document.get("spirits", ()))
    if ids != tuple(range(1, 31)):
        raise SystemExit("pilot-status spirit ids no longer match catalog-13 mapping")
    return set(range(50, 80))


def padded_main_menu_slots(document: dict) -> set[int]:
    """Map values whose translation address starts after stock zero padding."""
    expected = {"mono_value", "stereo_value", "none_value"}
    fields = {
        item.get("key")
        for item in document.get("fields", ())
        if isinstance(item, dict) and item.get("key") in expected
    }
    if fields != expected:
        raise SystemExit("main-menu padded values no longer match catalog-13 mapping")
    return {94, 95, 98}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "build/reports/catalog-13-coverage.json")
    args = parser.parse_args()

    rom = CLEAN.read_bytes()
    entry = next(item for item in load(rom) if item.index == 13)
    pointer_slots: dict[int, list[int]] = {}
    for slot, pointer in enumerate(read_slots(rom, entry)):
        pointer_slots.setdefault(pointer, []).append(slot)

    d2_pc_start = entry.pc & ~0xFFFF
    d2_pc_end = d2_pc_start + 0x10000
    coverage: dict[str, list[int]] = {}
    combined: set[int] = set()
    for path in sorted(TRANSLATIONS.glob("*.json")):
        try:
            document = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        slots = slots_for(
            document,
            pointer_slots,
            d2_pc_start,
            d2_pc_end,
            accepts_direct_slots=owns_catalog_13(document),
        )
        if slots:
            coverage[path.name] = sorted(slots)
            combined.update(slots)

    skills = json.loads((TRANSLATIONS / "pilot-status.th.json").read_text())
    skill_slots = pilot_skill_slots(skills)
    coverage["pilot-status.th.json#special-skills"] = sorted(skill_slots)
    combined.update(skill_slots)
    spirit_slots = pilot_spirit_slots(skills)
    coverage["pilot-status.th.json#spirits"] = sorted(spirit_slots)
    combined.update(spirit_slots)
    main_menu = json.loads((TRANSLATIONS / "main-menu-screens.th.json").read_text())
    padded_slots = padded_main_menu_slots(main_menu)
    coverage["main-menu-screens.th.json#padded-values"] = sorted(padded_slots)
    combined.update(padded_slots)

    missing = sorted(set(range(entry.slots)) - combined)
    payload = {
        "catalog": 13,
        "clean_descriptor": {"bank": f"${entry.bank:02X}", "address": f"${entry.address:04X}"},
        "slots": entry.slots,
        "sources": coverage,
        "covered_slots": len(combined),
        "missing_slots": missing,
        "coverage_complete": not missing,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"catalog 13: {len(combined)}/{entry.slots} slots covered; {len(missing)} missing")
    if missing:
        print("descriptor repoint blocked until every slot has a migrated record")
    else:
        print("coverage gate passes; compile and ROM verification are still required")


if __name__ == "__main__":
    main()
