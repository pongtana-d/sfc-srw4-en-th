#!/usr/bin/env python3
"""Quantize the cleaned concept into the existing EN logo sprite surface."""

import json
from pathlib import Path

from PIL import Image

from import_title_logo import nearest_palette
from rebuild_title_logo_shadow import DEFAULT_DEPTH, rebuild, render

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets/title-logo-concept-v2.png"
# Measured bounds of the gold face in the 1341x1173 concept (shadow excluded).
FACE_BOX = (144, 256, 1235, 551)
# Keep the hand-edited logo's screen placement and face envelope.
FACE_ORIGIN = (8, 8)
FACE_SIZE = (187, 48)


def main():
    target = ROOT / "data/assets/title-logo.json"
    document = json.loads(target.read_text())
    with Image.open(SOURCE) as image:
        if image.size != (1341, 1173):
            raise ValueError("Concept dimensions changed; remeasure face bounds")
        face = image.convert("RGBA").crop(FACE_BOX)
        # Mask before shrinking so Earth colors cannot become gold speckles.
        pixels = []
        for r, g, b, _ in (face.getpixel((x, y))
                           for y in range(face.height) for x in range(face.width)):
            warm = r >= 20 and r >= 2 * b + 10 and r > g
            highlight = min(r, g, b) >= 205 and max(r, g, b) - min(r, g, b) <= 75
            pixels.append((r, g, b, 255 if warm or highlight else 0))
        face.putdata(pixels)
        face = face.resize(FACE_SIZE, Image.Resampling.LANCZOS)
    rows = [["0"] * 200 for _ in range(64)]
    for y in range(face.height):
        for x in range(face.width):
            r, g, b, alpha = face.getpixel((x, y))
            if alpha >= 128:
                # Match the stock full-brightness gold ramp, not baked lighting.
                pixel = (255, min(255, round(g * 255 / max(r, 1))),
                         min(255, round(b * 255 / max(r, 1))))
                color = 11 if r < 100 else nearest_palette(pixel)
                if color < 12:
                    rows[y + FACE_ORIGIN[1]][x + FACE_ORIGIN[0]] = f"{color:X}"
    document["rows"] = rebuild(["".join(row) for row in rows], DEFAULT_DEPTH)
    document["source"] = str(SOURCE.relative_to(ROOT))
    document["refinement"] = {
        "face_box": list(FACE_BOX), "face_origin": list(FACE_ORIGIN),
        "face_size": list(FACE_SIZE), "resampling": "LANCZOS",
    }
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    render(document["rows"], document["palette_bgr555"],
           ROOT / "build/repro/title-logo-v2-native.png")


if __name__ == "__main__":
    main()
