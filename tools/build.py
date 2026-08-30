#!/usr/bin/env python3
"""Build the SRW4 Thai ROM from the clean ROM plus the data in this repo.

P0 stage: the image is expanded from 3 MB to 4 MB and the checksum is fixed;
no text or code is written yet. The point of this stage is that the build is
reproducible, so that every later stage can be judged by its byte diff.

  tools/build.py                 build build/srw4-th.sfc + build/reports/build.json
  tools/build.py --check         build twice in memory and compare sha256
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.allocation import AllocationMap  # noqa: E402
from srw4.asm65816 import assemble  # noqa: E402
from srw4.blitter import build as build_blitter  # noqa: E402
from srw4.blitter import (  # noqa: E402
    STOCK_RASTERISER,
    build_tables,
    fixed_advances,
    menu_adapter_constants,
    menu_adapter_source,
)
from srw4.catalog13 import build as build_catalog13  # noqa: E402
from srw4.command_overlay import (  # noqa: E402
    build as build_command_overlay,
    native_index_table,
    native_route_table,
    serialize as serialize_command_overlay,
)
from srw4.intro import HOOK_AT as INTRO_HOOK_AT, HOOK_EXPECTED as INTRO_HOOK_EXPECTED, build as build_intro  # noqa: E402
from srw4.naming import (  # noqa: E402
    NAMING_RASTER_CALL,
    NAMING_RASTER_EXPECTED,
    adapter_source as naming_adapter_source,
    preset_writes,
)
from srw4.naming_router import parser_source, width_source  # noqa: E402
from srw4.menu_router import (  # noqa: E402
    native_command_source,
    parser_source as menu_parser_source,
)
from srw4.pipeline import Pipeline  # noqa: E402
from srw4.repack import repack  # noqa: E402
from srw4.script import load_blocks, load_summary, mirror_banks, plan_mirror  # noqa: E402
from srw4.rom import CLEAN_SHA256, EXPANDED_SIZE, Rom, RomError, sha256  # noqa: E402
from build_current_full import build_current, EXPECTED_SHA256 as CURRENT_FULL_SHA256  # noqa: E402

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
ALLOCATION_MAP = ROOT / "data" / "config" / "allocation-map.json"
WRAM_MAP = ROOT / "data" / "config" / "wram-map.json"
SCRIPT_SOURCE = ROOT / "data" / "translations" / "script.source.json"
SCRIPT_BANKS = (0xF0, 0xF8)
OUT_ROM = ROOT / "build" / "srw4-th.sfc"
OUT_REPORT = ROOT / "build" / "reports" / "build.json"


def cpu_address(pc: int) -> int:
    """HiROM: the expanded banks are $C0 + (pc >> 16)."""
    return ((0xC0 + (pc >> 16)) << 16) | (pc & 0xFFFF)


def shared_dispatch_source(default_entry: int, menu_entry: int, command_entry: int) -> str:
    """Route `$FA`, and test native `$D2` pointers before the default parser."""
    return f""".a16
.i16
shared_dispatch:
  php
  rep #$20
  pha
  sep #$20
  lda $1C
  cmp #$D2
  beq native_command
  cmp #$FA
  beq menu
  rep #$20
  pla
  plp
  jml ${default_entry:06X}
menu:
  rep #$20
  pla
  plp
  jml ${menu_entry:06X}
native_command:
  rep #$20
  pla
  plp
  jml ${command_entry:06X}
"""


def shared_raster_source(*, default_entry: int, menu_entry: int) -> str:
    """Route only relocated `$FA` command records to the menu raster.

    Preserve A: it is the glyph id consumed by the destination renderer.
    The earlier lifecycle-state dispatcher accidentally replaced every glyph
    with the value of `MENU_ACTIVE`.
    """
    return f""".a16
.i16
shared_raster:
  php
  rep #$30
  pha
  sep #$20
  lda $1C
  cmp #$FA
  beq menu
  rep #$20
  pla
  plp
  jml ${default_entry:06X}
menu:
  rep #$20
  pla
  plp
  jml ${menu_entry:06X}
"""


def menu_catalog_source(pool_address: int, menu_active: int) -> str:
    """Select the $FA catalog only while the command-menu parser is active."""
    return f""".a16
.i16
menu_catalog_descriptor:
  php
  rep #$30
  lda.l ${menu_active:06X}
  beq stock
  lda #${pool_address:04X}
  sta $1A
  sep #$20
  lda #$FA
  sta $1C
  rep #$20
  plp
  jml $8183E6
stock:
  plp
  lda $C900D8,x
  jml $8183DE
"""


def context_base(name: str) -> int:
    document = json.loads(WRAM_MAP.read_text())
    for region in document["regions"]:
        for context in region.get("contexts", []):
            if context["id"] == name:
                return int(context["start"], 16) & 0xFFFF
    raise RomError(f"no context called {name} in the WRAM map")


STORY_RASTER_CALL = 0x019238   # "jsl $8184EB" inside the story engine's loop
STOCK_CALL_BYTES = bytes([0x22, 0xEB, 0x84, 0x81])
CATALOG_MASTER = 0x0900D8
CATALOG13_DESCRIPTOR = CATALOG_MASTER + 13 * 3
CATALOG16_DESCRIPTOR = CATALOG_MASTER + 16 * 3
CATALOG13_STOCK = bytes((0x03, 0x81, 0xD2))
CATALOG16_STOCK = bytes((0xC3, 0x82, 0xD2))


def place_renderer(
    rom: Rom, allocation: AllocationMap, *, hook: bool, names: bool = False,
    naming_presets: bool = False, command_menu: bool = False,
    command_stage: str = "full", intro: bool = False,
) -> dict:
    """Put the atlas, its tables and the blitter into the expanded banks.

    Nothing is hooked up yet: the game still runs its own text engine and none
    of this is reachable. What it proves is that the pieces fit where the
    allocation map says they do, and that their addresses are stable.
    """
    pipeline = Pipeline.load(ROOT, CLEAN_ROM)
    tables = build_tables(pipeline.token_map, pipeline.atlas)

    placed: dict[str, int] = {}
    for name, payload in tables.blocks:
        at = allocation.allocate("glyph_atlas", f"atlas.{name}", len(payload), align=0x100)
        rom.write_at(at, payload)
        placed[name] = cpu_address(at)

    code_at = allocation.allocate("renderer_code", "blitter", 0x800, align=0x100)
    program = build_blitter(
        cpu_address(code_at),
        context_base("dialogue"),
        placed,
        len(pipeline.token_map.tokens),
        with_adapter=hook,
        script_banks=SCRIPT_BANKS,
        with_names=names,
    )
    if len(program.code) > 0x800:
        raise RomError(f"the blitter grew to {len(program.code)} bytes, past its reservation")
    rom.write_at(code_at, program.code)

    hooked = None
    if hook:
        # The story loop calls the stock rasteriser once per glyph. That call is
        # the only thing we take away from it.
        if rom.read_at(STORY_RASTER_CALL, 4) != STOCK_CALL_BYTES:
            raise RomError(
                f"the story loop does not look the way we expect at {STORY_RASTER_CALL:#08x}"
            )
        entry = program.labels["draw_thai_glyph"]
        rom.write_at(
            STORY_RASTER_CALL,
            bytes([0x22, entry & 0xFF, (entry >> 8) & 0xFF, entry >> 16]),
        )
        hooked = {
            "at": f"{STORY_RASTER_CALL:#08x}",
            "was": "jsl $8184EB",
            "now": f"jsl ${entry:06X}",
        }

    naming = None
    if naming_presets:
        clean = Rom.load_clean(CLEAN_ROM).to_bytes()
        writes, preset_report = preset_writes(ROOT, clean, pipeline)
        for write in writes:
            if rom.read_at(write.pc, len(write.expected)) != write.expected:
                raise RomError(f"{write.owner} no longer matches its asserted clean-ROM bytes")
            rom.write_at(write.pc, write.payload)

        fixed = fixed_advances(pipeline.token_map, pipeline.atlas)
        fixed_at = allocation.allocate(
            "glyph_atlas", "atlas.naming_fixed_advances", len(fixed), align=0x100
        )
        rom.write_at(fixed_at, fixed)
        naming_tables = {**placed, "advances": cpu_address(fixed_at)}
        naming_at = allocation.allocate("renderer_code", "naming_blitter", 0x800, align=0x100)
        naming_program = build_blitter(
            cpu_address(naming_at),
            context_base("naming"),
            naming_tables,
            len(pipeline.token_map.tokens),
            adapter_source=naming_adapter_source(),
        )
        if len(naming_program.code) > 0x800:
            raise RomError("naming blitter grew past its reservation")
        rom.write_at(naming_at, naming_program.code)
        parser_hooks = (
            (0x018402, bytes((0xC9, 0xF0, 0x00, 0x90, 0x23)), False),
            (0x01840F, bytes((0xC9, 0xF6, 0x00, 0xB0, 0xF3)), True),
        )
        parsers = []
        for index, (hook_at, expected, alternate) in enumerate(parser_hooks, start=1):
            parser_at = allocation.allocate(
                "hook_trampolines", f"naming_parser_{index}", 0x100, align=0x100
            )
            parser = assemble(parser_source(alternate=alternate), cpu_address(parser_at))
            parser_entry = parser.labels["naming_parser"]
            if len(parser.code) > 0x100:
                raise RomError("naming parser grew past its reservation")
            if rom.read_at(hook_at, len(expected)) != expected:
                raise RomError(f"naming parser hook changed at {hook_at:#08x}")
            rom.write_at(parser_at, parser.code)
            if not command_menu:
                rom.write_at(
                    hook_at,
                    bytes((0x5C, parser_entry & 0xFF, (parser_entry >> 8) & 0xFF, parser_entry >> 16, 0xEA)),
                )
            parsers.append({"at": f"{hook_at:#08x}", "entry": f"${parser_entry:06X}"})
        width_at = allocation.allocate("hook_trampolines", "naming_width", 0x100, align=0x100)
        width = assemble(width_source(), cpu_address(width_at))
        width_entry = width.labels["naming_width"]
        width_expected = bytes((0x85, 0x26, 0xC9, 0x00, 0x01))
        if rom.read_at(0x018456, len(width_expected)) != width_expected:
            raise RomError("naming width hook changed at 0x018456")
        rom.write_at(width_at, width.code)
        rom.write_at(
            0x018456,
            bytes((0x5C, width_entry & 0xFF, (width_entry >> 8) & 0xFF, width_entry >> 16, 0xEA)),
        )
        if rom.read_at(NAMING_RASTER_CALL, 4) != NAMING_RASTER_EXPECTED:
            raise RomError(f"naming raster call changed at {NAMING_RASTER_CALL:#08x}")
        entry = naming_program.labels["draw_naming_glyph"]
        if not command_menu:
            rom.write_at(
                NAMING_RASTER_CALL,
                bytes([0x22, entry & 0xFF, (entry >> 8) & 0xFF, entry >> 16]),
            )
        naming = {
            "hook": {"at": f"{NAMING_RASTER_CALL:#08x}", "entry": f"${entry:06X}"},
            "parser_hooks": parsers,
            "width_hook": {"at": "0x018456", "entry": f"${width_entry:06X}"},
            "blitter": {"cpu": f"{cpu_address(naming_at):#08x}", "bytes": len(naming_program.code)},
            "presets": preset_report,
        }

    command = None
    if command_menu:
        # `$82:843B` also parses ordinary catalog-13 records (for example the
        # map `%DWN` label).  P7 therefore keeps the master descriptor stock
        # and switches only the measured `$D2:8614…` parser pointers.
        command_runtime_enabled = True
        command_descriptor_enabled = False
        catalog = build_catalog13(ROOT, Rom.load_clean(CLEAN_ROM).to_bytes(), pipeline)
        pool_at = allocation.allocate("catalog_pool", "catalog_13", len(catalog.pool.payload), align=0x100)
        if cpu_address(pool_at) != (catalog.pool.bank << 16) | catalog.pool.address:
            raise RomError("catalog 13 allocation no longer matches its compiled pointer bank")
        rom.write_at(pool_at, catalog.pool.payload)
        overlays = build_command_overlay(ROOT, Rom.load_clean(CLEAN_ROM).to_bytes(), pipeline)
        overlay_payload, overlay_report = serialize_command_overlay(overlays, catalog.pool)
        overlay_at = allocation.allocate(
            "routing_tables", "command_overlay", len(overlay_payload), align=0x100
        )
        rom.write_at(overlay_at, overlay_payload)
        route_payload = native_route_table(overlays, catalog.pool)
        route_at = allocation.allocate(
            "routing_tables", "command_native_route", len(route_payload), align=0x100
        )
        rom.write_at(route_at, route_payload)
        index_payload = native_index_table(overlays)
        index_at = allocation.allocate(
            "routing_tables", "command_native_index", len(index_payload), align=0x100
        )
        rom.write_at(index_at, index_payload)

        menu_at = allocation.allocate("renderer_code", "menu_blitter", 0x1000, align=0x100)
        # Catalog 13 is shared by ordinary UI surfaces.  Its first installed
        # stage therefore uses the ordinary adapter only; command-menu frame
        # ownership is a later P7 hook after this shared path is proven live.
        menu_program = build_blitter(
            cpu_address(menu_at),
            context_base("menu"),
            placed,
            len(pipeline.token_map.tokens),
            adapter_source=menu_adapter_source(),
            script_banks=(0xFA, 0xFA),
            extra_constants=menu_adapter_constants(overlay=cpu_address(overlay_at)),
        )
        if len(menu_program.code) > 0x1000:
            raise RomError("menu blitter grew past its reservation")
        rom.write_at(menu_at, menu_program.code)

        descriptor_entry = None
        if command_descriptor_enabled:
            descriptor_at = allocation.allocate(
                "hook_trampolines", "menu_catalog_descriptor", 0x100, align=0x100
            )
            descriptor = assemble(
                menu_catalog_source(catalog.pool.address, menu_adapter_constants()["MENU_ACTIVE"]),
                cpu_address(descriptor_at),
            )
            if len(descriptor.code) > 0x100:
                raise RomError("menu catalog descriptor hook exceeds reservation")
            if rom.read_at(0x0183DA, 4) != bytes((0xBF, 0xD8, 0x00, 0xC9)):
                raise RomError("menu catalog descriptor hook changed at 0x0183da")
            rom.write_at(descriptor_at, descriptor.code)
            descriptor_entry = descriptor.labels["menu_catalog_descriptor"]
            rom.write_at(
                0x0183DA,
                bytes((0x22, descriptor_entry & 0xFF, (descriptor_entry >> 8) & 0xFF, descriptor_entry >> 16)),
            )

        parser_hooks = (
            (0x018402, bytes((0xC9, 0xF0, 0x00, 0x90, 0x23)), False),
            (0x01840F, bytes((0xC9, 0xF6, 0x00, 0xB0, 0xF3)), True),
        )
        parser_entries = []
        for index, (hook_at, expected, alternate) in enumerate(parser_hooks, start=1):
            parser_at = allocation.allocate(
                "hook_trampolines", f"menu_parser_{index}", 0x100, align=0x100
            )
            parser = assemble(menu_parser_source(alternate=alternate), cpu_address(parser_at))
            parser_entry = parser.labels["menu_parser"]
            if len(parser.code) > 0x100:
                raise RomError("menu parser grew past its reservation")
            if rom.read_at(hook_at, len(expected)) != expected:
                raise RomError(f"menu parser hook changed at {hook_at:#08x}")
            rom.write_at(parser_at, parser.code)
            if not naming_presets:
                rom.write_at(
                    hook_at,
                    bytes((0x5C, parser_entry & 0xFF, (parser_entry >> 8) & 0xFF, parser_entry >> 16, 0xEA)),
                )
            parser_entries.append({"at": f"{hook_at:#08x}", "entry": f"${parser_entry:06X}"})

        command_parser_entries = []
        for index, parser_entry in enumerate(parser_entries):
            router_at = allocation.allocate(
                "hook_trampolines", f"native_command_parser_{index + 1}", 0x200, align=0x100
            )
            router = assemble(
                native_command_source(
                    table_address=cpu_address(route_at),
                    index_table=cpu_address(index_at),
                    menu_active=menu_adapter_constants()["MENU_ACTIVE"],
                    record_count=menu_adapter_constants()["MENU_RECORD_COUNT"],
                    records=menu_adapter_constants()["MENU_RECORDS"],
                    max_records=menu_adapter_constants()["MENU_MAX_ROWS"],
                    row_tile=(0x7E << 16) | menu_adapter_constants()["MENU_ROW_TILE"],
                    row_pending=menu_adapter_constants()["MENU_ROW_PENDING"],
                    row_stride=menu_adapter_constants()["MENU_ROW_STRIDE"],
                    current_record=menu_adapter_constants()["MENU_CURRENT_RECORD"],
                    first_token=menu_adapter_constants()["MENU_FIRST_TOKEN"],
                    row_rendered=menu_adapter_constants()["MENU_ROW_RENDERED"],
                    selection_entry=menu_program.labels["menu_selection_sync"],
                    fallback_entry=int((parsers[index] if naming_presets else parser_entry)["entry"][1:], 16),
                    menu_entry=int(parser_entry["entry"][1:], 16),
                    active_cookie=menu_adapter_constants()["MENU_ROUTING_COOKIE"],
                    frame_ptr=(0x7E << 16) | menu_adapter_constants()["MENU_FRAME_PTR"],
                ),
                cpu_address(router_at),
            )
            if len(router.code) > 0x200:
                raise RomError("native command parser exceeds reservation")
            rom.write_at(router_at, router.code)
            command_parser_entries.append({
                "at": f"{parser_entry['at']}",
                "entry": f"${router.labels['native_command_parser']:06X}",
            })

        # Keep the stock writer's `$18` cursor contract.  The en reference
        # expands through renderer side effects; rebasing `$18` to shadow-map
        # coordinates here made the raster treat tilemap offsets as tile ids.
        command_width_entry = None

        hooks = (
            (0x0184E4, STOCK_CALL_BYTES, "menu_raster_dispatch"),
        )
        installed = []
        for hook_at, expected, label in hooks:
            if rom.read_at(hook_at, len(expected)) != expected:
                raise RomError(f"command-menu hook changed at {hook_at:#08x}")
            entry = menu_program.labels[label]
            if not naming_presets and command_stage in {"raster", "full"}:
                rom.write_at(hook_at, bytes((0x22, entry & 0xFF, (entry >> 8) & 0xFF, entry >> 16)))
                installed.append({"at": f"{hook_at:#08x}", "entry": f"${entry:06X}"})
        activation_at = 0x0284BB
        activation_entry = None
        open_at = 0x02843B
        open_entry = None
        selection_at = 0x0389F5
        selection_entry = None
        if command_stage == "full":
            open_expected = bytes((0x22, 0xC6, 0x83, 0x81))
            if rom.read_at(open_at, len(open_expected)) != open_expected:
                raise RomError(f"command-menu open hook changed at {open_at:#08x}")
            open_entry = menu_program.labels["menu_command_open"]
            rom.write_at(
                open_at,
                bytes((0x22, open_entry & 0xFF, (open_entry >> 8) & 0xFF, open_entry >> 16)),
            )
            selection_expected = bytes((0x22, 0xC6, 0x83, 0x81))
            if rom.read_at(selection_at, len(selection_expected)) != selection_expected:
                raise RomError(f"command-menu selection hook changed at {selection_at:#08x}")
            selection_entry = menu_program.labels["menu_selection_update"]
            rom.write_at(
                selection_at,
                bytes((0x22, selection_entry & 0xFF, (selection_entry >> 8) & 0xFF, selection_entry >> 16)),
            )
            activation_expected = bytes((0xA9, 0xFF, 0x00, 0x1C, 0x26))
            if rom.read_at(activation_at, len(activation_expected)) != activation_expected:
                raise RomError(f"command-menu activation hook changed at {activation_at:#08x}")
            activation_entry = menu_program.labels["menu_activation"]
            rom.write_at(
                activation_at,
                bytes((0x5C, activation_entry & 0xFF, (activation_entry >> 8) & 0xFF, activation_entry >> 16, 0xEA)),
            )
        command = {
            "stage": command_stage,
            "pool": catalog.report["destination"],
            "pool_bytes": len(catalog.pool.payload),
            "overlay": {"cpu": f"${cpu_address(overlay_at):06X}", **overlay_report},
            "native_route": {"cpu": f"${cpu_address(route_at):06X}", "bytes": len(route_payload)},
            "native_index": {"cpu": f"${cpu_address(index_at):06X}", "bytes": len(index_payload)},
            "runtime_enabled": command_runtime_enabled,
            "descriptor_hook": (
                {"at": "0x0183da", "entry": f"${descriptor_entry:06X}"}
                if descriptor_entry is not None else None
            ),
            "parser_hooks": parser_entries,
            "native_parser_hooks": command_parser_entries,
            "width_hook": (
                {"at": "0x018456", "entry": f"${command_width_entry:06X}"}
                if command_width_entry is not None else None
            ),
            "blitter": {"cpu": f"{cpu_address(menu_at):#08x}", "bytes": len(menu_program.code)},
            "hooks": installed,
            "activation_hook": (
                {"at": f"{activation_at:#08x}", "entry": f"${activation_entry:06X}"}
                if activation_entry is not None else None
            ),
            "open_hook": (
                {"at": f"{open_at:#08x}", "entry": f"${open_entry:06X}"}
                if open_entry is not None else None
            ),
            "selection_hook": (
                {"at": f"{selection_at:#08x}", "entry": f"${selection_entry:06X}"}
                if selection_entry is not None else None
            ),
        }

    if naming_presets and command_menu and command_runtime_enabled:
        shared = []
        for index, hook_at in enumerate((0x018402, 0x01840F)):
            at = allocation.allocate("hook_trampolines", f"shared_parser_{index + 1}", 0x100, align=0x100)
            dispatcher = assemble(shared_dispatch_source(
                int(parsers[index]["entry"][1:], 16),
                int(parser_entries[index]["entry"][1:], 16),
                int(command_parser_entries[index]["entry"][1:], 16),
            ), cpu_address(at))
            if len(dispatcher.code) > 0x100:
                raise RomError("shared parser dispatcher exceeds reservation")
            rom.write_at(at, dispatcher.code)
            entry = dispatcher.labels["shared_dispatch"]
            rom.write_at(hook_at, bytes((0x5C, entry & 0xFF, (entry >> 8) & 0xFF, entry >> 16, 0xEA)))
            shared.append({"at": f"{hook_at:#08x}", "entry": f"${entry:06X}"})
        at = allocation.allocate("hook_trampolines", "shared_raster", 0x100, align=0x100)
        menu_raster_entry = (
            menu_program.labels["menu_raster_dispatch"]
            if command_stage in {"raster", "full"}
            else STOCK_RASTERISER
        )
        dispatcher = assemble(shared_raster_source(
            default_entry=naming_program.labels["draw_naming_glyph"],
            menu_entry=menu_raster_entry,
        ), cpu_address(at))
        if len(dispatcher.code) > 0x100:
            raise RomError("shared raster dispatcher exceeds reservation")
        rom.write_at(at, dispatcher.code)
        entry = dispatcher.labels["shared_raster"]
        rom.write_at(NAMING_RASTER_CALL, bytes((0x22, entry & 0xFF, (entry >> 8) & 0xFF, entry >> 16)))
        naming["shared_dispatchers"] = {"parsers": shared, "raster": {"at": f"{NAMING_RASTER_CALL:#08x}", "entry": f"${entry:06X}"}}
        command["shared_dispatchers"] = naming["shared_dispatchers"]

    intro_report = None
    if intro:
        intro_build = build_intro(ROOT, Rom.load_clean(CLEAN_ROM).to_bytes(), pipeline, allocation)
        for at, payload in intro_build.writes:
            rom.write_at(at, payload)
        rom.write_at(intro_build.hook_pc, intro_build.hook_code)
        if rom.read_at(INTRO_HOOK_AT, len(INTRO_HOOK_EXPECTED)) != INTRO_HOOK_EXPECTED:
            raise RomError(f"intro hook changed at {INTRO_HOOK_AT:#08x}")
        entry = cpu_address(intro_build.hook_pc)
        rom.write_at(INTRO_HOOK_AT, bytes((0x5C, entry & 0xFF, (entry >> 8) & 0xFF, entry >> 16, 0xEA)))
        intro_report = intro_build.report

    return {
        "tables": {name: f"{address:#08x}" for name, address in placed.items()},
        "blitter": {
            "cpu": f"{cpu_address(code_at):#08x}",
            "pc": f"{code_at:#08x}",
            "bytes": len(program.code),
            "entry_points": {
                name: f"{value:#08x}"
                for name, value in sorted(program.labels.items())
                if name in ("clear_line", "blit_glyph", "blit_stream")
            },
        },
        "context": "dialogue",
        "hooked_up": hooked,
        "naming": naming,
        "command_menu": command,
        "intro": intro_report,
    }


def relocate_script(rom: Rom, allocation: AllocationMap, mode: str) -> dict:
    """Move the story blocks into the expanded banks and repoint everything.

    `mirror` keeps every offset exactly where it was and only changes which
    bank the block lives in. The bytes are the game's own, so the screen must
    come out identical -- which is the point: it separates "can we move the
    script at all" from "is our text right".
    """
    if mode == "none":
        return {"mode": mode, "moved_bytes": 0, "blocks": []}

    source = rom.to_bytes()
    if mode == "thai":
        pipeline = Pipeline.load(ROOT, CLEAN_ROM)
        document = json.loads(SCRIPT_SOURCE.read_text())
        translations = json.loads(
            (ROOT / "data" / "translations" / "script.th.json").read_text()
        )["messages"]
        for bank in range(SCRIPT_BANKS[0], SCRIPT_BANKS[1] + 1):
            allocation.allocate("text_streams", f"script.bank_{bank:02X}", 0x10000)
        result = repack(
            rom,
            source,
            document["summary"]["blocks"],
            document["messages"],
            translations,
            pipeline.tokenizer,
            pipeline.token_map,
            SCRIPT_BANKS[0],
            SCRIPT_BANKS[1],
        ).report
        result["moved_bytes"] = result["bytes"]
        layout = result.pop("layout")
        path = ROOT / "build" / "reports" / "script-layout.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(layout, indent=1) + "\n")
        return result
    if mode != "mirror":
        raise RomError(f"unknown relocation mode: {mode}")

    blocks = load_blocks(source, load_summary(SCRIPT_SOURCE))
    moves = plan_mirror(blocks, first_bank=0xF0)

    for bank in sorted({move.to_bank for move in moves}):
        allocation.allocate("text_streams", f"script.bank_{bank:02X}", 0x10000)

    result = mirror_banks(rom, moves, source)
    result["mode"] = mode
    result["banks"] = sorted({f"${move.to_bank:02X}" for move in moves})
    return result


def build(
    relocation: str = "none", names: bool = False, naming_presets: bool = False,
    command_menu: bool = False, intro: bool = False, command_stage: str = "full",
) -> tuple[bytes, dict]:
    """Produce the ROM image and its report. No I/O beyond reading inputs."""
    rom = Rom.load_clean(CLEAN_ROM)
    clean_bytes = rom.to_bytes()
    allocation = AllocationMap.load(ALLOCATION_MAP)

    rom.expand(EXPANDED_SIZE)

    script = relocate_script(rom, allocation, relocation)
    if naming_presets and relocation != "thai":
        raise RomError("naming presets require --relocate thai so runtime names use the new renderer")
    renderer = place_renderer(
        rom, allocation, hook=relocation == "thai", names=names or naming_presets,
        naming_presets=naming_presets, command_menu=command_menu,
        command_stage=command_stage, intro=intro,
    )

    checksum = rom.fix_checksum()
    payload = rom.to_bytes()

    # Everything below 3 MB must still be the clean ROM, apart from the header
    # checksum bytes we just rewrote.
    diff = [
        i
        for i in range(len(clean_bytes))
        if clean_bytes[i] != payload[i]
    ]
    report = {
        "stage": "P5",
        "input": {
            "path": str(CLEAN_ROM.relative_to(ROOT)),
            "bytes": len(clean_bytes),
            "sha256": CLEAN_SHA256,
        },
        "output": {
            "bytes": len(payload),
            "sha256": sha256(payload),
            "checksum": f"{checksum:#06x}",
            "complement": f"{checksum ^ 0xFFFF:#06x}",
        },
        "stock_bytes_changed": [f"{i:#08x}" for i in diff],
        "script": script,
        "renderer": renderer,
        "allocation": allocation.report(),
    }
    return payload, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--relocate",
        choices=("none", "mirror", "thai"),
        default="none",
        help="move the story script into the expanded banks",
    )
    parser.add_argument(
        "--naming-presets",
        action="store_true",
        help="install the fixed Thai player-name presets and the naming-screen adapter",
    )
    parser.add_argument("--out", type=Path, default=OUT_ROM)
    parser.add_argument(
        "--names",
        action="store_true",
        help="also draw the seven runtime name buffers ($FB xx 80). Off until "
             "the names in them are our tokens: the game's own bytes would be "
             "read as glyph ids and come out as nonsense.",
    )
    parser.add_argument(
        "--command-menu",
        action="store_true",
        help="install the catalog-13 command-menu pool and measured menu adapter",
    )
    parser.add_argument(
        "--command-stage",
        choices=("route", "raster", "full"),
        default="full",
        help="incremental command-menu hook set (requires --command-menu)",
    )
    parser.add_argument("--intro", action="store_true", help="install Thai opening-crawl overlays")
    parser.add_argument(
        "--proven-full",
        action="store_true",
        help="build the current-source cumulative naming/menu/story/title/intro ROM that passed the native Mesen battle route",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="build twice and fail unless both images are byte-identical",
    )
    args = parser.parse_args()

    if args.proven_full:
        incompatible = (
            args.relocate != "none" or args.names or args.naming_presets
            or args.command_menu or args.intro or args.command_stage != "full"
        )
        if incompatible:
            parser.error("--proven-full is a complete stage; do not combine it with incremental stage flags")
        out_rom = args.out.resolve()
        digest = build_current(CLEAN_ROM, out_rom, OUT_REPORT)
        if digest != CURRENT_FULL_SHA256:
            raise AssertionError("build_current returned without enforcing its hash")
        shown = out_rom.relative_to(ROOT) if out_rom.is_relative_to(ROOT) else out_rom
        print(f"{shown}  {out_rom.stat().st_size} bytes  sha256 {digest}")
        print("runtime gate: current-source native battle route passed; deterministic hash locked")
        return 0

    try:
        payload, report = build(
            args.relocate, args.names, args.naming_presets, args.command_menu,
            args.intro, args.command_stage,
        )
        if args.check:
            again, _ = build(
                args.relocate, args.names, args.naming_presets, args.command_menu,
                args.intro, args.command_stage,
            )
            if sha256(payload) != sha256(again):
                print("NOT deterministic: the two builds differ", file=sys.stderr)
                return 1
            report["deterministic"] = True
    except RomError as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 1

    out_rom = args.out.resolve()
    out_rom.parent.mkdir(parents=True, exist_ok=True)
    out_rom.write_bytes(payload)
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(json.dumps(report, indent=2) + "\n")

    out = report["output"]
    shown = out_rom.relative_to(ROOT) if out_rom.is_relative_to(ROOT) else out_rom
    print(f"{shown}  {out['bytes']} bytes  sha256 {out['sha256']}")
    print(f"checksum {out['checksum']}  changed stock bytes: {len(report['stock_bytes_changed'])}")
    blitter = report["renderer"]["blitter"]
    hooked = report["renderer"]["hooked_up"]
    if hooked:
        print(f"blitter {blitter['bytes']} bytes at {blitter['cpu']}, "
              f"hooked at {hooked['at']} ({hooked['was']} -> {hooked['now']})")
    else:
        print(f"blitter {blitter['bytes']} bytes at {blitter['cpu']}, not hooked up yet")
    script = report["script"]
    if script["moved_bytes"]:
        count = script["blocks"] if isinstance(script["blocks"], int) else len(script["blocks"])
        print(
            f"script relocated ({script['mode']}): {count} blocks, "
            f"{script['moved_bytes']:,} bytes into {', '.join(script['banks'])}"
        )
        if "records_in_thai" in script:
            print(
                f"   {script['records_in_thai']:,} records in Thai, "
                f"{script['records_copied_through']} copied through, "
                f"{script['address_fields_rewritten']} address fields rewritten"
            )
            if script["stranded_pointers"]:
                print(f"   {len(script['stranded_pointers'])} pointers could not be followed")
    if args.check:
        print("deterministic: two builds are byte-identical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
