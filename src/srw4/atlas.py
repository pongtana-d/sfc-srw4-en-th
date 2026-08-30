"""Building one 8x16 bitmap per token in the manifest.

Three sources feed the same atlas, and they all come out with the same metrics
schema so a single blitter can draw any of them:

  cluster:  composed here from the project's hand-drawn Thai bases and marks
  char:     the image is imported from the game's own font in the clean ROM
  icon:     fixed artwork that ships in the manifest

Composition follows the rule recorded in `data/font/thai.json`: a mark's right
edge lines up with the base's ink right edge plus the mark's own dx, and a tone
mark moves up to its raised row when an above-vowel already sits over the base.
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
        self.marks = thai["marks"]
        self.raised_rows = thai["raised_rows"]
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

        rows = list(base["rows"])
        # A tone mark only moves up when a vowel already occupies the row above
        # the base. Tone marks themselves are the ones listed in raised_rows.
        vowels = [
            self.marks[m]
            for m in marks
            if self._mark_class(m) == "above" and m not in self.raised_rows
        ]
        vowel_top = min((v["y"] for v in vowels), default=None)
        for mark_char in marks:
            mark = self.marks.get(mark_char)
            if mark is None:
                raise EncodingError(f"{token}: no drawing for the mark {mark_char!r}")
            self._stamp(rows, base, mark, mark_char, vowel_top)

        return self._finish(token, tuple(rows), "composed", base["advance"])

    def _mark_class(self, mark_char: str) -> str:
        """Above or below. One mark in the data has no class; its row says which."""
        mark = self.marks[mark_char]
        recorded = mark.get("class")
        if recorded:
            return recorded
        return "above" if mark["y"] < CELL_ROWS // 2 else "below"

    def _stamp(
        self, rows: list[int], base: dict, mark: dict, mark_char: str, vowel_top: int | None
    ) -> None:
        # The mark's right edge follows the base's ink, nudged by the mark's dx.
        x = base["left"] + base["ink"] - mark["width"] + mark["dx"]
        x = max(0, min(x, CELL_WIDTH - mark["width"]))

        top = mark["y"]
        if vowel_top is not None and mark_char in self.raised_rows:
            # Clear the vowel rather than trusting the recorded row on its own:
            # a tall vowel such as "ue" starts higher than the usual one, and
            # sitting on it would merge the two into a single shape.
            top = max(0, min(self.raised_rows[mark_char], vowel_top - len(mark["sprite"])))

        for offset, sprite_row in enumerate(mark["sprite"]):
            row = top + offset
            if 0 <= row < CELL_ROWS:
                rows[row] |= _shift(sprite_row, x)

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
