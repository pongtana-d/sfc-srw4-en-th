"""The migrated renderer source must reproduce the runtime-proven body."""

import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.battle_contract import BattleContract  # noqa: E402
from srw4.battle_renderer import build  # noqa: E402


def test_migrated_battle_renderer_is_byte_identical_to_proven():
    contract = BattleContract.load(ROOT / "data" / "config" / "battle-contract.json")
    payload = build(contract)
    proven = (ROOT / "build" / "srw4-th-test.sfc").read_bytes()
    expected = proven[contract.renderer_pc:contract.renderer_pc + contract.renderer_bytes]
    assert len(payload) == contract.renderer_bytes
    assert hashlib.sha256(payload).hexdigest() == contract.renderer_sha256
    assert payload == expected
