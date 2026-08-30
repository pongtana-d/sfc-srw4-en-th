"""Reference layout for dynamic menu frames and selection geometry."""

from __future__ import annotations

from dataclasses import dataclass


TILE_PIXELS = 8


@dataclass(frozen=True)
class BorderTiles:
    top_left: int
    top: int
    top_right: int
    left: int
    right: int
    bottom_left: int
    bottom: int
    bottom_right: int


@dataclass(frozen=True)
class WindowSpec:
    anchor_x_tiles: int
    anchor_y_tiles: int
    min_outer_width_tiles: int
    padding_left_tiles: int
    padding_right_tiles: int
    item_height_tiles: int
    cursor_x_tiles: int
    cursor_y_tiles: int
    border: BorderTiles


@dataclass(frozen=True)
class MenuLayout:
    outer_width_tiles: int
    outer_height_tiles: int
    tilemap: tuple[tuple[int | None, ...], ...]
    label_positions_px: tuple[tuple[int, int], ...]
    cursor_positions_px: tuple[tuple[int, int], ...]


def menu_layout(spec: WindowSpec, label_widths_px: list[int]) -> MenuLayout:
    """Build the frame and positions after measuring every menu label.

    A label uses one 8x16 glyph row, so each logical item consumes two tilemap
    rows. The outer frame is one tile on every side. The returned tilemap uses
    None for cells that the glyph/tile allocator will fill later.
    """
    if not label_widths_px:
        raise ValueError("a menu needs at least one item")
    if any(width < 0 for width in label_widths_px):
        raise ValueError("label width cannot be negative")

    widest_tiles = max((width + TILE_PIXELS - 1) // TILE_PIXELS for width in label_widths_px)
    content_width = widest_tiles + spec.padding_left_tiles + spec.padding_right_tiles
    outer_width = max(spec.min_outer_width_tiles, content_width + 2)
    outer_height = 2 + len(label_widths_px) * spec.item_height_tiles

    grid: list[list[int | None]] = [[None] * outer_width for _ in range(outer_height)]
    border = spec.border
    grid[0][0], grid[0][-1] = border.top_left, border.top_right
    grid[-1][0], grid[-1][-1] = border.bottom_left, border.bottom_right
    for x in range(1, outer_width - 1):
        grid[0][x] = border.top
        grid[-1][x] = border.bottom
    for y in range(1, outer_height - 1):
        grid[y][0] = border.left
        grid[y][-1] = border.right

    label_x = (spec.anchor_x_tiles + 1 + spec.padding_left_tiles) * TILE_PIXELS
    label_positions = tuple(
        (label_x, (spec.anchor_y_tiles + 1 + index * spec.item_height_tiles) * TILE_PIXELS)
        for index in range(len(label_widths_px))
    )
    cursor_positions = tuple(
        (
            (spec.anchor_x_tiles + spec.cursor_x_tiles) * TILE_PIXELS,
            (spec.anchor_y_tiles + spec.cursor_y_tiles + index * spec.item_height_tiles) * TILE_PIXELS,
        )
        for index in range(len(label_widths_px))
    )
    return MenuLayout(
        outer_width,
        outer_height,
        tuple(tuple(row) for row in grid),
        label_positions,
        cursor_positions,
    )
