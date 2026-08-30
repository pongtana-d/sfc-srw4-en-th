"""English labels for the title-screen OPTION menu and the encyclopedia pages.

These screens are script records in catalog ``$CC:E9BD`` whose control bytes are
not reverse engineered, so each record keeps every byte except the visible
Japanese words.  The catalog cannot relocate — the intro overlay recognises its
crawl pages by their ``$CC`` source pointers — so the records are rebuilt inside
the same bank; see :mod:`srw4th.records`.
"""

from __future__ import annotations

import json
from pathlib import Path

from .catalogs import Write
from .parts import build_part_name_data
from .records import build_record_config_patches
from .text.japanese import CatalogDecoder
from .text.residue import lenient_decode, read_string


POINTER_TABLE_PC = 0x0CE9BD
POINTER_TABLE_ENTRIES = 96
FREE_RUN = (0x0C4409, 0x0C4600)
PART_EFFECT_SLOTS = (6, *range(17, 38))


def _part_effect_records(root: Path, clean: bytes) -> list[dict]:
    """Derive the untouched part-effect records while retaining all controls."""
    translated = json.loads(
        (root / "translations/part-effects.th.json").read_text(encoding="utf-8")
    )["records"]
    decoder = CatalogDecoder(root / "font/jp-kanji.json")
    records: list[dict] = []
    for slot in PART_EFFECT_SLOTS:
        pointer = clean[POINTER_TABLE_PC + slot * 2] | clean[POINTER_TABLE_PC + slot * 2 + 1] << 8
        source = read_string(clean, POINTER_TABLE_PC & 0xFF0000, pointer)
        lines = source[:-1].split(b"\xF6")
        replacement = translated[str(slot)]
        if len(lines) != len(replacement):
            raise ValueError(f"part effect {slot} has changed line count")
        labels, offset = [], 0
        for original, text in zip(lines, replacement):
            labels.append({
                "offset": offset,
                "length": len(original),
                "source_hex": original.hex().upper(),
                "source": lenient_decode(decoder, original),
                "text": text,
                # The original longest line is 30 fixed cells (240 px).
                "max_width_px": 240,
            })
            offset += len(original) + 1
        records.append({
            "slot": slot,
            "pointer": f"0x{pointer:04X}",
            "source_pc": f"0x{(POINTER_TABLE_PC & 0xFF0000) + pointer:06X}",
            "source_end": f"0x{(POINTER_TABLE_PC & 0xFF0000) + pointer + len(source):06X}",
            "source_hex": source.hex().upper(),
            "labels": labels,
        })
    return records


def build_option_menu_data(
    root: Path, clean: bytes, cursor: int, *, translation_dir: Path | None = None
) -> tuple[list[Write], dict[str, object]]:
    """Rebuild the OPTION and encyclopedia records with their new labels."""
    if not FREE_RUN[0] <= cursor < FREE_RUN[1]:
        raise ValueError(f"option menu cursor {cursor:#08x} is outside the verified run")
    pools = [{"start": cursor, "end": FREE_RUN[1], "kind": "verified-ff"}]
    translations = translation_dir or root / "translations"
    text = json.loads((translations / "option-menu.th.json").read_text(encoding="utf-8"))
    part_root = root if translation_dir is None else translation_dir.parent
    text["records"].extend(_part_effect_records(part_root, clean))
    writes, report = build_record_config_patches(root, clean, text, "option-menu", pools)

    # Slots 7–16 intentionally share the range-extension description in slot
    # 6.  Repoint every alias to its single rebuilt record rather than wasting
    # the scarce $CC free run on ten identical copies.
    slot6 = next(record for record in report["records"] if record["slot"] == 6)
    pointer = int(str(slot6["pointer"]), 0).to_bytes(2, "little")
    for slot in range(7, 17):
        writes.append(Write(POINTER_TABLE_PC + slot * 2, pointer, f"option-menu-slot-{slot}", False))
    name_writes, name_report = build_part_name_data(root, clean)
    writes.extend(name_writes)
    run = next(pool for pool in report["pools"] if pool["kind"] == "verified-ff")
    return writes, {
        **report,
        "part_names": name_report,
        "run": f"0x{FREE_RUN[0]:06X}-0x{FREE_RUN[1]:06X}",
        "run_end": run["start"],
    }
