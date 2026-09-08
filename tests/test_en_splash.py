import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))
from srw4.en_splash import (
    install_en_splash_credit, STOCK_TILES_PC, STOCK_TILES_SIZE,
    CREDIT_TILES_PC, CREDIT_TILE_COUNT, TILEMAP_PC, TILEMAP_SIZE,
    DMA_SOURCE_PC, DMA_SIZE_PC, CREDIT_X, CREDIT_Y, CREDIT_COLOR,
    CREDIT_TILE_COLUMNS, VERSION_CREDIT_HEIGHT,
)


def test_splash_preserves_every_pixel_outside_credit():
    base = (ROOT / 'rom/Dai-4-ji Super Robot Taisen (English combo).sfc').read_bytes()
    image = bytearray(base)
    report = install_en_splash_credit(image, base)
    assert report['text'] == 'น้องจ๋าแปลที v1.3'
    assert report['new_runtime_code_bytes'] == 0
    assert report['height'] == 9
    assert 0 < 256 - (CREDIT_X + report['width']) <= 16
    assert 0 < 224 - (CREDIT_Y + report['height']) <= 16
    assert image[STOCK_TILES_PC:STOCK_TILES_PC + STOCK_TILES_SIZE] == base[STOCK_TILES_PC:STOCK_TILES_PC + STOCK_TILES_SIZE]

    def pixel(rom, tiles_pc, x, y):
        at = TILEMAP_PC + ((y // 8) * 32 + x // 8) * 2
        tile = int.from_bytes(rom[at:at + 2], 'little')
        at = tiles_pc + tile * 64 + (y % 8) * 2
        return sum(((rom[at + (p // 2) * 16 + p % 2] >> (7 - x % 8)) & 1) << p for p in range(8))

    ink = 0
    for y in range(256):
        for x in range(256):
            old, new = pixel(base, STOCK_TILES_PC, x, y), pixel(image, CREDIT_TILES_PC, x, y)
            if CREDIT_X <= x < CREDIT_X + CREDIT_TILE_COLUMNS * 8 and CREDIT_Y <= y < CREDIT_Y + VERSION_CREDIT_HEIGHT:
                assert old == 0
                assert new in (0, CREDIT_COLOR)
                ink += new != 0
            else:
                assert old == new
    assert ink > 0
    allowed = set(range(CREDIT_TILES_PC, STOCK_TILES_PC))
    allowed.update(range(TILEMAP_PC, TILEMAP_PC + TILEMAP_SIZE))
    allowed.update(range(DMA_SOURCE_PC, DMA_SOURCE_PC + 2))
    allowed.update(range(DMA_SIZE_PC, DMA_SIZE_PC + 2))
    assert all(a == b or at in allowed for at, (a, b) in enumerate(zip(base, image)))
