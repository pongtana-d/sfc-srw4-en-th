#!/usr/bin/env python3
"""Extract every enhancement-part effect from the locked EN and JP ROMs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.proven.option_menu import (  # noqa: E402
    EN_POINTER_TABLE_PC,
    PART_EFFECT_SLOTS,
    _decode_en_part_text,
)
from srw4.proven.parts import NAMES  # noqa: E402
from srw4.proven.text.japanese import CatalogDecoder, read_catalog_string  # noqa: E402
from srw4.proven.text.residue import lenient_decode, read_string  # noqa: E402


EN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen English.sfc"
JP_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
OUTPUT = ROOT / "data" / "translations" / "part-effects.source.json"
JP_CATALOG_PC = 0x0CE9BD
DESCRIPTION_SLOTS = tuple(range(6, 38))


def _name_index(slot: int) -> int:
    """Map the ROM item id to the shared visible-name record."""
    if 6 <= slot <= 16:
        return 0  # All eleven radar grades share one name and description.
    if 17 <= slot <= 33:
        return slot - 16
    if 34 <= slot <= 37:
        return 18  # Four gold values share the same visible name.
    raise ValueError(f"part slot is outside 6..37: {slot}")


def _hex(payload: bytes) -> str:
    return payload.hex(" ").upper()


def extract(en: bytes, jp: bytes) -> dict[str, object]:
    decoder = CatalogDecoder(ROOT / "data" / "font" / "jp-kanji.json")
    bank_pc = JP_CATALOG_PC & 0xFF0000

    names: list[dict[str, object]] = []
    for index, (pc, expected, _legacy_abbreviation) in enumerate(NAMES[:-1]):
        en_raw = read_catalog_string(en, pc & 0xFF0000, pc & 0xFFFF)
        jp_raw = read_catalog_string(jp, pc & 0xFF0000, pc & 0xFFFF)
        if en_raw != jp_raw:
            raise ValueError(f"part name {index} differs between EN and JP ROMs")
        source = decoder.decode(jp_raw)
        if source != expected:
            raise ValueError(f"part name {index}: expected {expected!r}, found {source!r}")
        names.append({
            "name_index": index,
            "source_pc": f"0x{pc:06X}",
            "source": source,
            "source_hex": _hex(jp_raw),
        })

    items: list[dict[str, object]] = []
    for slot in DESCRIPTION_SLOTS:
        en_offset = EN_POINTER_TABLE_PC + slot * 2
        jp_offset = JP_CATALOG_PC + slot * 2
        en_pointer = int.from_bytes(en[en_offset:en_offset + 2], "little")
        jp_pointer = int.from_bytes(jp[jp_offset:jp_offset + 2], "little")
        name = names[_name_index(slot)]
        items.append({
            "id": slot,
            "part_name_jp_reference": name["source"],
            "name_index": name["name_index"],
            "en_effect_pointer": f"0x{en_pointer:04X}",
            "jp_effect_pointer": f"0x{jp_pointer:04X}",
        })

    effects: list[dict[str, object]] = []
    for slot in PART_EFFECT_SLOTS:
        item = next(item for item in items if item["id"] == slot)
        en_pointer = int(str(item["en_effect_pointer"]), 0)
        jp_pointer = int(str(item["jp_effect_pointer"]), 0)
        en_raw = read_string(en, EN_POINTER_TABLE_PC & 0xFF0000, en_pointer)
        jp_raw = read_string(jp, bank_pc, jp_pointer)
        aliases = [row["id"] for row in items if row["en_effect_pointer"] == item["en_effect_pointer"]]
        effects.append({
            "record": str(slot),
            "item_ids": aliases,
            "part_names_jp_reference": sorted({
                str(names[_name_index(item_id)]["source"]) for item_id in aliases
            }),
            "en_active": {
                "pointer": f"0x{en_pointer:04X}",
                "source_pc": f"0x{(EN_POINTER_TABLE_PC & 0xFF0000) + en_pointer:06X}",
                "source_lines": _decode_en_part_text(en_raw[:-1]).split("<F6>"),
                "source_hex": _hex(en_raw),
            },
            "jp_reference": {
                "pointer": f"0x{jp_pointer:04X}",
                "source_pc": f"0x{bank_pc + jp_pointer:06X}",
                "source_lines": lenient_decode(decoder, jp_raw).split("<BR>"),
                "source_hex": _hex(jp_raw),
            },
        })

    return {
        "schema": "srw4.part-effects.source.v2",
        "authority": (
            "ROM EN catalog $FE:66BB คือ source runtime และเป้าหมาย build; "
            "ROM JP catalog $CC:E9BD เก็บเป็น reference สำหรับตรวจความหมายเท่านั้น"
        ),
        "catalog": {
            "en_pointer_table_pc": f"0x{EN_POINTER_TABLE_PC:06X}",
            "en_pointer_table_cpu": "$FE:E6BB",
            "jp_reference_pointer_table_pc": f"0x{JP_CATALOG_PC:06X}",
            "jp_reference_pointer_table_cpu": "$CC:E9BD",
            "item_id_range": [6, 37],
            "items": len(items),
            "unique_effect_records": len(effects),
        },
        "roms": {
            "en": {"path": str(EN_ROM.relative_to(ROOT)), "sha256": hashlib.sha256(en).hexdigest()},
            "jp": {"path": str(JP_ROM.relative_to(ROOT)), "sha256": hashlib.sha256(jp).hexdigest()},
        },
        "translation_target": "data/translations/part-effects.th.json",
        "names_jp_reference": names,
        "items": items,
        "effect_records": effects,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--en-rom", type=Path, default=EN_ROM)
    parser.add_argument("--jp-rom", type=Path, default=JP_ROM)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    try:
        document = extract(args.en_rom.read_bytes(), args.jp_rom.read_bytes())
    except (OSError, ValueError) as exc:
        print(f"part-effect extraction failed: {exc}", file=sys.stderr)
        return 1

    output = args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    catalog = document["catalog"]
    print(
        f"extracted {catalog['items']} item ids / "
        f"{catalog['unique_effect_records']} unique effect records: {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
