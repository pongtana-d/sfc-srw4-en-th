"""Precomposed-glyph contracts for compiled EN-ROM Thai dialogue streams."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_dialogue_streams import (  # noqa: E402
    PrecomposedDialogueCompiler,
    compile_ordinary_text,
    compile_text,
)
from srw4.en_dialogue_font import SLOT  # noqa: E402
from srw4.stream import decode  # noqa: E402


LAYOUT = json.loads((ROOT / "data" / "font" / "encoding.json").read_text())


def _glyph_tokens(compiler: PrecomposedDialogueCompiler, text: str) -> list[str]:
    parsed = compiler.tokenizer.tokenize(text, branch_range=range(0x10000))
    assert not parsed.issues
    return [piece.token for piece in parsed.pieces if hasattr(piece, "token")]


def test_colon_and_space_select_their_final_precomposed_cells():
    compiler = PrecomposedDialogueCompiler()
    payload = compile_text("โคจิ: ทดสอบ<ENDFF>", LAYOUT)
    expected = _glyph_tokens(compiler, "โคจิ: ทดสอบ<ENDFF>")

    assert decode(payload, compiler.token_map).tokens == expected
    assert "char::" in expected
    assert "char: " in expected


def test_live_latin_glyphs_select_their_final_precomposed_cells():
    compiler = PrecomposedDialogueCompiler()
    payload = compile_text("โคจิ A<ENDFF>", LAYOUT)

    assert decode(payload, compiler.token_map).tokens == _glyph_tokens(
        compiler, "โคจิ A<ENDFF>"
    )
    assert payload.endswith(compiler.token_map.encode_glyph("char:A") + b"\xFF")


def test_multi_letter_english_run_uses_native_direct_or_extended_codes_only():
    compiler = PrecomposedDialogueCompiler()
    payload = compile_text("DC AEUG A-27<ENDFF>", LAYOUT)
    expected = [
        "char:D", "char:C", "char: ", "char:A", "char:E", "char:U",
        "char:G", "char: ", "char:A", "char:-", "char:2", "char:7",
    ]

    assert payload == b"".join(
        compiler.token_map.encode_glyph(token) for token in expected
    ) + b"\xFF"
    assert decode(payload, compiler.token_map).tokens == expected


def test_every_visible_story_character_has_an_authored_dialogue_glyph():
    compiler = PrecomposedDialogueCompiler()
    messages = json.loads(
        (ROOT / "data" / "translations" / "script.th.json").read_text()
    )["messages"]

    for message_id, text in messages.items():
        for token in _glyph_tokens(compiler, text):
            assert token in compiler.token_map, f"{message_id}: {token}"


def test_percent_uses_its_locked_precomposed_slot():
    compiler = PrecomposedDialogueCompiler()
    payload = compile_text("100%<ENDFF>", LAYOUT)

    assert decode(payload, compiler.token_map).tokens == [
        "char:1", "char:0", "char:0", "char:%",
    ]
    assert payload.endswith(compiler.token_map.encode_glyph("char:%") + b"\xFF")


def test_direct_dialogue_glyph_codes_stop_before_the_engine_control_band():
    compiler = PrecomposedDialogueCompiler()

    assert compiler.token_map.direct_slots == 0xD0
    assert len(compiler.token_map.direct) == 0xD0
    assert all(
        len(compiler.token_map.encode_glyph(token)) == 1
        for token in compiler.token_map.direct
    )


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
