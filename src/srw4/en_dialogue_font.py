"""Supplementary FF page for ASCII and icon glyphs used by Thai dialogue."""
from __future__ import annotations

from pathlib import Path

from .atlas import AtlasBuilder


# These are the only authored dialogue characters absent from encoding.json.
# Slot order is part of the compressed EN dialogue stream contract.
PAGE_TWO_TOKENS = (
    "%", "A", "B", "C", "D", "E", "F", "G", "H", "I", "K", "L", "M",
    "N", "O", "P", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "x", "♥",
    # Preserve the released dialogue slots above. Catalog text appends every
    # remaining authored Latin/digit glyph to this same proportional page.
    " ", "(", ")", "+", "-", ".", "/",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "J", "Q", "b", "k", "m", "ν",
    # Complete the authored non-Thai set from thai.json. These currently
    # unused catalog characters cost no extra ROM space because the bitmap
    # page and advance table are fixed at 256 entries.
    "!", ",", ":", "?", "a", "c", "d", "e", "f", "g", "h", "i", "j",
    "l", "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "y", "z",
    "~", "Ⅱ",
)
SLOT = {token: index for index, token in enumerate(PAGE_TWO_TOKENS)}

# Battle Info prints a stock glyph immediately after ``เลเวล``.  With the
# normal 4px advance of เ, the final ล crosses into that stock cell and loses
# its right edge.  This duplicate keeps the same authored bitmap but advances
# 3px, allowing the final ล to remain wholly inside its VWF cell.
BATTLE_INFO_COMPACT_E_CODE = 0x7F
BATTLE_INFO_COMPACT_E_ADVANCE = 3
# Battle-pilot short names add one otherwise absent Thai cluster, ผ. Keep that
# authored bitmap in a stable supplement slot instead of changing catalog-page
# numbering when the battle-name corpus changes.
BATTLE_PILOT_PHO_PHUNG_CODE = 0x7E

# Weapon badges must not be allocated at the tail of the full catalog-cluster
# page.  The live weapon-list path drops cluster codes $E8-$EA before they
# reach the renderer, which left only P ($EB) visible.  Keep all four badges
# together in explicit free supplement slots so their runtime contract cannot
# move when the catalog token set changes.
WEAPON_ATTRIBUTE_SLOTS = {
    "MAP_L": 0x7A,
    "MAP_R": 0x7B,
    "B": 0x7C,
    "P": 0x7D,
}


def build_page_two(font_dir: Path, en_rom: bytes) -> tuple[bytes, bytes]:
    """Return the 256×16 bitmap page and matching 256-byte width table."""
    atlas = AtlasBuilder(font_dir, en_rom)
    page = bytearray(0x1000)
    widths = bytearray(0x100)
    for token, slot in SLOT.items():
        glyph = atlas.build(f"char:{token}")
        page[slot * 16:(slot + 1) * 16] = bytes(glyph.rows)
        widths[slot] = glyph.advance
    compact_e = atlas.build("cluster:เ")
    start = BATTLE_INFO_COMPACT_E_CODE * 16
    page[start:start + 16] = bytes(compact_e.rows)
    widths[BATTLE_INFO_COMPACT_E_CODE] = BATTLE_INFO_COMPACT_E_ADVANCE
    pho_phung = atlas.build("cluster:ผ")
    start = BATTLE_PILOT_PHO_PHUNG_CODE * 16
    page[start:start + 16] = bytes(pho_phung.rows)
    widths[BATTLE_PILOT_PHO_PHUNG_CODE] = pho_phung.advance
    for name, slot in WEAPON_ATTRIBUTE_SLOTS.items():
        glyph = atlas.build(f"icon:{name}")
        start = slot * 16
        page[start:start + 16] = bytes(glyph.rows)
        widths[slot] = glyph.advance
    return bytes(page), bytes(widths)
