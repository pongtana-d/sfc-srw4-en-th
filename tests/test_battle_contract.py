"""The migrated battle contract must match clean and proven ROM evidence."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.battle_contract import BattleContract  # noqa: E402


CONTRACT = ROOT / "data" / "config" / "battle-contract.json"
CLEAN = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
PROVEN = ROOT / "build" / "srw4-th-test.sfc"


def test_battle_contract_matches_clean_and_proven_roms():
    contract = BattleContract.load(CONTRACT)
    contract.verify_clean(CLEAN.read_bytes())
    contract.verify_proven(PROVEN.read_bytes())


def test_battle_contract_uses_three_disjoint_private_wram_blocks():
    contract = BattleContract.load(CONTRACT)
    assert contract.private_wram == (
        ("ordinary_state", 0x7EFFA0, 0x7EFFC0),
        ("battle_state", 0x7EFFC0, 0x7EFFE0),
        ("renderer_scratch", 0x7EFFE0, 0x7F0000),
    )
