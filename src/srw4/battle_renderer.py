"""Contract-driven entrypoint for the migrated battle-safe renderer source."""
from __future__ import annotations

from .battle_contract import BattleContract
from .proven.renderer65816 import BATTLE_STATE_BASE, build_renderer


def build(contract: BattleContract) -> bytes:
    inputs = dict(contract.renderer_inputs)
    return build_renderer(
        contract.renderer_pc,
        source_base=inputs["source_base"],
        advance=inputs["advance"],
        lock=inputs["lock"],
        combining={
            "mark_dx": inputs["mark_dx"],
            "mark_y": inputs["mark_y"],
            "mark_size": inputs["mark_size"],
            "base_ink": inputs["base_ink"],
            "raised_y": inputs["raised_y"],
        },
        shorthand={
            "first": inputs["shorthand_first"],
            "second": inputs["shorthand_second"],
            "third": inputs["shorthand_third"],
        },
        upper_stacks={
            "overlay": inputs["upper_overlay"],
            "dx": inputs["upper_dx"],
            "dy": inputs["upper_dy"],
            "size": inputs["upper_size"],
        },
        state_base=BATTLE_STATE_BASE,
        battle=True,
    )
