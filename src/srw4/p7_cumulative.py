"""Install the current expanded command menu into the cumulative ROM layout."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .asm65816 import assemble
from .blitter import (
    STOCK_RASTERISER,
    build as build_blitter,
    build_tables,
    menu_adapter_constants,
    menu_adapter_source,
)
from .catalog13 import build as build_catalog13
from .command_overlay import (
    build as build_command_overlay,
    cell_streams,
    native_index_table,
    native_cell_route_table,
    serialize as serialize_command_overlay,
)
from .menu_router import native_command_source, parser_source
from .pipeline import Pipeline
from .rom import RomError


ROOT = Path(__file__).resolve().parents[2]
CLEAN = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
STOCK_CATALOG_GROUP_TABLE_PC = 0x0900D8
COMMAND_CATALOG_ID = 0x0022
COMMAND_STOCK_GEOMETRY = bytes.fromhex(
    "F10020F700FDFFFF11F203192012F6F9001BF20328201CF61B"
    "F20328201CF6F740FC01FEFBFF0DFCFC02F700FA13F2031A2014F6FEFFFE00FF"
)
COMMAND_EN_GEOMETRY = bytes.fromhex(
    "F10020F700FDFFFF11F206192012F6F9001BF20628201CF61B"
    "F20628201CF6F740FC01FEFBFF0DFCF902F700FA13F2061A2014F6FEFFFE00FF"
)


def cpu(pc: int) -> int:
    return ((0xC0 + (pc >> 16)) << 16) | (pc & 0xFFFF)


def _pc(cpu_address: int) -> int:
    """Map a HiROM CPU address to its physical ROM offset."""
    return ((cpu_address >> 16) & 0x3F) << 16 | (cpu_address & 0xFFFF)


def _stock_catalog_bounds(clean: bytes, catalog_id: int) -> tuple[int, int]:
    """Resolve one stock parser record through `$C9:00D8`, like `$81:83C6`."""
    group = (catalog_id >> 8) & 0xFF
    record = catalog_id & 0xFF
    group_entry = STOCK_CATALOG_GROUP_TABLE_PC + group * 3
    table_cpu = int.from_bytes(clean[group_entry:group_entry + 3], "little")
    table_pc = _pc(table_cpu)
    pointer_at = table_pc + record * 2
    start = int.from_bytes(clean[pointer_at:pointer_at + 2], "little")
    end = int.from_bytes(clean[pointer_at + 2:pointer_at + 4], "little")
    bank = table_cpu & 0xFF0000
    return _pc(bank | start), _pc(bank | end)


def _expand_command_geometry(
    payload: bytearray, clean: bytes, writes: list[dict]
) -> dict:
    """Apply the EN command record's native six-cell window geometry."""
    start, end = _stock_catalog_bounds(clean, COMMAND_CATALOG_ID)
    record = clean[start:end]
    offsets = [
        at for at in range(len(record))
        if record.startswith(COMMAND_STOCK_GEOMETRY, at)
    ]
    if len(offsets) != 1:
        raise RomError(
            "command geometry record is not unique in stock catalog $0022: "
            f"found {len(offsets)}"
        )
    pc = start + offsets[0]
    if payload[pc:pc + len(COMMAND_STOCK_GEOMETRY)] != COMMAND_STOCK_GEOMETRY:
        raise RomError(f"command geometry source changed at {pc:#08x}")
    payload[pc:pc + len(COMMAND_STOCK_GEOMETRY)] = COMMAND_EN_GEOMETRY
    patch = {
        "owner": "p7-command-en-geometry",
        "pc": f"0x{pc:06X}",
        "bytes": len(COMMAND_EN_GEOMETRY),
        "catalog": f"0x{COMMAND_CATALOG_ID:04X}",
        "content_cells": 6,
        "cursor_adjust": -7,
    }
    writes.append(patch)
    return patch


@dataclass(frozen=True)
class Layout:
    pool: int = 0x3A4000
    command_streams: int = 0x3A5000
    code: int = 0x3B0000
    overlay: int = 0x3C5000
    route: int = 0x3C7000
    index: int = 0x3C7100
    glyphs: int = 0x3E5000
    slots: int = 0x3E7900
    advances: int = 0x3E7F00
    operands: int = 0x3E8200
    parser_1: int = 0x3E9000
    parser_2: int = 0x3E9100
    native_1: int = 0x3E9200
    # Cached-row recovery adds a bounded fallback path; keep each native
    # router in an explicit $200-byte reservation instead of overlapping.
    native_2: int = 0x3E9400


LAYOUT = Layout()


def _place(payload: bytearray, pc: int, data: bytes, owner: str, writes: list[dict]) -> None:
    if payload[pc:pc + len(data)] != b"\xFF" * len(data):
        raise RomError(f"P7 allocation {owner} is not free at {pc:#08x}")
    payload[pc:pc + len(data)] = data
    writes.append({"owner": owner, "pc": f"0x{pc:06X}", "bytes": len(data)})


def apply(
    image: bytes,
    clean: bytes,
    *,
    lifecycle_hooks: frozenset[str] = frozenset({"open", "activation"}),
) -> tuple[bytes, dict]:
    """Build current labels and the guarded command-menu lifecycle hooks."""
    payload = bytearray(image)
    pipeline = Pipeline.load(ROOT, CLEAN)
    tables = build_tables(pipeline.token_map, pipeline.atlas)
    table_pcs = {
        "glyphs": LAYOUT.glyphs,
        "slots": LAYOUT.slots,
        "advances": LAYOUT.advances,
        "operands": LAYOUT.operands,
    }
    writes: list[dict] = []
    for name, data in tables.blocks:
        _place(payload, table_pcs[name], data, f"p7-{name}", writes)

    catalog = build_catalog13(
        ROOT, clean, pipeline, bank=0xFA, address=LAYOUT.pool & 0xFFFF
    )
    _place(payload, LAYOUT.pool, catalog.pool.payload, "p7-catalog-13", writes)
    overlays = build_command_overlay(ROOT, clean, pipeline)
    overlay, overlay_report = serialize_command_overlay(overlays, catalog.pool)
    streams, stream_pointers = cell_streams(
        overlays, address=cpu(LAYOUT.command_streams) & 0xFFFF
    )
    route = native_cell_route_table(overlays, stream_pointers)
    index = native_index_table(overlays)
    for pc, data, owner in (
        (LAYOUT.command_streams, streams, "p7-command-cell-streams"),
        (LAYOUT.overlay, overlay, "p7-overlay"),
        (LAYOUT.route, route, "p7-native-route"),
        (LAYOUT.index, index, "p7-native-index"),
    ):
        _place(payload, pc, data, owner, writes)

    placed = {name: cpu(pc) for name, pc in table_pcs.items()}
    constants = menu_adapter_constants(
        overlay=cpu(LAYOUT.overlay),
        cell_stream_first=stream_pointers[0] + 1,
        cell_stream_end=(LAYOUT.command_streams & 0xFFFF) + len(streams),
    )
    constants["STOCK_RASTERISER"] = STOCK_RASTERISER
    menu = build_blitter(
        cpu(LAYOUT.code),
        0xCC00,
        placed,
        len(pipeline.token_map.tokens),
        adapter_source=menu_adapter_source(),
        script_banks=(0xFA, 0xFA),
        extra_constants=constants,
    )
    # `$FB:0000-$0FFF` is a verified free allocation; the dynamic-frame
    # cleanup no longer fits the obsolete `$800` provisional reservation.
    if len(menu.code) > 0x1000:
        raise RomError("cumulative P7 menu code exceeds $1000 bytes")
    _place(payload, LAYOUT.code, menu.code, "p7-menu-code", writes)

    parser_specs = (
        (LAYOUT.parser_1, LAYOUT.native_1, False, 0xFD0300),
        (LAYOUT.parser_2, LAYOUT.native_2, True, 0xFD1300),
    )
    parser_entries = []
    for pc, _native_pc, alternate, _fallback in parser_specs:
        program = assemble(
            parser_source(
                alternate=alternate,
                cell_prepare_entry=menu.labels["menu_prepare_overlay_cell"],
            ),
            cpu(pc),
        )
        if len(program.code) > 0x100:
            raise RomError("cumulative P7 parser exceeds $100 bytes")
        _place(payload, pc, program.code, "p7-menu-parser", writes)
        parser_entries.append(program.labels["menu_parser"])

    native_entries = []
    for number, ((_parser_pc, pc, _alternate, fallback), menu_entry) in enumerate(
        zip(parser_specs, parser_entries), start=1
    ):
        program = assemble(
            native_command_source(
                table_address=cpu(LAYOUT.route),
                index_table=cpu(LAYOUT.index),
                menu_active=constants["MENU_ACTIVE"],
                record_count=constants["MENU_RECORD_COUNT"],
                records=constants["MENU_RECORDS"],
                max_records=constants["MENU_MAX_ROWS"],
                row_tile=(0x7E << 16) | constants["MENU_ROW_TILE"],
                row_pending=constants["MENU_ROW_PENDING"],
                row_stride=constants["MENU_ROW_STRIDE"],
                current_record=constants["MENU_CURRENT_RECORD"],
                first_token=constants["MENU_FIRST_TOKEN"],
                row_rendered=constants["MENU_ROW_RENDERED"],
                selection_entry=menu.labels["menu_selection_sync"],
                fallback_entry=fallback,
                menu_entry=menu_entry,
                active_cookie=constants["MENU_ROUTING_COOKIE"],
                stream_base=LAYOUT.command_streams & 0xFFFF,
                overlay_records=len(overlays),
                recovery_flag=constants["MENU_CACHE_RECOVERY"],
                frame_ptr=(0x7E << 16) | constants["MENU_FRAME_PTR"],
            ),
            cpu(pc),
        )
        if len(program.code) > 0x200:
            raise RomError("cumulative P7 native router exceeds $200 bytes")
        _place(payload, pc, program.code, f"p7-native-parser-{number}", writes)
        native_entries.append(program.labels["native_command_parser"])

    core_hooks = (
        (0x018402, bytes.fromhex("5C0003FDEA"), native_entries[0], "jml5"),
        (0x01840F, bytes.fromhex("5C0013FDEA"), native_entries[1], "jml5"),
        (0x0184E4, bytes.fromhex("22EB8481"), menu.labels["menu_raster_dispatch"], "jsl4"),
    )
    lifecycle_specs = (
        ("open", 0x02843B, bytes.fromhex("22C68381"), menu.labels["menu_command_open"], "jsl4"),
        ("activation", 0x0284BB, bytes.fromhex("A9FF001C26"), menu.labels["menu_activation"], "jml5"),
    )
    unknown = lifecycle_hooks - {spec[0] for spec in lifecycle_specs}
    if unknown:
        raise RomError(f"unknown P7 lifecycle hooks: {sorted(unknown)}")
    hooks = core_hooks + tuple(spec[1:] for spec in lifecycle_specs if spec[0] in lifecycle_hooks)
    hook_report = []
    for pc, expected, entry, kind in hooks:
        if payload[pc:pc + len(expected)] != expected:
            raise RomError(f"cumulative P7 hook source changed at {pc:#08x}")
        opcode = 0x22 if kind == "jsl4" else 0x5C
        replacement = bytes((opcode, entry & 0xFF, entry >> 8 & 0xFF, entry >> 16))
        if len(expected) > 4:
            replacement += b"\xEA" * (len(expected) - 4)
        payload[pc:pc + len(expected)] = replacement
        hook_report.append({"pc": f"0x{pc:06X}", "entry": f"${entry:06X}"})

    geometry_patch = _expand_command_geometry(payload, clean, writes)

    return bytes(payload), {
        "labels": [overlay.translation for overlay in overlays],
        "pool_bytes": len(catalog.pool.payload),
        "overlay": overlay_report,
        "cell_stream_bytes": len(streams),
        "menu_code_bytes": len(menu.code),
        "writes": writes,
        "hooks": hook_report,
        "geometry_patch": geometry_patch,
    }
