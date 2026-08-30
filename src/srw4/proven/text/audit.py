"""Discover and validate runtime translation targets."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import encoding
from .stock import mixed_segments


TOKEN_RE = re.compile(r"<[^>]*>")
JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")


@dataclass(frozen=True)
class Target:
    file: str
    key: str
    text: str


def _translation_fields(value, prefix: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_key = f"{prefix}.{key}" if prefix else str(key)
            if key in {"translation", "target"} and isinstance(child, str):
                yield child_key, child
            else:
                yield from _translation_fields(child, child_key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_key = f"{prefix}[{index}]"
            yield from _translation_fields(child, child_key)


def discover_targets(translations: Path) -> list[Target]:
    targets: list[Target] = []
    for path in sorted(translations.glob("*.th.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if path.name == "script.th.json":
            for key, text in data["messages"].items():
                targets.append(Target(path.name, f"messages.{key}", str(text)))
            continue

        for key, text in _translation_fields(data):
            targets.append(Target(path.name, key, text))

        # Naming labels are direct values rather than translation records.
        if path.name == "naming-screen.th.json":
            for key, text in data.get("labels", {}).items():
                targets.append(Target(path.name, f"labels.{key}", str(text)))
    return targets


def audit_targets(targets: list[Target], layout: dict) -> dict:
    failures: list[dict[str, str]] = []
    japanese: list[dict[str, str]] = []
    stock_runs = 0
    thai_segments = 0
    encoded_bytes = 0

    for target in targets:
        visible = TOKEN_RE.sub("", target.text)
        match = JAPANESE_RE.search(visible)
        if match:
            japanese.append({
                "file": target.file,
                "key": target.key,
                "character": match.group(0),
                "text": visible,
            })
        for line in visible.splitlines():
            for is_stock, segment in mixed_segments(line):
                if not segment:
                    continue
                if is_stock:
                    stock_runs += 1
                    continue
                thai_segments += 1
                try:
                    payload = encoding.encode(
                        segment,
                        layout["codes"],
                        layout.get("shorthand"),
                        layout.get("phrases"),
                    )
                    encoded_bytes += len(payload)
                except encoding.EncodingError as error:
                    failures.append({
                        "file": target.file,
                        "key": target.key,
                        "segment": segment,
                        "error": str(error),
                    })

    return {
        "targets": len(targets),
        "thai_segments": thai_segments,
        "stock_runs": stock_runs,
        "encoded_thai_bytes": encoded_bytes,
        "encode_failure_count": len(failures),
        "japanese_target_count": len(japanese),
        "encode_failures": failures,
        "japanese_targets": japanese,
    }
