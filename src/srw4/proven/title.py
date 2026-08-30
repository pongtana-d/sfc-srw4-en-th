"""Deterministic replacement for the title-screen menu lettering."""

from __future__ import annotations

import json
from pathlib import Path

from .catalogs import Write


RESOURCE_TABLE_PC = 0x0E0000
TITLE_OBJ_RESOURCE_ID = 0x16
TITLE_OBJ_SOURCE_CPU = 0xCEDA6A
TITLE_OBJ_OUTPUT_SIZE = 0x3000
TEXT_DATA_END = 0x3C0000

# x, y, top-left OBJ tile. Every entry is a stock 16x16 sprite.
MENU_ROWS = (
    ("START", ((112, 128, 0x0CE), (128, 128, 0x0E0))),
    ("LOAD", ((112, 144, 0x0E2), (128, 144, 0x0E4))),
    (
        "CONTINUE",
        ((96, 160, 0x0E6), (112, 160, 0x0E8),
         (128, 160, 0x0EA), (144, 160, 0x0EC)),
    ),
    ("OPTION", ((104, 176, 0x0EE), (120, 176, 0x100), (136, 176, 0x102))),
)

# Live OAM captured from an isolated title redraw.  Each entry is a stock
# 16x16 OBJ; the two entries at (56, 48) intentionally overlap in the original
# Japanese composition.
LOGO_SPRITES = (
    (24, 48, 0x002), (40, 48, 0x004), (56, 48, 0x0CA),
    (56, 48, 0x0CC), (72, 48, 0x008), (88, 48, 0x00A),
    (104, 48, 0x00C), (120, 48, 0x00E), (136, 48, 0x020),
    (152, 48, 0x022), (168, 48, 0x024), (184, 48, 0x026),
    (200, 48, 0x028), (216, 48, 0x02A),
    (24, 64, 0x02C), (40, 64, 0x02E), (56, 64, 0x040),
    (72, 64, 0x042), (88, 64, 0x044), (104, 64, 0x046),
    (120, 64, 0x048), (136, 64, 0x04A), (152, 64, 0x04C),
    (168, 64, 0x04E), (184, 64, 0x060), (200, 64, 0x062),
    (216, 64, 0x064),
    (16, 80, 0x066), (32, 80, 0x068), (48, 80, 0x06A),
    (64, 80, 0x06C), (80, 80, 0x06E), (96, 80, 0x080),
    (112, 80, 0x082), (128, 80, 0x084), (144, 80, 0x086),
    (160, 80, 0x088), (176, 80, 0x08A), (192, 80, 0x08C),
    (208, 80, 0x08E),
    (16, 96, 0x0A0), (32, 96, 0x0A2), (48, 96, 0x0A4),
    (64, 96, 0x0A6), (80, 96, 0x0A8), (96, 96, 0x0AA),
    (112, 96, 0x0AC), (128, 96, 0x0AE), (144, 96, 0x0C0),
    (160, 96, 0x0C2), (176, 96, 0x0C4), (192, 96, 0x0C6),
    (208, 96, 0x0C8),
)


def cpu_to_pc(address: int) -> int:
    bank = (address >> 16) & 0xFF
    if not 0xC0 <= bank <= 0xFF:
        raise ValueError(f"unsupported HiROM address ${address:06X}")
    return (bank - 0xC0) * 0x10000 + (address & 0xFFFF)


def decompress_lz(
    rom: bytes, source_pc: int, limit: int = 0x20000
) -> tuple[bytes, int]:
    """Decode the stock $80:F93D LZ stream and return data and packed size."""
    source = 0
    output = bytearray()
    control = 0
    bit_counter = 0x80

    def read_bit() -> int:
        nonlocal source, control, bit_counter
        reload_control = bit_counter >> 7
        bit_counter = (bit_counter << 1) & 0xFF
        if reload_control:
            bit_counter = ((bit_counter << 1) & 0xFF) | 1
            control = rom[source_pc + source]
            source += 1
        result = control >> 7
        control = (control << 1) & 0xFF
        return result

    while len(output) < limit:
        if read_bit():
            output.append(rom[source_pc + source])
            source += 1
            continue
        if not read_bit():
            length_bits = (read_bit() << 1) | read_bit()
            offset = rom[source_pc + source] - 0x100
            source += 1
            length = length_bits + 2
        else:
            high = rom[source_pc + source]
            low = rom[source_pc + source + 1]
            source += 2
            packed = (high << 8) | low
            offset = (packed >> 3) | 0xE000
            if offset & 0x8000:
                offset -= 0x10000
            length_bits = packed & 7
            if length_bits:
                length = length_bits + 2
            else:
                length_byte = rom[source_pc + source]
                source += 1
                if length_byte == 0:
                    return bytes(output), source
                length = length_byte + 1
        for _ in range(length):
            read_at = len(output) + offset
            if read_at < 0:
                raise ValueError(
                    f"invalid LZ reference {offset} at output {len(output):#x}"
                )
            output.append(output[read_at])
    raise ValueError(f"LZ stream exceeded safety limit {limit:#x}")


def compress_literals(data: bytes) -> bytes:
    """Encode a valid literal-only stream followed by the stock terminator."""
    output = bytearray()
    control_offset: int | None = None
    control_bits = 0

    def emit_bit(value: int) -> None:
        nonlocal control_offset, control_bits
        if control_bits == 0:
            control_offset = len(output)
            output.append(0)
        assert control_offset is not None
        if value:
            output[control_offset] |= 1 << (7 - control_bits)
        control_bits = (control_bits + 1) & 7

    for value in data:
        emit_bit(1)
        output.append(value)
    emit_bit(0)
    emit_bit(1)
    output.extend(b"\x00\x00\x00")
    return bytes(output)


def _obj_tile_offset(tile: int) -> int:
    if tile < 0x100:
        return tile * 32
    return 0x2000 + (tile & 0xFF) * 32


def _set_tile_pixel(
    tiles: bytearray, tile: int, x: int, y: int, color: int
) -> None:
    offset = _obj_tile_offset(tile)
    mask = 1 << (7 - x)
    for plane in range(4):
        byte_offset = offset + y * 2 + (plane & 2) * 8 + (plane & 1)
        if color >> plane & 1:
            tiles[byte_offset] |= mask
        else:
            tiles[byte_offset] &= ~mask


def _clear_sprite(tiles: bytearray, tile: int) -> None:
    for part in (tile, tile + 1, tile + 0x10, tile + 0x11):
        offset = _obj_tile_offset(part)
        tiles[offset:offset + 32] = bytes(32)


def _set_sprite_pixel(
    tiles: bytearray,
    sprites: tuple[tuple[int, int, int], ...],
    screen_x: int,
    screen_y: int,
    color: int,
) -> None:
    for x, y, tile in sprites:
        if x <= screen_x < x + 16 and y <= screen_y < y + 16:
            local_x = screen_x - x
            local_y = screen_y - y
            part = tile + local_x // 8 + (local_y // 8) * 0x10
            _set_tile_pixel(tiles, part, local_x & 7, local_y & 7, color)
            return


def latin_bitmap(root: Path, text: str) -> tuple[set[tuple[int, int]], int, int]:
    art = json.loads((root / "assets/title-menu.json").read_text(encoding="utf-8"))
    rows = art["labels"][text]["rows"]
    if not rows or len({len(row) for row in rows}) != 1:
        raise ValueError(f"invalid title bitmap for {text}")
    pixels = {
        (x, y)
        for y, row in enumerate(rows)
        for x, value in enumerate(row)
        if value == "#"
    }
    if not pixels:
        raise ValueError(f"empty title bitmap for {text}")
    width = max(x for x, _ in pixels) + 1
    return pixels, width, len(rows)


def latin_origin(root: Path, text: str) -> tuple[int, int] | None:
    """Return the explicit box-relative origin of a label, if the art sets one."""
    art = json.loads((root / "assets/title-menu.json").read_text(encoding="utf-8"))
    origin = art["labels"][text].get("origin")
    if origin is None:
        return None
    return int(origin["x"]), int(origin["y"])


def draw_latin_menu(root: Path, tiles: bytearray) -> None:
    for text, sprites in MENU_ROWS:
        for _, _, tile in sprites:
            _clear_sprite(tiles, tile)
        pixels, width, height = latin_bitmap(root, text)
        origin = latin_origin(root, text)
        left = min(x for x, _, _ in sprites)
        top = min(y for _, y, _ in sprites)
        right = max(x + 16 for x, _, _ in sprites)
        if origin is None:
            x0 = left + (right - left - width) // 2
            y0 = top + (16 - height) // 2
        else:
            x0 = left + origin[0]
            y0 = top + origin[1]
        outline = {
            (x + dx, y + dy)
            for x, y in pixels
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
        }
        for x, y in outline - pixels:
            _set_sprite_pixel(tiles, sprites, x0 + x, y0 + y, 8)
        for x, y in pixels:
            if (x, y - 1) not in pixels or (x - 1, y) not in pixels:
                color = 1
            elif (x, y + 1) not in pixels or (x + 1, y) not in pixels:
                color = 6
            else:
                color = 2 + min(3, y * 4 // height)
            _set_sprite_pixel(tiles, sprites, x0 + x, y0 + y, color)


def draw_thai_logo(root: Path, tiles: bytearray) -> str:
    art = json.loads((root / "assets/title-logo.json").read_text(encoding="utf-8"))
    box = art["screen_box"]
    rows = art["rows"]
    width = int(box["width"])
    height = int(box["height"])
    if len(rows) != height or any(len(row) != width for row in rows):
        raise ValueError("invalid Thai title-logo bitmap dimensions")
    if art.get("palette_bgr555") != [
        "0000", "7FFF", "57FF", "03FF", "037F", "02FF", "027F", "01FF",
        "017F", "00FB", "0017", "0047", "4C00", "3C00", "2C00", "1C00",
    ]:
        raise ValueError("Thai title logo does not use the captured stock palette")
    for _, _, tile in LOGO_SPRITES:
        _clear_sprite(tiles, tile)
    left = int(box["x"])
    top = int(box["y"])
    for y, row in enumerate(rows):
        for x, value in enumerate(row):
            color = int(value, 16)
            if color:
                _set_sprite_pixel(tiles, LOGO_SPRITES, left + x, top + y, color)
    return str(art["text"])


def build_title_data(
    root: Path, clean: bytes, text_cursor: int
) -> tuple[list[Write], dict[str, object]]:
    """Build the title OBJ payload after already allocated text data."""
    entry = RESOURCE_TABLE_PC + TITLE_OBJ_RESOURCE_ID * 3
    expected_pointer = TITLE_OBJ_SOURCE_CPU.to_bytes(3, "little")
    if clean[entry:entry + 3] != expected_pointer:
        raise ValueError("title resource pointer source mismatch")
    tiles, original_packed_size = decompress_lz(
        clean, cpu_to_pc(TITLE_OBJ_SOURCE_CPU)
    )
    if len(tiles) != TITLE_OBJ_OUTPUT_SIZE:
        raise ValueError(
            f"title resource decoded to {len(tiles):#x}; "
            f"expected {TITLE_OBJ_OUTPUT_SIZE:#x}"
        )
    patched = bytearray(tiles)
    logo_text = draw_thai_logo(root, patched)
    draw_latin_menu(root, patched)
    payload = compress_literals(bytes(patched))
    decoded, consumed = decompress_lz(payload, 0)
    if decoded != bytes(patched) or consumed != len(payload):
        raise AssertionError("title literal LZ round trip failed")
    payload_pc = (text_cursor + 0xFF) & ~0xFF
    payload_end = payload_pc + len(payload)
    if payload_end > TEXT_DATA_END:
        raise ValueError("title payload exceeds the text_data region")
    payload_cpu = ((0xC0 + (payload_pc >> 16)) << 16) | (payload_pc & 0xFFFF)
    return [
        Write(payload_pc, payload, "title-obj-payload", True),
        Write(entry, payload_cpu.to_bytes(3, "little"), "title-resource-pointer", False),
    ], {
        "menu": [text for text, _ in MENU_ROWS],
        "logo": logo_text,
        "resource_id": f"0x{TITLE_OBJ_RESOURCE_ID:02X}",
        "original_resource_cpu": f"0x{TITLE_OBJ_SOURCE_CPU:06X}",
        "original_packed_size": original_packed_size,
        "decoded_size": len(patched),
        "new_resource_cpu": f"0x{payload_cpu:06X}",
        "new_resource_pc": f"0x{payload_pc:06X}",
        "new_packed_size": len(payload),
        "allocation": {
            "region": "text_data", "owner": "title-obj-payload",
            "start": f"0x{payload_pc:06X}", "end": f"0x{payload_end:06X}",
            "size": len(payload),
        },
    }
