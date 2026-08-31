#!/usr/bin/env python3
"""Report dialogue whose Japanese source uses a glossary key but Thai omits its canonical form.

This is a strict review aid, not a pass/fail test: ordinary terms may be translated
idiomatically.  Names and proper nouns in the report should normally be corrected.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TRANS = ROOT / "data" / "translations"


def leaves(node: object) -> dict[str, str]:
    result: dict[str, str] = {}
    if not isinstance(node, dict):
        return result
    for key, value in node.items():
        if key.startswith("_"):
            continue
        if isinstance(value, str):
            result[key] = value
        elif isinstance(value, dict):
            result.update(leaves(value))
    return result


def has_source_key(source: str, key: str) -> bool:
    source = re.sub(r"\s+", "", source)
    key = re.sub(r"\s+", "", key)
    left = r"(?<![ァ-ヶー])" if key and re.match(r"[ァ-ヶー]", key[0]) else ""
    right = r"(?![ァ-ヶー])" if key and re.match(r"[ァ-ヶー]", key[-1]) else ""
    return re.search(left + re.escape(key) + right, source) is not None


def contains_rendered_term(translation: str, expected: str) -> bool:
    """Treat ROM line wrapping as layout, not a glossary spelling mismatch."""
    compact = re.sub(r"\s+", "", translation)
    return re.sub(r"\s+", "", expected) in compact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=2)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    glossary = leaves(json.loads((TRANS / "glossary.th.json").read_text(encoding="utf-8")))
    thai = json.loads((TRANS / "script.th.json").read_text(encoding="utf-8"))["messages"]
    source_rows = json.loads((TRANS / "script.source.json").read_text(encoding="utf-8"))["messages"]
    missing: dict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(list)
    for row in source_rows:
        message_id, source = row["id"], row["source"]
        translation = thai[message_id]
        for key, expected in glossary.items():
            if has_source_key(source, key) and not contains_rendered_term(translation, expected):
                missing[(key, expected)].append((message_id, source, translation))

    total = sum(len(rows) for rows in missing.values())
    print(f"strict glossary mismatches: {total} uses in {len(missing)} groups")
    ordered = sorted(missing.items(), key=lambda item: (-len(item[1]), item[0][0]))
    for (key, expected), rows in ordered[: args.limit]:
        print(f"\n{key} -> {expected}: {len(rows)}")
        for message_id, source, translation in rows[: args.samples]:
            print(f"  {message_id} JP: {source.replace(chr(10), ' / ')}")
            print(f"  {message_id} TH: {translation.replace(chr(10), ' / ')}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
