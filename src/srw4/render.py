"""The reference renderer: where a token stream becomes pixels.

This is the specification the 65816 blitter has to match, so it does exactly
what the ASM will do and nothing more. Per token: resolve the glyph, shift its
8-pixel bitmap to the pen, OR it into a 1bpp line canvas, widen the dirty cell
range, then move the pen on by the glyph's advance.

There is deliberately no logic here about vowels, tone marks, below marks or
collisions. All of that is settled in the atlas compiler; if any of it appeared
in this path, the ROM renderer would have to grow it too.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .text import (
    ENGINE_FLOOR,
    ENGINE_OPERANDS,
    NEWLINE_BYTE,
    follows,
)
from .contract import TERMINATORS
from .tokens import DIRECT_MAX, EXTENDED_LEAD, EncodingError

CANVAS_WIDTH = 256       # 32 cells; matches the 512-byte line canvas in WRAM
CELL_WIDTH = 8
CELL_ROWS = 16


@dataclass
class LineCanvas:
    """One line of 1bpp pixels, plus the range of cells that were touched."""

    width: int = CANVAS_WIDTH
    rows: list[int] = field(default_factory=list)
    pen: int = 0
    dirty_first: int | None = None
    dirty_last: int | None = None
    overflow: int = 0        # pixels that fell off the right edge

    def __post_init__(self) -> None:
        if not self.rows:
            self.rows = [0] * CELL_ROWS

    def blit(self, bitmap: tuple[int, ...], x: int) -> None:
        """OR an 8-pixel-wide glyph into the canvas at pixel column `x`."""
        if x >= self.width:
            self.overflow += CELL_WIDTH
            return
        shift = self.width - CELL_WIDTH - x
        drawn = False
        for index, row in enumerate(bitmap):
            if not row:
                continue
            value = row << shift if shift >= 0 else row >> -shift
            self.rows[index] |= value & ((1 << self.width) - 1)
            drawn = True
        if shift < 0:
            self.overflow += -shift
        if drawn:
            self._touch(x, min(x + CELL_WIDTH - 1, self.width - 1))

    def _touch(self, first_px: int, last_px: int) -> None:
        first, last = first_px // CELL_WIDTH, last_px // CELL_WIDTH
        self.dirty_first = first if self.dirty_first is None else min(self.dirty_first, first)
        self.dirty_last = last if self.dirty_last is None else max(self.dirty_last, last)

    @property
    def dirty_cells(self) -> int:
        if self.dirty_first is None:
            return 0
        return self.dirty_last - self.dirty_first + 1

    @property
    def tile_count(self) -> int:
        """Two 8x8 tiles per dirty cell: the top half and the bottom half."""
        return self.dirty_cells * 2

    def to_rows(self) -> list[bytes]:
        stride = self.width // 8
        return [row.to_bytes(stride, "big") for row in self.rows]

    def to_tiles(self) -> bytes:
        """1bpp tiles in the order the ASM uploads them: per cell, top then bottom."""
        rows = self.to_rows()
        out = bytearray()
        for cell in range(self.width // CELL_WIDTH):
            for half in (0, 8):
                for y in range(half, half + 8):
                    out.append(rows[y][cell])
        return bytes(out)

    def art(self) -> list[str]:
        """The canvas as text, trimmed to the drawn width. For fixtures."""
        end = max(self.pen, (self.dirty_last + 1) * CELL_WIDTH if self.dirty_last is not None else 0)
        end = min(max(end, 1), self.width)
        return [
            "".join("#" if row >> (self.width - 1 - x) & 1 else "." for x in range(end))
            for row in self.rows
        ]


@dataclass
class RenderedLine:
    canvas: LineCanvas
    tokens: list[str]
    engine: list[bytes]

    @property
    def width(self) -> int:
        return self.canvas.pen


@dataclass
class Rendered:
    lines: list[RenderedLine]
    terminator: int | None

    def report(self) -> dict:
        return {
            "lines": len(self.lines),
            "widths": [line.width for line in self.lines],
            "dirty_cells": [line.canvas.dirty_cells for line in self.lines],
            "tiles": [line.canvas.tile_count for line in self.lines],
            "overflow": [line.canvas.overflow for line in self.lines],
            "terminator": f"{self.terminator:#04x}" if self.terminator is not None else None,
        }


class Renderer:
    """Draws a pilot stream. `atlas` maps token -> glyph with rows and advance."""

    def __init__(self, token_map, atlas: dict, width: int = CANVAS_WIDTH):
        self.token_map = token_map
        self.atlas = atlas
        self.width = width

    def render(self, data: bytes, branch_tables: dict[int, int] | None = None) -> Rendered:
        lines: list[RenderedLine] = []
        line = RenderedLine(LineCanvas(self.width), [], [])
        terminator = None
        index = 0

        while index < len(data):
            byte = data[index]

            if byte <= DIRECT_MAX:
                self._draw(line, self.token_map.token_at(byte))
                index += 1
                continue

            if byte < ENGINE_FLOOR:
                raise EncodingError(f"byte {byte:#04x} at {index} is in the reserved gap $D0-$EB")

            if EXTENDED_LEAD <= byte < EXTENDED_LEAD + self.token_map.extended_pages:
                if index + 1 >= len(data):
                    raise EncodingError(f"extended lead {byte:#04x} at {index} has no index byte")
                page = byte - EXTENDED_LEAD
                glyph_id = (DIRECT_MAX + 1) + page * 0x100 + data[index + 1]
                self._draw(line, self.token_map.token_at(glyph_id))
                index += 2
                continue

            entries = (branch_tables or {}).get(index)
            if entries is not None:
                end = index + 2 + entries * 2
                line.engine.append(data[index:end])
                index = end
                continue

            if byte == NEWLINE_BYTE:
                lines.append(line)
                line = RenderedLine(LineCanvas(self.width), [], [])
                index += 1
                continue

            operands = ENGINE_OPERANDS.get(byte, 0)
            # A command can carry more than its lead declares -- an address, a
            # branch table, one more operand. Those bytes are not text, and
            # drawing them would put nonsense on the line and swallow the rest.
            carries = follows(byte, list(data[index + 1 : index + 1 + operands]))
            # "branch" is normally handled above, from the table the compiler
            # found. The fallback is here so a caller that passes no tables
            # still steps over one instead of drawing sixteen glyphs.
            operands += {"address": 2, "operand": 1, "branch": 16}.get(carries, 0)
            end = index + 1 + operands
            if end > len(data):
                raise EncodingError(
                    f"engine lead {byte:#04x} at {index} wants {operands} operand bytes"
                )
            line.engine.append(data[index:end])
            if byte in TERMINATORS:
                terminator = byte
            index = end

        lines.append(line)
        return Rendered(lines, terminator)

    def _draw(self, line: RenderedLine, token: str) -> None:
        glyph = self.atlas.get(token)
        if glyph is None:
            raise EncodingError(f"no glyph in the atlas for {token}")
        line.canvas.blit(glyph.rows, line.canvas.pen)
        line.canvas.pen += glyph.advance
        line.tokens.append(token)
