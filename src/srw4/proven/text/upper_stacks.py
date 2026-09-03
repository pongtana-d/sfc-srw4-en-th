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


def build_contextual_upper_stack_assets(model: dict, layout: dict) -> dict[str, bytes]:
    """Serialize the editor's fixed upper-mark artwork for the EN renderer.

    The EN dialogue byte stream remains ``base + vowel + tone``.  The renderer
    therefore needs a lookup from the arriving mark (or vowel/tone pair) to the
    final 8x16 overlay that the font editor shows.  This intentionally carries
    both normal and left-bearing families: their pixels are already placed, so
    the runtime must never re-solve their x/y geometry.
    """
    contextual = model["contextual"]["upper_stacks"]
    normal = contextual["normal"]
    left = contextual["left"]
    keys = tuple(normal)
    if tuple(left) != keys:
        raise ValueError("contextual upper-stack families must use the same key order")
    if len(keys) > 0x20:
        raise ValueError("contextual upper stack index exceeds one family page")
    if any(len(rows) != ROWS for family in (normal, left) for rows in family.values()):
        raise ValueError("contextual upper stack must be a full 8x16 bitmap")

    codes = layout["codes"]
    index = {key: value for value, key in enumerate(keys)}
    direct = bytearray([0xFF] * 0x100)
    for key, value in index.items():
        if len(key) == 1 and key in codes:
            direct[int(codes[key])] = value

    # The 65816 renderer already classifies this exact 6 x 5 grid.  Preserve
    # its index so unsupported combinations can retain the old generic path.
    pairs = bytearray([0xFF] * PAIR_COUNT)
    for vowel_index, vowel in enumerate(UPPER_VOWELS):
        for tone_index, tone in enumerate(TONE_MARKS):
            key = vowel + tone
            if key in index:
                pairs[vowel_index * len(TONE_MARKS) + tone_index] = index[key]

    families = bytearray(0x100)
    for char in model["contextual"]["upper_left_bases"]:
        code = codes.get(char)
        if code is None:
            raise ValueError(f"upper-left base {char!r} has no encoding code")
        families[int(code)] = 1

    overlays = bytearray()
    clear = bytearray()
    sizes = bytearray()
    for family in (normal, left):
        for key in keys:
            rows = family[key]
            overlays.extend(rows)
            # A vowel is drawn before its following tone.  The two entries
            # below deliberately remove only ink which the final stack no
            # longer owns; all other stacks are additive.
            previous = family.get(key[:-1], [0] * ROWS) if len(key) > 1 else [0] * ROWS
            clear.extend(before & ~after & 0xFF for before, after in zip(previous, rows))
            height = max((row + 1 for row, bits in enumerate(rows) if bits), default=0)
            sizes.append((height << 4) | 8)

    return {
        "thai-contextual-upper-overlay.bin": bytes(overlays),
        "thai-contextual-upper-clear.bin": bytes(clear),
        "thai-contextual-upper-size.bin": bytes(sizes),
        "thai-contextual-upper-direct.bin": bytes(direct),
        "thai-contextual-upper-pairs.bin": bytes(pairs),
        "thai-contextual-upper-family.bin": bytes(families),
    }
