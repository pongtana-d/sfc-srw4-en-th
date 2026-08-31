#!/usr/bin/env python3
"""Synchronize literal dialogue speaker labels with reviewed pilot catalogs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TRANS = ROOT / "data" / "translations"
CONTROL_PREFIX = re.compile(r"^(?:<[^>]+>)*")
JP_SPEAKER = re.compile(r"([^「\n]+)「")
TH_SPEAKER = re.compile(r"^((?:<[^>]+>)*)([^:\n]*):")


def canonical(value: str) -> str:
    return value.replace("－", "ー").replace("＝", "=").replace("・", "=")


def labels() -> dict[str, str]:
    result: dict[str, str] = {}
    # Full labels are useful when the script prints a full name.  Short-name
    # records override exact duplicates because they are the battle/dialogue
    # display authority.
    for filename in ("pilots.th.json", "pilot-short-names.th.json"):
        for row in json.loads((TRANS / filename).read_text(encoding="utf-8")):
            source = str(row.get("source", ""))
            translation = str(row.get("translation", ""))
            if source and translation and not translation.startswith("<"):
                result[canonical(source)] = translation
    return result


def source_key(source: str, catalog: dict[str, str]) -> str | None:
    visible = CONTROL_PREFIX.sub("", source)
    match = JP_SPEAKER.match(visible)
    if not match:
        return None
    speaker = match.group(1).strip()
    key = canonical(speaker)
    if key in catalog:
        return key
    # Some extracted records retain a one/two-character portrait selector
    # before an ideographic space, e.g. ``ダ　ライザ``.
    if "　" in speaker:
        prefix, remainder = speaker.split("　", 1)
        alternate = canonical(remainder)
        if len(prefix) <= 2 and alternate in catalog:
            return alternate
    # A few malformed source rows concatenate the portrait selector directly
    # with the name (for example ``ｒⅡ香月``).  Accept only a very short
    # non-Japanese prefix and an exact catalog suffix.
    for candidate in sorted(catalog, key=len, reverse=True):
        if not key.endswith(candidate):
            continue
        prefix = key[: -len(candidate)]
        if prefix and len(prefix) <= 3 and not re.search(r"[一-龯ぁ-んァ-ヶー]", prefix):
            return candidate
    return None


def baseline_aliases(
    rows: list[dict], catalog: dict[str, str]
) -> dict[str, set[str]]:
    """Learn legacy spellings from the version being corrected, not by guess."""
    raw = subprocess.check_output(
        ["git", "show", "HEAD:data/translations/script.th.json"], cwd=ROOT
    )
    baseline = json.loads(raw)["messages"]
    source = {row["id"]: row["source"] for row in rows}
    aliases: dict[str, set[str]] = {}
    for message_id, thai in baseline.items():
        key = source_key(source[message_id], catalog)
        match = TH_SPEAKER.match(thai)
        if key is None or match is None:
            continue
        old = match.group(2).strip()
        if old and old != catalog[key]:
            aliases.setdefault(key, set()).add(old)
    return aliases


def replace_alias(text: str, old: str, new: str) -> str:
    if new.startswith(old):
        suffix = new[len(old) :]
        if suffix:
            return re.sub(re.escape(old) + f"(?!{re.escape(suffix)})", new, text)
    return text.replace(old, new)


def contains_jp_token(text: str, key: str) -> bool:
    """Match a catalog label without accepting a katakana-word substring."""
    left = r"(?<![ァ-ヶー])" if key and re.match(r"[ァ-ヶー]", key[0]) else ""
    right = r"(?![ァ-ヶー])" if key and re.match(r"[ァ-ヶー]", key[-1]) else ""
    return re.search(left + re.escape(key) + right, text) is not None


def audit() -> tuple[dict, list[tuple[str, str, str]]]:
    catalog = labels()
    rows = json.loads((TRANS / "script.source.json").read_text(encoding="utf-8"))["messages"]
    source = {row["id"]: row["source"] for row in rows}
    aliases = baseline_aliases(rows, catalog)
    document = json.loads((TRANS / "script.th.json").read_text(encoding="utf-8"))
    changes: list[tuple[str, str, str]] = []
    for message_id, thai in document["messages"].items():
        key = source_key(source[message_id], catalog)
        match = TH_SPEAKER.match(thai)
        if key is None or match is None:
            continue
        expected = catalog[key]
        current = match.group(2).strip()
        if current == expected:
            continue
        revised = thai[: match.start(2)] + expected + thai[match.end(2) :]
        document["messages"][message_id] = revised
        changes.append((message_id, current, expected))

    # Reuse the same source-bound aliases inside utterances.  Only maximal
    # Japanese keys are eligible, preventing e.g. ``ルー`` from matching
    # inside ``ルーザ``.  If another source key deliberately translates to
    # the old form, leave the ambiguous sentence for manual review.
    for message_id, thai in document["messages"].items():
        jp = canonical(source[message_id])
        label_match = re.match(r"^((?:<[^>]+>)*[^:\n]*:)(.*)$", thai, re.DOTALL)
        label = label_match.group(1) if label_match else ""
        body = label_match.group(2) if label_match else thai
        present_catalog = [key for key in catalog if contains_jp_token(jp, key)]
        present = [key for key in aliases if key in present_catalog]
        maximal = [
            key
            for key in present
            if not any(key in other for other in present_catalog if len(other) > len(key))
        ]
        revised = body
        for key in maximal:
            if key == "ロザミア" and "ロザミー" in jp:
                continue
            expected = catalog[key]
            for old in aliases[key]:
                # One-syllable Thai forms occur inside ordinary words
                # (e.g. บาน in สาบาน).  Handle those few cases manually.
                if len(old) < 4:
                    continue
                protected = any(
                    other != key and contains_jp_token(jp, other) and translated == old
                    for other, translated in catalog.items()
                )
                if not protected:
                    revised = replace_alias(revised, old, expected)
        if revised != body:
            document["messages"][message_id] = label + revised
            changes.append((message_id, body, revised))
    return document, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    document, changes = audit()
    print(f"speaker-label corrections: {len(changes)}")
    if args.verbose:
        for message_id, old, new in changes:
            print(f"{message_id}: {old} -> {new}")
    if args.write and changes:
        (TRANS / "script.th.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 1 if changes and not args.write else 0


if __name__ == "__main__":
    raise SystemExit(main())
