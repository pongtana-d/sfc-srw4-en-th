"""Verified Thai VWF builder for the map Spirit help messages."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from .catalogs import Write
from .text.encoding import CONTROL_BASE, advance_table, encode
from .text.stock import encode_stock, thai_first_segments


LINE_BREAK = 0xF6


def _number(value: str) -> int:
    return int(value, 0)


def _route_runs(start: int, flags: list[bool]) -> list[tuple[int, int]]:
    """Convert byte flags to ranges of already-advanced source pointers."""
    result: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(flags):
        if not flags[cursor]:
            cursor += 1
            continue
        run = cursor
        while cursor < len(flags) and flags[cursor]:
            cursor += 1
        result.append(((start + run + 1) & 0xFFFF, (start + cursor + 1) & 0xFFFF))
    return result


def _advance_pen(pen: int, payload: bytes, advances: bytes) -> tuple[int, bool]:
    """Return the pen after `payload` and whether its last glyph spilled."""
    spilled = False
    for code in payload:
        if code >= CONTROL_BASE:
            continue
        step = advances[code]
        if not step:
            continue
        pen += step
        crossed = False
        while pen >= 8:
            pen -= 8
            crossed = True
        spilled = crossed and bool(pen)
    return pen, spilled


def _encode_line(
    value: str,
    layout: dict[str, object],
    advances: bytes,
    thai_chars: frozenset[str],
) -> tuple[bytes, list[bool], int, int, str]:
    payload = bytearray()
    routes: list[bool] = []
    width = 0
    pen = 0
    spilled = False
    guards = 0
    stock_text = ""
    space = int(layout["codes"][" "])
    for is_stock, part in thai_first_segments(value, thai_chars):
        if is_stock:
            if spilled:
                # The engine prepares the next tilemap word between source
                # bytes, so a stock glyph that follows a spilling Thai glyph
                # replaces the spill. One real space keeps the tail.
                payload.append(space)
                routes.append(True)
                width += advances[space]
                guards += 1
            # These messages are fixed-position scripts, so direct stock bytes
            # are safe and keep HP/EN/EXP adjacent to the VWF run. The FB run
            # macro is for pointer catalogs; inside this parser it consumes a
            # whole prepared cell per operand and leaves a visible gap.
            stock_text += part
            encoded = encode_stock(part)
            payload.extend(encoded)
            routes.extend([False] * len(encoded))
            # A stock glyph starts on the next whole cell, so an open Thai
            # cell is paid for in full before it.
            if pen:
                width += 8 - pen
            width += len(part) * 8
            pen = 0
            spilled = False
            continue
        encoded = encode(
            part,
            layout["codes"],
            layout.get("shorthand"),
            layout.get("phrases"),
        )
        payload.extend(encoded)
        routes.extend([True] * len(encoded))
        width += sum(advances[code] for code in encoded)
        pen, spilled = _advance_pen(pen, encoded, advances)
    return bytes(payload), routes, width, guards, stock_text


def build_spirit_help_data(
    root: Path, clean: bytes, *, translation_dir: Path | None = None
) -> tuple[list[Write], dict[str, object]]:
    """Replace the 29 fixed-position help records and route Thai bytes only."""
    translations = translation_dir or root / "translations"
    text = json.loads((translations / "spirit-descriptions.th.json").read_text(encoding="utf-8"))
    layout_info = text["_layout"]
    script = layout_info["script"]
    script_start = _number(str(script["address"]))
    script_end = _number(str(script["end"]))
    actual_hash = sha256(clean[script_start:script_end]).hexdigest()
    expected_hash = str(script["source_sha256"])
    if actual_hash != expected_hash:
        raise ValueError(
            f"Spirit help script hash mismatch: {actual_hash} != {expected_hash}"
        )

    layout = json.loads((root / "font/encoding.json").read_text(encoding="utf-8"))
    model = json.loads((root / "font/thai.json").read_text(encoding="utf-8"))
    advances = advance_table(model, layout)
    thai_chars = frozenset(
        key for key in layout["codes"] if len(key) == 1
    )
    line_width = int(layout_info["help_box"]["line_width_px"])
    max_lines = int(layout_info["help_box"]["max_lines"])

    messages = sorted(text["script_messages"], key=lambda item: int(item["spirit_id"]))
    if [int(item["spirit_id"]) for item in messages] != list(range(1, 30)):
        raise ValueError("Spirit help must cover Spirit IDs 1-29 exactly")

    writes: list[Write] = []
    route_ranges: list[tuple[int, int]] = []
    report: list[dict[str, object]] = []
    cursor = script_start
    preserved = {
        _number(str(item["address"])): item
        for item in layout_info.get("preserved_spans", [])
    }
    wrapped: list[int] = []
    for item in messages:
        start = _number(str(item["source_pc"]))
        expected = bytes.fromhex(str(item["source_hex"]))
        if start != cursor:
            gap = preserved.get(cursor)
            if gap is None or _number(str(gap["end"])) != start:
                raise ValueError(f"unexpected Spirit help gap at {cursor:#x}-{start:#x}")
            gap_expected = bytes.fromhex(str(gap["source_hex"]))
            if len(gap_expected) != start - cursor or clean[cursor:start] != gap_expected:
                raise ValueError(f"Spirit help preserved span mismatch at {cursor:#x}")
            cursor = start
        if not expected or expected[-1] != 0xFF:
            raise ValueError(f"Spirit help record at {start:#x} has no terminator")
        if clean[start:start + len(expected)] != expected:
            raise ValueError(f"Spirit help source mismatch at {start:#x}")

        lines = str(item["translation"]).split("\n")
        if not 1 <= len(lines) <= max_lines or any(not line for line in lines):
            raise ValueError(f"Spirit help ID {item['spirit_id']} has invalid lines")
        payload = bytearray()
        route_flags: list[bool] = []
        widths: list[int] = []
        guards = 0
        stock_text = ""
        for index, line in enumerate(lines):
            encoded, flags, width, line_guards, line_stock = _encode_line(
                line, layout, advances, thai_chars
            )
            guards += line_guards
            stock_text += line_stock
            if width > line_width:
                raise ValueError(
                    f"Spirit help ID {item['spirit_id']} is {width}px; "
                    f"line holds {line_width}px"
                )
            payload.extend(encoded)
            route_flags.extend(flags)
            widths.append(width)
            if index + 1 < len(lines):
                payload.append(LINE_BREAK)
                route_flags.append(False)
        if len(lines) == 2:
            wrapped.append(int(item["spirit_id"]))

        capacity = len(expected) - 1
        if len(payload) > capacity:
            raise ValueError(
                f"Spirit help ID {item['spirit_id']} needs {len(payload)} bytes; "
                f"record holds {capacity}"
            )
        replacement = bytes(payload) + b"\xFF" * (len(expected) - len(payload))
        writes.append(Write(start, replacement, f"spirit-help:{item['spirit_id']}", False))
        # Route the first terminator as Thai too. This closes the active VWF
        # run before the stock parser handles $FF; unused padding is never read.
        route_flags.append(True)
        route_ranges.extend(_route_runs(start, route_flags))
        report.append({
            "spirit_id": int(item["spirit_id"]),
            "source": item["source"],
            "translation": item["translation"],
            "pc": f"0x{start:06X}",
            "encoded_bytes": len(payload),
            "capacity": capacity,
            "line_widths_px": widths,
            "lines": len(lines),
            "padding": capacity - len(payload),
            "stock_encoding": "direct",
            "spill_guards": guards,
            "stock_text": stock_text,
        })
        cursor = start + len(expected)

    if cursor != script_end:
        raise ValueError(
            f"Spirit help block ends at {cursor:#x}; expected {script_end:#x}"
        )
    expected_wrapped = [int(value) for value in layout_info["help_box"]["wrapped_ids"]]
    if wrapped != expected_wrapped:
        raise ValueError(f"Spirit help wrapped IDs changed: {wrapped!r}")

    return writes, {
        "script_start": f"0x{script_start:06X}",
        "script_end": f"0x{script_end:06X}",
        "messages": report,
        "wrapped_ids": wrapped,
        "source_routes": {
            "0xCC": [[start, end] for start, end in route_ranges]
        },
    }
