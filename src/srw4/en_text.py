"""Direct character encoding owned by the English ROM font page."""

from __future__ import annotations


EN_DIRECT_REVERSE = {
    **{char: 0x16 + index for index, char in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")},
    **{char: 0x90 + index for index, char in enumerate("abcdefghijklmnopqrstuvwxyz")},
    **{char: 0xB0 + index for index, char in enumerate("0123456789")},
    " ": 0x43,
    "+": 0x10,
    ",": 0x3A,
    "-": 0x60,
    "(": 0x68,
    ")": 0x69,
    ".": 0xAA,
}


def encode_en_direct(text: str) -> bytes:
    """Encode text with the active EN page, including lowercase ``$90-$A9``."""
    try:
        return bytes(EN_DIRECT_REVERSE[char] for char in text)
    except KeyError as error:
        raise ValueError(f"{error.args[0]!r} has no direct EN glyph") from error
