"""Supplementary FF page for ASCII and icon glyphs used by Thai dialogue."""
from __future__ import annotations

from pathlib import Path

from .atlas import AtlasBuilder
from .tokens import TokenMap


# Only glyphs used by the current EN-ROM Thai build are authored here.  Codes
# stay explicit so deleting a dead glyph never renumbers a live byte stream.
SLOT = {
    "%": 0x00,
    "A": 0x01, "B": 0x02, "C": 0x03, "D": 0x04, "E": 0x05,
    "F": 0x06, "G": 0x07, "H": 0x08, "I": 0x09, "K": 0x0A,
    "L": 0x0B, "M": 0x0C, "N": 0x0D, "O": 0x0E, "P": 0x0F,
    "R": 0x10, "S": 0x11, "T": 0x12, "U": 0x13, "V": 0x14,
    "W": 0x15, "X": 0x16, "k": 0x17, "Z": 0x18, "x": 0x19, "♥": 0x1A,
    " ": 0x1B, "(": 0x1C, ")": 0x1D, "!": 0x1E, "-": 0x1F, ".": 0x20,
    "/": 0x21, "0": 0x22, "1": 0x23, "2": 0x24, "3": 0x25,
    "4": 0x26, "5": 0x27, "6": 0x28, "7": 0x29, "8": 0x2A,
    "9": 0x2B, ":": 0x2C, "?": 0x2D,
    "e": 0x39, "a": 0x3A, "l": 0x3B, "u": 0x3C,
    "ν": 0x3D,
}

# EN battle dispatch headers reserve two bytes between the pilot-name command
# and the quote selector. Thai quote records already begin with their own
# ``: `` separator.  The locked precomposed token map owns an explicit blank,
# zero-advance ``icon:Pad`` glyph; it deliberately encodes to two native
# `$F0-$F3` bytes so dispatch offsets stay unchanged.
_FONT = Path(__file__).resolve().parents[2] / "data" / "font"
BATTLE_QUOTE_PADDING_TOKEN = "icon:Pad"
BATTLE_QUOTE_PADDING = TokenMap.load(
    _FONT / "renewal-clusters.json"
).encode_glyph(BATTLE_QUOTE_PADDING_TOKEN)
if len(BATTLE_QUOTE_PADDING) != 2:
    raise RuntimeError("battle quote padding must retain the EN header's two bytes")

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

# The reviewed Spirit-help wording added these clusters after the primary
# catalog page had reached its parser-safe $00-$EB capacity.  Keep them in
# explicit free supplement slots so later corpus changes cannot renumber them.
CATALOG_CLUSTER_SUPPLEMENT_SLOTS = {
    "cluster:ก่": 0x71,
    "cluster:ค่": 0x72,
    "cluster:ค้": 0x73,
    "cluster:ชิ้": 0x74,
    "cluster:นึ่": 0x75,
    "cluster:ป้": 0x76,
    "cluster:ฝั": 0x77,
    "cluster:ยู่": 0x78,
    "cluster:รึ่": 0x79,
}

_SUPPLEMENT_RESERVED_SLOTS = {
    *SLOT.values(),
    *WEAPON_ATTRIBUTE_SLOTS.values(),
}
if _SUPPLEMENT_RESERVED_SLOTS.intersection(CATALOG_CLUSTER_SUPPLEMENT_SLOTS.values()):
    raise ValueError("catalog cluster supplement slots overlap another dialogue glyph")
if len(set(CATALOG_CLUSTER_SUPPLEMENT_SLOTS.values())) != len(
    CATALOG_CLUSTER_SUPPLEMENT_SLOTS
):
    raise ValueError("catalog cluster supplement slots contain a duplicate")


def build_page_two(font_dir: Path, en_rom: bytes) -> tuple[bytes, bytes]:
    """Return the 256×16 bitmap page and matching 256-byte width table."""
    atlas = AtlasBuilder(font_dir, en_rom)
    page = bytearray(0x1000)
    widths = bytearray(0x100)
    for token, slot in SLOT.items():
        glyph = atlas.build(f"char:{token}")
        page[slot * 16:(slot + 1) * 16] = bytes(glyph.rows)
        widths[slot] = glyph.advance
    for name, slot in WEAPON_ATTRIBUTE_SLOTS.items():
        glyph = atlas.build(f"icon:{name}")
        start = slot * 16
        page[start:start + 16] = bytes(glyph.rows)
        widths[slot] = glyph.advance
    for token, slot in CATALOG_CLUSTER_SUPPLEMENT_SLOTS.items():
        glyph = atlas.build(token)
        start = slot * 16
        page[start:start + 16] = bytes(glyph.rows)
        widths[slot] = glyph.advance
    return bytes(page), bytes(widths)


def overlay_primary_dialogue_glyphs(
    assets: dict[str, bytes], layout: dict, font_dir: Path, en_rom: bytes
) -> dict[str, bytes]:
    """Copy every live dialogue Latin/icon glyph onto the primary Thai page."""
    atlas = AtlasBuilder(font_dir, en_rom)
    page = bytearray(assets["thai-page.bin"])
    advance = bytearray(assets["thai-advance.bin"])
    base_ink = bytearray(assets["thai-base-ink.bin"])
    chars = str(layout["dialogue_primary_glyphs"])
    codes = layout["codes"]
    if len(chars) != len(set(chars)):
        raise ValueError("dialogue primary glyph list contains a duplicate")
    for char in chars:
        code = int(codes[char])
        if code >= 0xC0:
            raise ValueError(f"dialogue primary glyph {char!r} uses reserved code {code:#x}")
        glyph = atlas.build(f"char:{char}")
        start = code * 16
        page[start:start + 16] = bytes(glyph.rows)
        advance[code] = glyph.advance
        base_ink[code] = min(glyph.ink_width, 15)
    return {
        **assets,
        "thai-page.bin": bytes(page),
        "thai-advance.bin": bytes(advance),
        "thai-base-ink.bin": bytes(base_ink),
    }
