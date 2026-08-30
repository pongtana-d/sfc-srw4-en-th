"""The P7 overlay payload is derived from real command records, not guesses."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.catalog13 import build as build_catalog13  # noqa: E402
from srw4.command_overlay import (  # noqa: E402
    COMMAND_CELL_TOKENS, NATIVE_ADVANCED_SPAN, SERIALIZED_CELLS,
    SERIALIZED_ROW_BYTES, build, cell_streams, native_cell_route_table,
    native_index_table, native_route_table, MAX_LABEL_WIDTH, serialize,
)
from srw4.pipeline import Pipeline  # noqa: E402


def test_command_overlay_covers_the_verified_command_slots_with_compact_tiles():
    clean_path = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
    overlays = build(ROOT, clean_path.read_bytes(), Pipeline.load(ROOT, clean_path))

    assert tuple(item.source for item in overlays) == (
        "移動", "攻撃", "修理", "変形", "合体", "分離", "精神", "補給",
        "地中", "水中", "地上", "空中", "能力", "待機", "パーツ",
    )
    assert tuple(item.translation for item in overlays) == (
        "เคลื่อนที่", "โจมตี", "ซ่อม", "แปลงร่าง", "รวมร่าง", "แยกร่าง",
        "สปิริต", "เติมเสบียง", "ใต้ดิน", "ใต้น้ำ", "พื้นดิน", "ขึ้นบิน",
        "สถานะ", "รอ", "ชิ้นส่วน",
    )
    assert {slot for item in overlays for slot in item.slots} == set(range(112, 128))
    assert max(item.width_px for item in overlays) <= MAX_LABEL_WIDTH
    assert max(item.cells for item in overlays) == 6
    assert all(item.cells * 16 == len(item.tiles) for item in overlays)

    catalog = build_catalog13(ROOT, clean_path.read_bytes(), Pipeline.load(ROOT, clean_path))
    payload, report = serialize(overlays, catalog.pool)
    assert int.from_bytes(payload[:2], "little") == len(overlays) == 15
    assert report["bytes"] == len(payload)
    assert all(row["tile_bytes"] == SERIALIZED_ROW_BYTES for row in report["records"])
    assert len(payload) == 2 + len(overlays) * 8 + len(overlays) * SERIALIZED_ROW_BYTES
    assert len({row["start"] for row in report["records"]}) == 15
    assert all(int(row["tile_offset"][1:], 16) < len(payload) for row in report["records"])
    route = native_route_table(overlays, catalog.pool)
    assert len(route) == NATIVE_ADVANCED_SPAN * 2
    assert int.from_bytes(route[0:2], "little") == catalog.pool.slot_pointers[112]
    assert int.from_bytes(route[5 * 2:5 * 2 + 2], "little") == catalog.pool.slot_pointers[114]
    indices = native_index_table(overlays)
    assert indices[0] == 0
    assert indices[5] == 1
    assert indices[1] == 0xFF

    streams, pointers = cell_streams(overlays, address=0x5000)
    assert len(streams) == len(overlays) * (SERIALIZED_CELLS + 1)
    assert streams[:SERIALIZED_CELLS] == COMMAND_CELL_TOKENS
    assert streams[SERIALIZED_CELLS] == 0xFF
    cell_route = native_cell_route_table(overlays, pointers)
    assert int.from_bytes(cell_route[0:2], "little") == 0x5000
    assert int.from_bytes(cell_route[5 * 2:5 * 2 + 2], "little") == 0x5007
