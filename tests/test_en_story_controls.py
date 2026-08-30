"""EN control dispatch must come from the locked ROM, not an assumed grammar."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_story_controls import story_control_contract  # noqa: E402


def test_english_story_control_table_has_the_observed_handler_shape():
    rom = (ROOT / "rom" / "Dai-4-ji Super Robot Taisen English.sfc").read_bytes()
    document = story_control_contract(rom)
    assert document["byte_classes"][2] == {
        "range": "$F0-$F4", "kind": "inline-control", "operand_bytes": 1
    }
    assert document["dispatch"] == [
        {"lead": "$F5", "handler": "$C1:FFC0", "inline_operand_policy": "handler-defined; do not consume speculatively"},
        {"lead": "$F6", "handler": "$C1:92C4", "inline_operand_policy": "handler-defined; do not consume speculatively"},
        {"lead": "$F7", "handler": "$C1:92C7", "inline_operand_policy": "handler-defined; do not consume speculatively"},
        {"lead": "$F8", "handler": "$C1:92DF", "inline_operand_policy": "handler-defined; do not consume speculatively"},
        {"lead": "$F9", "handler": "$C1:9315", "inline_operand_policy": "handler-defined; do not consume speculatively"},
        {"lead": "$FA", "handler": "$C1:9369", "inline_operand_policy": "handler-defined; do not consume speculatively"},
        {"lead": "$FB", "handler": "$C1:9381", "inline_operand_policy": "handler-defined; do not consume speculatively"},
        {"lead": "$FC", "handler": "$C1:93AE", "inline_operand_policy": "handler-defined; do not consume speculatively"},
        {"lead": "$FD", "handler": "$C1:93BB", "inline_operand_policy": "handler-defined; do not consume speculatively"},
        {"lead": "$FE", "handler": "$C1:947B", "inline_operand_policy": "handler-defined; do not consume speculatively"},
        {"lead": "$FF", "handler": "$C1:94DC", "inline_operand_policy": "handler-defined; do not consume speculatively"},
    ]
