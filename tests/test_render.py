"""P4 tests: the reference renderer, and the fixtures the ROM code must match."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from srw4.pipeline import Pipeline  # noqa: E402
from srw4.render import CANVAS_WIDTH, CELL_ROWS, LineCanvas, Renderer  # noqa: E402
from srw4.tokens import EncodingError  # noqa: E402

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
GOLDEN_DIR = ROOT / "tests" / "golden"


@pytest.fixture(scope="module")
def pipeline() -> Pipeline:
    return Pipeline.load(ROOT, CLEAN_ROM)


# --- the canvas -------------------------------------------------------------


def test_a_glyph_lands_where_the_pen_is():
    canvas = LineCanvas(width=32)
    canvas.blit((0b10000001,) + (0,) * 15, 0)
    canvas.blit((0b10000001,) + (0,) * 15, 11)
    row = canvas.to_rows()[0]
    bits = "".join(f"{byte:08b}" for byte in row)
    assert bits[0] == "1" and bits[7] == "1"
    assert bits[11] == "1" and bits[18] == "1"


def test_a_glyph_may_straddle_a_cell_boundary():
    canvas = LineCanvas(width=32)
    canvas.blit((0b11111111,) + (0,) * 15, 5)
    assert canvas.dirty_first == 0
    assert canvas.dirty_last == 1  # pixels 5..12 touch cells 0 and 1


def test_dirty_cells_and_tiles_are_counted_per_line():
    canvas = LineCanvas(width=CANVAS_WIDTH)
    canvas.blit((0xFF,) + (0,) * 15, 0)
    canvas.blit((0xFF,) + (0,) * 15, 40)
    assert canvas.dirty_first == 0 and canvas.dirty_last == 5
    assert canvas.dirty_cells == 6
    assert canvas.tile_count == 12  # a top and a bottom tile per cell


def test_pixels_past_the_right_edge_are_counted_not_wrapped():
    canvas = LineCanvas(width=16)
    canvas.blit((0xFF,) + (0,) * 15, 12)
    assert canvas.overflow == 4
    assert len(canvas.to_rows()[0]) == 2


def test_a_blank_canvas_has_no_dirty_cells():
    canvas = LineCanvas(width=32)
    canvas.blit((0,) * CELL_ROWS, 0)
    assert canvas.dirty_cells == 0
    assert canvas.tile_count == 0


def test_tiles_come_out_top_half_then_bottom_half():
    canvas = LineCanvas(width=CANVAS_WIDTH)
    canvas.rows[0] = 1 << (CANVAS_WIDTH - 1)   # top-left pixel
    canvas.rows[8] = 1 << (CANVAS_WIDTH - 9)   # first pixel of cell 1, lower half
    tiles = canvas.to_tiles()
    assert len(tiles) == (CANVAS_WIDTH // 8) * 2 * 8
    assert tiles[0] == 0x80          # cell 0, top tile, row 0
    assert tiles[16 + 8] == 0x80     # cell 1, bottom tile, row 0


# --- the renderer -----------------------------------------------------------


def test_a_newline_starts_a_new_line(pipeline):
    drawn = pipeline.draw("ก\nข<ENDFF>", where="t")
    assert len(drawn.lines) == 2
    assert drawn.lines[0].tokens == ["cluster:ก"]
    assert drawn.lines[1].tokens == ["cluster:ข"]


def test_the_terminator_is_reported(pipeline):
    assert pipeline.draw("ก<ENDF7>", where="t").terminator == 0xF7
    assert pipeline.draw("ก<ENDFF>", where="t").terminator == 0xFF


def test_engine_bytes_are_kept_but_draw_nothing(pipeline):
    plain = pipeline.draw("ก<ENDFF>", where="t")
    with_control = pipeline.draw("<FC:05>ก<ENDFF>", where="t")
    assert with_control.lines[0].width == plain.lines[0].width
    assert b"\xfc\x05" in with_control.lines[0].engine[0]


def test_the_pen_moves_by_the_advance_not_the_ink(pipeline):
    drawn = pipeline.draw("กกก<ENDFF>", where="t")
    advance = pipeline.atlas["cluster:ก"].advance
    assert drawn.lines[0].width == advance * 3


def test_the_renderer_only_blits_what_the_atlas_gives_it(pipeline):
    # No mark logic lives here: a cluster is drawn exactly as the atlas built it.
    drawn = pipeline.draw("สู้<ENDFF>", where="t")
    glyph = pipeline.atlas["cluster:สู้"]
    rows = drawn.lines[0].canvas.rows
    for index, row in enumerate(glyph.rows):
        assert rows[index] >> (CANVAS_WIDTH - 8) == row


def test_icons_digits_and_clusters_share_one_blitter(pipeline):
    drawn = pipeline.draw("<B>7ก<ENDFF>", where="t")
    assert drawn.lines[0].tokens == ["icon:B", "char:7", "cluster:ก"]
    assert drawn.lines[0].canvas.dirty_cells > 0


def test_a_reserved_byte_stops_the_renderer(pipeline):
    with pytest.raises(EncodingError, match="reserved gap"):
        Renderer(pipeline.token_map, pipeline.atlas).render(b"\xe0")


def test_a_narrow_canvas_reports_the_overflow(pipeline):
    drawn = pipeline.draw("ทดสอบขอบจอ<ENDFF>", where="t", width=32)
    assert drawn.lines[0].canvas.overflow > 0


# --- golden fixtures --------------------------------------------------------


def test_the_fixtures_still_draw_exactly_as_recorded(pipeline):
    from render_lines import as_text, render_all  # tools/render_lines.py

    translations = json.loads(
        (ROOT / "data" / "translations" / "script.th.json").read_text()
    )["messages"]
    rendered = render_all(pipeline, translations)

    for name, entry in rendered.items():
        golden = GOLDEN_DIR / f"{name}.txt"
        assert golden.exists(), f"missing golden file for {name}"
        assert golden.read_text() == as_text(name, entry), (
            f"{name} no longer matches its golden file; "
            "review the change, then rerun tools/render_lines.py --update-golden"
        )


def test_the_fixture_set_covers_the_cases_that_break_renderers():
    from render_lines import FIXTURES

    assert {"line-break", "icons", "digits", "runtime-name", "stacked-marks"} <= set(FIXTURES)
