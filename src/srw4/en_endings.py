"""Pinned English source contracts for the two ending crawl variants."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Mapping

from .en_text import encode_en_direct

_CONTROL = re.compile(r"<[^>]+>")
_LINE_BREAK = bytes.fromhex("F6 FC 00 01")


def _control(tag: str) -> bytes:
    if tag == "<ENDFF>":
        return b"\xFF"
    return bytes.fromhex(tag[1:-1].replace(":", ""))


def encode_source(text: str) -> bytes:
    """Encode pinned EN source including its four-byte line break."""
    payload = bytearray()
    cursor = 0
    for match in _CONTROL.finditer(text):
        payload.extend(_LINE_BREAK.join(encode_en_direct(line) for line in text[cursor:match.start()].split("\n")))
        payload.extend(_control(match.group()))
        cursor = match.end()
    payload.extend(_LINE_BREAK.join(encode_en_direct(line) for line in text[cursor:].split("\n")))
    return bytes(payload)


def load(path: Path) -> list[Mapping[str, object]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != "srw4-en-ending-narratives/1":
        raise ValueError("ending narrative schema changed")
    records = document.get("records")
    if not isinstance(records, list) or len(records) != 2:
        raise ValueError("expected exactly two EN ending narrative variants")
    return records
