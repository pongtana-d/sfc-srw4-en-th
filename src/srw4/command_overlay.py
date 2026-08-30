"""Pre-rendered command-menu labels for the eventual P7 reflow adapter.

The stock command writer is vertical and only owns one Japanese cell per
label.  A runtime reflow must therefore receive fixed, audited tiles rather
than try to reinterpret arbitrary token bytes while it is also maintaining
the game's menu state.  This module derives the affected catalog-13 slots
from asserted source addresses and emits exactly those tile payloads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .catalog import load, read_slots
from .catalog_pool import CatalogPool
from .pipeline import Pipeline
from .rom import RomError


CATALOG_INDEX = 13
MAX_LABEL_WIDTH = 56  # widest approved command label; seven 8px cells
NATIVE_FIRST_ADVANCED = 0x8614
NATIVE_ADVANCED_SPAN = 0x47
SERIALIZED_CELLS = 6
SERIALIZED_ROW_BYTES = SERIALIZED_CELLS * 64
# Six verified direct tokens from the existing `เคลื่อนที่` record.  Their
# pixels are ignored; they preserve the parser's proven six-glyph cadence while
# the overlay raster supplies one 8x16 bitmap cell per token.
COMMAND_CELL_TOKENS = bytes([0x03]) * SERIALIZED_CELLS


def _serialize_planar_row(tiles: bytes, cells: int) -> bytes:
    """Expand one 1bpp 8x16 run into the menu's ready-to-copy 4bpp row."""
    if len(tiles) != cells * 16 or cells > SERIALIZED_CELLS:
        raise RomError("command overlay tile payload violates the fixed row contract")
    payload = bytearray()
    for cell in range(SERIALIZED_CELLS):
        bitmap = tiles[cell * 16:(cell + 1) * 16] if cell < cells else bytes(16)
        for half in (bitmap[:8], bitmap[8:]):
            for value in half:
                payload.extend((value, 0xFF))
            payload.extend(bytes(16))
    if len(payload) != SERIALIZED_ROW_BYTES:
        raise RomError("serialized command row has the wrong planar size")
    return bytes(payload)


@dataclass(frozen=True)
class CommandOverlay:
    """One command source record rendered as a single 1bpp tile run."""

    address: int
    source: str
    translation: str
    slots: tuple[int, ...]
    width_px: int
    cells: int
    tiles: bytes


def serialize(overlays: tuple[CommandOverlay, ...], pool: CatalogPool) -> tuple[bytes, dict]:
    """Encode lookup rows keyed by the relocated pool-record range.

    Header: count (u16).  Every following eight-byte row is ``start, end,
    width, cells, tile_offset`` in little endian.  ``end`` is exclusive and
    lets the runtime match its already-advanced source pointer without trying
    to decode controls a second time.
    """
    records: list[tuple[int, int, CommandOverlay]] = []
    for overlay in overlays:
        starts = {pool.slot_pointers[slot] for slot in overlay.slots}
        if len(starts) != 1:
            raise RomError(f"command overlay {overlay.source!r} split across pool records")
        start = starts.pop()
        record = next((row for row in pool.records if row[1] == start), None)
        if record is None:
            raise RomError(f"command overlay {overlay.source!r} has no pool record")
        records.append((start, start + record[2], overlay))
    records.sort(key=lambda row: row[0])
    if len({start for start, _, _ in records}) != len(records):
        raise RomError("command overlay records are not unique")

    table_size = 2 + len(records) * 8
    payload = bytearray(len(records).to_bytes(2, "little"))
    tiles = bytearray()
    rows = []
    for start, end, overlay in records:
        offset = table_size + len(tiles)
        payload.extend(start.to_bytes(2, "little"))
        payload.extend(end.to_bytes(2, "little"))
        payload.extend((overlay.width_px, overlay.cells))
        payload.extend(offset.to_bytes(2, "little"))
        planar = _serialize_planar_row(overlay.tiles, overlay.cells)
        tiles.extend(planar)
        rows.append({
            "source": overlay.source,
            "slots": list(overlay.slots),
            "start": f"${start:04X}",
            "end": f"${end:04X}",
            "width_px": overlay.width_px,
            "cells": overlay.cells,
            "tile_offset": f"${offset:04X}",
            "tile_bytes": len(planar),
        })
    payload.extend(tiles)
    return bytes(payload), {"bytes": len(payload), "records": rows}


def native_route_table(overlays: tuple[CommandOverlay, ...], pool: CatalogPool) -> bytes:
    """Return the sparse `$D2:8614..865A` -> `$FA` parser-pointer map."""
    table = bytearray(NATIVE_ADVANCED_SPAN * 2)
    for overlay in overlays:
        starts = {pool.slot_pointers[slot] for slot in overlay.slots}
        if len(starts) != 1:
            raise RomError(f"command route {overlay.source!r} split across pool records")
        advanced = (overlay.address & 0xFFFF) + 1
        offset = advanced - NATIVE_FIRST_ADVANCED
        if offset < 0 or offset >= NATIVE_ADVANCED_SPAN:
            raise RomError(f"command route {overlay.source!r} is outside the native range")
        # The runtime router must fetch the relocated record's first token;
        # its incoming A still belongs to the native `$D2` record.
        destination = starts.pop()
        if destination > 0xFFFF:
            raise RomError(f"command route {overlay.source!r} crosses the `$FA` bank")
        at = offset * 2
        if table[at:at + 2] != b"\x00\x00":
            raise RomError(f"command route {overlay.source!r} duplicates a native pointer")
        table[at:at + 2] = destination.to_bytes(2, "little")
    return bytes(table)


def cell_streams(
    overlays: tuple[CommandOverlay, ...], *, address: int
) -> tuple[bytes, tuple[int, ...]]:
    """Build EN-shaped six-cell records for the stock command writer.

    The visible pixels come from the pre-rendered overlay.  These bytes exist
    solely so the stock parser advances its tilemap cursor exactly six narrow
    cells and keeps ownership of every border/highlight side effect.
    """
    if len(COMMAND_CELL_TOKENS) != SERIALIZED_CELLS:
        raise RomError("command cell token cadence is not six glyphs")
    record = COMMAND_CELL_TOKENS + b"\xFF"
    payload = record * len(overlays)
    pointers = tuple(address + index * len(record) for index in range(len(overlays)))
    if pointers and pointers[-1] + len(record) > 0x10000:
        raise RomError("command cell streams cross their bank")
    return payload, pointers


def native_cell_route_table(
    overlays: tuple[CommandOverlay, ...], pointers: tuple[int, ...]
) -> bytes:
    """Map native command records to the private EN-shaped cell streams."""
    if len(pointers) != len(overlays):
        raise RomError("command stream pointer count does not match overlays")
    table = bytearray(NATIVE_ADVANCED_SPAN * 2)
    for overlay, destination in zip(overlays, pointers):
        advanced = (overlay.address & 0xFFFF) + 1
        offset = advanced - NATIVE_FIRST_ADVANCED
        if offset < 0 or offset >= NATIVE_ADVANCED_SPAN:
            raise RomError(f"command route {overlay.source!r} is outside the native range")
        at = offset * 2
        if table[at:at + 2] != b"\x00\x00":
            raise RomError(f"command route {overlay.source!r} duplicates a native pointer")
        table[at:at + 2] = destination.to_bytes(2, "little")
    return bytes(table)


def native_index_table(overlays: tuple[CommandOverlay, ...]) -> bytes:
    """Return the sparse native parser-pointer -> overlay-record index map.

    `$FF` means that the parser pointer is not a command-record beginning.
    The value is deliberately independent of the relocated catalog pool so a
    runtime copier can select bitmap data without re-decoding token bytes.
    """
    table = bytearray([0xFF]) * NATIVE_ADVANCED_SPAN
    for index, overlay in enumerate(overlays):
        advanced = (overlay.address & 0xFFFF) + 1
        offset = advanced - NATIVE_FIRST_ADVANCED
        if offset < 0 or offset >= len(table):
            raise RomError(f"command index {overlay.source!r} is outside the native range")
        if table[offset] != 0xFF:
            raise RomError(f"command index {overlay.source!r} duplicates a native pointer")
        table[offset] = index
    return bytes(table)


def build(root: Path, clean: bytes, pipeline: Pipeline) -> tuple[CommandOverlay, ...]:
    """Compile every command label with its verified catalog-13 slot(s)."""
    document = json.loads((root / "data" / "translations" / "unit-commands.th.json").read_text())
    commands = document.get("commands")
    if not isinstance(commands, list) or not commands:
        raise RomError("unit command translations are missing")

    descriptor = next(item for item in load(clean) if item.index == CATALOG_INDEX)
    pointers = read_slots(clean, descriptor)
    overlays: list[CommandOverlay] = []
    claimed: set[int] = set()
    for index, command in enumerate(commands):
        if not isinstance(command, dict):
            raise RomError(f"unit command {index} is not an object")
        try:
            address = int(str(command["address"]), 0)
            source = str(command["source"])
            translation = str(command["translation"])
        except (KeyError, ValueError) as exc:
            raise RomError(f"unit command {index} is malformed") from exc
        slots = tuple(slot for slot, pointer in enumerate(pointers) if pointer == (address & 0xFFFF))
        if not slots:
            raise RomError(f"unit command {source!r} has no catalog-13 slot")
        if claimed.intersection(slots):
            raise RomError(f"unit command {source!r} reuses a previous slot")
        claimed.update(slots)

        rendered = pipeline.draw(translation, where=f"command-overlay[{source}]")
        if len(rendered.lines) != 1 or rendered.terminator is not None:
            raise RomError(f"unit command {source!r} has engine controls, not one drawable line")
        line = rendered.lines[0]
        if line.width <= 0 or line.width > MAX_LABEL_WIDTH or line.canvas.overflow:
            raise RomError(f"unit command {source!r} width {line.width}px exceeds overlay contract")
        overlays.append(CommandOverlay(
            address=address,
            source=source,
            translation=translation,
            slots=slots,
            width_px=line.width,
            cells=(line.width + 7) // 8,
            tiles=line.canvas.to_tiles()[:((line.width + 7) // 8) * 16],
        ))
    return tuple(overlays)
