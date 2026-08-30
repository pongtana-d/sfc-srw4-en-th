"""Assembling the blitter and the tables it reads.

The same assembly source is used for the fixture ROM and for the real one; only
the constants differ, which is what makes a pixel-for-pixel comparison against
the Python renderer worth anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .asm65816 import Assembled, assemble
from .atlas import CELL_ROWS
from .contract import EXTENDED_PAGES
from .render import CANVAS_WIDTH
from .text import ENGINE_OPERANDS
from .tokens import DIRECT_MAX

SOURCE = Path(__file__).parent / "asm" / "blitter.s"
ADAPTER = Path(__file__).parent / "asm" / "adapter.s"
MENU_ADAPTER = Path(__file__).parent / "asm" / "menu-adapter.s"
WINDOW = Path(__file__).parent / "asm" / "window.s"

CANVAS_STRIDE = 34      # 32 bytes of line, plus two for a glyph at the edge
CANVAS_ROWS = CELL_ROWS
CANVAS_BYTES = CANVAS_STRIDE * CANVAS_ROWS      # 544, the budgeted line canvas

# Offsets inside a context block, following data/config/wram-map.json:
# the canvas first, then the renderer state, then decode scratch.
OFF_CANVAS = 0
OFF_PEN = 544
OFF_DIRTY_FIRST = 546
OFF_DIRTY_LAST = 548
OFF_OVERFLOW = 550
OFF_SRC = 552
OFF_LEN = 556
OFF_LAST_CURSOR = 558
OFF_CODE_SAVE = 560
OFF_LINE_BASE = 562
OFF_TMP = 672          # inside the 64-byte decode scratch

WRAM_BANK = 0x7E
ARENA_BASE = 0x7F8000          # the tile arena the stock rasteriser writes to
STOCK_RASTERISER = 0x8184EB    # what the story loop calls when the text is not ours

# The runtime name buffers `$FB xx 80` draws from, named by the table of
# 3-byte pointers at $C1:8E6E. Two strides, back to back: six pilot names of
# seven bytes from $7E:1008, then three unit names of eleven from $7E:1032.
# The script uses seven of the nine, but the range has to cover them all.
NAME_BANK = 0x00
NAME_FIRST = 0x1008
NAME_LAST = 0x1053

MENU_CONTEXT_BASE = 0xCC00
MENU_STATE_BASE = MENU_CONTEXT_BASE + 720


def menu_adapter_source() -> str:
    """The normal adapter plus the catalog-13 command-menu entry points."""
    return ADAPTER.read_text() + "\n" + MENU_ADAPTER.read_text()


def menu_adapter_constants(
    *, overlay: int = 0, cell_stream_first: int = 0x0000,
    cell_stream_end: int = 0xFFFF,
) -> dict[str, int]:
    """Menu-only state after the generic context/frame reservation."""
    return {
        "MENU_POOL_BANK": 0xFA,
        "MENU_POINTER_SAVE": (WRAM_BANK << 16) | (MENU_STATE_BASE + 0),
        "MENU_BANK_SAVE": (WRAM_BANK << 16) | (MENU_STATE_BASE + 2),
        "MENU_MAX_PEN": (WRAM_BANK << 16) | (MENU_STATE_BASE + 4),
        "MENU_ACTIVE": (WRAM_BANK << 16) | (MENU_STATE_BASE + 6),
        # A full cookie prevents old savestates' unrelated WRAM contents from
        # activating the global D2 command-pointer router by accident.
        "MENU_ROUTING_COOKIE": 0xC7A5,
        "MENU_WIDTH": MENU_STATE_BASE + 8,
        # Dynamic top-left byte offset in the stock `$7E:A000` shadow map.
        # The stock command record chooses this from the unit's screen
        # position; keeping it dynamic is the key contract copied from EN.
        "MENU_FRAME_PTR": MENU_STATE_BASE + 10,
        "MENU_CONTENT_PTR": MENU_STATE_BASE + 12,
        "MENU_ROW_TILE": MENU_STATE_BASE + 14,
        "MENU_ROW_TILE_LONG": (WRAM_BANK << 16) | (MENU_STATE_BASE + 14),
        "MENU_ATTR": MENU_STATE_BASE + 16,
        "MENU_CELLS": MENU_STATE_BASE + 18,
        "MENU_RECORD_COUNT": (WRAM_BANK << 16) | (MENU_STATE_BASE + 20),
        "MENU_RECORDS": (WRAM_BANK << 16) | (MENU_STATE_BASE + 22),
        "MENU_CURRENT_RECORD": (WRAM_BANK << 16) | (MENU_STATE_BASE + 30),
        "MENU_ROW_PENDING": (WRAM_BANK << 16) | (MENU_STATE_BASE + 32),
        "MENU_SELECTED_ROW": MENU_STATE_BASE + 34,
        "MENU_ROW_INDEX": MENU_STATE_BASE + 36,
        "MENU_ROWS": MENU_STATE_BASE + 38,
        "MENU_ROW_RENDERED": (WRAM_BANK << 16) | (MENU_STATE_BASE + 40),
        "MENU_FIRST_TOKEN": (WRAM_BANK << 16) | (MENU_STATE_BASE + 42),
        "MENU_CACHE_RECOVERY": (WRAM_BANK << 16) | (MENU_STATE_BASE + 44),
        "MENU_OVERLAY": overlay,
        # `$1A` has already advanced past the current token at raster time.
        # Only this private interval is command overlay data; catalog/status
        # streams can also live in bank $FA and must retain their stock owner.
        "MENU_CELL_STREAM_FIRST": cell_stream_first,
        "MENU_CELL_STREAM_END": cell_stream_end,
        "MENU_OVERLAY_RECORDS": 15,
        "MENU_OVERLAY_BYTES": 120,
        "MENU_OVERLAY_ROW_BLOCKS": 12,
        "FRAME_TOP_LEFT_TILE": 0x0011,
        "FRAME_TOP_TILE": 0x0019,
        "FRAME_TOP_RIGHT_TILE": 0x0012,
        "MENU_DRAW_OUTER": 8,             # 6 content cells plus two borders
        "MENU_CLEAN_MARGIN": 2,           # measured Thai stock drift on each side
        "MENU_TILEMAP_ROW_CELLS": 32,
        "MENU_CONTENT_CELLS": 6,          # never trust stock's mutable width
        "MENU_ROW_GAP": 2,                # 14-tile command row minus six cells * 2
        "MENU_MAX_ROWS": 8,               # byte slots reserved at MENU_RECORDS
        "MENU_FRAME_HEIGHT_MAX": 18,       # 8 rows * 2 tile rows + borders
        "MENU_TILEMAP_BYTES": 0x0800,         # 32x32 words
        "MENU_CONTENT_DELTA": 0x0042,     # one row plus one cell from frame top-left
        "MENU_FIRST_TILE": 0x0000,
        "MENU_ROW_STRIDE": 14,            # six 8x16 content cells plus one tail tile
        "MENU_ROW_SECOND": 28,
        "MENU_ROW_THIRD": 42,
    }


@dataclass(frozen=True)
class Tables:
    """Everything the blitter reads out of ROM."""

    glyphs: bytes        # 16 bytes per unique bitmap
    slots: bytes         # 2 bytes per token: offset of its bitmap
    advances: bytes      # 1 byte per token
    operands: bytes      # 256 bytes: how many operands each engine byte takes

    @property
    def blocks(self) -> list[tuple[str, bytes]]:
        return [
            ("glyphs", self.glyphs),
            ("slots", self.slots),
            ("advances", self.advances),
            ("operands", self.operands),
        ]


def build_tables(token_map, atlas: dict) -> Tables:
    bitmaps: dict[tuple[int, ...], int] = {}
    packed = bytearray()
    slots = bytearray()
    advances = bytearray()

    for token in token_map.tokens:
        glyph = atlas[token]
        offset = bitmaps.get(glyph.rows)
        if offset is None:
            offset = len(packed)
            bitmaps[glyph.rows] = offset
            packed += bytes(glyph.rows)
        slots += offset.to_bytes(2, "little")
        advances.append(glyph.advance)

    operands = bytearray(256)
    for byte, count in ENGINE_OPERANDS.items():
        operands[byte] = count

    return Tables(bytes(packed), bytes(slots), bytes(advances), bytes(operands))


def fixed_advances(token_map, atlas: dict) -> bytes:
    """One full cell per token for the stock naming grid.

    The naming screen owns fixed tile positions and does not use the dialogue
    width contract.  Its routed tokens therefore advance exactly one cell.
    """
    return bytes(8 for _ in token_map.tokens)


def constants(
    context_base: int,
    table_base: dict[str, int],
    glyph_count: int,
    script_banks: tuple[int, int] = (0xF0, 0xF6),
    *,
    with_names: bool = False,
) -> dict[str, int]:
    """Symbols the assembly source expects the build to fill in."""
    return {
        "CANVAS": (context_base + OFF_CANVAS) & 0xFFFF,
        "PEN": (context_base + OFF_PEN) & 0xFFFF,
        "DIRTY_FIRST": (context_base + OFF_DIRTY_FIRST) & 0xFFFF,
        "DIRTY_LAST": (context_base + OFF_DIRTY_LAST) & 0xFFFF,
        "OVERFLOW": (context_base + OFF_OVERFLOW) & 0xFFFF,
        "SRC": (context_base + OFF_SRC) & 0xFFFF,
        "LEN": (context_base + OFF_LEN) & 0xFFFF,
        "TMP": (context_base + OFF_TMP) & 0xFFFF,
        "GLYPH_BASE": table_base["glyphs"],
        "SLOT_TABLE": table_base["slots"],
        "ADVANCE_TABLE": table_base["advances"],
        "OPERAND_TABLE": table_base["operands"],
        "CANVAS_STRIDE": CANVAS_STRIDE,
        "CANVAS_ROWS": CANVAS_ROWS,
        "CANVAS_BYTES": CANVAS_BYTES,
        "CANVAS_WIDTH": CANVAS_WIDTH,
        "GLYPH_COUNT": glyph_count,
        "GLYPH_DIRECT_SLOTS": DIRECT_MAX + 1,
        "GLYPH_EXTENDED_PAGES": EXTENDED_PAGES,
        "CANVAS_ROW8": (context_base + OFF_CANVAS + 8 * CANVAS_STRIDE) & 0xFFFF,
        "CANVAS_CELLS": CANVAS_WIDTH // 8,
        "LAST_CURSOR": (context_base + OFF_LAST_CURSOR) & 0xFFFF,
        "LINE_BASE": (context_base + OFF_LINE_BASE) & 0xFFFF,
        "CODE_SAVE": (WRAM_BANK << 16) | ((context_base + OFF_CODE_SAVE) & 0xFFFF),
        "ARENA_BASE": ARENA_BASE,
        "STOCK_RASTERISER": STOCK_RASTERISER,
        "NAME_BANK": NAME_BANK,
        "NAME_FIRST": NAME_FIRST,
        # An empty range is how the name buffers are left to the stock
        # rasteriser. They hold the game's own bytes until something puts our
        # tokens there; drawing those as glyph ids would be nonsense, so
        # claiming them is off until the names themselves are ours.
        "NAME_LAST": NAME_LAST if with_names else NAME_FIRST,
        # The command-menu evidence uses the same 32x32 shadow at `$7E:A000`.
        # These variables fit after the blitter scratch in every 800-byte
        # context reservation; they are not direct-page state.
        "TILEMAP": 0xA000,
        "FRAME_CURSOR": (context_base + 704) & 0xFFFF,
        "FRAME_WIDTH": (context_base + 706) & 0xFFFF,
        "FRAME_HEIGHT": (context_base + 708) & 0xFFFF,
        "FRAME_INNER": (context_base + 710) & 0xFFFF,
        "FRAME_ROWS": (context_base + 712) & 0xFFFF,
        "FRAME_WIDTH_BYTES": (context_base + 714) & 0xFFFF,
        "FRAME_RIGHT_DELTA": (context_base + 716) & 0xFFFF,
        "FRAME_NEXT_DELTA": (context_base + 718) & 0xFFFF,
        "FRAME_TOP_LEFT": 0x2011,
        "FRAME_TOP": 0x2019,
        "FRAME_TOP_RIGHT": 0x2012,
        "FRAME_LEFT": 0x201B,
        "FRAME_RIGHT": 0x201C,
        "FRAME_BOTTOM_LEFT": 0x2013,
        "FRAME_BOTTOM": 0x201A,
        "FRAME_BOTTOM_RIGHT": 0x2014,
        "SCRIPT_BANK_FIRST": script_banks[0],
        "SCRIPT_BANK_LAST": script_banks[1],
    }


def build(
    origin: int,
    context_base: int,
    table_base: dict[str, int],
    glyph_count: int,
    *,
    with_adapter: bool = False,
    script_banks: tuple[int, int] = (0xF0, 0xF6),
    with_names: bool = False,
    adapter_source: str | None = None,
    extra_constants: dict[str, int] | None = None,
) -> Assembled:
    """Assemble the blitter, and the adapter alongside it when it is needed.

    The fixture ROM wants the blitter on its own; the real build wants both, in
    one program, so the adapter can call into the blitter by label.
    """
    source = SOURCE.read_text() + "\n" + WINDOW.read_text()
    if adapter_source is not None:
        source += "\n" + adapter_source
    elif with_adapter:
        source += "\n" + ADAPTER.read_text()
    symbols = constants(
        context_base, table_base, glyph_count, script_banks, with_names=with_names
    )
    symbols.update(extra_constants or {})
    return assemble(
        source,
        origin,
        symbols,
    )
