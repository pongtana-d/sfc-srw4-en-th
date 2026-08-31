"""Translator-facing dialogue reference stays complete and reproducible."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from build_dialogue_reference import OUTPUT, build  # noqa: E402
from audit_dialogue_glossary import compact_source, has_source_key  # noqa: E402


def test_dialogue_reference_is_current():
    assert json.loads(OUTPUT.read_text(encoding="utf-8")) == build()


def test_dialogue_reference_contains_every_required_category():
    document = build()
    categories = document["categories"]
    assert set(categories) == {
        "pilots",
        "pilot_labels",
        "units",
        "weapons",
        "series",
        "terrain",
        "glossary",
    }
    assert len(document["lookup"]) > 1_000


def test_hiragana_catalog_name_is_not_matched_inside_an_ordinary_word():
    assert not has_source_key(compact_source("記憶しておきます"), compact_source("した"))


def test_full_width_dash_and_long_vowel_mark_resolve_to_the_same_key():
    assert has_source_key(compact_source("アムロ－"), compact_source("アムロー"))
