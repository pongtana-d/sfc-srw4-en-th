"""Page-selection contracts for compiled EN-ROM Thai dialogue streams."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_dialogue_font import SLOT  # noqa: E402
from srw4.en_dialogue_streams import compile_text  # noqa: E402


LAYOUT = json.loads((ROOT / "data" / "font" / "encoding.json").read_text())


def test_primary_page_owns_colon_and_space_between_thai_runs():
    payload = compile_text("โคจิ: ทดสอบ<ENDFF>", LAYOUT)

    assert bytes((LAYOUT["codes"][":"], LAYOUT["codes"][" "])) in payload
    assert b"\xC2" not in payload


def test_supplement_page_still_owns_absent_latin_glyphs():
    payload = compile_text("โคจิ A<ENDFF>", LAYOUT)

    assert bytes((0xC2, SLOT["A"])) in payload
