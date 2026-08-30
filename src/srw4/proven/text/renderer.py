#!/usr/bin/env python3
"""Reference implementation of the runtime Thai renderer.

This is the specification the 65816 routine written in P4 has to match.  Keep
it deliberately dumb: every decision here must be reproducible with range
compares, a table read, a shift and an OR, because that is all the assembly
will get to do inside vblank.

    python3 tools/thai_render.py "สวัสดีครับ"      # ASCII proof sheet
    python3 tools/thai_render.py --sheet           # render a fixed sample set
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import encoding as enc
from .upper_stacks import upper_stack

ROOT = Path(__file__).resolve().parents[4] / "data" / "proven"
ROWS = 16
CELL_WIDTH = 8


class Renderer:
    def __init__(self, model: dict, layout: dict) -> None:
        self.model = model
        self.layout = layout
        self.codes = layout["codes"]
        self.blocks = layout["blocks"]
        self.by_code = {code: token for token, code in self.codes.items()}
        self.advance = enc.advance_table(model, layout)
        # A shorthand byte stands in for the two or three codes it was built
        # from.  Expanding it up front is exactly what the ROM does at the top
        # of the renderer, so everything below stays unaware it happened.
        self.expansion = {
            code: [self.codes[char] for char in cluster]
            for cluster, code in layout.get("shorthand", {}).items()
        }
        self.expansion.update({
            code: [self.codes[token] for token in expansion]
            for phrase, code in layout.get("phrases", {}).items()
            for expansion in [layout.get("phrase_expansions", {}).get(phrase, [])]
        })

    def expand(self, payload: bytes) -> list[int]:
        out: list[int] = []
        for code in payload:
            out.extend(self.expansion.get(code, [code]))
        return out

    # -- classification: three range compares, exactly as the ASM will do it --

    def is_mark(self, code: int) -> bool:
        return self.blocks["mark_above_base"] <= code < self.blocks["control_base"]

    def is_tone(self, code: int) -> bool:
        return self.blocks["mark_tone_base"] <= code < self.blocks["mark_below_base"]

    def is_below(self, code: int) -> bool:
        return self.blocks["mark_below_base"] <= code < self.blocks["control_base"]

    # -- drawing ---------------------------------------------------------

    def draw(self, payload: bytes, width_px: int) -> list[int]:
        """Rasterize page bytes into a single row of `width_px` pixels."""
        canvas = [0] * (ROWS * ((width_px + CELL_WIDTH - 1) // CELL_WIDTH))
        stride = (width_px + CELL_WIDTH - 1) // CELL_WIDTH
        surface = [[0] * stride for _ in range(ROWS)]

        pen = 0
        base_left = base_ink = base_top = 0
        upper_vowel: str | None = None
        upper_x = upper_top = 0

        for code in self.expand(payload):
            if code >= self.blocks["control_base"]:
                continue
            token = self.by_code.get(code)
            if token is None:
                continue

            if not self.is_mark(code):
                spec = self.model["bases"].get(token)
                if spec is None:
                    # The space carries no ink, only an advance, and a mark can
                    # never anchor to it.
                    pen += self.advance[code]
                    base_left = pen
                    base_ink = base_top = 0
                    upper_vowel = None
                    continue
                # Draw so the glyph's ink starts exactly at the pen.  Blitting
                # the raw 8px cell instead would spend the glyph's own left
                # bearing on top of the 1px right bearing the advance already
                # includes, making the gap between glyphs depend on which pair
                # happens to be adjacent.
                self._blit(surface, spec["rows"], pen - spec["left"], 0, width_px)
                base_left = pen
                base_ink = spec["ink"]
                base_top = spec["top"]
                upper_vowel = None
                pen += self.advance[code]
                continue

            spec = self.model["marks"][token]
            stack = None
            if self.is_tone(code) and upper_vowel is not None:
                stack = upper_stack(self.model, upper_vowel, token)
            width = spec["width"]
            # A mark wider than its base's ink starts left of the pen.  There is
            # nowhere to put that on the first base of the line, so it is
            # clamped rather than clipped — the ROM does the same against the
            # first cell of the run, and losing a pixel off a mark reads as a
            # broken glyph where shifting it right by one does not.
            if stack is None:
                x = max(0, base_left + base_ink - width + spec["dx"])
                top = spec["y"]
            else:
                # The pair geometry is precomputed.  Follow the vowel after it
                # has moved around a tall base, then clamp only at the cell edge.
                x = max(0, upper_x + stack.dx)
                top = max(0, upper_top + stack.dy)
            if stack is None and not self.is_below(code):
                top = self._lift(surface, spec, x, top, width_px)
            self._blit(surface, self._sprite_rows(spec), x, top, width_px)
            if code < self.blocks["mark_tone_base"]:
                upper_vowel = token
                upper_x = x
                upper_top = top
            elif self.is_below(code):
                upper_vowel = None

        for y in range(ROWS):
            for cell in range(stride):
                canvas[cell * ROWS + y] = surface[y][cell]
        return canvas

    def _sprite_rows(self, spec: dict) -> list[int]:
        return list(spec["sprite"])

    def _lift(self, surface, spec: dict, x: int, top: int, width_px: int) -> int:
        """Raise an above mark until it stops touching ink already drawn."""
        rows = self._sprite_rows(spec)
        while top > 0 and self._collides(surface, rows, x, top, width_px):
            top -= 1
        return max(0, top)

    def _collides(self, surface, rows: list[int], x: int, top: int, width_px: int) -> bool:
        for index, value in enumerate(rows):
            y = top + index
            if not 0 <= y < ROWS or not value:
                continue
            if self._read(surface, x, y, width_px) & value:
                return True
        return False

    def _read(self, surface, x: int, y: int, width_px: int) -> int:
        """Read the 8 pixels starting at x as a byte, MSB leftmost."""
        out = 0
        for offset in range(CELL_WIDTH):
            column = x + offset
            if 0 <= column < width_px:
                cell, bit = divmod(column, CELL_WIDTH)
                if cell < len(surface[y]) and surface[y][cell] >> (7 - bit) & 1:
                    out |= 1 << (7 - offset)
        return out

    def _blit(self, surface, rows: list[int], x: int, top: int, width_px: int) -> None:
        for index, value in enumerate(rows):
            y = top + index
            if not 0 <= y < ROWS or not value:
                continue
            for offset in range(CELL_WIDTH):
                if not value >> (7 - offset) & 1:
                    continue
                column = x + offset
                if not 0 <= column < width_px:
                    continue
                cell, bit = divmod(column, CELL_WIDTH)
                if cell < len(surface[y]):
                    surface[y][cell] |= 1 << (7 - bit)

    # -- helpers ---------------------------------------------------------

    def width_of(self, payload: bytes) -> int:
        return sum(self.advance[code] for code in payload if code < 0xEC)

    def render_text(self, text: str) -> tuple[list[int], int]:
        payload = enc.encode(
            text,
            self.codes,
            self.layout.get("shorthand"),
            self.layout.get("phrases"),
        )
        width = self.width_of(payload)
        return self.draw(payload, max(width, CELL_WIDTH)), width


def ascii_art(canvas: list[int], width_px: int) -> str:
    stride = (width_px + CELL_WIDTH - 1) // CELL_WIDTH
    lines = []
    for y in range(ROWS):
        row = ""
        for cell in range(stride):
            value = canvas[cell * ROWS + y]
            row += "".join("#" if value >> (7 - bit) & 1 else "." for bit in range(8))
        lines.append(row[:width_px])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="*", help="Thai text to render")
    parser.add_argument("--sheet", action="store_true", help="render a fixed sample set")
    args = parser.parse_args()

    model = json.loads((ROOT / "font" / "thai.json").read_text())
    layout = json.loads((ROOT / "font" / "encoding.json").read_text())
    renderer = Renderer(model, layout)

    samples = args.text or []
    if args.sheet or not samples:
        samples = [
            "สวัสดี",
            "ผู้บังคับ",
            "เครื่องยนต์",
            "ก็ได้",
            "กระสุน",
            "ปืนใหญ่",
            "ซื้อ",
            "ฮึ่ม",
        ]

    for text in samples:
        canvas, width = renderer.render_text(text)
        cells = -(-width // CELL_WIDTH)
        print(f"== {text}   {width}px / {cells} cells "
              f"(fixed would be {len(enc.clusters(text))})")
        print(ascii_art(canvas, width))
        print()


if __name__ == "__main__":
    main()
