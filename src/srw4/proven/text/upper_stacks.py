"""Precomputed geometry for Thai above-vowel plus tone-mark stacks.

Text and save data keep their normal ``base + vowel + tone`` bytes.  The
renderer uses these pair records only when the tone arrives, anchoring its
overlay to the vowel's final position instead of solving the second layer from
the pixels already in VRAM.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import encoding as enc


UPPER_VOWELS = tuple(enc.ABOVE_VOWELS)
TONE_MARKS = tuple(enc.TONE_MARKS)
PAIR_COUNT = len(UPPER_VOWELS) * len(TONE_MARKS)
ROWS = 16


@dataclass(frozen=True)
class UpperStack:
    vowel: str
    tone: str
    index: int
    dx: int
    dy: int
    width: int
    height: int
    overlay: bytes


def stack_index(vowel: str, tone: str) -> int:
    return UPPER_VOWELS.index(vowel) * len(TONE_MARKS) + TONE_MARKS.index(tone)


def upper_stack(model: dict, vowel: str, tone: str) -> UpperStack:
    """Return the tone overlay's fixed position relative to its upper vowel."""
    vowel_spec = model["marks"][vowel]
    tone_spec = model["marks"][tone]
    vowel_x = -int(vowel_spec["width"]) + int(vowel_spec["dx"])
    tone_x = -int(tone_spec["width"]) + int(tone_spec["dx"])
    tone_y = int(model["raised_rows"][tone])
    overlay = bytes(tone_spec["sprite"]) + bytes(ROWS - len(tone_spec["sprite"]))
    return UpperStack(
        vowel=vowel,
        tone=tone,
        index=stack_index(vowel, tone),
        dx=tone_x - vowel_x,
        dy=tone_y - int(vowel_spec["y"]),
        width=int(tone_spec["width"]),
        height=int(tone_spec["height"]),
        overlay=overlay,
    )


def build_upper_stack_assets(model: dict, layout: dict) -> dict[str, bytes]:
    """Build the 30 pair overlays and their signed relative-position tables."""
    codes = layout["codes"]
    for index, token in enumerate(UPPER_VOWELS):
        if codes[token] != enc.MARK_ABOVE_BASE + index:
            raise ValueError("upper-stack vowel codes are not contiguous")
    for index, token in enumerate(TONE_MARKS):
        if codes[token] != enc.MARK_TONE_BASE + index:
            raise ValueError("upper-stack tone codes are not contiguous")

    stacks = [
        upper_stack(model, vowel, tone)
        for vowel in UPPER_VOWELS
        for tone in TONE_MARKS
    ]
    if [item.index for item in stacks] != list(range(PAIR_COUNT)):
        raise ValueError("upper-stack pair order is not contiguous")
    return {
        "thai-upper-stack-overlay.bin": b"".join(item.overlay for item in stacks),
        "thai-upper-stack-dx.bin": bytes(item.dx & 0xFF for item in stacks),
        "thai-upper-stack-dy.bin": bytes(item.dy & 0xFF for item in stacks),
        "thai-upper-stack-size.bin": bytes(
            (item.height << 4) | item.width for item in stacks
        ),
    }
