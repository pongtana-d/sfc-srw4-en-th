#!/usr/bin/env python3
"""P3 — byte-code layout and codec for the combining Thai font.

Codes are laid out in contiguous class blocks so the 65816 renderer can decide
what a byte is with plain range compares instead of a 256-byte lookup:

    code <  MARK_ABOVE_BASE   spacing glyph — advance from the attribute table
    code <  MARK_TONE_BASE    above mark, first level    (advance 0)
    code <  MARK_BELOW_BASE   tone mark, rides above a vowel when present
    code <  CONTROL_BASE      below mark                 (advance 0)
    code >= CONTROL_BASE      control byte, untouched

`$EC`-`$FF` stay exactly as `tools/jp_script.py` documents them: MAP/B/P icons,
kanji page leads, line break, terminators and the `FB`/`FC` runtime macros.
The layout leaves the block boundaries as round constants so the assembly can
hard-code them.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from .stock import STOCK_REUSED_GLYPHS

ROOT = Path(__file__).resolve().parents[4] / "data" / "proven"
MODEL = ROOT / "font" / "thai.json"
ENCODING = ROOT / "font" / "encoding.json"
SHORTHAND = ROOT / "font" / "shorthand.json"
ICONS = ROOT / "font" / "icons.json"

# Phrase shorthands use the same one-byte expansion mechanism as cluster
# shorthand.  The first three are deliberately prefixes rather than whole words: the
# renderer can expand three glyph codes per byte, so ``เลเ`` + ``วล``
# spells ``เลเวล`` in two bytes, while ``กำ`` + ``ลั`` + ``ง`` + ``ใ`` +
# ``จ`` spells ``กำลังใจ`` in five.  The line break between them then brings the
# complete unit-status label back to the original eight-byte span. ``ช่`` keeps
# that base and its tone mark in one renderer call: the yes/no selector prepares
# a tilemap entry per source byte, and a separate mark byte would replace the
# base's spill cell before the mark renderer could reuse it.
PHRASE_DEFINITIONS = (
    {"text": "เลเ", "expansion": ["เ", "ล", "เ"]},
    {"text": "วล", "expansion": ["ว", "ล"]},
    {"text": "กำ", "expansion": ["ก", "ำ"]},
    {"text": "ช่", "expansion": ["ช", "่"]},
)

CONTROL_BASE = 0xEC
# Codes that name a glyph in the stock font rather than one on this page; the
# classifier hands them back to the stock renderer.  They sit in the tail of the
# below-mark block because that block is the emptiest — two of ten spare slots.
# They cannot come out of $30-$39: those are the digit codes the menu pokes, so
# a parenthesis put there is indistinguishable from a runtime '0' or '1'.
PASSTHROUGH_BASE = 0xEA
MARK_BELOW_BASE = 0xE0
MARK_TONE_BASE = 0xDA
MARK_ABOVE_BASE = 0xD0

SPACE = 0x00

# The menu writes runtime numbers by poking these codes directly, so whatever
# page is active has to keep the stock digit glyphs there.  Skipping them costs
# nothing — the spacing block has over a hundred slots to spare.
RESERVED_SPACING = frozenset(range(0x30, 0x3A))

# Thai text order inside a cluster: base, then below-or-above vowel, then tone.
ABOVE_VOWELS = "ัิีึื็"
TONE_MARKS = "่้๊๋์"
BELOW_VOWELS = "ุู"

CONSONANTS = "กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรฤลฦวศษสหฬอฮ"
SPACING_VOWELS = "ะาำเแโใไๅๆ์ฯ"  # ์ is handled as a tone mark; kept out below


class EncodingError(ValueError):
    """Raised when text cannot be represented on the Thai page."""


def clusters(text: str) -> list[str]:
    """Split text into base+marks clusters."""
    result: list[str] = []
    current = ""
    for char in text:
        if unicodedata.category(char).startswith("M"):
            if not current:
                raise EncodingError(f"combining mark {char!r} with no base")
            current += char
        else:
            if current:
                result.append(current)
            current = char
    if current:
        result.append(current)
    return result


def validate_cluster(cluster: str) -> None:
    """Reject mark orders the renderer cannot draw."""
    base, marks = cluster[0], cluster[1:]
    if base in ABOVE_VOWELS or base in TONE_MARKS or base in BELOW_VOWELS:
        raise EncodingError(f"{cluster!r}: cluster starts with a combining mark")
    seen_above = seen_below = seen_tone = False
    for mark in marks:
        if mark in BELOW_VOWELS:
            if seen_below:
                raise EncodingError(f"{cluster!r}: two below vowels")
            if seen_tone:
                raise EncodingError(f"{cluster!r}: below vowel after a tone mark")
            seen_below = True
        elif mark in ABOVE_VOWELS:
            if seen_above:
                raise EncodingError(f"{cluster!r}: two above vowels")
            if seen_tone:
                raise EncodingError(f"{cluster!r}: above vowel after a tone mark")
            seen_above = True
        elif mark in TONE_MARKS:
            if seen_tone:
                raise EncodingError(f"{cluster!r}: two tone marks")
            seen_tone = True
        else:
            raise EncodingError(f"{cluster!r}: {mark!r} is not a known mark")


def load_icons() -> dict:
    """The fixed-width artwork that shares the page with the letters."""
    if not ICONS.exists():
        return {"advance": 8, "glyphs": {}}
    return json.loads(ICONS.read_text())


def load_shorthand() -> list[str]:
    """The clusters that get a byte of their own, or none if not built yet."""
    if not SHORTHAND.exists():
        return []
    return list(json.loads(SHORTHAND.read_text())["clusters"])


def load_phrase_definitions() -> list[dict[str, object]]:
    """Fixed phrase prefixes that share the shorthand byte page."""
    if not SHORTHAND.exists():
        return [dict(item) for item in PHRASE_DEFINITIONS]
    raw = json.loads(SHORTHAND.read_text())
    return list(raw.get("phrases", PHRASE_DEFINITIONS))


def assign(model: dict, shorthand: list[str] | None = None) -> dict:
    """Lay the model's glyphs out over the byte page."""
    bases = model["bases"]
    marks = model["marks"]

    above = [m for m in ABOVE_VOWELS if m in marks]
    tones = [m for m in TONE_MARKS if m in marks]
    below = [m for m in BELOW_VOWELS if m in marks]

    if len(above) > MARK_TONE_BASE - MARK_ABOVE_BASE:
        raise EncodingError("too many above vowels for the reserved block")
    if len(tones) > MARK_BELOW_BASE - MARK_TONE_BASE:
        raise EncodingError("too many tone marks for the reserved block")
    if len(below) > PASSTHROUGH_BASE - MARK_BELOW_BASE:
        raise EncodingError("too many below vowels for the reserved block")

    codes: dict[str, int] = {" ": SPACE}

    # Spacing glyphs run from $01 upward, consonants first so the common case
    # sits in one tight range, then vowels, then Latin/digits/punctuation.
    ordered: list[str] = []
    for group in (CONSONANTS, "".join(c for c in SPACING_VOWELS if c not in TONE_MARKS)):
        ordered.extend(char for char in group if char in bases)
    ordered.extend(
        token
        for token in sorted(bases)
        if token not in ordered and token != " " and token not in STOCK_REUSED_GLYPHS
    )
    # The terrain badges are not letters and never combine, but they are drawn
    # from this page and so need codes on it.  They go before the shorthand
    # because artwork cannot be re-derived from other codes the way a cluster
    # can — if the block ever runs short, it is a shorthand that gives way.
    ordered.extend(load_icons()["glyphs"])

    cursor = SPACE + 1
    for token in ordered:
        while cursor in RESERVED_SPACING:
            cursor += 1
        if cursor >= MARK_ABOVE_BASE:
            raise EncodingError(
                f"spacing glyphs overflow the page at {token!r} "
                f"({len(ordered)} glyphs, {MARK_ABOVE_BASE - 1} slots)"
            )
        codes[token] = cursor
        cursor += 1
    spacing_end = cursor

    # Marks take fixed codes above the spacing block, so they can be laid down
    # before the shorthand — which needs to look every one of its characters up.
    for index, mark in enumerate(above):
        codes[mark] = MARK_ABOVE_BASE + index
    for index, mark in enumerate(tones):
        codes[mark] = MARK_TONE_BASE + index
    for index, mark in enumerate(below):
        codes[mark] = MARK_BELOW_BASE + index

    # Shorthand codes sit in the tail of the same block, so the renderer only
    # needs `code < MARK_ABOVE_BASE` to know a byte occupies a cell — the
    # expansion itself is table-driven and needs no range at all.  Bases always
    # get first refusal: drawing a new consonant takes a slot from here, never
    # from a glyph.
    shorthand_codes: dict[str, int] = {}
    for cluster in (load_shorthand() if shorthand is None else shorthand):
        while cursor in RESERVED_SPACING:
            cursor += 1
        if cursor >= MARK_ABOVE_BASE:
            break
        if any(char not in codes for char in cluster):
            raise EncodingError(
                f"shorthand {cluster!r} uses a character with no glyph"
            )
        validate_cluster(cluster)
        shorthand_codes[cluster] = cursor
        cursor += 1

    phrase_codes: dict[str, int] = {}
    phrase_expansions: dict[str, list[str]] = {}
    for definition in load_phrase_definitions():
        text = str(definition["text"])
        expansion = [str(token) for token in definition["expansion"]]
        if not text or not expansion or len(expansion) > 3:
            raise EncodingError(f"invalid phrase shorthand {text!r}")
        for token in expansion:
            if token not in codes:
                raise EncodingError(
                    f"phrase shorthand {text!r} uses unknown token {token!r}"
                )
        while cursor in RESERVED_SPACING:
            cursor += 1
        if cursor >= MARK_ABOVE_BASE:
            break
        phrase_codes[text] = cursor
        phrase_expansions[text] = expansion
        cursor += 1

    return {
        "blocks": {
            "space": SPACE,
            "spacing_first": SPACE + 1,
            "spacing_last": spacing_end - 1,
            "mark_above_base": MARK_ABOVE_BASE,
            "mark_tone_base": MARK_TONE_BASE,
            "mark_below_base": MARK_BELOW_BASE,
            "passthrough_base": PASSTHROUGH_BASE,
            "control_base": CONTROL_BASE,
        },
        "codes": codes,
        "shorthand": shorthand_codes,
        "phrases": phrase_codes,
        "phrase_expansions": phrase_expansions,
        "free_spacing_slots": MARK_ABOVE_BASE - cursor,
    }


def encode(text: str, codes: dict[str, int],
           shorthand: dict[str, int] | None = None,
           phrases: dict[str, int] | None = None) -> bytes:
    """Encode Thai text to page bytes, validating every cluster.

    Longest match first, so a cluster with a shorthand for all three of its
    characters does not settle for the two-character one.  Phrase prefixes are
    checked before clusters because they intentionally cross base-character
    boundaries.
    """
    shorthand = shorthand or {}
    phrases = phrases or {}
    out = bytearray()

    def emit_cluster(cluster: str) -> None:
        if cluster == " ":
            out.append(SPACE)
            return
        validate_cluster(cluster)
        rest = cluster
        for width in (3, 2):
            if len(rest) < width:
                continue
            code = shorthand.get(rest[:width])
            if code is not None:
                out.append(code)
                rest = rest[width:]
                break
        for char in rest:
            code = codes.get(char)
            if code is None:
                raise EncodingError(f"{char!r} has no glyph on the Thai page")
            out.append(code)

    if not phrases:
        for cluster in clusters(text):
            emit_cluster(cluster)
        return bytes(out)

    phrase_items = sorted(
        ((str(text), int(code)) for text, code in phrases.items()),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    cursor = 0
    while cursor < len(text):
        for phrase, code in phrase_items:
            phrase_end = cursor + len(phrase)
            if (
                text.startswith(phrase, cursor)
                and (phrase_end == len(text)
                     or not unicodedata.category(text[phrase_end]).startswith("M"))
            ):
                out.append(code)
                cursor = phrase_end
                break
        else:
            cluster = clusters(text[cursor:])[0]
            emit_cluster(cluster)
            cursor += len(cluster)
    return bytes(out)


def advance_table(model: dict, layout: dict) -> bytes:
    """256-byte advance table: marks are zero, controls are zero, rest is ink+1."""
    icons = load_icons()
    table = bytearray(256)
    for token, code in layout["codes"].items():
        if code >= MARK_ABOVE_BASE:
            continue  # combining marks never advance the pen
        if token in icons["glyphs"]:
            table[code] = icons.get("advances", {}).get(token, icons["advance"])
            continue
        spec = model["bases"].get(token)
        table[code] = spec["advance"] if spec else 0
    table[SPACE] = 4
    # A shorthand moves the pen exactly as far as the base it starts with; the
    # marks it carries are zero-advance by construction.
    for cluster, code in layout.get("shorthand", {}).items():
        table[code] = table[layout["codes"][cluster[0]]]
    for phrase, code in layout.get("phrases", {}).items():
        expansion = layout.get("phrase_expansions", {}).get(phrase, [])
        table[code] = sum(table[layout["codes"][token]] for token in expansion)
    return bytes(table)


def shorthand_tables(layout: dict) -> tuple[bytes, bytes, bytes]:
    """Three 256-byte tables the renderer expands a shorthand byte through.

    Component one is zero for every code that is not a shorthand, which is the
    test itself — no range compare, and nothing to keep in step when the block
    moves because a new base was drawn.  Component three is zero when the
    cluster is only two characters long.
    """
    first, second, third = bytearray(256), bytearray(256), bytearray(256)
    def add(code: int, parts: list[int]) -> None:
        if not 1 <= len(parts) <= 3:
            raise EncodingError(f"shorthand code {code:#x} has {len(parts)} parts")
        first[code] = parts[0]
        second[code] = parts[1] if len(parts) > 1 else 0
        third[code] = parts[2] if len(parts) > 2 else 0

    for cluster, code in layout.get("shorthand", {}).items():
        add(code, [layout["codes"][char] for char in cluster])
    for phrase, code in layout.get("phrases", {}).items():
        expansion = layout.get("phrase_expansions", {}).get(phrase, [])
        add(code, [layout["codes"][token] for token in expansion])
    return bytes(first), bytes(second), bytes(third)


def main() -> None:
    model = json.loads(MODEL.read_text())
    layout = assign(model)
    payload = dict(layout)
    payload["_comment"] = (
        "Generated by srw4th.text.encoding from font/thai.json. "
        "Block boundaries are hard-coded in the renderer; do not reorder by hand."
    )
    ENCODING.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")

    blocks = layout["blocks"]
    print(f"spacing glyphs : ${blocks['spacing_first']:02X}-${blocks['spacing_last']:02X}"
          f" ({blocks['spacing_last']}) ")
    print(f"above marks    : ${blocks['mark_above_base']:02X}-"
          f"${blocks['mark_tone_base'] - 1:02X}")
    print(f"tone marks     : ${blocks['mark_tone_base']:02X}-"
          f"${blocks['mark_below_base'] - 1:02X}")
    print(f"below marks    : ${blocks['mark_below_base']:02X}-"
          f"${blocks['passthrough_base'] - 1:02X}")
    print(f"stock glyphs   : ${blocks['passthrough_base']:02X}-"
          f"${blocks['control_base'] - 1:02X}")
    print(f"shorthand      : {len(layout['shorthand'])} clusters")
    print(f"free slots     : {layout['free_spacing_slots']}")
    print(f"wrote {ENCODING.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
