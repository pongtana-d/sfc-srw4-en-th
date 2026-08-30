#!/usr/bin/env python3
"""P3: build one glyph per token in the manifest, and a sheet to check them by eye.

  tools/build_atlas.py            -> build/atlas/*, build/reports/atlas.json
  tools/build_atlas.py --used     only the tokens the compiled script actually uses
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.atlas import CELL_ROWS, CELL_WIDTH, AtlasBuilder  # noqa: E402
from srw4.png import write_greyscale  # noqa: E402
from srw4.rom import Rom  # noqa: E402
from srw4.tokens import EncodingError, TokenMap  # noqa: E402

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
FONT_DIR = ROOT / "data" / "font"
MANIFEST = FONT_DIR / "renewal-clusters.json"
OUT_DIR = ROOT / "build" / "atlas"
OUT_REPORT = ROOT / "build" / "reports" / "atlas.json"

SCALE = 3
GAP = 2
COLUMNS = 32
INK = 0
PAPER = 255
GRID = 220
BASELINE = 245     # a faint band behind the cell, so extents are visible


def proof_sheet(glyphs: list) -> list[list[int]]:
    """A grid of every glyph, scaled up, on a faintly tinted cell."""
    cell_w = CELL_WIDTH * SCALE + GAP
    cell_h = CELL_ROWS * SCALE + GAP
    rows = (len(glyphs) + COLUMNS - 1) // COLUMNS
    width = COLUMNS * cell_w
    height = rows * cell_h
    canvas = [[GRID] * width for _ in range(height)]

    for position, glyph in enumerate(glyphs):
        column, row = position % COLUMNS, position // COLUMNS
        x0, y0 = column * cell_w, row * cell_h
        for y in range(CELL_ROWS):
            bits = glyph.rows[y]
            for x in range(CELL_WIDTH):
                lit = bits >> (7 - x) & 1
                shade = INK if lit else (BASELINE if x < glyph.advance else PAPER)
                for dy in range(SCALE):
                    line = canvas[y0 + y * SCALE + dy]
                    for dx in range(SCALE):
                        line[x0 + x * SCALE + dx] = shade
    return canvas


def build(only_used: bool) -> dict:
    token_map = TokenMap.load(MANIFEST)
    rom = Rom.load_clean(CLEAN_ROM).to_bytes()
    builder = AtlasBuilder(FONT_DIR, rom)

    tokens = list(token_map.tokens)
    if only_used:
        index = json.loads((ROOT / "build" / "streams" / "script-index.json").read_text())
        del index  # the index does not carry tokens; fall back to the manifest
    glyphs = []
    failures = []
    for token in tokens:
        try:
            glyphs.append(builder.build(token))
        except EncodingError as exc:
            failures.append({"token": token, "error": str(exc)})

    # Dedupe on the bitmap alone: two tokens may share an image but keep their
    # own metrics.
    bitmaps: dict[tuple[int, ...], int] = {}
    entries = []
    for glyph in glyphs:
        slot = bitmaps.setdefault(glyph.rows, len(bitmaps))
        entries.append(
            {
                "token": glyph.token,
                "id": token_map.index(glyph.token),
                "bitmap": slot,
                "source": glyph.source,
                **glyph.metrics(),
            }
        )

    packed = bytearray()
    for rows in bitmaps:
        packed += bytes(rows)

    sources = Counter(glyph.source for glyph in glyphs)
    blank = [e["token"] for e in entries if e["ink_width"] == 0]
    spans = Counter(e["cell_span"] for e in entries)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "glyphs.bin").write_bytes(bytes(packed))
    (OUT_DIR / "metrics.json").write_text(json.dumps(entries, indent=1, ensure_ascii=False) + "\n")
    write_greyscale(OUT_DIR / "proof-sheet.png", proof_sheet(glyphs))

    return {
        "stage": "P3",
        "tokens": {
            "in_manifest": len(token_map.tokens),
            "built": len(glyphs),
            "failed": len(failures),
        },
        "bitmaps": {
            "unique": len(bitmaps),
            "bytes": len(packed),
            "shared": len(glyphs) - len(bitmaps),
        },
        "sources": dict(sources),
        "cell_span": {str(k): v for k, v in sorted(spans.items())},
        "blank_glyphs": blank,
        "advance": {
            "min": min((e["advance"] for e in entries), default=0),
            "max": max((e["advance"] for e in entries), default=0),
        },
        "findings": {"failures": failures},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--used", action="store_true", help="(reserved) restrict to used tokens")
    args = parser.parse_args()

    report = build(args.used)
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    tok, bit = report["tokens"], report["bitmaps"]
    print(f"built {tok['built']}/{tok['in_manifest']} glyphs, {tok['failed']} failed")
    print(f"{bit['unique']} unique bitmaps ({bit['shared']} shared), {bit['bytes']:,} bytes")
    print("sources: " + ", ".join(f"{k} {v}" for k, v in sorted(report["sources"].items())))
    print(f"advance {report['advance']['min']}-{report['advance']['max']} px")
    print(f"proof sheet: {(OUT_DIR / 'proof-sheet.png').relative_to(ROOT)}")
    return 1 if report["findings"]["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
