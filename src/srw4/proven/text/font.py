#!/usr/bin/env python3
"""P5 — emit the combining Thai font page and its attribute tables.

This is the half of the new build that does not depend on the runtime renderer
existing yet: it turns `font/thai.json` + `font/encoding.json` into the exact
bytes the 65816 side will read, and checks every finished translation against
the line budget.  Nothing here writes to the ROM's code; the ROM patch lands in
P4/P5 once the renderer is testable.

Layout produced (sizes are fixed so the assembly can hard-code them):

    glyph page      256 x 16 bytes   1bpp, 16 rows, MSB leftmost
    advance table   256 bytes        pixels to move the pen; 0 for marks
    mark dx table   256 bytes        signed nudge from the right-align anchor
    mark y table    256 bytes        starting row
    mark size table 256 bytes        high nibble = height, low nibble = width
    base ink table  256 bytes        ink width; bases are stored left-normalised
    raised y table  256 bytes        tone row when a vowel is already stacked,
                                     $FF where the mark never raises

Mark sprites sit at rows 0..height-1 of their cell, not at their resting `y`.
The renderer has to be able to lift a mark clear of a tall base at runtime, so
the row offset has to be a number it adds, not something baked into the bitmap.
Bases keep their natural 16 rows.

    python3 tools/build_thai_font.py --report
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from . import encoding as enc
from . import stock
from .renderer import Renderer

ROOT = Path(__file__).resolve().parents[4] / "data" / "proven"
BUILD = ROOT / "build"

ROWS = 16
PAGE_GLYPHS = 256
TABLE_SIZE = 256

# Working line budget in cells, from docs/measurements.md section C.
LINE_BUDGET_CELLS = 32
LINE_BUDGET_PX = LINE_BUDGET_CELLS * 8


def sprite_to_cell(spec: dict) -> list[int]:
    """Place a mark sprite at the top of its cell, left-aligned.

    Its resting row travels in the mark-y table instead of being baked in, so
    the renderer can lift the mark clear of a tall base by adding to that number.
    """
    rows = [0] * ROWS
    for index, value in enumerate(spec["sprite"]):
        if index < ROWS:
            rows[index] = value & 0xFF
    return rows


def resize_display_rows(rows: list[int], sizing: dict) -> list[int]:
    """Enlarge a display glyph vertically while preserving its baseline."""
    if sizing.get("anchor") != "baseline":
        raise ValueError("display glyph sizing must be baseline-anchored")
    grow_up = int(sizing.get("grow_up_px", 0))
    grow_down = int(sizing.get("grow_down_px", 0))
    offset_y = int(sizing.get("offset_y_px", 0))
    if grow_up < 0 or grow_down < 0:
        raise ValueError("display glyph sizing cannot shrink")
    ink_rows = [index for index, row in enumerate(rows) if row]
    if not ink_rows or not (grow_up or grow_down):
        return rows
    top, bottom = ink_rows[0], ink_rows[-1]
    height = bottom - top + 1
    output_height = height + grow_up + grow_down
    result = [0] * ROWS
    for target in range(output_height):
        source = round(target * (height - 1) / max(1, output_height - 1))
        row = top - grow_up + offset_y + target
        if 0 <= row < ROWS:
            result[row] = rows[top + source]
    return result


def build_page(model: dict, layout: dict) -> dict[str, bytes]:
    codes = layout["codes"]
    blocks = layout["blocks"]

    page = bytearray(PAGE_GLYPHS * ROWS)
    advance = bytearray(TABLE_SIZE)
    mark_dx = bytearray(TABLE_SIZE)
    mark_y = bytearray(TABLE_SIZE)
    mark_size = bytearray(TABLE_SIZE)
    base_ink = bytearray(TABLE_SIZE)
    raised_y = bytearray(0xFF for _ in range(TABLE_SIZE))
    raised = model.get("raised_rows", {})
    display_sizing = model.get("display_sizing", {})
    latin_sizing = display_sizing.get("latin_and_digits", {})
    latin_tokens = set(str(latin_sizing.get("characters", "")))
    icons = enc.load_icons()

    for token, code in codes.items():
        offset = code * ROWS
        if token in icons["glyphs"]:
            # Artwork and spacers are explicitly assigned outside the normal
            # Thai base/mark blocks when necessary (notably <Gap> at $E2).
            page[offset : offset + ROWS] = bytes(icons["glyphs"][token])
            advance[code] = icons.get("advances", {}).get(token, icons["advance"])
            continue
        if code >= blocks["mark_above_base"]:
            spec = model["marks"][token]
            page[offset : offset + ROWS] = bytes(sprite_to_cell(spec))
            mark_dx[code] = spec["dx"] & 0xFF
            mark_y[code] = spec["y"]
            mark_size[code] = (min(spec["height"], 15) << 4) | min(spec["width"], 15)
            if token in raised:
                raised_y[code] = raised[token] & 0xFF
            continue
        spec = model["bases"].get(token)
        if spec is None:
            continue  # the space slot carries no ink
        # Bases are stored with their ink already at column 0.  The advance is
        # ink width plus one pixel of right bearing, so a glyph still carrying
        # its own left bearing would put the gap between two glyphs at "one
        # pixel plus whatever bearing the next one happens to have".  The
        # reference renderer compensates by blitting at `pen - left`; doing it
        # here instead costs the runtime nothing and needs no bearing table.
        left = spec["left"]
        rows = list(spec["rows"])
        if token in latin_tokens:
            rows = resize_display_rows(rows, latin_sizing)
        page[offset : offset + ROWS] = bytes((row << left) & 0xFF
                                             for row in rows)
        advance[code] = spec["advance"]
        base_ink[code] = min(spec["ink"], 15)

    advance[enc.SPACE] = 4

    # A shorthand byte has no glyph of its own — the renderer expands it into
    # the codes below and draws those.  Its advance still has to be right,
    # because the width check that decides whether a name fits reads this table
    # and never expands anything.
    first, second, third = enc.shorthand_tables(layout)
    for cluster, code in layout.get("shorthand", {}).items():
        advance[code] = advance[codes[cluster[0]]]
    for phrase, code in layout.get("phrases", {}).items():
        expansion = layout.get("phrase_expansions", {}).get(phrase, [])
        advance[code] = sum(advance[codes[token]] for token in expansion)

    return {
        "thai-page.bin": bytes(page),
        "thai-advance.bin": bytes(advance),
        "thai-mark-dx.bin": bytes(mark_dx),
        "thai-mark-y.bin": bytes(mark_y),
        "thai-mark-size.bin": bytes(mark_size),
        "thai-base-ink.bin": bytes(base_ink),
        "thai-raised-y.bin": bytes(raised_y),
        "thai-shorthand-1.bin": first,
        "thai-shorthand-2.bin": second,
        "thai-shorthand-3.bin": third,
    }


def collect_translations() -> dict[str, list[str]]:
    """Every finished Thai string, grouped by the field it has to fit."""
    translations = ROOT / "translations"
    groups: dict[str, list[str]] = {}

    def add(name: str, values) -> None:
        groups[name] = [v for v in values if v]

    for name, field in (
        ("weapons.th.json", "weapon"),
        ("units.th.json", "unit_name"),
        ("pilots.th.json", "pilot_name"),
    ):
        entries = json.loads((translations / name).read_text())
        add(field, [str(e.get("translation") or "").replace("<FB>", "") for e in entries])

    status = json.loads((translations / "pilot-status.th.json").read_text())
    for key, entries in status.items():
        if isinstance(entries, list):
            add(f"status_{key}", [str(e.get("translation") or "") for e in entries])

    script = json.loads((translations / "script.th.json").read_text())
    add("script", [str(v) for v in script.get("messages", {}).values()])
    return groups


def check(groups: dict[str, list[str]], renderer: Renderer) -> dict:
    """Encode everything and measure it; report anything that will not fit."""
    results: dict[str, dict] = {}
    for field, values in groups.items():
        widest = 0
        over: list[tuple[str, int]] = []
        failed: list[tuple[str, str]] = []
        saved = fixed = 0
        for text in values:
            clean = re.sub(r"<[^>]*>", "", text)
            for line in clean.split("\n"):
                if not line.strip():
                    continue
                width = 0
                failed_line = False
                for is_stock, segment in stock.mixed_segments(line):
                    if is_stock:
                        width += 8 * len(segment)
                        continue
                    try:
                        payload = enc.encode(
                            segment,
                            renderer.codes,
                            renderer.layout.get("shorthand"),
                            renderer.layout.get("phrases"),
                        )
                    except enc.EncodingError as error:
                        failed.append((line, str(error)))
                        failed_line = True
                        break
                    width += renderer.width_of(payload)
                if failed_line:
                    continue
                cells = -(-width // 8)
                widest = max(widest, cells)
                fixed += len(enc.clusters(line))
                saved += cells
                if cells > LINE_BUDGET_CELLS:
                    over.append((line, cells))
        results[field] = {
            "strings": len(values),
            "widest_cells": widest,
            "over_budget": over[:10],
            "over_budget_count": len(over),
            "encode_failures": failed[:10],
            "encode_failure_count": len(failed),
            "fixed_cells": fixed,
            "packed_cells": saved,
            "saving_pct": round(100 * (1 - saved / fixed), 1) if fixed else 0,
        }
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--out", type=Path, default=BUILD / "thai-font")
    args = parser.parse_args()

    model = json.loads((ROOT / "font" / "thai.json").read_text())
    layout = json.loads((ROOT / "font" / "encoding.json").read_text())
    renderer = Renderer(model, layout)

    artifacts = build_page(model, layout)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, payload in artifacts.items():
        (args.out / name).write_bytes(payload)
        print(f"  {name:22} {len(payload):5} bytes")

    results = check(collect_translations(), renderer)
    print()
    print(f"{'field':16} {'strings':>8} {'widest':>7} {'over':>5} {'fail':>5} {'saving':>7}")
    for field, stats in results.items():
        print(
            f"{field:16} {stats['strings']:8} {stats['widest_cells']:7} "
            f"{stats['over_budget_count']:5} {stats['encode_failure_count']:5} "
            f"{stats['saving_pct']:6}%"
        )

    if args.report:
        for field, stats in results.items():
            if stats["encode_failures"]:
                print(f"\n{field} encode failures:")
                for line, error in stats["encode_failures"]:
                    print(f"  {line!r}: {error}")
            if stats["over_budget"]:
                print(f"\n{field} over {LINE_BUDGET_CELLS} cells:")
                for line, cells in stats["over_budget"]:
                    print(f"  {cells:3} {line!r}")

    (BUILD / "thai-font-report.json").write_text(
        json.dumps(
            {
                "line_budget_cells": LINE_BUDGET_CELLS,
                "artifacts": {name: len(data) for name, data in artifacts.items()},
                "fields": results,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n"
    )
    print(f"\nwrote {(BUILD / 'thai-font-report.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
