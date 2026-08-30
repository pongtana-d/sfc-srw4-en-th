"""Current-build entrypoint for the migrated battle stock-FB adapter."""
from __future__ import annotations

from .battle_contract import BattleAdapter
from .proven.stock_fb import build_battle_stock_fb


def build(spec: BattleAdapter) -> bytes:
    if spec.id != "stock_fb":
        raise ValueError(f"expected stock_fb adapter, got {spec.id}")
    return build_battle_stock_fb(spec.pc, spec.dependency_cpu)
