"""Building one 8x16 bitmap per token in the manifest.

Three sources feed the same atlas, and they all come out with the same metrics
schema so a single blitter can draw any of them:

  cluster:  composed from hand-drawn bases and exact contextual stack bitmaps
  char:     the image is imported from the game's own font in the clean ROM
  icon:     fixed artwork that ships in the manifest

Thai composition uses hand-tuned full-cell contextual stacks recorded in
`data/font/thai.json`.  Their pixels already contain the final x/y position;
the builder only selects normal/left and ORs those rows over the base.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .tokens import EncodingError

CELL_WIDTH = 8
CELL_ROWS = 16
STOCK_FONT_PC = 0x2E8000     # 1bpp, 16 bytes per glyph, indexed by font code
STOCK_GLYPH_BYTES = 16
MIN_ADVANCE = 3
MAX_ADVANCE = 8
SPACE_ADVANCE = 4            # a blank glyph has no ink to measure


@dataclass(frozen=True)
class Glyph:
    token: str
    rows: tuple[int, ...]    # 16 rows, bit 7 is the leftmost pixel
    advance: int
    ink_width: int
    left: int
    top: int
    cell_span: int
    flags: int
    source: str

    def metrics(self) -> dict:
        return {
            "advance": self.advance,
            "ink_width": self.ink_width,
            "left": self.left,
            "top": self.top,
            "cell_span": self.cell_span,
            "flags": self.flags,
        }


def ink_box(rows: tuple[int, ...]) -> tuple[int, int, int]:
    """Return (left, ink_width, top) of the drawn pixels."""
    used = [row for row in rows if row]
    if not used:
        return 0, 0, 0
    left = min(7 - value.bit_length() + 1 for value in used)
    right = max(
        max(bit for bit in range(8) if value >> (7 - bit) & 1) for value in used
    )
    top = next(index for index, row in enumerate(rows) if row)
    return left, right - left + 1, top


def _shift(row: int, offset: int) -> int:
    """Shift a row right by `offset` pixels, dropping anything pushed out."""
    if offset >= 0:
        return (row >> offset) & 0xFF
    return (row << -offset) & 0xFF


class AtlasBuilder:
    def __init__(self, font_dir: Path, rom: bytes):
        thai = json.loads((font_dir / "thai.json").read_text())
        self.bases = thai["bases"]
        self.contextual = thai["contextual"]
        self.icons = json.loads((font_dir / "renewal-icons.json").read_text())["glyphs"]
        self.stock = json.loads((font_dir / "renewal-stock.json").read_text())["glyphs"]
        self.overrides = json.loads((font_dir / "renewal-overrides.json").read_text())["overrides"]
        self.rom = rom

    def build(self, token: str) -> Glyph:
        kind, value = token.split(":", 1)
        override = self.overrides.get(token)
        if override:
            if "reason" not in override or "sample" not in override:
                raise EncodingError(f"override for {token} needs a reason and a sample")
            return self._finish(token, tuple(override["rows"]), "override", override.get("advance"))
        if kind == "icon":
            return self._icon(token, value)
        if kind == "char":
            return self._char(token, value)
        if kind == "cluster":
            return self._cluster(token, value)
        raise EncodingError(f"unknown token kind: {token}")

    # --- sources ------------------------------------------------------------

    def _icon(self, token: str, name: str) -> Glyph:
        entry = self.icons.get(name)
        if entry is None:
            raise EncodingError(f"no artwork for {token}")
        return self._finish(
            token,
            tuple(entry["rows"]),
            "icon",
            entry.get("advance"),
            cell_span=entry.get("cell_span", 1),
        )

    def _char(self, token: str, char: str) -> Glyph:
        # Latin, digits and punctuation are drawn in thai.json too, on the same
        # baseline and to the same widths as the Thai clusters. Prefer those:
        # the game's own font is fixed-pitch, so its spacing has to be guessed
        # back out of the bitmap, and it sits on a different baseline. Only the
        # few characters we never drew still come from the ROM.
        ours = self.bases.get(char)
        if ours is not None:
            return self._finish(token, tuple(ours["rows"]), "drawn", ours["advance"])
        entry = self.stock.get(char)
        if entry is None:
            raise EncodingError(f"{token} has no stock font code in renewal-stock.json")
        start = STOCK_FONT_PC + entry["code"] * STOCK_GLYPH_BYTES
        rows = tuple(self.rom[start : start + STOCK_GLYPH_BYTES])
        if len(rows) != CELL_ROWS:
            raise EncodingError(f"{token}: stock glyph runs past the end of the ROM")
        # The stock font is fixed-pitch, so its glyphs carry a left bearing the
        # cell paid for. Here the advance is measured from the ink alone, so the
        # bearing has to go: left it in, and the next glyph is blitted over it.
        # A period, drawn three pixels in and advanced three, vanished entirely.
        left, _, _ = ink_box(rows)
        if left:
            rows = tuple(_shift(row, -left) for row in rows)
        advance = SPACE_ADVANCE if not any(rows) else None
        return self._finish(token, rows, "stock", advance)

    def _cluster(self, token: str, cluster: str) -> Glyph:
        base_char, marks = cluster[0], cluster[1:]
        base = self.bases.get(base_char)
        if base is None:
            raise EncodingError(f"{token}: no drawing for the base {base_char!r}")

        lower = [mark for mark in marks if self._mark_class(mark) == "below"]
        upper = "".join(mark for mark in marks if self._mark_class(mark) == "above")
        if len(lower) > 1:
            raise EncodingError(f"{token}: more than one lower mark")

        variant = self.contextual["lower_base_variants"].get(base_char) if lower else None
        rows = list(variant["rows"] if variant else base["rows"])

        if upper:
            family = "left" if base_char in self.contextual["upper_left_bases"] else "normal"
            stack = self.contextual["upper_stacks"][family].get(upper)
            if stack is None:
                raise EncodingError(f"{token}: no {family} upper stack for {upper!r}")
            self._overlay(rows, stack, token, f"{family} upper {upper!r}")

        if lower:
            family = "left" if base_char in self.contextual["lower_left_bases"] else "normal"
            stack = self.contextual["lower_stacks"][family].get(lower[0])
            if stack is None:
                raise EncodingError(f"{token}: no {family} lower stack for {lower[0]!r}")
            self._overlay(rows, stack, token, f"{family} lower {lower[0]!r}")

        return self._finish(token, tuple(rows), "composed", base["advance"])

    def _mark_class(self, mark_char: str) -> str:
        """Return the recorded contextual family; placement is never inferred."""
        recorded = self.contextual["mark_classes"].get(mark_char)
        if recorded not in {"above", "below"}:
            raise EncodingError(f"no contextual class for mark {mark_char!r}")
        return recorded

    @staticmethod
    def _overlay(rows: list[int], stack: list[int], token: str, label: str) -> None:
        if len(stack) != CELL_ROWS or any(not 0 <= row <= 0xFF for row in stack):
            raise EncodingError(f"{token}: {label} must be {CELL_ROWS} byte rows")
        for index, bits in enumerate(stack):
            rows[index] |= bits

    # --- metrics ------------------------------------------------------------

    def _finish(
        self,
        token: str,
        rows: tuple[int, ...],
        source: str,
        advance: int | None = None,
        cell_span: int = 1,
    ) -> Glyph:
        if len(rows) != CELL_ROWS:
            raise EncodingError(f"{token}: expected {CELL_ROWS} rows, got {len(rows)}")
        left, ink_width, top = ink_box(rows)
        if advance is None:
            advance = min(max(ink_width + 1, MIN_ADVANCE), MAX_ADVANCE)
        return Glyph(
            token=token,
            rows=rows,
            advance=advance,
            ink_width=ink_width,
            left=left,
            top=top,
            cell_span=cell_span,
            flags=0,
            source=source,
        )
