#!/usr/bin/env python3
"""Draw characters into `thai.json` from the project's own TTF.

The Latin and digits already in the font file were made this way and then
tidied by hand, so this is not a new method -- it is the old one written down.
Rendering `m` and `1` with it reproduces what is in the file exactly, and the
others differ only where somebody cleaned up a diagonal.

The baseline is not guessed: `x` has neither ascender nor descender, so
wherever its last inked row lands is the baseline, and every glyph is placed
against that. The left bearing is dropped the same way the ROM-font import
drops it -- a glyph drawn three pixels in and advanced three vanishes under
the next one.

  tools/draw_from_font.py --check abcdefg     compare, change nothing
  tools/draw_from_font.py --write abcdefg     add them to thai.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

FONT = ROOT / "assets" / "fonts" / "RD CHULAJARUEK" / "RD CHULAJARUEK.ttf"
THAI = ROOT / "data" / "font" / "thai.json"
SIZE = 12          # what the existing glyphs were drawn at
THRESHOLD = 110    # anything paler is not a pixel at this size
CELL_WIDTH, CELL_ROWS = 8, 16
BASELINE = 12      # the row `x` sits on, and every other glyph with it
MIN_ADVANCE, MAX_ADVANCE = 3, 8


def ink(font, char: str, pad: int = 6) -> list[tuple[int, int]]:
    image = Image.new("L", (24, 28), 0)
    ImageDraw.Draw(image).text((pad, pad), char, font=font, fill=255)
    pixels = image.load()
    return [
        (x, y)
        for y in range(28)
        for x in range(24)
        if pixels[x, y] > THRESHOLD
    ]


def draw(font, char: str, baseline: int) -> dict:
    points = ink(font, char)
    if not points:
        raise SystemExit(f"the font has nothing for {char!r}")
    left = min(x for x, _ in points)
    rows = [0] * CELL_ROWS
    for x, y in points:
        row, column = y - baseline + BASELINE, x - left
        if not (0 <= row < CELL_ROWS):
            raise SystemExit(f"{char!r} does not fit the cell: row {row}")
        if not (0 <= column < CELL_WIDTH):
            raise SystemExit(f"{char!r} is wider than the cell: column {column}")
        rows[row] |= 0x80 >> column
    width = max(column for column, _ in ((x - left, y) for x, y in points)) + 1
    top = min(row for row in range(CELL_ROWS) if rows[row])
    return {
        "rows": rows,
        "left": 0,
        "ink": width,
        "top": top,
        "advance": min(max(width + 1, MIN_ADVANCE), MAX_ADVANCE),
    }


def art(rows: list[int]) -> list[str]:
    return ["".join("#" if row & (0x80 >> i) else "." for i in range(CELL_WIDTH)) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chars", help="the characters to draw, as one string")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    font = ImageFont.truetype(str(FONT), SIZE)
    baseline = max(y for _, y in ink(font, "x"))
    document = json.loads(THAI.read_text())
    bases = document["bases"]

    added, differ = [], []
    for char in args.chars:
        entry = draw(font, char, baseline)
        old = bases.get(char)
        if old is None:
            added.append(char)
        elif old["rows"] != entry["rows"]:
            differ.append(char)
            continue                      # never overwrite a hand-tidied glyph
        bases[char] = entry
        lines = art(entry["rows"])
        print(f"  {char}  ink {entry['ink']} advance {entry['advance']}"
              f"{'  (already there, unchanged)' if old else ''}")
        for line in lines[5:15]:
            print("     " + line)

    if differ:
        print(f"\nleft alone, the file's version differs: {''.join(differ)}")
    if args.write and added:
        document["bases"] = dict(sorted(bases.items()))
        THAI.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
        print(f"\nwrote {len(added)} new glyphs into {THAI.relative_to(ROOT)}")
    elif added:
        print(f"\n{len(added)} would be added; pass --write to keep them")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
