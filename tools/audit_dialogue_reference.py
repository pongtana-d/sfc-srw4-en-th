#!/usr/bin/env python3
"""Audit dialogue against the complete generated translation reference.

This is a strict review aid, not a pass/fail test: ordinary terms may be translated
idiomatically.  Names and proper nouns in the report should normally be corrected.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TRANS = ROOT / "data" / "translations"
DASHES = str.maketrans({"－": "ー"})
STRICT_CATEGORIES = {"pilots", "pilot_labels", "units", "weapons", "series"}
STRICT_GLOSSARY_GROUPS = {
    "characters",
    "battle_labels",
    "organisations",
    "mecha",
    "canonical_full_mecha",
    "ships",
    "places",
}
sys.path.insert(0, str(ROOT / "tools"))

from build_dialogue_reference import build  # noqa: E402


def compact_source(value: str) -> str:
    return re.sub(r"\s+", "", value).translate(DASHES)


def is_katakana(character: str) -> bool:
    return "ァ" <= character <= "ヶ" or character == "ー"


def is_kana(character: str) -> bool:
    return "ぁ" <= character <= "ん" or is_katakana(character)


def has_source_key(source: str, key: str) -> bool:
    """Match an already compacted key without accepting a kana-word substring."""
    start = source.find(key)
    while start >= 0:
        end = start + len(key)
        left_ok = not (key and is_kana(key[0]) and start and is_kana(source[start - 1]))
        right_ok = not (
            key
            and is_kana(key[-1])
            and end < len(source)
            and is_kana(source[end])
        )
        if left_ok and right_ok:
            return True
        start = source.find(key, start + 1)
    return False


def contains_rendered_term(translation: str, expected: str) -> bool:
    """Treat ROM line wrapping as layout, not a glossary spelling mismatch."""
    compact = re.sub(r"\s+", "", translation)
    return re.sub(r"\s+", "", expected) in compact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=2)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    glossary = {}
    for source, entry in build()["lookup"].items():
        origins = entry["origins"]
        strict = any(origin in STRICT_CATEGORIES for origin in origins) or any(
            origin.startswith("glossary.")
            and origin.removeprefix("glossary.") in STRICT_GLOSSARY_GROUPS
            for origin in origins
        )
        if strict:
            glossary[compact_source(source)] = (source, str(entry["translation"]))
    thai = json.loads((TRANS / "script.th.json").read_text(encoding="utf-8"))["messages"]
    source_rows = json.loads((TRANS / "script.source.json").read_text(encoding="utf-8"))["messages"]
    missing: dict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(list)
    for row in source_rows:
        message_id, source = row["id"], row["source"]
        compact = compact_source(source)
        translation = thai[message_id]
        for search_key, (key, expected) in glossary.items():
            if has_source_key(compact, search_key) and not contains_rendered_term(translation, expected):
                missing[(key, expected)].append((message_id, source, translation))

    total = sum(len(rows) for rows in missing.values())
    print(f"strict dialogue-reference mismatches: {total} uses in {len(missing)} groups")
    ordered = sorted(missing.items(), key=lambda item: (-len(item[1]), item[0][0]))
    for (key, expected), rows in ordered[: args.limit]:
        print(f"\n{key} -> {expected}: {len(rows)}")
        for message_id, source, translation in rows[: args.samples]:
            print(f"  {message_id} JP: {source.replace(chr(10), ' / ')}")
            print(f"  {message_id} TH: {translation.replace(chr(10), ' / ')}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
