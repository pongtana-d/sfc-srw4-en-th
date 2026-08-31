"""Font editor draft/undo contract: edits stay in RAM until Save."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from font_editor import Draft  # noqa: E402


def _changed(rows: list[int], row: int, bit: int) -> list[int]:
    result = rows.copy()
    result[row] ^= bit
    return result


def test_contextual_edit_stays_in_memory_and_undo_restores_disk_state():
    disk_before = (ROOT / "data/font/thai.json").read_bytes()
    draft = Draft()
    original = draft.thai["contextual"]["upper_stacks"]["normal"]["ิ"].copy()

    depth = draft.put_contextual("upper", "normal", "ิ", _changed(original, 0, 0x80))
    assert depth == 1
    assert draft.dirty
    assert (ROOT / "data/font/thai.json").read_bytes() == disk_before

    result = draft.undo("stack", "ิ", "upper", "normal")
    assert result == {"changed": True, "undo_depth": 0, "dirty": False}
    assert draft.thai["contextual"]["upper_stacks"]["normal"]["ิ"] == original
    assert (ROOT / "data/font/thai.json").read_bytes() == disk_before


def test_server_history_survives_editing_another_glyph():
    draft = Draft()
    first = draft.thai["contextual"]["upper_stacks"]["normal"]["ิ"].copy()
    second = draft.thai["contextual"]["upper_stacks"]["normal"]["ี"].copy()
    draft.put_contextual("upper", "normal", "ิ", _changed(first, 0, 0x80))
    draft.put_contextual("upper", "normal", "ี", _changed(second, 1, 0x40))

    result = draft.undo("stack", "ิ", "upper", "normal")
    assert result["changed"]
    assert draft.thai["contextual"]["upper_stacks"]["normal"]["ิ"] == first
    assert draft.thai["contextual"]["upper_stacks"]["normal"]["ี"] != second
