"""P5 tests: the tables the blitter reads, and the blitter itself on hardware."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from srw4.blitter import (  # noqa: E402
    CANVAS_BYTES,
    CANVAS_ROWS,
    CANVAS_STRIDE,
    OFF_LEN,
    OFF_OVERFLOW,
    OFF_PEN,
    build,
    build_tables,
    constants,
    menu_adapter_constants,
    menu_adapter_source,
)
from srw4.contract import EXTENDED_PAGES  # noqa: E402
from srw4.pipeline import Pipeline  # noqa: E402
from srw4.render import CANVAS_WIDTH  # noqa: E402

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
MESEN = Path("/Applications/Mesen.app/Contents/MacOS/Mesen")
WRAM_MAP = ROOT / "data" / "config" / "wram-map.json"


@pytest.fixture(scope="module")
def pipeline() -> Pipeline:
    return Pipeline.load(ROOT, CLEAN_ROM)


@pytest.fixture(scope="module")
def tables(pipeline):
    return build_tables(pipeline.token_map, pipeline.atlas)


# --- the canvas layout ------------------------------------------------------


def test_a_row_has_room_for_the_spill_past_its_last_cell():
    # A glyph starting in the last cell writes one byte beyond it; without the
    # slack it would land in the row below.
    assert CANVAS_STRIDE == CANVAS_WIDTH // 8 + 2


def test_the_canvas_fits_the_budget_the_wram_contract_promised():
    budget = json.loads(WRAM_MAP.read_text())["budget_per_context"]
    assert CANVAS_BYTES == budget["line_canvas"]
    assert OFF_PEN >= CANVAS_BYTES
    assert OFF_OVERFLOW + 2 <= budget["line_canvas"] + budget["renderer_state"]


def test_the_whole_context_block_stays_inside_its_reservation():
    document = json.loads(WRAM_MAP.read_text())
    dialogue = next(
        context
        for region in document["regions"]
        for context in region.get("contexts", [])
        if context["id"] == "dialogue"
    )
    size = int(dialogue["end"], 16) - int(dialogue["start"], 16)
    assert OFF_LEN + 2 <= size


def test_the_window_builder_state_fits_the_same_context_reservation(pipeline):
    symbols = constants(
        0xC5C0,
        {"glyphs": 0x019000, "slots": 0x01C000, "advances": 0x01C800, "operands": 0x01CB00},
        len(pipeline.token_map.tokens),
    )
    # The final derived field is a word at context offset 718.  The context
    # owns 800 bytes, so window state remains clear of its neighbour.
    assert symbols["FRAME_NEXT_DELTA"] + 2 <= 0xC5C0 + 800


# --- the tables -------------------------------------------------------------


def test_every_token_has_an_advance_and_a_slot(tables, pipeline):
    count = len(pipeline.token_map.tokens)
    assert len(tables.advances) == count
    assert len(tables.slots) == count * 2


def test_the_slot_table_points_at_real_bitmaps(tables, pipeline):
    for index, token in enumerate(pipeline.token_map.tokens):
        offset = int.from_bytes(tables.slots[index * 2 : index * 2 + 2], "little")
        assert offset % CANVAS_ROWS == 0
        assert tables.glyphs[offset : offset + CANVAS_ROWS] == bytes(pipeline.atlas[token].rows)


def test_bitmaps_are_shared_rather_than_repeated(tables, pipeline):
    unique = {pipeline.atlas[token].rows for token in pipeline.token_map.tokens}
    assert len(tables.glyphs) == len(unique) * CANVAS_ROWS


def test_the_glyph_page_stays_inside_one_bank(tables):
    assert len(tables.glyphs) < 0x10000


def test_the_operand_table_says_how_much_of_a_command_to_skip(tables):
    assert tables.operands[0xFB] == 2      # FB takes a two-byte pointer
    assert tables.operands[0xFC] == 1
    assert tables.operands[0xFF] == 0      # a terminator has no operand
    assert len(tables.operands) == 256


def test_the_runtime_extended_page_count_comes_from_the_text_contract(pipeline):
    symbols = constants(
        0xC5C0,
        {"glyphs": 0x019000, "slots": 0x01C000, "advances": 0x01C800, "operands": 0x01CB00},
        len(pipeline.token_map.tokens),
    )
    assert symbols["GLYPH_EXTENDED_PAGES"] == EXTENDED_PAGES == 4


# --- assembling -------------------------------------------------------------


def test_the_blitter_assembles_and_exports_its_entry_points(pipeline):
    program = build(
        0x008000,
        0xC5C0,
        {"glyphs": 0x019000, "slots": 0x01C000, "advances": 0x01C800, "operands": 0x01CB00},
        len(pipeline.token_map.tokens),
    )
    for entry in ("clear_line", "blit_glyph", "blit_stream", "draw_window_frame"):
        assert entry in program.labels
    assert len(program.code) > 0


def test_assembling_twice_gives_the_same_bytes(pipeline):
    arguments = (
        0x008000,
        0xC5C0,
        {"glyphs": 0x019000, "slots": 0x01C000, "advances": 0x01C800, "operands": 0x01CB00},
        len(pipeline.token_map.tokens),
    )
    assert build(*arguments).code == build(*arguments).code


def test_the_command_menu_adapter_assembles_with_its_private_state(pipeline):
    program = build(
        0x008000,
        0xCC00,
        {"glyphs": 0x019000, "slots": 0x01C000, "advances": 0x01C800, "operands": 0x01CB00},
        len(pipeline.token_map.tokens),
        adapter_source=menu_adapter_source(),
        script_banks=(0xFA, 0xFA),
        extra_constants=menu_adapter_constants(),
    )
    for entry in (
        "menu_raster_dispatch", "menu_command_open", "menu_selection_update",
        "menu_selection_sync", "menu_find_frame", "menu_upload_overlay_cell",
        "menu_expand_current_palette", "menu_refresh_palette",
    ):
        assert entry in program.labels


def test_command_menu_reserves_eight_dynamic_rows_without_state_overlap():
    symbols = menu_adapter_constants()
    assert symbols["MENU_MAX_ROWS"] == 8
    records = symbols["MENU_RECORDS"] & 0xFFFF
    current = symbols["MENU_CURRENT_RECORD"] & 0xFFFF
    assert current - records == symbols["MENU_MAX_ROWS"]
    assert symbols["MENU_FRAME_HEIGHT_MAX"] == symbols["MENU_MAX_ROWS"] * 2 + 2
    assert symbols["MENU_DRAW_OUTER"] == 8
    assert symbols["MENU_CONTENT_CELLS"] == 6
    assert symbols["MENU_CLEAN_MARGIN"] == 2
    assert symbols["MENU_OVERLAY_ROW_BLOCKS"] * 32 == 6 * 64
    assert symbols["MENU_ROW_GAP"] == 2
    assert symbols["MENU_ROW_STRIDE"] == 14


def test_the_command_menu_adapter_reads_one_headered_overlay_cell_per_stock_glyph(pipeline):
    symbols = menu_adapter_constants()
    program = build(
        0x008000,
        0xCC00,
        {"glyphs": 0x019000, "slots": 0x01C000, "advances": 0x01C800, "operands": 0x01CB00},
        len(pipeline.token_map.tokens),
        adapter_source=menu_adapter_source(),
        script_banks=(0xFA, 0xFA),
        extra_constants=symbols,
    )
    start = program.labels["menu_upload_overlay_cell"] - 0x008000
    end = program.labels["menu_activation"] - 0x008000
    cell = program.code[start:end]
    overlay = symbols["MENU_OVERLAY"]
    assert bytes((0xBF, (overlay + 8) & 0xFF, (overlay + 8) >> 8 & 0xFF, overlay >> 16)) in cell
    assert bytes((0xA9, 0x02, 0x00)) in cell
    assert bytes((0x69, 0x0C, 0x00)) in cell
    assert bytes((0x85, 0xD0)) in cell
    assert program.labels["menu_prepare_overlay_cell"] < program.labels["menu_activation"]
    assert program.labels["menu_activation"] < program.labels["menu_command_open"]
    assert program.labels["menu_command_open"] < program.labels["menu_command_after_parser"]


def test_command_overlay_claims_only_its_private_fa_stream_interval(pipeline):
    symbols = menu_adapter_constants(
        cell_stream_first=0x5001,
        cell_stream_end=0x5069,
    )
    program = build(
        0x008000,
        0xCC00,
        {"glyphs": 0x019000, "slots": 0x01C000, "advances": 0x01C800, "operands": 0x01CB00},
        len(pipeline.token_map.tokens),
        adapter_source=menu_adapter_source(),
        script_banks=(0xFA, 0xFA),
        extra_constants=symbols,
    )
    first = bytes((0xC9, 0x01, 0x50))
    end = bytes((0xC9, 0x69, 0x50))
    # Both the global raster dispatcher and per-cell preparation must enforce
    # the same half-open interval; one guard without the other can still let a
    # status-page stream overwrite a command row.
    assert program.code.count(first) == 2
    assert program.code.count(end) == 2


def test_command_highlight_extends_palette_without_replacing_tile_ids(pipeline):
    program = build(
        0x008000,
        0xCC00,
        {"glyphs": 0x019000, "slots": 0x01C000, "advances": 0x01C800, "operands": 0x01CB00},
        len(pipeline.token_map.tokens),
        adapter_source=menu_adapter_source(),
        script_banks=(0xFA, 0xFA),
        extra_constants=menu_adapter_constants(),
    )
    start = program.labels["menu_expand_current_palette"] - 0x008000
    end = program.labels["menu_refresh_palette"] - 0x008000
    mirror = program.code[start:end]
    assert bytes((0x29, 0xFF, 0xFB)) in mirror  # clear only palette bit $0400
    assert bytes((0xC9, 0x00, 0x01)) in mirror  # first stock tile id
    assert bytes((0xC9, 0x0A, 0x01)) in mirror  # sixth stock tile id
    assert bytes((0x9D, 0x00, 0xA0)) in mirror  # top tilemap row
    assert bytes((0x9D, 0x40, 0xA0)) in mirror  # bottom tilemap row


def test_command_selection_mirrors_the_stock_row_without_rebuilding_surface(pipeline):
    program = build(
        0x008000,
        0xCC00,
        {"glyphs": 0x019000, "slots": 0x01C000, "advances": 0x01C800, "operands": 0x01CB00},
        len(pipeline.token_map.tokens),
        adapter_source=menu_adapter_source(),
        script_banks=(0xFA, 0xFA),
        extra_constants=menu_adapter_constants(),
    )
    start = program.labels["menu_selection_update"] - 0x008000
    end = program.labels["menu_selection_done"] - 0x008000
    wrapper = program.code[start:end]
    # Stock parser owns the tilemap-upload request; the wrapper must call it
    # before mirroring the selected palette band into the expanded surface.
    assert bytes((0x22, 0xC6, 0x83, 0x81)) in wrapper
    frame_ptr = menu_adapter_constants()["MENU_FRAME_PTR"]
    assert bytes((0xAE, frame_ptr & 0xFF, frame_ptr >> 8)) in wrapper
    assert bytes((0x29, 0xFF, 0x03, 0xC9, 0x11, 0x00)) in wrapper
    assert bytes((0xAD, 0x3A, 0x0E)) in wrapper  # stock selected-row byte
    assert bytes((0x20,)) + program.labels["menu_refresh_selection"].to_bytes(3, "little")[:2] in wrapper
    assert bytes((0x20,)) + program.labels["menu_surface"].to_bytes(3, "little")[:2] not in wrapper


def test_the_fixture_rom_is_reproducible():
    from build_fixture_rom import build as build_rom  # tools/build_fixture_rom.py

    assert build_rom()["sha256"] == build_rom()["sha256"]


# --- on hardware ------------------------------------------------------------


@pytest.mark.skipif(not MESEN.exists(), reason="Mesen is not installed here")
def test_the_rom_blitter_draws_what_the_reference_draws():
    """The one test that decides whether P5 is finished."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_blitter.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    report = json.loads((ROOT / "build" / "reports" / "blitter.json").read_text())
    assert report["matching"] == report["fixtures"]
    assert report["fixtures"] >= 10
    assert report["guard"]["match"] is True
    assert report["command_frame"]["differing_words"] == []
