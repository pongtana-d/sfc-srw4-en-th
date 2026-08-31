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
from srw4.en_dialogue_font import BATTLE_QUOTE_PADDING, BATTLE_QUOTE_PADDING_TOKEN
from srw4.en_dialogue_streams import PrecomposedDialogueCompiler
from srw4.en_precomposed import (
    ADVANCE_PC as PRECOMPOSED_ADVANCE_PC,
    PAGE_BYTES as PRECOMPOSED_PAGE_BYTES,
    PAGE_COUNT as PRECOMPOSED_PAGE_COUNT,
    PAGE_PC as PRECOMPOSED_PAGE_PC,
    WIDTH_PC as PRECOMPOSED_WIDTH_PC,
    build_assets as build_precomposed_assets,
    slot_for_token,
)
from srw4.rom import sha256
from srw4.script import read_master_table


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=ROOT / "build" / "srw4-en-th.sfc")
    args = parser.parse_args()
    rom = args.rom.read_bytes()
    base = (ROOT / "rom" / "Dai-4-ji Super Robot Taisen English.sfc").read_bytes()
    if sha256(base) != EN_SHA256:
        raise SystemExit("workspace EN base ROM does not match the pinned hash")
    source = json.loads((ROOT / "data" / "translations" / "script.source.json").read_text())
    translations = json.loads((ROOT / "data" / "translations" / "script.th.json").read_text())["messages"]
    rows_by_block: dict[int, list[dict]] = {}
    for row in source["messages"]:
        rows_by_block.setdefault(int(row["block"]), []).append(row)
    branch_ranges = {
        block: range(
            min(int(row["offset"], 0) for row in rows),
            int(next(item for item in source["summary"]["blocks"]
                     if int(item["slot"]) == block)["extent"], 0) + 1,
        )
        for block, rows in rows_by_block.items()
    }
    compiler = PrecomposedDialogueCompiler()
    streams = {
        str(row["id"]): compiler.compile(
            translations[str(row["id"])],
            where=str(row["id"]),
            branch_range=branch_ranges[int(row["block"])],
        )
        for row in source["messages"]
    }
    if len(streams) != 9382:
        raise SystemExit(f"expected 9382 translated records, got {len(streams)}")
    assets = build_precomposed_assets(base)
    for page in range(PRECOMPOSED_PAGE_COUNT):
        page_at = PRECOMPOSED_PAGE_PC + page * PRECOMPOSED_PAGE_BYTES
        if rom[page_at:page_at + PRECOMPOSED_PAGE_BYTES] != assets.pages[page]:
            raise SystemExit(f"precomposed glyph page {page} differs from editable font source")
        advance_at = PRECOMPOSED_ADVANCE_PC + page * 0x100
        if rom[advance_at:advance_at + 0x100] != assets.advances[page]:
            raise SystemExit(f"precomposed advance page {page} differs from editable font source")
        width_at = PRECOMPOSED_WIDTH_PC + page * 0x100
        if rom[width_at:width_at + 0x100] != assets.widths[page]:
            raise SystemExit(f"precomposed EN-width page {page} differs from editable font source")
    pad_page, pad_slot = slot_for_token(assets.token_map, BATTLE_QUOTE_PADDING_TOKEN)
    if BATTLE_QUOTE_PADDING != assets.token_map.encode_glyph(BATTLE_QUOTE_PADDING_TOKEN):
        raise SystemExit("battle quote padding does not use the locked precomposed token")
    if len(BATTLE_QUOTE_PADDING) != 2:
        raise SystemExit("battle quote padding changed the EN dispatch record length")
    if assets.advances[pad_page][pad_slot] != 0 or any(
        assets.pages[pad_page][pad_slot * 16:(pad_slot + 1) * 16]
    ):
        raise SystemExit("battle quote padding is not blank and zero-advance")
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
        "precomposed_tokens": len(assets.token_map.tokens),
        "precomposed_pages": PRECOMPOSED_PAGE_COUNT,
        "status": "ok",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
