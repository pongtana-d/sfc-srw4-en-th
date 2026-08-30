"""Migrated font assets must equal every byte consumed by the renderer."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.battle_assets import build  # noqa: E402
from srw4.battle_contract import BattleContract  # noqa: E402


def test_battle_assets_are_byte_identical_to_proven_rom():
    contract = BattleContract.load(ROOT / "data" / "config" / "battle-contract.json")
    artifacts, addresses = build(contract)
    proven = (ROOT / "build" / "srw4-th-test.sfc").read_bytes()
    assert len(artifacts) == 14
    for name, payload in artifacts.items():
        at = addresses[name]
        assert payload == proven[at:at + len(payload)], name
