"""Current menu translations own production payloads independently of font snapshots."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.proven.map_hud import build_map_hud_data
from srw4.proven.map_menu import build_map_menu_data
from srw4.proven.naming import build_naming_data
from srw4.proven.main_menu import build_main_menu_data
from srw4.proven.option_menu import (
    FREE_RUN,
    build_en_part_effect_data,
    build_option_menu_data,
    build_part_effect_data,
)
from srw4.proven.pilot_status import build_pilot_status_data
from srw4.proven.protagonist import build_protagonist_data
from srw4.proven.spirit_help import build_spirit_help_data
from srw4.proven.terrain_effects import build_terrain_effect_data
from srw4.proven.unit_status import build_unit_status_data
from srw4.proven.unit_commands import build_unit_commands_data
from srw4.proven.catalogs import CatalogEncoder
from srw4.proven.text.stock import StockCatalog
from srw4.proven.weapon_detail import build_weapon_detail_data
from srw4.en_th_catalogs import ClusterCatalogEncoder, build_part_stock_catalog


CLEAN = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
SNAPSHOT = ROOT / "data" / "proven" / "full"
CURRENT = ROOT / "data" / "translations"


def test_current_map_hud_uses_thai_vwf_and_preserves_dynamic_value_controls():
    clean = CLEAN.read_bytes()
    snapshot_writes, _ = build_map_hud_data(SNAPSHOT, clean)
    current_writes, report = build_map_hud_data(
        SNAPSHOT, clean, translation_dir=CURRENT
    )
    assert current_writes != snapshot_writes
    assert [item["translation"] for item in report["labels"]] == [
        "เทิร์น", "เงิน", "LOAD",
    ]
    assert [item["font"] for item in report["labels"]] == [
        "thai_vwf", "thai_vwf", "stock_direct",
    ]
    assert report["source_routes"]["0xCC"] == [
        [0x9647, 0x964E], [0x9652, 0x9656],
    ]
    assert [item["name"] for item in report["dynamic_values"]] == [
        "turn_value", "funds_value",
    ]
    assert Path(report["translation_source"]) == CURRENT / "map-hud.th.json"


def test_current_map_menu_uses_thai_vwf_within_its_byte_and_width_limits():
    clean = CLEAN.read_bytes()
    snapshot_writes, _ = build_map_menu_data(SNAPSHOT, clean)
    current_writes, report = build_map_menu_data(
        SNAPSHOT, clean, translation_dir=CURRENT
    )
    assert current_writes != snapshot_writes
    assert [item["translation"] for item in report["labels"]] == [
        "จบเทิร์น", "รายชื่อ", "แผนที่", "หาพลังจิต",
        "คำสั่ง", "ระบบ", "ภารกิจ", "บันทึก",
    ]
    assert all(item["font"] == "thai_vwf" for item in report["labels"])
    assert all(item["width_px"] <= item["max_width_px"] for item in report["labels"])
    assert report["encoded_bytes"] == 55
    assert report["capacity"] == 59
    assert report["padding"] == 4
    assert len(report["source_routes"]["0xCC"]) == 8
    assert report["renderer_route"]["preserve_tilemap"] == {
        "first_post_read_pointer": 0x95EF,
        "last_post_read_pointer": 0x9620,
        "source_address": 0x7E8040,
        "backup_address": 0x7FF000,
        "row_bytes": 24,
        "rows": 6,
        "stride": 64,
    }
    assert Path(report["translation_source"]) == CURRENT / "map-menu.th.json"


def test_current_surface_payloads_match_the_runtime_snapshot_byte_for_byte():
    clean = CLEAN.read_bytes()
    builders = (
        build_unit_status_data,
        build_spirit_help_data,
        build_main_menu_data,
        build_protagonist_data,
        build_terrain_effect_data,
    )
    for builder in builders:
        snapshot_writes, _ = builder(SNAPSHOT, clean)
        current_writes, _ = builder(SNAPSHOT, clean, translation_dir=CURRENT)
        assert current_writes == snapshot_writes, builder.__name__

    snapshot_writes, _ = build_weapon_detail_data(SNAPSHOT, clean)
    current_writes, report = build_weapon_detail_data(
        SNAPSHOT, clean, translation_dir=CURRENT
    )
    snapshot_by_owner = {write.owner: write for write in snapshot_writes}
    current_by_owner = {write.owner: write for write in current_writes}
    assert current_by_owner.keys() == snapshot_by_owner.keys()
    assert current_by_owner["weapon-detail:power"] != snapshot_by_owner["weapon-detail:power"]
    assert {
        owner: write for owner, write in current_by_owner.items()
        if owner != "weapon-detail:power"
    } == {
        owner: write for owner, write in snapshot_by_owner.items()
        if owner != "weapon-detail:power"
    }
    power = next(item for item in report["fixed_fields"] if item["key"] == "power")
    assert power["translation"] == "PWR"
    assert power["cells"] == 3
    assert power["capacity"] == 6

    _, unit_report = build_unit_status_data(SNAPSHOT, clean)
    overflow = int(unit_report["overflow_end"], 16)
    snapshot_writes, _ = build_pilot_status_data(
        SNAPSHOT, clean, overflow_start=overflow
    )
    current_writes, _ = build_pilot_status_data(
        SNAPSHOT, clean, overflow_start=overflow, translation_dir=CURRENT
    )
    assert current_writes == snapshot_writes

    snapshot_writes, _ = build_unit_commands_data(SNAPSHOT, clean)
    current_writes, report = build_unit_commands_data(ROOT / "data", clean)
    snapshot_by_owner = {write.owner: write for write in snapshot_writes}
    current_by_owner = {write.owner: write for write in current_writes}
    assert current_by_owner.keys() == snapshot_by_owner.keys()
    assert {
        owner: write for owner, write in current_by_owner.items()
        if not owner.startswith("unit-shield:")
    } == {
        owner: write for owner, write in snapshot_by_owner.items()
        if not owner.startswith("unit-shield:")
    }
    assert current_by_owner["unit-shield:ไม่มีโล่"].payload == bytes.fromhex(
        "40 B3 A3 CB FF FF FF"
    )
    assert current_by_owner["unit-shield:มีโล่"].payload == bytes.fromhex(
        "A3 CB FF FF FF FF FF"
    )
    assert Path(report["shield_owner"]) == CURRENT / "unit-commands.th.json"
    assert Path(report["legacy_command_owner"]) == CURRENT / "unit-commands.th.json"
    assert report["visible_command_owner"] == "p7-current-overlay"

    snapshot_writes, _ = build_naming_data(SNAPSHOT, clean)
    current_writes, _ = build_naming_data(
        SNAPSHOT, clean, translation_dir=CURRENT
    )
    assert current_writes == snapshot_writes

    snapshot_writes, _ = build_option_menu_data(SNAPSHOT, clean, FREE_RUN[0])
    current_writes, _ = build_option_menu_data(
        SNAPSHOT, clean, FREE_RUN[0], translation_dir=CURRENT
    )
    assert current_writes == snapshot_writes


def test_shield_tail_is_one_renderer_call_instead_of_a_separate_tone_byte():
    import json

    model = json.loads((ROOT / "data/font/thai.json").read_text(encoding="utf-8"))
    layout = json.loads((ROOT / "data/font/encoding.json").read_text(encoding="utf-8"))
    encoder = CatalogEncoder(model, layout, StockCatalog.locked())

    no_shield, no_shield_width = encoder.visible("ไม่มีโล่")
    shield, shield_width = encoder.visible("มีโล่")
    assert no_shield == bytes.fromhex("40 B3 A3 CB")
    assert shield == bytes.fromhex("A3 CB")
    assert (no_shield_width, shield_width) == (33, 19)
    assert layout["phrase_expansions"]["โล่"] == ["โ", "ล", "่"]


def test_en_part_effect_stage_rebuilds_active_fe_catalog_without_part_names():
    clean = (ROOT / "rom/Dai-4-ji Super Robot Taisen (English combo).sfc").read_bytes()
    part_stock, en_direct_runs = build_part_stock_catalog()
    encoder = ClusterCatalogEncoder(
        clean,
        part_stock,
        include_part_effects=True,
        en_direct_stock_runs=en_direct_runs,
    )
    writes, report = build_en_part_effect_data(
        ROOT / "data", clean, label_encoder=encoder.part_runs
    )

    assert len(report["records"]) == 22
    assert {int(record["slot"]) for record in report["records"]} == {
        6, *range(17, 38)
    }
    alias_owners = {f"en-part-effects-slot-{slot}" for slot in range(7, 17)}
    assert {write.owner for write in writes if write.owner in alias_owners} == alias_owners
    assert all(not write.owner.startswith("part-name:") for write in writes)
    assert report["source_routes"]["0xFE"]
    movement = next(write for write in writes if write.owner == "en-part-effects-record-18")
    assert movement.payload.startswith(b"\xFB")
    assert movement.payload.endswith(b"\xFE\xFF")
    minovsky = next(
        write for write in writes if write.owner == "en-part-effects-record-17"
    )
    minovsky_runs, _ = encoder.part_runs("ชนิด Movement เป็น Air-Ground")
    assert minovsky.payload == b"".join(payload for payload, _ in minovsky_runs) + b"\xFF"
    labels = {
        int(record["slot"]): record["labels"] for record in report["records"]
    }
    assert labels[6][0]["text"] == "Range +1 (ยกเว้น MAP, Range 1)"
    assert labels[18][0]["text"] == "Movement +1"
