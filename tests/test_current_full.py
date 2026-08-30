"""The promoted cumulative build must not depend on a pinned Git checkout."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from build_current_full import (  # noqa: E402
    DEFAULT_CLEAN,
    EXPECTED_SHA256,
    build_current,
)


def test_current_full_is_hash_locked_and_owned_by_workspace_source(tmp_path):
    output = tmp_path / "current.sfc"
    report = tmp_path / "current.json"

    digest = build_current(DEFAULT_CLEAN, output, report)

    assert digest == EXPECTED_SHA256
    assert output.stat().st_size == 4 * 1024 * 1024
    document = json.loads(report.read_text())
    owner = document["current_source"]
    assert owner["owner"] == "src/srw4/cumulative.py"
    assert owner["git_archive"] is False
    assert owner["story_records"] == 9382
    assert owner["battle_placement"]["owner"] == "current modules"
    map_menu = document["map_menu"]
    assert [item["translation"] for item in map_menu["labels"]] == [
        "จบเทิร์น", "รายชื่อ", "แผนที่", "หาพลังจิต",
        "คำสั่ง", "ระบบ", "ภารกิจ", "บันทึก",
    ]
    assert map_menu["encoded_bytes"] == 55
    assert map_menu["padding"] == 4
    for route in map_menu["source_routes"]["0xCC"]:
        assert [f"0x{value:04X}" for value in route] in document["catalog_routes"]["0xCC"]
    map_hud = document["map_hud"]
    assert [item["translation"] for item in map_hud["labels"]] == [
        "เทิร์น", "เงิน", "LOAD",
    ]
    for route in map_hud["source_routes"]["0xCC"]:
        assert [f"0x{value:04X}" for value in route] in document["catalog_routes"]["0xCC"]
    command = owner["command_placement"]
    assert all(hook["pc"] != "0x018B39" for hook in command["hooks"])
    glyph_stores = {"0x0184A8", "0x0184B0", "0x0184BD", "0x0184C5", "0x0184D4", "0x0184DC"}
    assert glyph_stores.isdisjoint({hook["pc"] for hook in command["hooks"]})
    assert "0x0389F5" not in {hook["pc"] for hook in command["hooks"]}
    assert command["cell_stream_bytes"] == 15 * 7
    assert all(hook["pc"] != "0x018456" for hook in command["hooks"])
    assert command["geometry_patch"] == {
        "owner": "p7-command-en-geometry",
        "pc": "0x0C966E",
        "bytes": 57,
        "catalog": "0x0022",
        "content_cells": 6,
        "cursor_adjust": -7,
    }
    geometry_pc = int(command["geometry_patch"]["pc"], 16)
    geometry = output.read_bytes()[geometry_pc:geometry_pc + 57]
    assert geometry.count(bytes.fromhex("F206")) == 4
    assert bytes.fromhex("0DFCF902") in geometry
    ele = next(
        row for row in document["catalogs"]["catalogs"]["pilots"]
        if row["source_pointer"] == "0x7119"
    )
    assert ele["translation"] == "เอเล ฮัมม์"
