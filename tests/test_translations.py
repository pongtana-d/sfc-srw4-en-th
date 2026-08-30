"""Whole-corpus audit: every translation file, not just the script."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from audit_translations import classify, walk  # noqa: E402  tools/audit_translations.py
from srw4.text import (  # noqa: E402
    Engine,
    Glyph,
    Pointer,
    Tokenizer,
    load_stock_codes,
)

FONT_DIR = ROOT / "data" / "font"


@pytest.fixture(scope="module")
def icons() -> set[str]:
    return set(json.loads((FONT_DIR / "renewal-icons.json").read_text())["glyphs"])


@pytest.fixture(scope="module")
def stock_codes() -> dict[int, str]:
    return load_stock_codes(FONT_DIR / "renewal-stock.json")


@pytest.fixture(scope="module")
def tokenizer(icons, stock_codes) -> Tokenizer:
    return Tokenizer(icons, stock_codes)


# --- walking files of every shape ------------------------------------------


def test_bookkeeping_and_originals_are_left_alone():
    tree = {
        "_comment": "ignore me",
        "source_hex": "FF FF",
        "address": "0x1234",
        "translation": "ไทย",
    }
    assert [path for path, _ in walk(tree)] == ["translation"]


def test_nesting_is_followed_and_the_path_says_where():
    tree = {"records": [{"translation": "ก"}, {"translation": "ข"}]}
    assert list(walk(tree)) == [
        ("records[0].translation", "ก"),
        ("records[1].translation", "ข"),
    ]


def test_strings_are_sorted_by_what_they_hold():
    assert classify("ไทย") == "check"
    assert classify("<FC:05>ก") == "check"
    assert classify("<F8><83>") == "check"          # escapes with no Thai still count
    assert classify("こんにちは") == "japanese original"
    assert classify("FF FE FD") == "hex dump"
    assert classify("MOV") == "ascii only"
    assert classify("   ") == "empty"


# --- telling an operand from a forgotten character --------------------------


def test_a_byte_right_after_a_command_is_flagged_as_a_suspected_operand(tokenizer):
    result = tokenizer.tokenize("<FC:05><06>ก<ENDFF>", where="t")
    assert result.foldings[0].after_command is True


def test_fc00_takes_a_second_operand_rather_than_dropping_a_character(tokenizer):
    """`$FC:00:01` prefixes every line of the opening crawl, always the same."""
    result = tokenizer.tokenize("<FC:00><01>ก<ENDFF>", where="t")
    assert result.foldings == []
    assert [p for p in result.pieces if isinstance(p, Glyph)] == [Glyph("cluster:ก")]


def test_fc07_carries_an_address_the_way_fb_0c_does(tokenizer):
    result = tokenizer.tokenize("<FC:07><44><08>ก<ENDFF>", where="t",
                                branch_range=range(0x0800, 0x0900))
    assert Pointer(0x0844, 0xFC) in result.pieces
    assert result.foldings == []


def test_the_catalog_engine_reads_f8_as_a_two_byte_command(icons, stock_codes):
    story = Tokenizer(icons, stock_codes)
    catalog = Tokenizer(icons, stock_codes, engine="catalog")
    assert story.tokenize("<F8><83>ก", where="t").foldings != []
    assert catalog.tokenize("<F8><83>ก", where="t").foldings == []


def test_a_byte_in_the_middle_of_text_is_not(tokenizer):
    result = tokenizer.tokenize("ก<06>ข<ENDFF>", where="t")
    assert result.foldings[0].after_command is False


def test_the_first_byte_of_a_record_is_not_called_an_operand(tokenizer):
    result = tokenizer.tokenize("<06>ก<ENDFF>", where="t")
    assert result.foldings[0].after_command is False


# --- the corpus itself ------------------------------------------------------


def test_no_translation_uses_a_token_the_manifest_does_not_have():
    from audit_translations import audit

    report = audit(verbose=False)
    assert report["tokens_outside_manifest"] == 0, report["findings"]["tokens_outside_manifest"][:5]


def test_every_string_the_tokenizer_reads_parses_cleanly():
    from audit_translations import audit

    report = audit(verbose=False)
    assert report["unreadable_strings"] == 0, report["findings"]["unreadable"][:5]


def test_production_census_includes_ascii_glyphs():
    from audit_translations import audit

    report = audit(verbose=False, include_ascii=True)
    assert report["include_ascii"] is True
    assert report["tokens_outside_manifest"] == 0, report["findings"]["tokens_outside_manifest"][:5]
    assert report["strings_checked"] > 11_000


def test_the_audit_actually_looks_at_most_of_the_corpus():
    from audit_translations import audit

    report = audit(verbose=False)
    assert report["files"] >= 30
    assert report["strings_checked"] > 10_000
