#!/usr/bin/env python3
"""Classify every master catalog entry and reject unowned string tables."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.catalog import MASTER_SLOTS, load, read_master  # noqa: E402

CLEAN = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
REPORT = ROOT / "build" / "reports" / "catalog-residue.json"
OWNERS = {
    0: "menu.field_screens",
    1: "menu.intermission",
    2: "intro.crawl_pages+menu.part_effects",
    3: "null",
    4: "catalog.unit_names",
    5: "catalog.unit_names:window-256",
    6: "catalog.pilot_names",
    7: "story.runtime_fb_names+catalog.battle_pilot_labels",
    8: "catalog.weapon_names",
    9: "catalog.weapon_names:window-256",
    10: "catalog.weapon_names:window-512",
    11: "map.terrain_names",
    12: "menu.bgm_titles:exception",
    13: "catalog.labels",
    14: "menu.scenario_titles",
    15: "battle.status_tokens:unused-verified",
    16: "catalog.labels:window-224",
    17: "song.lyrics:exception",
    18: "graphics:not-text",
}


def main() -> int:
    clean = CLEAN.read_bytes()
    master = read_master(clean)
    descriptors = {item.index: item for item in load(clean)}
    if len(master) != MASTER_SLOTS or set(OWNERS) != set(range(MASTER_SLOTS)):
        raise SystemExit("master catalog ownership table is incomplete")
    if master[3] != (0, 0):
        raise SystemExit(f"catalog 3 is no longer null: {master[3]}")
    if master[18] != (0xA2, 0x0263):
        raise SystemExit(f"catalog 18 graphics pointer changed: {master[18]}")
    unknown = sorted(set(descriptors) - set(OWNERS))
    items = []
    for index, (bank, address) in enumerate(master):
        descriptor = descriptors.get(index)
        items.append({
            "index": index,
            "cpu": f"${bank:02X}:{address:04X}",
            "owner": OWNERS[index],
            "kind": "null" if index == 3 else "graphics" if index == 18 else "text",
            "slots": None if descriptor is None else descriptor.slots,
            "window_of": None if descriptor is None else descriptor.window_of,
        })
    report = {"entries": MASTER_SLOTS, "classified": len(items),
              "unknown": unknown, "items": items}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(f"master catalogs: {len(items)}/{MASTER_SLOTS} classified, unknown={len(unknown)}")
    return 1 if unknown else 0


if __name__ == "__main__":
    raise SystemExit(main())
