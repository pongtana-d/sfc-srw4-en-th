"""Font-editor round trip: export the atlas to BDF and read it back unchanged."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from srw4.bdf import BdfError, BdfGlyph, codepoint_for, read, safe_name, write  # noqa: E402


@pytest.fixture(scope="module")
def exported():
    from export_font import collect  # tools/export_font.py

    return collect(include_rom=True)


def test_a_single_character_keeps_its_own_codepoint():
    assert codepoint_for("char:A", 0) == ord("A")
    assert codepoint_for("char: ", 5) == ord(" ")


def test_clusters_and_icons_go_to_the_private_use_area():
    assert codepoint_for("cluster:ก", 0) == 0xE000
    assert codepoint_for("icon:B", 7) == 0xE007


def test_glyph_names_stay_ascii():
    name = safe_name("cluster:ม่")
    assert name.isascii() and " " not in name
    assert safe_name("char: ") == "char_u0020"


def test_every_exported_glyph_survives_the_round_trip(exported):
    parsed = read(write(exported, note="test"))
    assert len(parsed) == len(exported)
    for glyph in exported:
        back = parsed[glyph.codepoint]
        assert back.rows == glyph.rows, glyph.token
        assert back.advance == glyph.advance, glyph.token


def test_codepoints_do_not_collide(exported):
    codepoints = [glyph.codepoint for glyph in exported]
    assert len(set(codepoints)) == len(codepoints)


def test_the_shareable_set_holds_no_pixel_from_the_rom():
    from export_font import collect
    from srw4.atlas import AtlasBuilder
    from srw4.rom import Rom
    from srw4.tokens import TokenMap

    from export_font import CLEAN_ROM, FONT_DIR

    font_dir = FONT_DIR
    builder = AtlasBuilder(font_dir, Rom.load_clean(CLEAN_ROM).to_bytes())
    token_map = TokenMap.load(font_dir / "renewal-clusters.json")

    full = {glyph.token for glyph in collect(include_rom=True)}
    clean = {glyph.token for glyph in collect(include_rom=False)}
    assert clean < full
    # What is held back is the glyph whose image came from the ROM, not every
    # single character: most of the Latin set is drawn in thai.json and ships.
    assert full - clean == {
        token for token in token_map.tokens if builder.build(token).source == "stock"
    }


def test_a_hand_edit_is_detected(exported):
    edited = list(exported)
    original = edited[0]
    edited[0] = BdfGlyph(
        original.token, original.codepoint, original.advance, (0xFF,) + original.rows[1:]
    )
    parsed = read(write(edited, note="test"))
    assert parsed[original.codepoint].rows != original.rows


def test_a_short_bitmap_is_refused():
    text = write([BdfGlyph("char:A", 65, 8, tuple([0] * 16))], note="t")
    broken = text.replace("BITMAP\n00\n", "BITMAP\n", 1)
    with pytest.raises(BdfError, match="rows"):
        read(broken)


def test_a_bad_bitmap_row_is_refused():
    text = write([BdfGlyph("char:A", 65, 8, tuple([0] * 16))], note="t")
    with pytest.raises(BdfError, match="bad bitmap row"):
        read(text.replace("BITMAP\n00", "BITMAP\nZZ", 1))


def test_an_empty_file_is_refused():
    with pytest.raises(BdfError, match="no glyphs"):
        read("STARTFONT 2.1\nENDFONT\n")
