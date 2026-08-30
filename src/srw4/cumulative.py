"""Incremental deterministic builders for the Core rewrite."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from .proven.allocation import Allocator
from .proven.renderer65816 import (
    BATTLE_STATE_BASE,
    ORDINARY_STATE_BASE,
    SHL_TABLE,
    SHR_TABLE,
    build_renderer,
    pc_to_cpu,
    shift_tables,
)
from .proven.driver import build_driver
from .proven.stock_fb import (
    BATTLE_HOOK_EXPECTED,
    BATTLE_HOOK_SITE,
    ORDINARY_HOOK_EXPECTED,
    ORDINARY_HOOK_SITE,
    build_battle_stock_fb,
    build_ordinary_stock_fb,
    hook_jump,
)
from .proven.catalog_router import (
    build_battle_dispatch,
    build_classifier,
    build_halfwidth,
    build_parser_1,
    build_parser_1_alt,
    build_parser_2,
    build_route_tables,
    build_width,
    hook_jml,
    hook_jsl,
)
from .proven.catalogs import build_catalog_data
from .proven.naming import (
    FIXED_SOURCE_RANGES,
    LABEL_SOURCE_RANGES,
    MARK_PREVIEW_RANGES,
    RUNTIME_SOURCE_RANGES,
    build_naming_data,
    fixed_advance,
    page_with_previews,
)
from .proven.text.encoding import advance_table
from .proven.manifest import load_hooks, load_rom_map
from .proven.rom_image import RomContract, RomImage
from .proven.text.font import build_page
from .proven.text.stock import StockCatalog
from .proven.text.upper_stacks import (
    PAIR_COUNT,
    TONE_MARKS,
    UPPER_VOWELS,
    build_upper_stack_assets,
)
from .proven.unit_status import build_unit_status_data
from .proven.pilot_status import build_pilot_status_data
from .proven.weapon_detail import build_weapon_detail_data
from .proven.spirit_help import build_spirit_help_data
from .proven.unit_commands import build_unit_commands_data
from .proven.map_menu import build_map_menu_data
from .proven.map_hud import build_map_hud_data
from .proven.main_menu import build_main_menu_data
from .proven.story import build_story_data
from .proven.protagonist import build_protagonist_data
from .proven.option_menu import build_option_menu_data
from .proven.relocation import build_relocated_catalog, build_relocated_script_catalog
from .proven.screens import build_screens_data
from .proven.series import build_series_data
from .proven.title import build_title_data
from .proven.intro import build_intro_data
from .proven.terrain_effects import build_terrain_effect_data


DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
FONT_ROOT = DATA_ROOT / "font"
CONFIG_ROOT = DATA_ROOT / "config"


def build_font_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Build a boot-safe 4 MiB image containing data only; no engine hooks."""
    rom_map = load_rom_map(CONFIG_ROOT / "rom-map.json")
    spec = rom_map["rom"]
    image = RomImage.read(clean_path)
    image.verify(RomContract(int(spec["input_size"]), str(spec["sha256"])))
    image.expand(int(spec["expanded_size"]))

    model = json.loads((FONT_ROOT / "thai.json").read_text(encoding="utf-8"))
    layout = json.loads((FONT_ROOT / "encoding.json").read_text(encoding="utf-8"))
    artifacts = build_page(model, layout)
    artifacts.update(build_upper_stack_assets(model, layout))
    artifacts["thai-page.bin"] = page_with_previews(
        artifacts["thai-page.bin"], model
    )

    allocator = Allocator.from_file(CONFIG_ROOT / "memory-map.json")
    for name, payload in artifacts.items():
        region = "core"
        alignment = 0x1000 if name == "thai-page.bin" else 0x100
        allocation = allocator.reserve(region, len(payload), name, alignment=alignment)
        image.place(allocation.start, payload, name)

    checksum, complement = image.repair_checksum()
    report = {
        "stage": "font-assets-only",
        "release_ready": False,
        "hooks_enabled": [],
        "input_sha256": str(spec["sha256"]),
        "output_sha256": image.digest,
        "size": len(image.data),
        "checksum": f"0x{checksum:04X}",
        "complement": f"0x{complement:04X}",
        "allocations": allocator.report(),
        "artifacts": {
            name: {"bytes": len(payload), "sha256": sha256(payload).hexdigest()}
            for name, payload in artifacts.items()
        },
    }
    return image, report


def build_renderer_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Place font, metrics and both renderer contexts without enabling hooks."""
    image, font_report = build_font_stage(clean_path)
    allocator = Allocator.from_file(CONFIG_ROOT / "memory-map.json")

    # Reproduce the font-stage reservations so subsequent addresses are derived
    # from the same registry rather than copied from a report.
    model = json.loads((FONT_ROOT / "thai.json").read_text(encoding="utf-8"))
    layout = json.loads((FONT_ROOT / "encoding.json").read_text(encoding="utf-8"))
    artifacts = build_page(model, layout)
    artifacts.update(build_upper_stack_assets(model, layout))
    artifacts["thai-page.bin"] = page_with_previews(
        artifacts["thai-page.bin"], model
    )
    for name, payload in artifacts.items():
        region = "core"
        alignment = 0x1000 if name == "thai-page.bin" else 0x100
        allocator.reserve(region, len(payload), name, alignment=alignment)

    naming_advance = fixed_advance(artifacts["thai-advance.bin"], model)
    naming_advance_alloc = allocator.reserve(
        "core", len(naming_advance), "thai-naming-fixed-advance.bin", alignment=0x100
    )
    image.place(
        naming_advance_alloc.start,
        naming_advance,
        naming_advance_alloc.owner,
    )

    shr, shl = shift_tables()
    shr_alloc = allocator.reserve("core", len(shr), "thai-shift-right.bin", alignment=0x800)
    shl_alloc = allocator.reserve("core", len(shl), "thai-shift-left.bin", alignment=0x800)
    if shr_alloc.start != SHR_TABLE or shl_alloc.start != SHL_TABLE:
        raise ValueError("shift-table constants disagree with the memory-map allocation")
    image.place(shr_alloc.start, shr, shr_alloc.owner)
    image.place(shl_alloc.start, shl, shl_alloc.owner)

    lock = bytes(256)
    lock_alloc = allocator.reserve("core", len(lock), "thai-grid-lock.bin", alignment=0x100)
    image.place(lock_alloc.start, lock, lock_alloc.owner)

    page_pc = next(
        item.start for item in allocator.allocations if item.owner == "thai-page.bin"
    )
    metrics = {
        item.owner: item.start
        for item in allocator.allocations
        if item.owner.startswith("thai-")
    }
    renderer_args = {
        "source_base": page_pc & 0xFFFF,
        "advance": metrics["thai-advance.bin"],
        "lock": lock_alloc.start,
        "combining": {
            "mark_dx": metrics["thai-mark-dx.bin"],
            "mark_y": metrics["thai-mark-y.bin"],
            "mark_size": metrics["thai-mark-size.bin"],
            "base_ink": metrics["thai-base-ink.bin"],
            "raised_y": metrics["thai-raised-y.bin"],
        },
        "upper_stacks": {
            "overlay": metrics["thai-upper-stack-overlay.bin"],
            "dx": metrics["thai-upper-stack-dx.bin"],
            "dy": metrics["thai-upper-stack-dy.bin"],
            "size": metrics["thai-upper-stack-size.bin"],
        },
        "shorthand": {
            "first": metrics["thai-shorthand-1.bin"],
            "second": metrics["thai-shorthand-2.bin"],
            "third": metrics["thai-shorthand-3.bin"],
        },
    }

    map_menu_data = json.loads(
        (DATA_ROOT / "translations/map-menu.th.json").read_text(encoding="utf-8")
    )
    map_menu_external_tilemap = bool(map_menu_data.get("external_tilemap", False))
    raw_preserve = map_menu_data.get("preserve_tilemap")
    map_menu_preserve = None if raw_preserve is None else {
        "pointer_dp": 0x1A,
        "first_pointer": int(str(raw_preserve["first_post_read_pointer"]), 0),
        "last_pointer": int(str(raw_preserve["last_post_read_pointer"]), 0),
        "source": int(str(raw_preserve["source_address"]), 0),
        "backup": int(str(raw_preserve["backup_address"]), 0),
        "row_bytes": int(raw_preserve["row_bytes"]),
        "rows": int(raw_preserve["rows"]),
        "stride": int(raw_preserve["stride"]),
    }

    renderer_reports = []
    for context, state_base, battle, context_advance, preview_ranges in (
        ("ordinary", ORDINARY_STATE_BASE, False, metrics["thai-advance.bin"], ()),
        ("battle", BATTLE_STATE_BASE, True, metrics["thai-advance.bin"], ()),
        (
            "naming_fixed",
            ORDINARY_STATE_BASE,
            False,
            naming_advance_alloc.start,
            MARK_PREVIEW_RANGES,
        ),
        (
            "map_menu",
            ORDINARY_STATE_BASE,
            False,
            metrics["thai-advance.bin"],
            (),
        ),
    ):
        # Reserve a conservative bank-local slot, generate at its real origin,
        # then retain only the bytes actually used in the report.
        slot = allocator.reserve("core", 0x1000, f"thai-{context}-renderer-slot", alignment=0x1000)
        code = build_renderer(
            slot.start,
            **{**renderer_args, "advance": context_advance},
            state_base=state_base,
            battle=battle,
            preview_ranges=preview_ranges,
            external_tilemap=(
                map_menu_external_tilemap if context == "map_menu" else False
            ),
            tilemap_preserve=(map_menu_preserve if context == "map_menu" else None),
        )
        if len(code) > slot.end - slot.start:
            raise ValueError(f"{context} renderer overflowed its 4 KiB slot")
        image.place(slot.start, code, f"thai-{context}-renderer")
        renderer_reports.append({
            "context": context,
            "pc": f"0x{slot.start:06X}",
            "bytes": len(code),
            "slot_bytes": slot.end - slot.start,
            "state": f"0x{state_base:06X}",
            "sha256": sha256(code).hexdigest(),
            "external_tilemap": (
                map_menu_external_tilemap if context == "map_menu" else False
            ),
            "tilemap_preserve": (map_menu_preserve if context == "map_menu" else None),
        })

    checksum, complement = image.repair_checksum()
    report = {
        **font_report,
        "stage": "renderer-assets-only",
        "output_sha256": image.digest,
        "checksum": f"0x{checksum:04X}",
        "complement": f"0x{complement:04X}",
        "allocations": allocator.report(),
        "renderers": renderer_reports,
        "upper_stacks": {
            "pairs": PAIR_COUNT,
            "vowels": list(UPPER_VOWELS),
            "tones": list(TONE_MARKS),
            "encoding_changed": False,
            "save_format_changed": False,
        },
        "hooks_enabled": [],
        "release_ready": False,
    }
    return image, report


def build_renderer_fixture(
    clean_path: Path,
    text: str,
    *,
    battle: bool = False,
) -> tuple[RomImage, dict]:
    """Add a test-only driver that calls one renderer without game routing."""
    image, report = build_renderer_stage(clean_path)
    allocator = Allocator.from_file(CONFIG_ROOT / "memory-map.json")
    # Mesen's exec callback resumes by advancing PC once.  Keep the driver away
    # from bank offset $0000 so the harness can seed the preceding byte without
    # relying on a bank carry the 65816 program counter does not perform.
    allocator.reserve("adapters", 0x100, "renderer-fixture-entry-guard")
    driver_slot = allocator.reserve("adapters", 0x1000, "renderer-fixture-driver", alignment=0x100)

    layout = json.loads((FONT_ROOT / "encoding.json").read_text(encoding="utf-8"))
    model = json.loads((FONT_ROOT / "thai.json").read_text(encoding="utf-8"))
    renderer_entry = next(
        int(item["pc"], 16)
        for item in report["renderers"]
        if item["context"] == ("battle" if battle else "ordinary")
    )
    # The payload address follows the fixed driver slot, making it stable even
    # if the generated driver grows as long test strings are added.
    string_alloc = allocator.reserve("adapters", 0x1000, "renderer-fixture-string-slot", alignment=0x1000)
    driver, payload, width = build_driver(
        text,
        layout,
        advance_table(model, layout),
        driver_slot.start,
        string_alloc.start,
        renderer_entry,
        battle=battle,
    )
    if len(driver) > driver_slot.end - driver_slot.start:
        raise ValueError("isolated renderer driver overflowed its slot")
    if len(payload) > string_alloc.end - string_alloc.start:
        raise ValueError("isolated renderer string overflowed its slot")
    image.place(driver_slot.start, driver, "renderer-fixture-driver")
    image.place(string_alloc.start, payload, "renderer-fixture-string")
    checksum, complement = image.repair_checksum()
    fixture = {
        "text": text,
        "context": "battle" if battle else "ordinary",
        "driver_pc": f"0x{driver_slot.start:06X}",
        "driver_cpu": f"0x{((0xC0 + (driver_slot.start >> 16)) << 16) | (driver_slot.start & 0xFFFF):06X}",
        "renderer_pc": f"0x{renderer_entry:06X}",
        "string_pc": f"0x{string_alloc.start:06X}",
        "driver_bytes": len(driver),
        "payload_bytes": len(payload),
        "width_px": width,
        "cells": max(1, (width + 7) // 8),
    }
    report = {
        **report,
        "stage": "isolated-renderer-fixture",
        "output_sha256": image.digest,
        "checksum": f"0x{checksum:04X}",
        "complement": f"0x{complement:04X}",
        "fixture": fixture,
    }
    return image, report


def build_catalog_stage(
    clean_path: Path,
    *,
    include_naming: bool = False,
) -> tuple[RomImage, dict]:
    """Install verified Thai data and stock assets without enabling hooks."""
    image, renderer_report = build_renderer_stage(clean_path)
    clean = clean_path.read_bytes()
    writes, catalog_report = build_catalog_data(
        DATA_ROOT,
        clean,
        font_dir=DATA_ROOT / "font",
        translation_dir=DATA_ROOT / "translations",
        kanji_path=DATA_ROOT / "font" / "jp-kanji.json",
    )
    for write in writes:
        if write.expected_ff:
            image.place(write.pc, write.payload, write.owner)
        else:
            expected = clean[write.pc:write.pc + len(write.payload)]
            image.patch(write.pc, expected, write.payload, write.owner)

    naming_report = None
    protagonist_report = None
    if include_naming:
        naming_writes, naming_report = build_naming_data(
            DATA_ROOT, clean
        )
        for write in naming_writes:
            expected = clean[write.pc:write.pc + len(write.payload)]
            image.patch(write.pc, expected, write.payload, write.owner)
        catalog_report["pools"].extend(naming_report["pools"])
        protagonist_writes, protagonist_report = build_protagonist_data(
            DATA_ROOT, clean
        )
        for write in protagonist_writes:
            expected = clean[write.pc:write.pc + len(write.payload)]
            image.patch(write.pc, expected, write.payload, write.owner)

    allocator = Allocator.from_file(CONFIG_ROOT / "memory-map.json")
    table_alloc = allocator.reserve(
        "text_data", 256 * 3, "stock-run-pointer-table", alignment=0x100
    )
    stock = StockCatalog.locked()
    _, provisional_pool, _ = stock.assets(table_alloc.end)
    pool_alloc = allocator.reserve(
        "text_data", len(provisional_pool), "stock-run-string-pool", alignment=1
    )
    table, pool, stock_entries = stock.assets(pool_alloc.start)
    if len(table) != table_alloc.end - table_alloc.start or len(pool) != len(provisional_pool):
        raise ValueError("stock-run asset size changed during allocation")
    image.place(table_alloc.start, table, table_alloc.owner)
    image.place(pool_alloc.start, pool, pool_alloc.owner)

    checksum, complement = image.repair_checksum()
    return image, {
        **renderer_report,
        "stage": "catalog-data-only",
        "output_sha256": image.digest,
        "checksum": f"0x{checksum:04X}",
        "complement": f"0x{complement:04X}",
        "allocations": renderer_report["allocations"] + allocator.report(),
        "catalogs": catalog_report,
        **({"naming_screen": naming_report} if naming_report is not None else {}),
        **({"protagonist_settings": protagonist_report}
           if protagonist_report is not None else {}),
        "stock_assets": {
            "pointer_table_pc": f"0x{table_alloc.start:06X}",
            "string_pool_pc": f"0x{pool_alloc.start:06X}",
            "pool_bytes": len(pool),
            "entries": stock_entries,
        },
        "hooks_enabled": [],
        "release_ready": False,
    }


def build_stock_fb_stage(
    clean_path: Path,
    *,
    include_naming: bool = False,
) -> tuple[RomImage, dict]:
    """Enable only the ordinary/battle FB adapters for stock-font runs."""
    image, catalog_report = build_catalog_stage(
        clean_path, include_naming=include_naming
    )
    pointer_table_pc = int(catalog_report["stock_assets"]["pointer_table_pc"], 16)
    allocator = Allocator.from_file(CONFIG_ROOT / "memory-map.json")
    allocator.reserve("adapters", 0x100, "battle-bg-guard-reservation", alignment=0x100)
    ordinary_slot = allocator.reserve("adapters", 0x100, "ordinary-stock-fb-slot", alignment=0x100)
    battle_slot = allocator.reserve("adapters", 0x100, "battle-stock-fb-slot", alignment=0x100)

    ordinary = build_ordinary_stock_fb(ordinary_slot.start, pointer_table_pc)
    battle = build_battle_stock_fb(battle_slot.start, pointer_table_pc)
    for slot, payload, owner in (
        (ordinary_slot, ordinary, "ordinary-stock-fb-adapter"),
        (battle_slot, battle, "battle-stock-fb-adapter"),
    ):
        if len(payload) > slot.end - slot.start:
            raise ValueError(f"{owner} overflowed its adapter slot")
        image.place(slot.start, payload, owner)

    image.patch(
        ORDINARY_HOOK_SITE,
        ORDINARY_HOOK_EXPECTED,
        hook_jump(ordinary_slot.start),
        "ordinary-stock-fb-hook",
    )
    image.patch(
        BATTLE_HOOK_SITE,
        BATTLE_HOOK_EXPECTED,
        hook_jump(battle_slot.start),
        "battle-stock-fb-hook",
    )
    checksum, complement = image.repair_checksum()
    adapters = [
        {
            "context": "ordinary",
            "pc": f"0x{ordinary_slot.start:06X}",
            "bytes": len(ordinary),
            "hook_pc": f"0x{ORDINARY_HOOK_SITE:06X}",
            "sha256": sha256(ordinary).hexdigest(),
        },
        {
            "context": "battle",
            "pc": f"0x{battle_slot.start:06X}",
            "bytes": len(battle),
            "hook_pc": f"0x{BATTLE_HOOK_SITE:06X}",
            "sha256": sha256(battle).hexdigest(),
        },
    ]
    return image, {
        **catalog_report,
        "stage": "stock-fb-adapters",
        "output_sha256": image.digest,
        "checksum": f"0x{checksum:04X}",
        "complement": f"0x{complement:04X}",
        "allocations": catalog_report["allocations"] + allocator.report(),
        "stock_fb_adapters": adapters,
        "hooks_enabled": ["ordinary_stock_fb", "battle_stock_fb"],
        "release_ready": False,
    }


def _catalog_source_ranges(
    catalog_report: dict,
    *,
    include_naming: bool = False,
) -> dict[int, tuple[tuple[int, int], ...]]:
    grouped: dict[int, list[tuple[int, int]]] = {}
    for pool in catalog_report["catalogs"]["pools"]:
        used = int(pool["used"])
        if not used or str(pool["name"]).startswith("reserved_"):
            continue
        start = int(pool["start"], 16)
        end = start + used
        bank = 0xC0 + (start >> 16)
        grouped.setdefault(bank, []).append(((start & 0xFFFF) + 1, (end & 0xFFFF) + 1))
    if include_naming:
        for extra in (RUNTIME_SOURCE_RANGES, LABEL_SOURCE_RANGES):
            for bank, ranges in extra.items():
                grouped.setdefault(bank, []).extend(ranges)
        for bank_text, ranges in catalog_report["protagonist_settings"][
            "source_routes"
        ].items():
            grouped.setdefault(int(bank_text, 16), []).extend(
                (int(start), int(end)) for start, end in ranges
            )
    return {bank: tuple(sorted(ranges)) for bank, ranges in sorted(grouped.items())}


def _follow_moved_records(
    routes: dict[int, list[tuple[int, int]]], report: dict
) -> dict[int, list[tuple[int, int]]]:
    """Move another adapter's Thai runs with the records they describe.

    Main-menu and protagonist fields sit inside the relocated catalog, so the
    ranges they published for the old bank now address bytes nobody reads.
    Each range is carried to the record's new address instead of being dropped,
    which keeps those screens routed without touching their adapters.
    """
    old_bank = int(str(report["moved_from_bank"]), 16)
    new_bank = int(str(report["catalog_cpu"]).split(":")[0].lstrip("$"), 16)
    if old_bank not in routes:
        return routes
    moves = [
        (
            int(str(item["from"]), 0) & 0xFFFF,
            (int(str(item["from"]), 0) & 0xFFFF) + int(item["bytes"]),
            int(item["to_cpu"]),
        )
        for item in report["moved_records"]
    ]
    stayed: list[tuple[int, int]] = []
    for start, end in routes[old_bank]:
        # Ranges are quoted one past the text, so compare on the byte itself.
        for low, high, target in moves:
            if low < start <= high and low < end <= high + 1:
                offset = target - low
                routes.setdefault(new_bank, []).append((start + offset, end + offset))
                break
        else:
            stayed.append((start, end))
    routes[old_bank] = stayed
    return routes


RELOCATED_CATALOGS = {
    "terrain": "translations/terrain-names.th.json",
    "scenario": "translations/scenario-titles.th.json",
}
# Catalogs land in text_data in this order, so a build stays reproducible no
# matter which subset a milestone enables.
RELOCATED_ORDER = ("terrain", "scenario")


def build_catalog_router_stage(
    clean_path: Path,
    *,
    include_naming: bool = False,
    include_unit_status: bool = False,
    include_pilot_status: bool = False,
    include_weapon_detail: bool = False,
    include_spirit_help: bool = False,
    include_unit_commands: bool = False,
    include_map_menu: bool = False,
    include_map_hud: bool = False,
    include_main_menu: bool = False,
    include_story: bool = False,
    include_title: bool = False,
    include_intro: bool = False,
    include_relocated: tuple[str, ...] = (),
    include_option_menu: bool = False,
    include_series: bool = False,
    include_intermission: bool = False,
    include_screens: bool = False,
) -> tuple[RomImage, dict]:
    """Enable verified catalog routes and optionally the Thai naming system."""
    image, stock_report = build_stock_fb_stage(
        clean_path, include_naming=include_naming
    )
    if include_screens:
        include_intermission = True
    if include_intermission:
        include_series = True
    if include_series:
        include_option_menu = True
    if include_option_menu:
        include_relocated = include_relocated or ("terrain", "scenario")
    if include_relocated:
        include_intro = True
    if include_intro:
        include_title = True
    if include_title:
        include_story = True
    if include_story:
        include_main_menu = True
    if include_main_menu:
        include_map_hud = True
    if include_map_hud:
        include_map_menu = True
    if include_map_menu:
        include_unit_commands = True
    if include_unit_commands:
        include_spirit_help = True
    if include_spirit_help:
        include_weapon_detail = True
    if include_weapon_detail:
        include_pilot_status = True
    if include_pilot_status:
        include_unit_status = True
    unit_status_report = None
    pilot_status_report = None
    weapon_detail_report = None
    spirit_help_report = None
    unit_commands_report = None
    map_menu_report = None
    map_hud_report = None
    main_menu_report = None
    story_report = None
    title_report = None
    intro_report = None
    relocated_reports: dict[str, dict] = {}
    terrain_effect_report = None
    option_menu_report = None
    series_report = None
    intermission_report = None
    screens_report = None
    if include_unit_status:
        clean = clean_path.read_bytes()
        menu_writes, unit_status_report = build_unit_status_data(
            DATA_ROOT, clean
        )
        for write in menu_writes:
            if write.expected_ff:
                image.place(write.pc, write.payload, write.owner)
            else:
                expected = clean[write.pc:write.pc + len(write.payload)]
                image.patch(write.pc, expected, write.payload, write.owner)
        stock_report["catalogs"]["pools"].extend(unit_status_report["pools"])
    if include_pilot_status:
        clean = clean_path.read_bytes()
        assert unit_status_report is not None
        pilot_writes, pilot_status_report = build_pilot_status_data(
            DATA_ROOT, clean, overflow_start=int(unit_status_report["overflow_end"], 16),
        )
        for write in pilot_writes:
            if write.expected_ff:
                image.place(write.pc, write.payload, write.owner)
            else:
                expected = clean[write.pc:write.pc + len(write.payload)]
                image.patch(write.pc, expected, write.payload, write.owner)
        stock_report["catalogs"]["pools"].extend(pilot_status_report["pools"])
    if include_weapon_detail:
        clean = clean_path.read_bytes()
        detail_writes, weapon_detail_report = build_weapon_detail_data(
            DATA_ROOT, clean
        )
        for write in detail_writes:
            image.patch(
                write.pc,
                clean[write.pc:write.pc + len(write.payload)],
                write.payload,
                write.owner,
            )
    if include_spirit_help:
        clean = clean_path.read_bytes()
        help_writes, spirit_help_report = build_spirit_help_data(
            DATA_ROOT, clean
        )
        for write in help_writes:
            image.patch(
                write.pc,
                clean[write.pc:write.pc + len(write.payload)],
                write.payload,
                write.owner,
            )
    if include_unit_commands:
        clean = clean_path.read_bytes()
        command_writes, unit_commands_report = build_unit_commands_data(
            DATA_ROOT, clean,
            font_dir=DATA_ROOT / "font",
        )
        for write in command_writes:
            image.patch(
                write.pc,
                clean[write.pc:write.pc + len(write.payload)],
                write.payload,
                write.owner,
            )
    if include_map_menu:
        clean = clean_path.read_bytes()
        map_writes, map_menu_report = build_map_menu_data(
            DATA_ROOT, clean
        )
        for write in map_writes:
            image.patch(
                write.pc,
                clean[write.pc:write.pc + len(write.payload)],
                write.payload,
                write.owner,
            )
    if include_map_hud:
        clean = clean_path.read_bytes()
        hud_writes, map_hud_report = build_map_hud_data(
            DATA_ROOT, clean
        )
        for write in hud_writes:
            image.patch(
                write.pc,
                clean[write.pc:write.pc + len(write.payload)],
                write.payload,
                write.owner,
            )
    if include_main_menu:
        clean = clean_path.read_bytes()
        main_writes, main_menu_report = build_main_menu_data(
            DATA_ROOT, clean
        )
        for write in main_writes:
            image.patch(
                write.pc,
                clean[write.pc:write.pc + len(write.payload)],
                write.payload,
                write.owner,
            )
    if include_story:
        clean = clean_path.read_bytes()
        story_writes, story_report = build_story_data(
            DATA_ROOT,
            clean,
            source_path=DATA_ROOT / "translations" / "script.source.json",
            translation_path=DATA_ROOT / "translations" / "script.th.json",
            layout_path=FONT_ROOT / "encoding.json",
            translation_dir=DATA_ROOT / "translations",
            allocation_path=CONFIG_ROOT / "memory-map.json",
        )
        for write in story_writes:
            if write.expected_ff:
                image.place(write.pc, write.payload, write.owner)
            else:
                image.patch(
                    write.pc,
                    clean[write.pc:write.pc + len(write.payload)],
                    write.payload,
                    write.owner,
                )
    if include_title:
        clean = clean_path.read_bytes()
        text_cursor = max(
            int(str(item["end"]), 0)
            for item in stock_report["allocations"]
            if item["region"] == "text_data"
        )
        title_writes, title_report = build_title_data(DATA_ROOT, clean, text_cursor)
        for write in title_writes:
            if write.expected_ff:
                image.place(write.pc, write.payload, write.owner)
            else:
                image.patch(
                    write.pc,
                    clean[write.pc:write.pc + len(write.payload)],
                    write.payload,
                    write.owner,
                )
    for name in RELOCATED_ORDER:
        if name not in include_relocated:
            continue
        clean = clean_path.read_bytes()
        cursor = max(
            [
                int(str(item["end"]), 0)
                for item in stock_report["allocations"]
                if item["region"] == "text_data"
            ]
            + ([] if title_report is None else [int(str(title_report["allocation"]["end"]), 0)])
            + [
                int(str(done["catalog_pc"]), 0)
                + int(done["table_bytes"])
                + int(done["pool_bytes"])
                for done in relocated_reports.values()
            ]
        )
        writes, report = build_relocated_catalog(
            DATA_ROOT, clean, cursor, RELOCATED_CATALOGS[name], name,
        )
        relocated_reports[name] = report
        for write in writes:
            if write.expected_ff:
                image.place(write.pc, write.payload, write.owner)
            else:
                image.patch(
                    write.pc,
                    clean[write.pc:write.pc + len(write.payload)],
                    write.payload,
                    write.owner,
                )
    if "terrain" in include_relocated:
        clean = clean_path.read_bytes()
        terrain_effect_writes, terrain_effect_report = build_terrain_effect_data(
            DATA_ROOT, clean
        )
        for write in terrain_effect_writes:
            image.patch(
                write.pc,
                clean[write.pc:write.pc + len(write.payload)],
                write.payload,
                write.owner,
            )
    if include_option_menu:
        clean = clean_path.read_bytes()
        pool = next(
            item for item in stock_report["catalogs"]["pools"]
            if item["name"] == "verified_weapon_mid_bank"
        )
        cursor = int(str(pool["start"]), 0) + int(pool["used"])
        option_writes, option_menu_report = build_option_menu_data(
            DATA_ROOT, clean, cursor
        )
        for write in option_writes:
            if write.expected_ff:
                image.place(write.pc, write.payload, write.owner)
            else:
                image.patch(
                    write.pc,
                    clean[write.pc:write.pc + len(write.payload)],
                    write.payload,
                    write.owner,
                )
    if include_series:
        clean = clean_path.read_bytes()
        # The relocated catalogs' old pools are the only bank $D2 space free
        # for these records, so the dependency is passed in explicitly.
        pools = [
            (
                int(str(relocated_reports[name]["released_pool"]["pc"]).split("-")[0], 0),
                int(str(relocated_reports[name]["released_pool"]["pc"]).split("-")[1], 0),
            )
            for name in ("terrain", "scenario")
        ]
        series_writes, series_report = build_series_data(
            DATA_ROOT, clean, pools
        )
        for write in series_writes:
            image.patch(
                write.pc,
                clean[write.pc:write.pc + len(write.payload)],
                write.payload,
                write.owner,
            )
    if include_intermission:
        clean = clean_path.read_bytes()
        cursor = max(
            [
                int(str(item["end"]), 0)
                for item in stock_report["allocations"]
                if item["region"] == "text_data"
            ]
            + ([] if title_report is None else [int(str(title_report["allocation"]["end"]), 0)])
            + [
                int(str(done["catalog_pc"]), 0)
                + int(done["table_bytes"])
                + int(done["pool_bytes"])
                for done in relocated_reports.values()
            ]
        )
        # Records are read back out of the image: main-menu and protagonist
        # fields live inside this catalog and have to travel with it.
        intermission_writes, intermission_report = build_relocated_script_catalog(
            DATA_ROOT, clean, bytes(image.data), cursor,
            "translations/intermission.th.json", "intermission",
        )
        for write in intermission_writes:
            if write.expected_ff:
                image.place(write.pc, write.payload, write.owner)
            else:
                image.patch(
                    write.pc,
                    clean[write.pc:write.pc + len(write.payload)],
                    write.payload,
                    write.owner,
                )
    if include_screens:
        clean = clean_path.read_bytes()
        assert intermission_report is not None
        low, high = (
            int(part, 0)
            for part in str(intermission_report["released_pool"]["pc"]).split("-")
        )
        screens_writes, screens_report = build_screens_data(
            DATA_ROOT, clean, bytes(image.data), (low, high),
        )
        for write in screens_writes:
            image.patch(
                write.pc,
                clean[write.pc:write.pc + len(write.payload)],
                write.payload,
                write.owner,
            )
    routes = _catalog_source_ranges(stock_report, include_naming=include_naming)
    if (unit_status_report is not None or pilot_status_report is not None
            or spirit_help_report is not None or unit_commands_report is not None
            or map_menu_report is not None or map_hud_report is not None
            or main_menu_report is not None
            or story_report is not None
            or relocated_reports or option_menu_report is not None
            or series_report is not None or intermission_report is not None
            or screens_report is not None):
        mutable = {bank: list(ranges) for bank, ranges in routes.items()}
        for report in (
            unit_status_report, pilot_status_report, weapon_detail_report, spirit_help_report,
            unit_commands_report,
            map_menu_report,
            map_hud_report,
            main_menu_report,
            story_report,
            *relocated_reports.values(),
            terrain_effect_report,
            option_menu_report,
            series_report,
            intermission_report,
        ):
            if report is None:
                continue
            for bank_text, ranges in report["source_routes"].items():
                bank = int(bank_text, 16)
                mutable.setdefault(bank, []).extend(
                    (int(start), int(end)) for start, end in ranges
                )
        if intermission_report is not None:
            mutable = _follow_moved_records(mutable, intermission_report)
        # Only after the move: the field screens are rebuilt into the pool the
        # move released, so their ranges sit inside spans that once held moved
        # records and would otherwise be dragged along with them.
        if screens_report is not None:
            for bank_text, ranges in screens_report["source_routes"].items():
                mutable.setdefault(int(bank_text, 16), []).extend(
                    (int(start), int(end)) for start, end in ranges
                )
        routes = {bank: tuple(sorted(ranges)) for bank, ranges in sorted(mutable.items())}
    fixed_routes = FIXED_SOURCE_RANGES if include_naming else {}
    cursor_left_pointers = {}
    if map_hud_report is not None:
        cursor_left_pointers = {
            int(bank, 16): tuple(int(pointer) for pointer in pointers)
            for bank, pointers in map_hud_report["cursor_left_pointers"].items()
        }
    allocator = Allocator.from_file(CONFIG_ROOT / "memory-map.json")
    allocator.reserve("adapters", 0x100, "battle-bg-guard-reservation", alignment=0x100)
    allocator.reserve("adapters", 0x100, "ordinary-stock-fb-slot", alignment=0x100)
    allocator.reserve("adapters", 0x100, "battle-stock-fb-slot", alignment=0x100)

    # Naming includes the protagonist setup, whose verified Thai runs add
    # enough source ranges to exceed the smaller milestone-only slots.
    route_slot = (
        0x1000 if include_naming or include_pilot_status
        else (0x800 if include_unit_status else 0x400)
    )
    classifier_slot = (
        0x1000 if include_naming or include_story
        else (0x800 if include_pilot_status else (0x400 if include_unit_status else 0x200))
    )
    slot_specs = (
        ("parser_1", route_slot),
        ("parser_1_alt", route_slot),
        ("parser_2", route_slot),
        ("classifier_1", classifier_slot),
        ("classifier_2", classifier_slot),
        ("width_1", 0x200),
        ("width_2", 0x200),
        ("halfwidth_left", 0x100),
        ("halfwidth_right", 0x100),
        ("battle_dispatch", 0x100),
    )
    slots = {
        name: allocator.reserve("adapters", size, f"catalog-{name}-slot", alignment=0x100)
        for name, size in slot_specs
    }
    intro_writes = []
    intro_hook_pc = None
    if include_intro:
        clean = clean_path.read_bytes()
        intro_writes, intro_report, intro_hook_pc = build_intro_data(
            DATA_ROOT,
            clean,
            allocator,
        )
    renderers = {
        item["context"]: int(item["pc"], 16)
        for item in stock_report["renderers"]
    }
    special_renderers: tuple[tuple[int, int, int, int], ...] = ()
    if map_menu_report is not None and map_menu_report["renderer_route"] is not None:
        route = map_menu_report["renderer_route"]
        special_renderers = ((
            int(str(route["bank"]), 16), int(route["start"]), int(route["end"]),
            renderers["map_menu"],
        ),)
    advance_pc = next(
        int(item["start"], 16)
        for item in stock_report["allocations"]
        if item["owner"] == "thai-advance.bin"
    )
    fixed_advance_pc = next(
        int(item["start"], 16)
        for item in stock_report["allocations"]
        if item["owner"] == "thai-naming-fixed-advance.bin"
    )
    # One descriptor per source bank plus packed bitmaps: the router used to
    # walk every declared range for every byte, which grew past the battle text
    # path's timing budget and hung the battle sequence.
    route_data = build_route_tables(routes, fixed_routes)
    route_slot = allocator.reserve(
        "font", len(route_data), "catalog-route-tables", alignment=0x100
    )
    route_tables = pc_to_cpu(route_slot.start)
    image.place(route_slot.start, route_data, "catalog-route-tables")

    payloads = {
        "parser_1": build_parser_1(
            slots["parser_1"].start, route_tables, cursor_left_pointers
        ),
        "parser_1_alt": build_parser_1_alt(
            slots["parser_1_alt"].start, route_tables, cursor_left_pointers
        ),
        "parser_2": build_parser_2(slots["parser_2"].start, route_tables),
        "classifier_1": build_classifier(
            slots["classifier_1"].start,
            0x1A,
            0x8184F7,
            renderers["ordinary"],
            route_tables,
            fixed_renderer_pc=(renderers["naming_fixed"] if include_naming else None),
            special_renderers=special_renderers,
        ),
        "classifier_2": build_classifier(
            slots["classifier_2"].start,
            0xCB,
            0x8187B8,
            renderers["ordinary"],
            route_tables,
            fixed_renderer_pc=(renderers["naming_fixed"] if include_naming else None),
        ),
        "width_1": build_width(
            slots["width_1"].start, 0x26, 0x81845B, 0x81848E, advance_pc,
            state_base=ORDINARY_STATE_BASE,
            battle=False,
            fixed_advance_pc=(fixed_advance_pc if include_naming else None),
        ),
        "width_2": build_width(
            slots["width_2"].start, 0x02, 0x81921E, 0x819236, advance_pc,
            state_base=BATTLE_STATE_BASE, battle=True,
        ),
        "halfwidth_left": build_halfwidth(
            slots["halfwidth_left"].start, 0x8184B9, 0x8184E0
        ),
        "halfwidth_right": build_halfwidth(
            slots["halfwidth_right"].start, 0x8184D0, 0x8184E0
        ),
        "battle_dispatch": build_battle_dispatch(
            slots["battle_dispatch"].start, renderers["battle"]
        ),
    }
    adapter_report = []
    for name, payload in payloads.items():
        slot = slots[name]
        if len(payload) > slot.end - slot.start:
            raise ValueError(f"catalog {name} overflowed its adapter slot")
        image.place(slot.start, payload, f"catalog-{name}")
        adapter_report.append({
            "name": name,
            "pc": f"0x{slot.start:06X}",
            "bytes": len(payload),
            "sha256": sha256(payload).hexdigest(),
        })
    for write in intro_writes:
        image.place(write.pc, write.payload, write.owner)

    hook_map = {
        item["id"]: item
        for item in load_hooks(CONFIG_ROOT / "hooks.json")["hooks"]
    }
    hook_targets = (
        ("text_parser_1", "parser_1", hook_jml),
        ("text_parser_1_alt", "parser_1_alt", hook_jml),
        ("text_parser_2", "parser_2", hook_jml),
        ("font_classifier_1", "classifier_1", hook_jml),
        ("font_classifier_2", "classifier_2", hook_jml),
        ("glyph_width_1", "width_1", hook_jml),
        ("glyph_width_2", "width_2", hook_jml),
        ("thai_halfwidth_left", "halfwidth_left", hook_jml),
        ("thai_halfwidth_right", "halfwidth_right", hook_jml),
        ("battle_renderer_dispatch", "battle_dispatch", hook_jsl),
    )
    enabled = list(stock_report["hooks_enabled"])
    for hook_id, adapter, jump_builder in hook_targets:
        hook = hook_map[hook_id]
        image.patch(
            int(hook["pc"], 16),
            bytes.fromhex(hook["expected"]),
            jump_builder(slots[adapter].start),
            hook_id,
        )
        enabled.append(hook_id)
    if intro_hook_pc is not None:
        hook = hook_map["intro_final_overlay"]
        image.patch(
            int(hook["pc"], 16),
            bytes.fromhex(hook["expected"]),
            hook_jml(intro_hook_pc),
            "intro_final_overlay",
        )
        enabled.append("intro_final_overlay")

    checksum, complement = image.repair_checksum()
    return image, {
        **stock_report,
        "stage": "catalog-router-active",
        "output_sha256": image.digest,
        "checksum": f"0x{checksum:04X}",
        "complement": f"0x{complement:04X}",
        "allocations": (
            stock_report["allocations"]
            + ([] if story_report is None else story_report["allocations"])
            + ([] if title_report is None else [title_report["allocation"]])
            + allocator.report()
        ),
        "catalog_routes": {
            f"0x{bank:02X}": [[f"0x{start:04X}", f"0x{end:04X}"] for start, end in ranges]
            for bank, ranges in routes.items()
        },
        **({
            "fixed_routes": {
                f"0x{bank:02X}": [
                    [f"0x{start:04X}", f"0x{end:04X}"] for start, end in ranges
                ]
                for bank, ranges in fixed_routes.items()
            }
        } if include_naming else {}),
        **({"unit_status": unit_status_report} if unit_status_report is not None else {}),
        **({"pilot_status": pilot_status_report} if pilot_status_report is not None else {}),
        **({"weapon_detail": weapon_detail_report}
           if weapon_detail_report is not None else {}),
        **({"spirit_help": spirit_help_report}
           if spirit_help_report is not None else {}),
        **({"unit_commands": unit_commands_report}
           if unit_commands_report is not None else {}),
        **({"map_menu": map_menu_report}
           if map_menu_report is not None else {}),
        **({"map_hud": map_hud_report}
           if map_hud_report is not None else {}),
        **({"main_menu": main_menu_report}
           if main_menu_report is not None else {}),
        **({"story": story_report}
           if story_report is not None else {}),
        **({"title": title_report}
           if title_report is not None else {}),
        **({"intro": intro_report}
           if intro_report is not None else {}),
        **{name: report for name, report in relocated_reports.items()},
        **({"terrain_effects": terrain_effect_report}
           if terrain_effect_report is not None else {}),
        **({"option_menu": option_menu_report}
           if option_menu_report is not None else {}),
        **({"intermission": intermission_report}
           if intermission_report is not None else {}),
        **({"screens": screens_report}
           if screens_report is not None else {}),
        **({"series": series_report}
           if series_report is not None else {}),
        **({"series": series_report}
           if series_report is not None else {}),
        "catalog_adapters": adapter_report,
        "hooks_enabled": enabled,
        "release_ready": False,
    }


def build_naming_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Named milestone for the active Thai player-name system."""
    image, report = build_catalog_router_stage(clean_path, include_naming=True)
    return image, {**report, "stage": "thai-naming-active"}


def build_unit_status_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Active Thai VWF milestone for the complete unit-status screen."""
    image, report = build_catalog_router_stage(
        clean_path, include_naming=True, include_unit_status=True
    )
    return image, {**report, "stage": "thai-unit-status-active"}


def build_pilot_status_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Active Thai VWF milestone for unit and pilot status surfaces."""
    image, report = build_catalog_router_stage(
        clean_path,
        include_naming=True,
        include_unit_status=True,
        include_pilot_status=True,
    )
    return image, {**report, "stage": "thai-pilot-status-active"}


def build_weapon_detail_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Active milestone for the stock-label weapon list/detail page."""
    image, report = build_catalog_router_stage(
        clean_path,
        include_naming=True,
        include_unit_status=True,
        include_pilot_status=True,
        include_weapon_detail=True,
    )
    return image, {**report, "stage": "thai-weapon-detail-active"}


def build_spirit_help_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Active Thai VWF milestone for the map Spirit help box."""
    image, report = build_catalog_router_stage(
        clean_path,
        include_naming=True,
        include_unit_status=True,
        include_pilot_status=True,
        include_weapon_detail=True,
        include_spirit_help=True,
    )
    return image, {**report, "stage": "thai-spirit-help-active"}


def build_unit_commands_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Active milestone for map unit commands and Thai shield labels."""
    image, report = build_catalog_router_stage(
        clean_path,
        include_naming=True,
        include_unit_status=True,
        include_pilot_status=True,
        include_weapon_detail=True,
        include_spirit_help=True,
        include_unit_commands=True,
    )
    return image, {**report, "stage": "thai-unit-commands-active"}


def build_map_menu_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Active stock-font milestone for the battle-map command menu."""
    image, report = build_catalog_router_stage(
        clean_path,
        include_naming=True,
        include_unit_status=True,
        include_pilot_status=True,
        include_weapon_detail=True,
        include_spirit_help=True,
        include_unit_commands=True,
        include_map_menu=True,
    )
    return image, {**report, "stage": "map-command-menu-active"}


def build_map_hud_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Active stock-font milestone for aligned map HUD labels and values."""
    image, report = build_catalog_router_stage(
        clean_path,
        include_naming=True,
        include_unit_status=True,
        include_pilot_status=True,
        include_weapon_detail=True,
        include_spirit_help=True,
        include_unit_commands=True,
        include_map_menu=True,
        include_map_hud=True,
    )
    return image, {**report, "stage": "map-hud-active"}


def build_main_menu_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Active Thai VWF milestone for main and system menu screens."""
    image, report = build_catalog_router_stage(
        clean_path,
        include_naming=True,
        include_unit_status=True,
        include_pilot_status=True,
        include_weapon_detail=True,
        include_spirit_help=True,
        include_unit_commands=True,
        include_map_menu=True,
        include_map_hud=True,
        include_main_menu=True,
    )
    return image, {**report, "stage": "main-system-menu-active"}


def build_story_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Active Thai VWF milestone for all story and battle-quote blocks."""
    image, report = build_catalog_router_stage(
        clean_path,
        include_naming=True,
        include_unit_status=True,
        include_pilot_status=True,
        include_weapon_detail=True,
        include_spirit_help=True,
        include_unit_commands=True,
        include_map_menu=True,
        include_map_hud=True,
        include_main_menu=True,
        include_story=True,
    )
    return image, {**report, "stage": "thai-story-active"}


def build_title_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Cumulative milestone with the Thai logo and English menu."""
    image, report = build_catalog_router_stage(
        clean_path,
        include_naming=True,
        include_unit_status=True,
        include_pilot_status=True,
        include_weapon_detail=True,
        include_spirit_help=True,
        include_unit_commands=True,
        include_map_menu=True,
        include_map_hud=True,
        include_main_menu=True,
        include_story=True,
        include_title=True,
    )
    return image, {**report, "stage": "thai-title-active"}


def build_intro_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Cumulative milestone with all five Thai opening-crawl overlays."""
    image, report = build_catalog_router_stage(
        clean_path,
        include_naming=True,
        include_unit_status=True,
        include_pilot_status=True,
        include_weapon_detail=True,
        include_spirit_help=True,
        include_unit_commands=True,
        include_map_menu=True,
        include_map_hud=True,
        include_main_menu=True,
        include_story=True,
        include_title=True,
        include_intro=True,
    )
    return image, {**report, "stage": "thai-intro-active"}




def _relocated_stage(clean_path: Path, names: tuple[str, ...], stage: str):
    image, report = build_catalog_router_stage(
        clean_path,
        include_naming=True,
        include_unit_status=True,
        include_pilot_status=True,
        include_weapon_detail=True,
        include_spirit_help=True,
        include_unit_commands=True,
        include_map_menu=True,
        include_map_hud=True,
        include_main_menu=True,
        include_story=True,
        include_title=True,
        include_intro=True,
        include_relocated=names,
    )
    return image, {**report, "stage": stage}


def build_terrain_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Cumulative milestone with the relocated Thai terrain-name catalog."""
    return _relocated_stage(clean_path, ("terrain",), "thai-terrain-active")


def build_scenario_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Cumulative milestone with the relocated Thai scenario-title catalog."""
    return _relocated_stage(clean_path, ("terrain", "scenario"), "thai-scenario-active")


def build_option_menu_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Cumulative milestone with the English OPTION menu."""
    image, report = build_catalog_router_stage(
        clean_path,
        include_naming=True,
        include_unit_status=True,
        include_pilot_status=True,
        include_weapon_detail=True,
        include_spirit_help=True,
        include_unit_commands=True,
        include_map_menu=True,
        include_map_hud=True,
        include_main_menu=True,
        include_story=True,
        include_title=True,
        include_intro=True,
        include_relocated=("terrain", "scenario"),
        include_option_menu=True,
    )
    return image, {**report, "stage": "english-option-menu-active"}


def build_screens_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Cumulative milestone with the Thai deployment and result screens."""
    image, report = build_catalog_router_stage(
        clean_path,
        include_naming=True,
        include_unit_status=True,
        include_pilot_status=True,
        include_weapon_detail=True,
        include_spirit_help=True,
        include_unit_commands=True,
        include_map_menu=True,
        include_map_hud=True,
        include_main_menu=True,
        include_story=True,
        include_title=True,
        include_intro=True,
        include_relocated=("terrain", "scenario"),
        include_option_menu=True,
        include_series=True,
        include_intermission=True,
        include_screens=True,
    )
    return image, {**report, "stage": "thai-field-screens-active"}


def build_intermission_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Cumulative milestone with the Thai Intermission menu."""
    image, report = build_catalog_router_stage(
        clean_path,
        include_naming=True,
        include_unit_status=True,
        include_pilot_status=True,
        include_weapon_detail=True,
        include_spirit_help=True,
        include_unit_commands=True,
        include_map_menu=True,
        include_map_hud=True,
        include_main_menu=True,
        include_story=True,
        include_title=True,
        include_intro=True,
        include_relocated=("terrain", "scenario"),
        include_option_menu=True,
        include_series=True,
        include_intermission=True,
    )
    return image, {**report, "stage": "thai-intermission-active"}


def build_series_stage(clean_path: Path) -> tuple[RomImage, dict]:
    """Cumulative milestone with Thai series titles in the encyclopedia."""
    image, report = build_catalog_router_stage(
        clean_path,
        include_naming=True,
        include_unit_status=True,
        include_pilot_status=True,
        include_weapon_detail=True,
        include_spirit_help=True,
        include_unit_commands=True,
        include_map_menu=True,
        include_map_hud=True,
        include_main_menu=True,
        include_story=True,
        include_title=True,
        include_intro=True,
        include_relocated=("terrain", "scenario"),
        include_option_menu=True,
        include_series=True,
    )
    return image, {**report, "stage": "thai-series-active"}
