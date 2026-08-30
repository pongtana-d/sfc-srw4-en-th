#!/usr/bin/env python3
"""Rebuild a continuous stock-palette extrusion behind the hand-tuned logo face."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data" / "assets" / "title-logo.json"
DEFAULT_OUTPUT = ROOT / "build" / "title-logo-shadow-candidate.json"
DEFAULT_PREVIEW = ROOT / "build" / "repro" / "title-logo-shadow-candidate.png"
FACE_COLORS = frozenset("123456789AB")
SHADOW_COLORS = "CDEF"
DEFAULT_DEPTH = 10
HORIZONTAL_STEP_EVERY = 3
PREVIEW_SCALE = 6


def shadow_color(depth: int, maximum_depth: int) -> str:
    """Map near-to-far depth evenly across the four captured blue colors."""
    band = min(len(SHADOW_COLORS) - 1, (depth - 1) * len(SHADOW_COLORS) // maximum_depth)
    return SHADOW_COLORS[band]


def rebuild(rows: list[str], depth: int) -> list[str]:
    height = len(rows)
    width = len(rows[0])
    face = [[pixel if pixel in FACE_COLORS else "0" for pixel in row] for row in rows]
    rebuilt = [["0"] * width for _ in range(height)]

    # Paint far-to-near.  Each integer depth is present, so the extrusion is a
    # continuous solid sweep rather than a set of disconnected copies.
    for distance in range(depth, 0, -1):
        offset_x = (distance + HORIZONTAL_STEP_EVERY - 1) // HORIZONTAL_STEP_EVERY
        color = shadow_color(distance, depth)
        for y in range(height - distance):
            for x in range(width - offset_x):
                if face[y][x] != "0":
                    rebuilt[y + distance][x + offset_x] = color

    # The approved hand-tuned face is authoritative and always wins over shadow.
    for y in range(height):
        for x in range(width):
            if face[y][x] != "0":
                rebuilt[y][x] = face[y][x]
    return ["".join(row) for row in rebuilt]


def render(rows: list[str], palette_bgr555: list[str], output: Path) -> None:
    palette = []
    for raw in palette_bgr555:
        value = int(raw, 16)
        palette.append((
            (value & 31) * 255 // 31,
            ((value >> 5) & 31) * 255 // 31,
            ((value >> 10) & 31) * 255 // 31,
        ))
    image = Image.new("RGB", (len(rows[0]), len(rows)))
    image.putdata([palette[int(pixel, 16)] for row in rows for pixel in row])
    output.parent.mkdir(parents=True, exist_ok=True)
    image.resize(
        (image.width * PREVIEW_SCALE, image.height * PREVIEW_SCALE),
        Image.Resampling.NEAREST,
    ).save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--preview", type=Path, default=DEFAULT_PREVIEW)
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    args = parser.parse_args()
    if args.depth <= 0:
        raise SystemExit("depth must be positive")

    document = json.loads(args.input.read_text(encoding="utf-8"))
    rows = document["rows"]
    if len(rows) != 64 or any(len(row) != 200 for row in rows):
        raise SystemExit("title logo must be exactly 200x64")
    rebuilt = rebuild(rows, args.depth)
    document["rows"] = rebuilt
    document["manual_edit"] = True
    document["shadow_rebuild"] = {
        "depth": args.depth,
        "horizontal_step_every": HORIZONTAL_STEP_EVERY,
        "palette_indices": SHADOW_COLORS,
        "face_preserved": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    render(rebuilt, document["palette_bgr555"], args.preview)
    print(args.output)
    print(args.preview)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
