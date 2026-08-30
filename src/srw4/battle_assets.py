"""Generate the font and geometry assets consumed by the battle renderer."""
from __future__ import annotations

import json
from pathlib import Path

from .battle_contract import BattleContract
from .proven.text.font import build_page
from .proven.text.upper_stacks import build_upper_stack_assets


ROOT = Path(__file__).resolve().parents[2]
FONT = ROOT / "data" / "proven" / "font"
MARK_PREVIEW_CODES = dict(
    zip(
        ("ั", "ิ", "ี", "ึ", "ื", "็", "่", "้", "๊", "๋", "์", "ุ", "ู"),
        (0xD6, 0xD7, 0xD8, 0xD9, 0xDF, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9),
    )
)


def preview_glyphs(model: dict) -> dict[int, bytes]:
    """Build the centered naming-screen artwork for zero-width marks."""
    result = {}
    for token, code in MARK_PREVIEW_CODES.items():
        spec = model["marks"][token]
        rows = [0] * 16
        below = token in ("ุ", "ู")
        width = int(spec["width"])
        x = max(0, (8 - width) // 2)
        sprite = [int(value) >> x for value in spec["sprite"]]
        start = 9 if below else max(2, 7 - len(sprite))
        for index, value in enumerate(sprite):
            rows[start + index] |= value
        result[code] = bytes(rows)
    return result


def build(contract: BattleContract) -> tuple[dict[str, bytes], dict[str, int]]:
    """Return generated artifacts and their contract-owned ROM PC addresses."""
    model = json.loads((FONT / "thai.json").read_text())
    layout = json.loads((FONT / "encoding.json").read_text())
    artifacts = build_page(model, layout)
    artifacts.update(build_upper_stack_assets(model, layout))
    page = bytearray(artifacts["thai-page.bin"])
    for code, glyph in preview_glyphs(model).items():
        page[code * 16:code * 16 + 16] = glyph
    artifacts["thai-page.bin"] = bytes(page)

    inputs = dict(contract.renderer_inputs)
    bank = contract.renderer_pc & ~0xFFFF
    addresses = {
        "thai-page.bin": bank | inputs["source_base"],
        "thai-advance.bin": inputs["advance"],
        "thai-mark-dx.bin": inputs["mark_dx"],
        "thai-mark-y.bin": inputs["mark_y"],
        "thai-mark-size.bin": inputs["mark_size"],
        "thai-base-ink.bin": inputs["base_ink"],
        "thai-raised-y.bin": inputs["raised_y"],
        "thai-shorthand-1.bin": inputs["shorthand_first"],
        "thai-shorthand-2.bin": inputs["shorthand_second"],
        "thai-shorthand-3.bin": inputs["shorthand_third"],
        "thai-upper-stack-overlay.bin": inputs["upper_overlay"],
        "thai-upper-stack-dx.bin": inputs["upper_dx"],
        "thai-upper-stack-dy.bin": inputs["upper_dy"],
        "thai-upper-stack-size.bin": inputs["upper_size"],
    }
    if set(addresses) != set(artifacts):
        raise ValueError("battle renderer asset set changed")
    return artifacts, addresses
