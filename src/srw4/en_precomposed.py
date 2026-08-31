"""Shared EN-ROM assets for fully precomposed dialogue glyphs.

The source is the editable font data through :class:`AtlasBuilder`.  A token
always occupies its locked direct or extended slot, so the runtime only picks
the already-drawn bitmap and its saved advance; it never positions a Thai mark.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .atlas import AtlasBuilder
from .contract import DIRECT_SLOTS, ENGINE_CODE_BASE, EXTENDED_PAGE_SIZE, EXTENDED_PAGES
from .proven.assembler import pc_to_cpu
from .tokens import TokenMap


ROOT = Path(__file__).resolve().parents[2]
FONT = ROOT / "data" / "font"

# `$EA:8000-$EA:D9FF` is erased in the pinned EN ROM and remains unused after
# the complete EN build.  Five fixed 4 KiB pages mirror the engine's one direct
# page plus its four native `$F0-$F3` extended pages.
PAGE_PC = 0x2A8000
PAGE_BYTES = 0x1000
PAGE_COUNT = 1 + EXTENDED_PAGES
ADVANCE_PC = PAGE_PC + PAGE_COUNT * PAGE_BYTES
WIDTH_PC = ADVANCE_PC + PAGE_COUNT * EXTENDED_PAGE_SIZE
ASSET_END_PC = WIDTH_PC + PAGE_COUNT * EXTENDED_PAGE_SIZE
SOURCE_BANK = pc_to_cpu(PAGE_PC) >> 16
PAGE_STATES = tuple((PAGE_PC & 0xFFFF) + index * PAGE_BYTES for index in range(PAGE_COUNT))

if PAGE_PC >> 16 != (ASSET_END_PC - 1) >> 16:
    raise RuntimeError("precomposed dialogue assets must stay in one source bank")
if any(state & 0x0FFF for state in PAGE_STATES):
    raise RuntimeError("precomposed dialogue page states must be 4 KiB aligned")


@dataclass(frozen=True)
class PrecomposedAssets:
    """Pages and metrics indexed exactly like the engine's glyph codes."""

    token_map: TokenMap
    pages: tuple[bytes, ...]
    advances: tuple[bytes, ...]
    widths: tuple[bytes, ...]


def engine_page_index(code: int) -> int | None:
    """Return the physical source page for one engine glyph code."""
    if 0 <= code < DIRECT_SLOTS:
        return 0
    if ENGINE_CODE_BASE <= code < ENGINE_CODE_BASE + EXTENDED_PAGES * EXTENDED_PAGE_SIZE:
        return 1 + (code - ENGINE_CODE_BASE) // EXTENDED_PAGE_SIZE
    return None


def engine_page_state(code: int) -> int | None:
    """Return the renderer's saved source-page offset for ``code``."""
    page = engine_page_index(code)
    return None if page is None else PAGE_STATES[page]


def slot_for_token(token_map: TokenMap, token: str) -> tuple[int, int]:
    """Return ``(page, slot)`` under the locked direct/extended contract."""
    index = token_map.index(token)
    if index < DIRECT_SLOTS:
        return 0, index
    page, slot = divmod(index - DIRECT_SLOTS, EXTENDED_PAGE_SIZE)
    if page >= EXTENDED_PAGES:
        raise ValueError(f"{token}: extended page exceeds the locked contract")
    return page + 1, slot


def build_assets(en_rom: bytes) -> PrecomposedAssets:
    """Serialize every manifest token from the current editable font source."""
    token_map = TokenMap.load(FONT / "renewal-clusters.json")
    atlas = AtlasBuilder(FONT, en_rom)
    pages = [bytearray(PAGE_BYTES) for _ in range(PAGE_COUNT)]
    advances = [bytearray(EXTENDED_PAGE_SIZE) for _ in range(PAGE_COUNT)]

    for token in token_map.tokens:
        page, slot = slot_for_token(token_map, token)
        glyph = atlas.build(token)
        if not 0 <= glyph.advance <= 0xFF:
            raise ValueError(f"{token}: advance is outside one byte")
        start = slot * 16
        pages[page][start:start + 16] = bytes(glyph.rows)
        advances[page][slot] = glyph.advance

    packed_advances = tuple(map(bytes, advances))
    return PrecomposedAssets(
        token_map=token_map,
        pages=tuple(map(bytes, pages)),
        advances=packed_advances,
        widths=tuple(
            bytes(0xFF if advance == 0 else advance - 1 for advance in page)
            for page in packed_advances
        ),
    )
