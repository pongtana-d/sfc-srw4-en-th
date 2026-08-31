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
from .records import LabelEncoder, build_record_config_patches
from .text.japanese import CatalogDecoder
from .text.residue import lenient_decode, read_string


POINTER_TABLE_PC = 0x0CE9BD
POINTER_TABLE_ENTRIES = 96
EN_POINTER_TABLE_PC = 0x3E66BB
EN_POINTER_TABLE_SHA256 = "790313f6da237b3711dc9cca629cd7a329a0d551a956e572f1eb720cc8bce495"
# Verified erased space in the same $FE text bank.  The active records are
# tightly packed, while the merged consumable descriptions can grow by bytes.
EN_FREE_RUN = (0x3E8016, 0x3E8200)
# A second verified erased run in the same bank. It is used only when the
# localized active records cannot fit inside their vacated spans and EN_FREE_RUN.
EN_OVERFLOW_FREE_RUN = (0x3EFDBE, 0x3F0000)
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


def build_part_effect_data(
    root: Path, clean: bytes, cursor: int
) -> tuple[list[Write], dict[str, object]]:
    """Rebuild only Part descriptions for the EN-target production build."""
    if not FREE_RUN[0] <= cursor < FREE_RUN[1]:
        raise ValueError(f"part-effect cursor {cursor:#08x} is outside the verified run")
    option = json.loads(
        (root / "translations/option-menu.th.json").read_text(encoding="utf-8")
    )
    text = {
        "_layout": option["_layout"],
        "records": _part_effect_records(root, clean),
    }
    writes, report = build_record_config_patches(
        root,
        clean,
        text,
        "part-effects",
        [{"start": cursor, "end": FREE_RUN[1], "kind": "verified-ff"}],
    )

    # Item ids 7-16 are additional radar grades and share the description for
    # id 6. Keep one rebuilt record and preserve the original alias contract.
    slot6 = next(record for record in report["records"] if record["slot"] == 6)
    pointer = int(str(slot6["pointer"]), 0).to_bytes(2, "little")
    for slot in range(7, 17):
        writes.append(
            Write(
                POINTER_TABLE_PC + slot * 2,
                pointer,
                f"part-effects-slot-{slot}",
                False,
            )
        )
    return writes, report


def _decode_en_part_text(payload: bytes) -> str:
    """Decode the direct English page used by the EN hack's Part catalog."""
    direct = {
        0x10: "+", 0x3A: ",", 0x43: " ", 0x60: "-",
        0x68: "(", 0x69: ")", 0xAA: ".", 0xF6: "<F6>",
    }
    direct.update({0x16 + index: char for index, char in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")})
    direct.update({0x90 + index: char for index, char in enumerate("abcdefghijklmnopqrstuvwxyz")})
    direct.update({0xB0 + index: char for index, char in enumerate("0123456789")})
    return "".join(direct.get(value, f"<{value:02X}>") for value in payload)


def _en_part_effect_records(root: Path, clean: bytes) -> list[dict]:
    translated = json.loads(
        (root / "translations/part-effects.th.json").read_text(encoding="utf-8")
    )["records"]
    records: list[dict] = []
    bank_pc = EN_POINTER_TABLE_PC & 0xFF0000
    for slot in PART_EFFECT_SLOTS:
        at = EN_POINTER_TABLE_PC + slot * 2
        pointer = clean[at] | clean[at + 1] << 8
        source = read_string(clean, bank_pc, pointer)
        lines = source[:-1].split(b"\xF6")
        replacement = list(translated[str(slot)])
        # The EN hack removed the explicit break from the radar description
        # and lets its VWF wrap automatically. Preserve that one-line grammar.
        if len(lines) == 1 and len(replacement) > 1:
            replacement = [" ".join(replacement)]
        # The EN VWF's Thai route is evaluated after a byte read.  A second
        # line reached through $F6 therefore does not enter that route.  Keep
        # every translated phrase in the first source line, which has ample
        # room (240 px) and is rendered by the tested path.
        elif len(lines) > 1:
            if len(replacement) > 1:
                replacement = [" ".join(replacement)]
            replacement += [""] * (len(lines) - len(replacement))
        if len(lines) != len(replacement):
            raise ValueError(f"EN part effect {slot} has changed line count")
        labels, offset = [], 0
        for original, text in zip(lines, replacement):
            labels.append({
                "offset": offset,
                "length": len(original),
                "source_hex": original.hex().upper(),
                "source": _decode_en_part_text(original),
                "text": text,
                "max_width_px": 240,
            })
            offset += len(original) + 1
        records.append({
            "slot": slot,
            "pointer": f"0x{pointer:04X}",
            "source_pc": f"0x{bank_pc + pointer:06X}",
            "source_end": f"0x{bank_pc + pointer + len(source):06X}",
            "source_hex": source.hex().upper(),
            "labels": labels,
        })
    return records


def build_en_part_effect_data(
    root: Path, clean: bytes, *, label_encoder: LabelEncoder
) -> tuple[list[Write], dict[str, object]]:
    """Rebuild the active bank-$FE Part descriptions in the English ROM."""
    text = {
        "_layout": {
            "pointer_table": {
                "address": f"0x{EN_POINTER_TABLE_PC:06X}",
                "entries": POINTER_TABLE_ENTRIES,
                "source_sha256": EN_POINTER_TABLE_SHA256,
            },
            "max_width_px": 240,
        },
        "records": _en_part_effect_records(root, clean),
    }
    writes, report = build_record_config_patches(
        root,
        clean,
        text,
        "en-part-effects",
        [
            {"start": EN_FREE_RUN[0], "end": EN_FREE_RUN[1], "kind": "verified-ff"},
            {
                "start": EN_OVERFLOW_FREE_RUN[0],
                "end": EN_OVERFLOW_FREE_RUN[1],
                "kind": "verified-ff-overflow",
            },
        ],
        label_encoder=label_encoder,
    )
    slot6 = next(record for record in report["records"] if record["slot"] == 6)
    pointer = int(str(slot6["pointer"]), 0).to_bytes(2, "little")
    for slot in range(7, 17):
        writes.append(
            Write(
                EN_POINTER_TABLE_PC + slot * 2,
                pointer,
                f"en-part-effects-slot-{slot}",
                False,
            )
        )
    return writes, report


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
