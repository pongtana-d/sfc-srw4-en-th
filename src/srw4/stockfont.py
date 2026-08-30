"""Recovering the game's single-byte font table from the extracted script.

`script.source.json` carries both the decoded Japanese line and its raw bytes.
Walking the two in step tells us which character each font code draws, without
anyone having to hand-maintain a table. Only records where the walk lands
exactly on the end of both sides are counted as evidence, which is what keeps
the result unambiguous.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from .text import ENGINE_FLOOR, ENGINE_OPERANDS

KANJI_LEADS = range(0xF0, 0xF6)
NEWLINE = 0xF6
UNIT = re.compile(r"<[^<>]*>|.", re.DOTALL)


def split_units(text: str) -> list[str]:
    """Split a decoded line into escapes and single characters."""
    return UNIT.findall(text)


def derive_table(messages: list[dict]) -> tuple[dict[int, str], dict]:
    """Return code -> character, plus a small report about the derivation."""
    counts: dict[int, Counter] = defaultdict(Counter)
    skipped = 0

    for message in messages:
        data = bytes.fromhex(message["source_hex"])
        pieces = split_units(message["source"])
        index = piece = 0
        learned: list[tuple[int, str]] = []
        aligned = True

        while index < len(data) and piece < len(pieces):
            byte = data[index]
            unit = pieces[piece]

            if byte in KANJI_LEADS:
                if unit.startswith("<"):
                    aligned = False
                    break
                index += 2
                piece += 1
            elif byte == NEWLINE:
                if unit != "\n":
                    aligned = False
                    break
                index += 1
                piece += 1
            elif byte >= ENGINE_FLOOR:
                if not unit.startswith("<"):
                    aligned = False
                    break
                index += 1 + ENGINE_OPERANDS.get(byte, 0)
                piece += 1
            elif unit.startswith("<"):
                aligned = False
                break
            else:
                learned.append((byte, unit))
                index += 1
                piece += 1

        if not aligned or index != len(data) or piece != len(pieces):
            skipped += 1
            continue
        for byte, unit in learned:
            counts[byte][unit] += 1

    table = {code: counter.most_common(1)[0][0] for code, counter in counts.items()}
    ambiguous = {
        code: dict(counter.most_common(4))
        for code, counter in counts.items()
        if len(counter) > 1
    }
    report = {
        "messages_used": len(messages) - skipped,
        "messages_skipped": skipped,
        "codes_seen": len(table),
        "ambiguous": {f"{code:#04x}": rows for code, rows in sorted(ambiguous.items())},
        "hits": {f"{code:#04x}": counts[code].most_common(1)[0][1] for code in sorted(counts)},
    }
    return table, report
