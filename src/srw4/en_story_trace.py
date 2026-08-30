"""Parse runtime byte-fetch evidence from the English story loop."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path

from .rom import RomError

LINE = re.compile(r"^frame=(\d+) ptr=([0-9A-F]{6}) byte=([0-9A-F]{2})$")


def read_trace(path: Path) -> list[dict[str, int]]:
    """Read a trace produced by ``tools/lua/story-byte-trace.lua``."""
    rows: list[dict[str, int]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        matched = LINE.fullmatch(line)
        if not matched:
            raise RomError(f"{path}:{number}: malformed story-byte trace row")
        frame, pointer, byte = matched.groups()
        rows.append({"frame": int(frame), "pointer": int(pointer, 16), "byte": int(byte, 16)})
    if not rows:
        raise RomError(f"{path}: trace has no fetches")
    return rows


def summarize_trace(rows: list[dict[str, int]]) -> dict[str, object]:
    """Return only observed discontinuities; this does not infer record bounds."""
    transitions = []
    controls = Counter()
    for previous, current in zip(rows, rows[1:]):
        if current["pointer"] == previous["pointer"] + 1:
            continue
        item = {
            "from": f"${previous['pointer'] >> 16:02X}:{previous['pointer'] & 0xFFFF:04X}",
            "lead": f"${previous['byte']:02X}",
            "to": f"${current['pointer'] >> 16:02X}:{current['pointer'] & 0xFFFF:04X}",
            "frame_from": previous["frame"],
            "frame_to": current["frame"],
        }
        transitions.append(item)
        if previous["byte"] >= 0xEC:
            controls[f"{previous['byte']:02X}"] += 1
    return {
        "fetches": len(rows),
        "nonsequential_transitions": transitions,
        "control_leads_before_transition": dict(sorted(controls.items())),
    }


def trace_report(paths: dict[str, Path]) -> dict[str, object]:
    contexts = {}
    for name, path in sorted(paths.items()):
        rows = read_trace(path)
        contexts[name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            **summarize_trace(rows),
        }
    return {
        "schema": "srw4.en-story.runtime-trace.v1",
        "authority": "Mesen execution at $C1:9763 after a genuine redraw; no record-boundary inference.",
        "contexts": contexts,
        "conclusions": [
            "FB, FC, and FA can redirect the story source pointer to another stream.",
            "FF can return from an indirect stream or precede a later source jump; it is not a standalone structural boundary rule.",
            "F7 remains an active control handler by static disassembly and must not be treated as a terminator.",
        ],
    }
