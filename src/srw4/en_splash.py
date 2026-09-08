"""Static Thai credit on the EN Aeon Genesis splash; no new runtime code."""
from __future__ import annotations

# The stock splash loads 68 8bpp tiles at $F0:8000, followed by its tilemap.
# Two rows of eight erased tiles extend that same DMA transfer backwards.
STOCK_TILES_PC = 0x308000
STOCK_TILES_SIZE = 0x1100
TILE_BYTES = 64
CREDIT_TILE_COLUMNS = 8
CREDIT_TILE_ROWS = 2
CREDIT_TILE_COUNT = CREDIT_TILE_COLUMNS * CREDIT_TILE_ROWS
CREDIT_TILES_PC = STOCK_TILES_PC - CREDIT_TILE_COUNT * TILE_BYTES
TILEMAP_PC = 0x309100
TILEMAP_SIZE = 0x800
PALETTE_PC = 0x309900
DMA_SOURCE_PC = 0x30C97E
DMA_SIZE_PC = 0x30C989
CREDIT_X, CREDIT_Y = 184, 208
CREDIT_COLOR = 152  # Stock grayscale palette: 19/31 brightness ($4E73).

VERSION_CREDIT = "น้องจ๋าแปลที"
VERSION_TEXT = VERSION_CREDIT + " v1.3"
VERSION_GLYPHS = (
    ("000", "101", "101", "101", "010"),
    ("010", "110", "010", "010", "111"),
    ("0", "0", "0", "0", "1"),
    ("110", "001", "010", "001", "110"),
)
# Hand-drawn credit clusters: five-pixel bodies plus three rows for Thai
# marks/ascenders. Keep these literal pixels independent of dialogue fonts.
VERSION_CREDIT_GLYPHS = (
    ("0101", "0010", "0000", "1101", "0101", "0101", "0101", "0111"),  # น้
    ("0000", "0000", "0000", "1110", "0001", "0101", "1001", "1110"),  # อ
    ("000", "000", "000", "011", "001", "001", "101", "011"),  # ง
    ("0100", "1110", "0100", "1110", "0001", "0101", "0011", "0001"),  # จ๋
    ("000", "000", "000", "110", "001", "001", "001", "001"),  # า
    ("00000", "00000", "00000", "01001", "01001", "01001", "01001", "11011"),  # แ
    ("0001", "0001", "0001", "1101", "0101", "0101", "0101", "1111"),  # ป
    ("0000", "0000", "0000", "1110", "0001", "0111", "1001", "1101"),  # ล
    ("0001", "1111", "0000", "1101", "0111", "0101", "0101", "0101"),  # ที
)
# Extend the middle body stroke by one row; retain the Thai mark spacing.
VERSION_CREDIT_GLYPHS = tuple(glyph[:5] + (glyph[5],) + glyph[5:]
                              for glyph in VERSION_CREDIT_GLYPHS)
VERSION_GLYPHS = tuple(glyph[:2] + (glyph[2],) + glyph[2:]
                       for glyph in VERSION_GLYPHS)
VERSION_CREDIT_HEIGHT = 9
VERSION_BODY_HEIGHT = 6


def install_en_splash_credit(image: bytearray, english_rom: bytes) -> dict:
    """Extend the stock tile DMA backwards and adjust only the splash map."""
    def replace(pc: int, expected: bytes, payload: bytes) -> None:
        if english_rom[pc:pc + len(expected)] != expected or image[pc:pc + len(expected)] != expected:
            raise ValueError(f"EN splash resource mismatch at {pc:#x}")
        image[pc:pc + len(payload)] = payload

    if english_rom[PALETTE_PC + CREDIT_COLOR * 2:PALETTE_PC + CREDIT_COLOR * 2 + 2] != bytes.fromhex("73 4E"):
        raise ValueError("EN splash gray palette mismatch")
    pixels = set()
    cursor = 0
    for glyph in VERSION_CREDIT_GLYPHS:
        pixels.update((cursor + x, y) for y, row in enumerate(glyph)
                      for x, bit in enumerate(row) if bit == "1")
        cursor += len(glyph[0]) + 1
    cursor += 2
    for glyph in VERSION_GLYPHS:
        pixels.update((cursor + x, y + VERSION_CREDIT_HEIGHT - VERSION_BODY_HEIGHT)
                      for y, row in enumerate(glyph)
                      for x, bit in enumerate(row) if bit == "1")
        cursor += len(glyph[0]) + 1
    tiles = bytearray(CREDIT_TILE_COUNT * TILE_BYTES)
    for x, y in pixels:
        if not (0 <= x < CREDIT_TILE_COLUMNS * 8 and 0 <= y < VERSION_CREDIT_HEIGHT):
            raise ValueError("Splash credit exceeds reserved tiles")
        for plane in range(8):
            if CREDIT_COLOR >> plane & 1:
                tile = (y // 8) * CREDIT_TILE_COLUMNS + x // 8
                at = tile * TILE_BYTES + (plane // 2) * 16 + (y % 8) * 2 + plane % 2
                tiles[at] |= 0x80 >> (x % 8)
    stock_map = english_rom[TILEMAP_PC:TILEMAP_PC + TILEMAP_SIZE]
    tilemap = bytearray(stock_map)
    for at in range(0, TILEMAP_SIZE, 2):
        value = int.from_bytes(stock_map[at:at + 2], "little")
        if value >= STOCK_TILES_SIZE // TILE_BYTES:
            raise ValueError("Unexpected EN splash tile index/attributes")
        tilemap[at:at + 2] = (value + CREDIT_TILE_COUNT).to_bytes(2, "little")
    for tile in range(CREDIT_TILE_COUNT):
        at = ((CREDIT_Y // 8 + tile // CREDIT_TILE_COLUMNS) * 32
              + CREDIT_X // 8 + tile % CREDIT_TILE_COLUMNS) * 2
        if stock_map[at:at + 2] != b"\0\0":
            raise ValueError("Splash credit overlaps original logo")
        tilemap[at:at + 2] = tile.to_bytes(2, "little")
    replace(CREDIT_TILES_PC, b"\xFF" * len(tiles), tiles)
    replace(TILEMAP_PC, stock_map, tilemap)
    replace(DMA_SOURCE_PC, (STOCK_TILES_PC & 0xFFFF).to_bytes(2, "little"),
            (CREDIT_TILES_PC & 0xFFFF).to_bytes(2, "little"))
    replace(DMA_SIZE_PC, STOCK_TILES_SIZE.to_bytes(2, "little"),
            (STOCK_TILES_SIZE + len(tiles)).to_bytes(2, "little"))
    return {"text": VERSION_TEXT, "x": CREDIT_X, "y": CREDIT_Y,
            "width": cursor - 1, "height": VERSION_CREDIT_HEIGHT,
            "color_bgr555": "4E73", "new_runtime_code_bytes": 0}
