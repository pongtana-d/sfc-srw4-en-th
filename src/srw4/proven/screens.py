"""Thai text for the field screens in catalog ``$CC:8E88``.

Deployment, battle results, spirit points and the sound test are screen scripts
whose control bytes are not reverse engineered, so each record keeps every byte
except the visible Japanese words; see :mod:`srw4th.records`.

The catalog stays where it is.  Records grow, but the Intermission catalog left
this bank and the pool it released is the space they grow into -- the adapter
is handed that span rather than finding it, so the two cannot disagree about
who owns those bytes.

The boot warning and the character-picker grids are left in Japanese: the
warning by the user's decision, and a picker because turning it Thai means
replacing the key table and the input mapping, not the words on it.
"""

from __future__ import annotations

import json
from pathlib import Path

from .catalogs import Write
from .records import build_record_config_patches, build_record_patches


POINTER_TABLE_PC = 0x0C8E88
POINTER_TABLE_ENTRIES = 240
# A run shorter than the smallest record is only fragmentation.
MINIMUM_SPAN = 16


def free_spans(clean: bytes, current: bytes, released: tuple[int, int]) -> list[dict]:
    """Split the released pool around bytes an earlier adapter already wrote.

    Main-menu and protagonist fields were patched into records that have since
    moved out of this bank.  Those writes are dead, but they are still bytes
    that differ from the clean ROM, and every write here asserts clean source
    bytes -- so the pool is offered as the runs that are still untouched.
    """
    start, end = released
    spans: list[dict] = []
    cursor = start
    while cursor < end:
        if clean[cursor] != current[cursor]:
            cursor += 1
            continue
        stop = cursor
        while stop < end and clean[stop] == current[stop]:
            stop += 1
        if stop - cursor >= MINIMUM_SPAN:
            spans.append({"start": cursor, "end": stop, "kind": "released-intermission"})
        cursor = stop
    return spans


def build_screens_data(
    root: Path, clean: bytes, current: bytes, released: tuple[int, int],
    *, translation_path: Path | None = None,
) -> tuple[list[Write], dict[str, object]]:
    """Rebuild the field-screen records with their Thai labels."""
    start, end = released
    if end <= start:
        raise ValueError("screens: the released pool is empty")
    pools = free_spans(clean, current, released)
    if not pools:
        raise ValueError("screens: the released pool has no untouched run left")
    if translation_path is None:
        writes, report = build_record_patches(
            root, clean, "translations/screens.th.json", "screens", pools
        )
    else:
        text = json.loads(translation_path.read_text(encoding="utf-8"))
        writes, report = build_record_config_patches(
            root, clean, text, "screens", pools
        )
    used = [item for item in report["pools"] if item["kind"] == "released-intermission"]
    return writes, {
        **report,
        "released_pool": f"0x{start:06X}-0x{end:06X}",
        "usable_runs": len(pools),
        "usable_bytes": sum(item["end"] - item["start"] for item in pools),
        "pool_ends": [item["start"] for item in used],
    }
