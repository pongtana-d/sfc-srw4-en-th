"""Migrated battle adapters must reproduce the proven artifacts exactly."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.battle_adapters import build_dispatch, build_width  # noqa: E402
from srw4.battle_contract import BattleContract  # noqa: E402
from srw4.battle_stock_fb import build as build_stock_fb  # noqa: E402


PROVEN = ROOT / "build" / "srw4-th-test.sfc"
CONTRACT = BattleContract.load(ROOT / "data" / "config" / "battle-contract.json")


def test_battle_stock_fb_is_byte_identical_to_proven():
    spec = next(row for row in CONTRACT.adapters if row.id == "stock_fb")
    expected = PROVEN.read_bytes()[spec.pc:spec.pc + spec.bytes]
    assert build_stock_fb(spec) == expected


def test_battle_dispatch_is_byte_identical_to_proven():
    spec = next(row for row in CONTRACT.adapters if row.id == "dispatch")
    expected = PROVEN.read_bytes()[spec.pc:spec.pc + spec.bytes]
    assert build_dispatch(spec.cpu, spec.dependency_cpu) == expected


def test_battle_width_is_byte_identical_to_proven():
    spec = next(row for row in CONTRACT.adapters if row.id == "width")
    expected = PROVEN.read_bytes()[spec.pc:spec.pc + spec.bytes]
    assert build_width(spec.cpu, spec.dependency_cpu) == expected
