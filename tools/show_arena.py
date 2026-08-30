#!/usr/bin/env python3
"""Turn a dump of the tile arena back into a picture of the line.

The arena holds 4bpp tiles: two per cell, the top half then the bottom, with
the glyph itself in plane 0. Pulling plane 0 back out shows exactly what the
renderer put there, without depending on catching the right frame.

  tools/show_arena.py build/reports/arena.bin
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.png import write_greyscale  # noqa: E402

CELL_BYTES = 64          # two 4bpp tiles: the top half of the cell, then the bottom
CELLS_PER_LINE = 31      # what the window is wide, measured from the engine's cursor
SCALE = 2


def rows_of(data: bytes, cell: int) -> list[int]:
    """The sixteen 1bpp rows of one cell, read out of plane 0."""
    base = cell * CELL_BYTES
    top = [data[base + row * 2] for row in range(8)]
    bottom = [data[base + 0x20 + row * 2] for row in range(8)]
    return top + bottom


def picture(data: bytes, cells: int, lines: int) -> list[list[int]]:
    canvas: list[list[int]] = []
    for line in range(lines):
        for row in range(16):
            pixels: list[int] = []
            for cell in range(cells):
                index = line * CELLS_PER_LINE + cell
                if (index + 1) * CELL_BYTES > len(data):
                    break
                byte = rows_of(data, index)[row]
                pixels += [0 if byte >> (7 - bit) & 1 else 255 for bit in range(8)]
            for _ in range(SCALE):
                canvas.append([value for value in pixels for _ in range(SCALE)])
        canvas.append([190] * len(canvas[-1]))
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path)
    parser.add_argument("--cells", type=int, default=31)
    parser.add_argument("--lines", type=int, default=4)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    data = args.dump.read_bytes()
    out = args.out or args.dump.with_suffix(".png")
    write_greyscale(out, picture(data, args.cells, args.lines))
    print(f"{out}  {args.cells} cells x {args.lines} lines from {len(data)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
