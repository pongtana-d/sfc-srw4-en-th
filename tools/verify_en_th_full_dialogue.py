#!/usr/bin/env python3
"""Verify the active EN story pointer graph after a Thai dialogue build."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_baseline import EN_SHA256
from srw4.en_dialogue_streams import compile_text
from srw4.rom import sha256
from srw4.script import read_master_table


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=ROOT / "build" / "srw4-en-th.sfc")
    args = parser.parse_args()
    rom = args.rom.read_bytes()
    source = json.loads((ROOT / "data" / "translations" / "script.source.json").read_text())
    translations = json.loads((ROOT / "data" / "translations" / "script.th.json").read_text())["messages"]
    layout = json.loads((ROOT / "data" / "font" / "encoding.json").read_text())
    streams = {key: compile_text(value, layout) for key, value in translations.items()}
    if len(streams) != 9382:
        raise SystemExit(f"expected 9382 translated records, got {len(streams)}")
    master = read_master_table(rom)
    active = [block for block in source["summary"]["blocks"] if block.get("kind") != "unused"]
    grouped: dict[int, list[tuple[int, int, dict]]] = {}
    for block in active:
        slot = int(block["slot"])
        bank, start = master[slot]
        if not bank or not start:
            raise SystemExit(f"active story block {slot} has null master pointer")
        grouped.setdefault(bank, []).append((start, slot, block))
    pointer_count = 0
    for bank, items in grouped.items():
        items.sort()
        if len({start for start, _, _ in items}) != len(items):
            raise SystemExit(f"story bank ${bank:02X} has duplicate block starts")
        for index, (start, slot, block) in enumerate(items):
            end = items[index + 1][0] if index + 1 < len(items) else 0x10000
            table_end = start + int(block["pointers"]) * 2
            if table_end >= end:
                raise SystemExit(f"story block {slot} has no payload interval")
            pc = (bank & 0x3F) << 16 | start
            for pointer in range(int(block["pointers"])):
                address = rom[pc + pointer * 2] | rom[pc + pointer * 2 + 1] << 8
                if not table_end <= address < end:
                    raise SystemExit(f"story block {slot}, pointer {pointer}: ${address:04X} outside payload")
                pointer_count += 1
    print(json.dumps({
        "schema": "srw4-en-th-dialogue-verify/1",
        "rom_sha256": sha256(rom),
        "expected_base_sha256": EN_SHA256,
        "blocks": len(active),
        "records": len(streams),
        "table_pointers": pointer_count,
        "status": "ok",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
