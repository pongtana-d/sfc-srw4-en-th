#!/usr/bin/env python3
"""Normalize strongly gendered Thai in anonymous/runtime dialogue.

A hidden/runtime speaker label is not enough to select Thai forms that assert
sex or age.  The project permits ``ฉัน`` as a neutral manga/anime convention;
genuine plural ``เรา`` is preserved.  Named speakers are handled by the
separate character-profile review.

Run without ``--write`` to audit.  ``--write`` updates ``script.th.json``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "translations" / "script.source.json"
TRANSLATION = ROOT / "data" / "translations" / "script.th.json"

CONTROL_PREFIX = re.compile(r"^(?:<[^>]+>)*")

# ``ฉัน`` is intentionally allowed: Thai manga/anime commonly uses it for
# speakers of any sex.  The other forms make a stronger gender/age claim.
THAI_PRONOUNS = re.compile(r"(?:กระผม|ดิฉัน|ผม|หนู)")
THAI_ENDINGS = re.compile(
    r"(?:เจ้าค่ะ|เจ้าคะ|เพคะ|ขอรับ|ครับ|ค่ะ|คะ|ย่ะ|(?<!แ)ฮะ)"
    r"(?=[!?？。、…\.\s<~♥]|$)"
    r"|ค่ะ(?=ที่)|คะ(?=เนี่ย)|ค่าา+(?=[!?？。、…\.\s<~♥]|$)"
)
GENDERED = re.compile(
    r"(?:กระผม|ดิฉัน|ผม|หนู)(?=[ก-๙!?？。、…\.\s<~♥]|$)"
    r"|(?:เจ้าค่ะ|เจ้าคะ|เพคะ|ขอรับ|ครับ|ค่ะ|คะ|ย่ะ|(?<!แ)ฮะ)"
    r"(?=[!?？。、…\.\s<~♥]|$)"
    r"|ค่ะ(?=ที่)|คะ(?=เนี่ย)|ค่าา+(?=[!?？。、…\.\s<~♥]|$)"
)
PRONOUN_SEQUENCE = re.compile(r"(?:กระผม|ดิฉัน|ผม|หนู|ฉัน|เรา)")
SINGULAR_PRONOUNS = {"กระผม", "ดิฉัน", "ผม", "หนู", "ฉัน"}


def anonymous(source: str) -> bool:
    """True when the Japanese record has no literal speaker name."""
    return CONTROL_PREFIX.sub("", source).startswith("「")


def normalize(text: str, source: str) -> str:
    """Remove gender claims while preserving meaning and runtime controls."""
    text = THAI_PRONOUNS.sub("ฉัน", text)
    text = THAI_ENDINGS.sub("", text)
    text = re.sub(r"[ \t]+([!?？。、…\.♥])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +\n", "\n", text)
    text = re.sub(r"\n +", "\n", text)
    text = re.sub(r" +(?=<END)", "", text)
    text = re.sub(r"\n(?=<END)", "", text)
    text = re.sub(r": +", ": ", text)
    # A bare gendered acknowledgement must not become an empty message.
    if re.fullmatch(r"(?:<[^>]+>)*:\s*(?:<END(?:F7|FF)>)", text):
        acknowledgement = "อืม" if re.search(r"「(?:ええ|はい)」", source) else "..."
        text = re.sub(r":\s*(?=<END)", f": {acknowledgement}", text)
    return text


def restore_neutral_singular(old: str, current: str) -> str:
    """Undo the earlier blanket ``ฉัน`` -> ``เรา`` migration safely.

    Pronoun occurrences are aligned with the pre-migration file.  Genuine
    plural ``เรา`` therefore stays ``เรา`` while singular forms become the
    project-approved neutral ``ฉัน``.
    """
    old_pronouns = PRONOUN_SEQUENCE.findall(old)
    current_matches = list(PRONOUN_SEQUENCE.finditer(current))
    if len(old_pronouns) != len(current_matches):
        return current
    pieces: list[str] = []
    cursor = 0
    for old_pronoun, match in zip(old_pronouns, current_matches):
        pieces.append(current[cursor : match.start()])
        pieces.append("ฉัน" if old_pronoun in SINGULAR_PRONOUNS else "เรา")
        cursor = match.end()
    pieces.append(current[cursor:])
    return "".join(pieces)


def audit() -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    source_rows = json.loads(SOURCE.read_text(encoding="utf-8"))["messages"]
    source = {str(item["id"]): str(item["source"]) for item in source_rows}
    document = json.loads(TRANSLATION.read_text(encoding="utf-8"))
    messages = document["messages"]
    baseline = json.loads(
        subprocess.check_output(
            ["git", "show", "HEAD:data/translations/script.th.json"], cwd=ROOT
        )
    )["messages"]
    changes: list[tuple[str, str, str]] = []

    for message_id, thai in messages.items():
        japanese = source[message_id]
        if not anonymous(japanese):
            continue
        revised = restore_neutral_singular(baseline[message_id], thai)
        if GENDERED.search(revised):
            revised = normalize(revised, japanese)
        if revised != thai:
            messages[message_id] = revised
            changes.append((message_id, thai, revised))
    return document, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    document, changes = audit()
    print(f"unknown-sex dialogue requiring neutral Thai: {len(changes)}")
    if args.verbose:
        for message_id, old, new in changes:
            print(f"{message_id}\n- {old.replace(chr(10), ' / ')}\n+ {new.replace(chr(10), ' / ')}")
    if args.write and changes:
        TRANSLATION.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 1 if changes and not args.write else 0


if __name__ == "__main__":
    raise SystemExit(main())
