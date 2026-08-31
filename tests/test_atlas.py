"""P3 tests: one glyph per token, and the composition rules behind them."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.atlas import (  # noqa: E402
    CELL_ROWS,
    MAX_ADVANCE,
    MIN_ADVANCE,
    STOCK_FONT_PC,
    AtlasBuilder,
    ink_box,
)
from srw4.png import write_greyscale  # noqa: E402
from srw4.tokens import EncodingError, TokenMap  # noqa: E402

FONT_DIR = ROOT / "data" / "font"
EN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen English.sfc"


@pytest.fixture(scope="module")
def rom() -> bytes:
    return EN_ROM.read_bytes()


@pytest.fixture(scope="module")
def builder(rom) -> AtlasBuilder:
    return AtlasBuilder(FONT_DIR, rom)


@pytest.fixture(scope="module")
def token_map() -> TokenMap:
    return TokenMap.load(FONT_DIR / "renewal-clusters.json")


@pytest.fixture(scope="module")
def glyphs(builder, token_map) -> dict:
    return {token: builder.build(token) for token in token_map.tokens}


# --- coverage ---------------------------------------------------------------


def test_every_token_in_the_manifest_has_a_glyph(glyphs, token_map):
    assert len(glyphs) == len(token_map.tokens)


def test_every_glyph_is_one_cell_of_sixteen_rows(glyphs):
    for glyph in glyphs.values():
        assert len(glyph.rows) == CELL_ROWS
        assert all(0 <= row <= 0xFF for row in glyph.rows)
        assert glyph.cell_span == 1


def test_advances_stay_inside_the_cell(glyphs):
    for token, glyph in glyphs.items():
        if token == "icon:Pad":
            assert glyph.advance == 0
        else:
            assert MIN_ADVANCE <= glyph.advance <= MAX_ADVANCE


def test_blank_glyphs_are_the_space_and_explicit_battle_padding(glyphs):
    blank = [token for token, glyph in glyphs.items() if glyph.ink_width == 0]
    assert blank == ["char: ", "icon:Pad"]


def test_the_atlas_fits_well_under_one_bank(glyphs):
    unique = {glyph.rows for glyph in glyphs.values()}
    assert len(unique) * CELL_ROWS < 0x10000


# --- metrics ----------------------------------------------------------------


def test_ink_box_measures_the_drawn_pixels():
    rows = tuple([0] * 4 + [0b00111000] * 3 + [0] * 9)
    left, width, top = ink_box(rows)
    assert (left, width, top) == (2, 3, 4)


def test_ink_box_of_an_empty_cell_is_zero():
    assert ink_box(tuple([0] * CELL_ROWS)) == (0, 0, 0)


def test_metrics_use_one_schema_for_every_source(glyphs):
    keys = {"advance", "ink_width", "left", "top", "cell_span", "flags"}
    for token in ("cluster:ก", "char:A", "icon:B"):
        assert set(glyphs[token].metrics()) == keys


# --- sources ----------------------------------------------------------------


def test_a_char_glyph_prefers_our_own_drawing(builder):
    ours = json.loads((FONT_DIR / "thai.json").read_text())["bases"]["A"]
    glyph = builder.build("char:A")
    assert glyph.rows == tuple(ours["rows"])
    assert glyph.advance == ours["advance"]


def test_a_char_we_never_drew_is_the_image_from_the_game_font(builder, rom):
    code = json.loads((FONT_DIR / "renewal-stock.json").read_text())["glyphs"]["\u2665"]["code"]
    start = STOCK_FONT_PC + code * CELL_ROWS
    assert builder.build("char:\u2665").rows == tuple(rom[start : start + CELL_ROWS])


def test_a_composed_cluster_keeps_every_pixel_of_its_base(builder):
    base = builder.build("cluster:ส")
    for token in ("cluster:สู", "cluster:สู้", "cluster:ส้"):
        composed = builder.build(token)
        for row, base_row in zip(composed.rows, base.rows):
            assert row & base_row == base_row


def test_sources_are_recorded_per_glyph(builder):
    assert builder.build("cluster:ก").source == "composed"
    assert builder.build("char:A").source == "drawn"
    assert builder.build("char:\u2665").source == "stock"
    assert builder.build("icon:B").source == "icon"


# --- composition rules ------------------------------------------------------


def test_a_below_mark_lands_under_the_base(builder):
    plain = builder.build("cluster:ส")
    with_mark = builder.build("cluster:สู")
    added = [i for i in range(CELL_ROWS) if with_mark.rows[i] != plain.rows[i]]
    assert min(added) > 12


def test_a_tone_mark_rises_above_an_above_vowel(builder):
    alone = builder.build("cluster:ส้")
    stacked = builder.build("cluster:สี้")
    assert stacked.top < alone.top


def test_contextual_stacks_are_used_at_their_saved_absolute_positions(builder, monkeypatch):
    normal = [0b00000001] + [0] * (CELL_ROWS - 1)
    left = [0b00000010] + [0] * (CELL_ROWS - 1)
    monkeypatch.setitem(builder.contextual["upper_stacks"]["normal"], "ี้", normal)
    monkeypatch.setitem(builder.contextual["upper_stacks"]["left"], "ี้", left)
    for token, stack in (("cluster:สี้", normal), ("cluster:ปี้", left)):
        glyph = builder.build(token)
        base = builder.bases[token.split(":", 1)[1][0]]["rows"]
        assert glyph.rows == tuple(a | b for a, b in zip(base, stack))


def test_yo_ying_uses_its_tail_cut_base_before_a_lower_vowel(builder):
    glyph = builder.build("cluster:ญู")
    cut = builder.contextual["lower_base_variants"]["ญ"]["rows"]
    lower = builder.contextual["lower_stacks"]["normal"]["ู"]
    assert glyph.rows == tuple(a | b for a, b in zip(cut, lower))


def test_a_tall_vowel_does_not_swallow_the_tone_above_it(builder):
    # "ue" starts a row higher than "uee", so a tone placed at the usual raised
    # row would merge with it and the two clusters would draw the same shape.
    assert builder.build("cluster:ซึ่").rows != builder.build("cluster:ซื่").rows


def test_marks_never_spill_outside_the_cell(builder, token_map):
    for token in token_map.tokens:
        glyph = builder.build(token)
        assert glyph.left + glyph.ink_width <= 8


def test_an_override_without_a_reason_is_refused(builder):
    builder.overrides["cluster:ก"] = {"rows": [0] * CELL_ROWS}
    try:
        with pytest.raises(EncodingError, match="reason"):
            builder.build("cluster:ก")
    finally:
        del builder.overrides["cluster:ก"]


# --- determinism ------------------------------------------------------------


def test_building_twice_gives_identical_bitmaps(builder, token_map):
    def pack() -> bytes:
        out = bytearray()
        for token in token_map.tokens:
            out += bytes(builder.build(token).rows)
        return bytes(out)

    assert hashlib.sha256(pack()).hexdigest() == hashlib.sha256(pack()).hexdigest()


def test_the_proof_sheet_is_a_valid_png(tmp_path):
    path = tmp_path / "sheet.png"
    write_greyscale(path, [[0, 128, 255], [255, 128, 0]])
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert data.endswith(b"IEND\xae\x42\x60\x82")
