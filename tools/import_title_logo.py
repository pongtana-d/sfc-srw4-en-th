#!/usr/bin/env python3
"""Convert the approved title-logo concept into the stock SNES OBJ palette."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "assets" / "title-logo-concept-v1.png"
DEFAULT_OUTPUT = ROOT / "data" / "assets" / "title-logo.json"
SCREEN_SIZE = (256, 224)
# All four stock logo sprite rows overlap this safe rectangle.  The approved
# concept is compressed into it so no Thai mark or the numeral 4 is clipped by
# the original row-specific OAM widths.
CONCEPT_LOGO_BOX = (16, 40, 240, 116)
LOGO_BOX = (24, 48, 224, 112)
FACE_SCALE_PERCENT = 102
SHADOW_DEPTH = 6
MIN_FACE_COMPONENT_PIXELS = 4
MIN_SHADOW_RUN_PIXELS = 3

# Exact stock OBJ palette 7 captured from CGRAM on the title redraw.
PALETTE = (
    (0, 0, 0),
    (255, 255, 255), (255, 255, 172),
    (255, 255, 0), (255, 222, 0), (255, 189, 0),
    (255, 156, 0), (255, 123, 0), (255, 90, 0),
    (222, 57, 0), (189, 0, 0), (57, 16, 0),
    (0, 0, 156), (0, 0, 123), (0, 0, 90), (0, 0, 57),
)


def screen_crop(image: Image.Image) -> Image.Image:
    """Remove only uniform near-black letterboxing, then restore 256x224."""
    rgb = image.convert("RGB")
    pixels = rgb.load()
    occupied_rows = [
        y for y in range(rgb.height)
        if any(max(pixels[x, y]) > 12 for x in range(rgb.width))
    ]
    if not occupied_rows:
        raise ValueError("concept image has no visible screen")
    cropped = rgb.crop((0, min(occupied_rows), rgb.width, max(occupied_rows) + 1))
    return cropped.resize(SCREEN_SIZE, Image.Resampling.NEAREST)


def is_face_pixel(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    warm = r >= 120 and g >= 35 and r >= b * 3 // 2
    highlight = min(rgb) >= 145 and max(rgb) - min(rgb) <= 75
    return warm or highlight


def shadow_color(depth: int) -> int:
    """Match the stock near-to-far blue extrusion ramp (indices 12..15)."""
    return 12 + min(3, (depth - 1) * 4 // SHADOW_DEPTH)


def remove_face_speckles(face: list[list[int]]) -> None:
    """Drop tiny disconnected color samples without deleting Thai marks."""
    height = len(face)
    width = len(face[0])
    visited: set[tuple[int, int]] = set()
    for y in range(height):
        for x in range(width):
            if not face[y][x] or (x, y) in visited:
                continue
            component: list[tuple[int, int]] = []
            pending = [(x, y)]
            visited.add((x, y))
            while pending:
                current_x, current_y = pending.pop()
                component.append((current_x, current_y))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        adjacent = (current_x + dx, current_y + dy)
                        if adjacent in visited:
                            continue
                        next_x, next_y = adjacent
                        if 0 <= next_x < width and 0 <= next_y < height and face[next_y][next_x]:
                            visited.add(adjacent)
                            pending.append(adjacent)
            if len(component) < MIN_FACE_COMPONENT_PIXELS:
                for component_x, component_y in component:
                    face[component_y][component_x] = 0


def remove_shadow_whiskers(indexed: list[list[int]]) -> None:
    """Remove narrow blue runs that protrude below the solid extrusion."""
    height = len(indexed)
    width = len(indexed[0])
    blue = [[value >= 12 for value in row] for row in indexed]
    keep = [[False] * width for _ in range(height)]
    radius = MIN_SHADOW_RUN_PIXELS // 2
    for y in range(height):
        for x in range(radius, width - radius):
            if all(blue[y][x + dx] for dx in range(-radius, radius + 1)):
                for dx in range(-radius, radius + 1):
                    keep[y][x + dx] = True
    for y in range(height):
        for x in range(width):
            if blue[y][x] and not keep[y][x]:
                indexed[y][x] = 0


def nearest_palette(rgb: tuple[int, int, int]) -> int:
    candidates = range(1, len(PALETTE))
    return min(
        candidates,
        key=lambda index: sum(
            (rgb[channel] - PALETTE[index][channel]) ** 2
            for channel in range(3)
        ),
    )


def import_logo(source: Path) -> dict[str, object]:
    with Image.open(source) as raw:
        screen = screen_crop(raw)
    left, top, right, bottom = LOGO_BOX
    width = right - left
    height = bottom - top
    scaled_size = (
        width * FACE_SCALE_PERCENT // 100,
        height * FACE_SCALE_PERCENT // 100,
    )
    scaled = screen.crop(CONCEPT_LOGO_BOX).resize(
        scaled_size, Image.Resampling.NEAREST
    )
    crop_left = (scaled.width - width) // 2
    crop_top = (scaled.height - height) // 2
    concept = scaled.crop((crop_left, crop_top, crop_left + width, crop_top + height))
    face = [[0] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            rgb = concept.getpixel((x, y))
            if is_face_pixel(rgb):
                face[y][x] = nearest_palette(rgb)
    remove_face_speckles(face)

    # Seed a short stock-palette extrusion. Manual edits in title-logo.json are
    # authoritative after this one-time import.
    indexed = [[0] * width for _ in range(height)]
    for depth in range(SHADOW_DEPTH, 0, -1):
        dx = (depth + 1) // 3
        color = shadow_color(depth)
        for y in range(height - depth):
            for x in range(width - dx):
                if face[y][x]:
                    indexed[y + depth][x + dx] = color
    for y in range(height):
        for x in range(width):
            if face[y][x]:
                indexed[y][x] = face[y][x]
    remove_shadow_whiskers(indexed)
    rows = ["".join(f"{value:X}" for value in row) for row in indexed]
    return {
        "schema_version": 1,
        "description": "Thai title logo quantized to the stock Japanese logo OBJ palette",
        "text": "ซูเปอร์โรบอตวอร์ส 4",
        "source": str(source.relative_to(ROOT)),
        "screen_box": {"x": left, "y": top, "width": right - left, "height": bottom - top},
        "palette_bgr555": [
            "0000", "7FFF", "57FF", "03FF", "037F", "02FF", "027F", "01FF",
            "017F", "00FB", "0017", "0047", "4C00", "3C00", "2C00", "1C00",
        ],
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--force", action="store_true",
        help="overwrite an existing hand-editable logo asset",
    )
    args = parser.parse_args()
    if args.output.exists() and not args.force:
        raise SystemExit(
            f"refusing to overwrite editable asset without --force: {args.output}"
        )
    data = import_logo(args.input.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
