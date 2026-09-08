"""Thai title logo for the pinned English-combo title layout."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


EN_TITLE_LOGO_PC = 0x300000
EN_TITLE_LOGO_SIZE = 0x2000
EXPECTED_PALETTE = (
    "0000", "7FFF", "57FF", "03FF", "037F", "02FF", "027F", "01FF",
    "017F", "00FB", "0017", "0047", "4C00", "3C00", "2C00", "1C00",
)

# Captured from the pinned English-combo ROM's live title OAM.  These are the
# 16x16 sprites in name table 0; Start/Load/Continue/Option use another name
# table and are intentionally outside this asset.
EN_LOGO_X = (*range(16, 193, 16), 200, 216, 232)
EN_LOGO_SPRITES = tuple(
    (x, y, tile)
    for y, tiles in (
        (48, (0x02, 0x04, 0x06, 0x08, 0x0A, 0x0C, 0x0E,
              0x20, 0x22, 0x24, 0x26, 0x28, 0xC2, 0xC4, 0xC6)),
        (64, (0x2A, 0x2C, 0x2E, 0x40, 0x42, 0x44, 0x46,
              0x48, 0x4A, 0x4C, 0x4E, 0x60, 0xC8, 0xCA, 0xCC)),
        (80, (0x62, 0x64, 0x66, 0x68, 0x6A, 0x6C, 0x6E,
              0x80, 0x82, 0x84, 0x86, 0x88, 0xE4, 0xE6, 0xE8)),
        (96, (0x8A, 0x8C, 0x8E, 0xA0, 0xA2, 0xA4, 0xA6,
              0xA8, 0xAA, 0xAC, 0xAE, 0xC0, 0xEA, 0xEC, 0xEE)),
    )
    for x, tile in zip(EN_LOGO_X, tiles)
)


def _tile_offset(tile: int) -> int:
    return tile * 32


def _set_tile_pixel(
    tiles: bytearray, tile: int, x: int, y: int, color: int
) -> None:
    offset = _tile_offset(tile)
    mask = 1 << (7 - x)
    for plane in range(4):
        byte_offset = offset + y * 2 + (plane & 2) * 8 + (plane & 1)
        if color >> plane & 1:
            tiles[byte_offset] |= mask
        else:
            tiles[byte_offset] &= ~mask


def _get_tile_pixel(tiles: bytes, tile: int, x: int, y: int) -> int:
    offset = _tile_offset(tile)
    bit = 7 - x
    return sum(
        ((tiles[offset + y * 2 + (plane & 2) * 8 + (plane & 1)] >> bit) & 1)
        << plane
        for plane in range(4)
    )


def _clear_sprite(tiles: bytearray, tile: int) -> None:
    for part in (tile, tile + 1, tile + 0x10, tile + 0x11):
        offset = _tile_offset(part)
        tiles[offset:offset + 32] = bytes(32)


def _set_sprite_pixel(
    tiles: bytearray, screen_x: int, screen_y: int, color: int
) -> None:
    for x, y, tile in EN_LOGO_SPRITES:
        if x <= screen_x < x + 16 and y <= screen_y < y + 16:
            local_x = screen_x - x
            local_y = screen_y - y
            part = tile + local_x // 8 + (local_y // 8) * 0x10
            _set_tile_pixel(tiles, part, local_x & 7, local_y & 7, color)
            return


def _get_sprite_pixel(tiles: bytes, screen_x: int, screen_y: int) -> int:
    for x, y, tile in EN_LOGO_SPRITES:
        if x <= screen_x < x + 16 and y <= screen_y < y + 16:
            local_x = screen_x - x
            local_y = screen_y - y
            part = tile + local_x // 8 + (local_y // 8) * 0x10
            return _get_tile_pixel(tiles, part, local_x & 7, local_y & 7)
    return 0


def build_en_title_logo(data_root: Path, english_rom: bytes) -> tuple[bytes, dict]:
    """Return the EN-native logo page with only its logo sprites replaced."""
    document = json.loads(
        (data_root / "assets" / "title-logo.json").read_text(encoding="utf-8")
    )
    box = document["screen_box"]
    rows = document["rows"]
    width = int(box["width"])
    height = int(box["height"])
    if box != {"x": 24, "y": 48, "width": 200, "height": 64}:
        raise ValueError("Thai title-logo geometry does not fit the EN OAM surface")
    if len(rows) != height or any(len(row) != width for row in rows):
        raise ValueError("invalid Thai title-logo bitmap dimensions")
    if tuple(document.get("palette_bgr555", ())) != EXPECTED_PALETTE:
        raise ValueError("Thai title logo palette differs from EN OBJ palette 7")

    end = EN_TITLE_LOGO_PC + EN_TITLE_LOGO_SIZE
    if len(english_rom) < end:
        raise ValueError("English ROM is too small for its title-logo page")
    tiles = bytearray(english_rom[EN_TITLE_LOGO_PC:end])
    before = bytes(tiles)
    for _, _, tile in EN_LOGO_SPRITES:
        _clear_sprite(tiles, tile)
    for y, row in enumerate(rows):
        for x, value in enumerate(row):
            color = int(value, 16)
            if color:
                _set_sprite_pixel(tiles, int(box["x"]) + x, int(box["y"]) + y, color)

    decoded_rows = [
        "".join(
            f"{_get_sprite_pixel(tiles, int(box['x']) + x, int(box['y']) + y):X}"
            for x in range(width)
        )
        for y in range(height)
    ]
    if decoded_rows != rows:
        mismatches = sum(
            expected != actual
            for expected_row, actual_row in zip(rows, decoded_rows)
            for expected, actual in zip(expected_row, actual_row)
        )
        raise AssertionError(
            f"EN title-logo tile mapping changed {mismatches} source pixels"
        )

    changed = sum(a != b for a, b in zip(before, tiles))
    if not changed:
        raise AssertionError("EN title-logo build made no pixel changes")
    return bytes(tiles), {
        "text": str(document["text"]),
        "pc": f"0x{EN_TITLE_LOGO_PC:06X}",
        "bytes": len(tiles),
        "changed_bytes": changed,
        "sha256": hashlib.sha256(tiles).hexdigest(),
        "menu_preserved": True,
    }


def install_en_title_logo(image: bytearray, data_root: Path, english_rom: bytes) -> dict:
    payload, report = build_en_title_logo(data_root, english_rom)
    end = EN_TITLE_LOGO_PC + len(payload)
    if image[EN_TITLE_LOGO_PC:end] != english_rom[EN_TITLE_LOGO_PC:end]:
        raise ValueError("EN title-logo page was already modified by another build stage")
    image[EN_TITLE_LOGO_PC:end] = payload
    return report
