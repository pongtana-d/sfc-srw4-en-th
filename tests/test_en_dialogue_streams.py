"""Page-selection contracts for compiled EN-ROM Thai dialogue streams."""

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_dialogue_streams import compile_ordinary_text, compile_text  # noqa: E402
from srw4.en_dialogue_font import SLOT  # noqa: E402


LAYOUT = json.loads((ROOT / "data" / "font" / "encoding.json").read_text())


def test_primary_page_owns_colon_and_space_between_thai_runs():
    payload = compile_text("โคจิ: ทดสอบ<ENDFF>", LAYOUT)

    assert bytes((LAYOUT["codes"][":"], LAYOUT["codes"][" "])) in payload
    assert b"\xC2" not in payload


def test_primary_page_owns_live_latin_glyphs():
    payload = compile_text("โคจิ A<ENDFF>", LAYOUT)

    assert payload[-3:] == bytes((LAYOUT["codes"][" "], LAYOUT["codes"]["A"], 0xFF))
    assert b"\xC2" not in payload


def test_multi_letter_english_run_stays_on_the_primary_page():
    payload = compile_text("DC AEUG A-27<ENDFF>", LAYOUT)

    expected = bytes((
        0xC1, LAYOUT["codes"]["D"], LAYOUT["codes"]["C"],
        LAYOUT["codes"][" "], LAYOUT["codes"]["A"],
        LAYOUT["codes"]["E"], LAYOUT["codes"]["U"],
        LAYOUT["codes"]["G"], LAYOUT["codes"][" "],
        LAYOUT["codes"]["A"], LAYOUT["codes"]["-"],
        LAYOUT["codes"]["2"],
        LAYOUT["codes"]["7"],
        0xFF,
    ))
    assert payload == expected
    assert b"\xC2" not in payload


def test_every_visible_story_character_has_an_authored_dialogue_glyph():
    messages = json.loads(
        (ROOT / "data" / "translations" / "script.th.json").read_text()
    )["messages"]
    visible = {
        char
        for text in messages.values()
        for char in re.sub(r"<[^>]*>", "", text)
        if char not in "\r\n\t"
    }

    assert visible <= set(LAYOUT["codes"]) | set(SLOT)


def test_percent_uses_the_supplement_page_and_keeps_primary_padding_free():
    payload = compile_text("100%<ENDFF>", LAYOUT)

    assert payload[-3:] == bytes((0xC2, SLOT["%"], 0xFF))
    assert "%" not in LAYOUT["codes"]


def test_primary_dialogue_glyph_codes_do_not_overlap_controls_or_marks():
    blocks = LAYOUT["blocks"]
    codes = [LAYOUT["codes"][char] for char in LAYOUT["dialogue_primary_glyphs"]]

    assert len(codes) == len(set(codes))
    assert all(code < 0xC0 for code in codes)
    assert all(code < blocks["mark_above_base"] for code in codes)
    occupied = {
        code
        for section in ("shorthand", "phrases")
        for code in LAYOUT[section].values()
    }
    assert set(codes).isdisjoint(occupied)


def test_character_archive_stream_uses_no_dialogue_page_leads():
    payload, routes = compile_ordinary_text(
        "ภาษาไทย\nA<FB:EEC0><ENDFF>", LAYOUT
    )

    line_break = payload.index(0xF6)
    insertion = payload.index(0xFB)
    assert payload[0] == LAYOUT["codes"]["ภ"]
    assert payload[line_break + 1] == LAYOUT["codes"]["A"]
    assert all(route == 1 for route in routes[:line_break])
    assert routes[line_break] == 0
    assert routes[insertion:insertion + 4] == (0, 0, 0, 0)
    assert payload[-1] == 0xFF


def test_character_archive_lowercase_latin_uses_the_supplement_page():
    payload, routes = compile_ordinary_text("Mk-II<ENDFF>", LAYOUT)

    assert payload[1] == SLOT["k"]
    assert routes[1] == 2
    assert routes[0] == routes[2] == routes[3] == routes[4] == 1
