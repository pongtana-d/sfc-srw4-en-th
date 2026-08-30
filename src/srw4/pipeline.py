"""Wiring the stages together, so tools and tests build the same objects.

Loading the manifest, the atlas and the tokenizer takes a few files and a clean
ROM; doing it in one place keeps every entry point honest about which inputs it
depends on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .atlas import AtlasBuilder, Glyph
from .render import Renderer
from .rom import Rom
from .stream import Record, encode
from .text import Tokenizer, load_stock_codes
from .tokens import TokenMap


@dataclass
class Pipeline:
    token_map: TokenMap
    tokenizer: Tokenizer
    atlas: dict[str, Glyph]
    renderer: Renderer

    @classmethod
    def from_rom_bytes(cls, root: Path, rom: bytes) -> "Pipeline":
        """Build the text pipeline from an already validated ROM image."""
        font_dir = root / "data" / "font"
        token_map = TokenMap.load(font_dir / "renewal-clusters.json")
        builder = AtlasBuilder(font_dir, rom)
        atlas = {token: builder.build(token) for token in token_map.tokens}
        tokenizer = Tokenizer(
            set(json.loads((font_dir / "renewal-icons.json").read_text())["glyphs"]),
            load_stock_codes(font_dir / "renewal-stock.json"),
        )
        return cls(token_map, tokenizer, atlas, Renderer(token_map, atlas))

    @classmethod
    def load(cls, root: Path, rom_path: Path) -> "Pipeline":
        return cls.from_rom_bytes(root, Rom.load_clean(rom_path).to_bytes())

    def compile(self, text: str, *, where: str = "", branch_range: range = range(0)) -> Record:
        result = self.tokenizer.tokenize(text, where=where, branch_range=branch_range)
        return encode(result.pieces, self.token_map)

    def draw(self, text: str, *, where: str = "", width: int | None = None):
        record = self.compile(text, where=where)
        renderer = self.renderer if width is None else Renderer(self.token_map, self.atlas, width)
        return renderer.render(record.data, record.branch_tables)
