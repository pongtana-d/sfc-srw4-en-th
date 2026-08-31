#!/usr/bin/env python3
"""Build Thai story/map/event and battle dialogue on the pinned English ROM."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_baseline import EN_SHA256
from srw4.en_dialogue_streams import PrecomposedDialogueCompiler
from srw4.en_ff_router import install as install_router
from srw4.en_intro import install as install_intro
from srw4.en_story_build import install_full_story
from srw4.en_th_catalogs import (
    ClusterCatalogEncoder,
    ProfileCatalogEncoder,
    build_part_stock_catalog,
    install as install_catalogs,
)
from srw4.en_th_renderer import install as install_renderer
from srw4.en_title import install_en_title_logo
from srw4.proven.option_menu import build_en_part_effect_data
from srw4.rom import Rom, sha256


BASE = ROOT / "rom" / "Dai-4-ji Super Robot Taisen English.sfc"
SOURCE = ROOT / "data" / "translations" / "script.source.json"
TRANSLATIONS = ROOT / "data" / "translations" / "script.th.json"
OBJECTIVES = ROOT / "data" / "translations" / "objectives.en.json"
# Character Archives owns all 240 pointer rows in block 48, then continues
# through rows 0-37 of block 49. Row 38 starts the unrelated Astonaige event.
PROFILE_CONTINUATION_POINTERS = 38

# EN dialogue data is placed before this area.  The title resource must occupy
# a contiguous erased range below the stock text-data boundary.
def encode_ips(base: bytes, target: bytes) -> bytes:
    """Encode an equal-size binary diff as a standard IPS patch."""
    if len(base) != len(target):
        raise ValueError("IPS output requires equal-size base and target ROMs")
    patch = bytearray(b"PATCH")
    offset = 0
    while offset < len(base):
        if base[offset] == target[offset]:
            offset += 1
            continue
        start = offset
        while offset < len(base) and base[offset] != target[offset] and offset - start < 0xFFFF:
            offset += 1
        data = target[start:offset]
        patch.extend(start.to_bytes(3, "big"))
        patch.extend(len(data).to_bytes(2, "big"))
        patch.extend(data)
    patch.extend(b"EOF")
    return bytes(patch)


def _place_fill(image: bytearray, pc: int, data: bytes, owner: str) -> None:
    if image[pc:pc + len(data)] != b"\xFF" * len(data):
        raise ValueError(f"{owner} overlaps occupied ROM bytes at {pc:#08x}")
    image[pc:pc + len(data)] = data


def _merge_routes(
    *groups: dict[int, tuple[tuple[int, int], ...]],
) -> dict[int, tuple[tuple[int, int], ...]]:
    merged: dict[int, list[tuple[int, int]]] = {}
    for group in groups:
        for bank, spans in group.items():
            merged.setdefault(bank, []).extend(spans)
    return {bank: tuple(sorted(spans)) for bank, spans in merged.items()}


def _apply_writes(image: bytearray, clean: bytes, writes) -> None:
    for write in writes:
        expected = (
            b"\xFF" * len(write.payload)
            if write.expected_ff
            else clean[write.pc:write.pc + len(write.payload)]
        )
        actual = bytes(image[write.pc:write.pc + len(write.payload)])
        if actual != expected:
            raise ValueError(f"{write.owner} overlaps changed bytes at {write.pc:#08x}")
        image[write.pc:write.pc + len(write.payload)] = write.payload


def _report_path(path: Path) -> str:
    """Use a workspace-relative path when possible, without rejecting --output."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=BASE)
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "srw4-en-th.sfc")
    parser.add_argument("--patch", type=Path, default=ROOT / "build" / "srw4-en-th.ips")
    parser.add_argument("--report", type=Path,
                        help="optional JSON build report; omitted to keep build/ release-only")
    parser.add_argument("--manifest", type=Path,
                        help="optional IPS manifest; omitted to keep build/ release-only")
    args = parser.parse_args()
    base = args.input.read_bytes()
    if sha256(base) != EN_SHA256:
        raise SystemExit("input is not the pinned English base ROM")

    document = json.loads(SOURCE.read_text(encoding="utf-8"))
    translated = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))["messages"]
    translated.update(json.loads(OBJECTIVES.read_text(encoding="utf-8"))["messages"])
    dialogue_compiler = PrecomposedDialogueCompiler()
    profile_ids = set()
    for row in document["messages"]:
        block = int(row["block"])
        pointer_rows = tuple(int(index) for index in row.get("table_slots", ()))
        if block == 48 or (
            block == 49
            and pointer_rows
            and max(pointer_rows) < PROFILE_CONTINUATION_POINTERS
        ):
            profile_ids.add(str(row["id"]))
    if len(profile_ids) != 240:
        raise ValueError(
            f"Character Archives record contract changed: expected 240, got {len(profile_ids)}"
        )
    profile_encoder = ProfileCatalogEncoder(
        base, [translated[message_id] for message_id in sorted(profile_ids)]
    )
    profile_records = {
        message_id: profile_encoder.record(translated[message_id])
        for message_id in profile_ids
    }
    rom = Rom(bytearray(base))
    full = install_full_story(
        rom,
        base,
        document,
        translated,
        lambda text, where, branch_range: dialogue_compiler.compile(
            text, where=where, branch_range=branch_range
        ),
        ordinary_records=profile_records,
    )

    renderer = install_renderer(rom.data)
    # The Thai copier uploads its dynamic tiles; retain parser and width hooks.
    router = install_router(rom.data, font_hooks=True, alt_hook=False, width_hooks=True)
    part_stock, en_direct_runs = build_part_stock_catalog()
    cluster_encoder = ClusterCatalogEncoder(
        base,
        part_stock,
        include_part_effects=True,
        en_direct_stock_runs=en_direct_runs,
    )
    part_writes, part_effects = build_en_part_effect_data(
        ROOT / "data", base, label_encoder=cluster_encoder.part_runs
    )
    _apply_writes(rom.data, base, part_writes)
    part_routes = {
        int(bank, 16): tuple((int(start), int(end)) for start, end in spans)
        for bank, spans in part_effects["source_routes"].items()
    }
    catalogs = install_catalogs(
        rom.data,
        base,
        extra_thai_routes=_merge_routes(full.ordinary_thai_routes, part_routes),
        extra_supplement_routes=full.ordinary_profile_page2_routes,
        extra_alternate_routes=full.ordinary_alternate_routes,
        profile_encoder=profile_encoder,
        profile_banks=tuple(sorted({
            *full.ordinary_thai_routes,
            *full.ordinary_profile_page2_routes,
            *full.ordinary_alternate_routes,
        })),
        cluster_encoder=cluster_encoder,
    )
    title = install_en_title_logo(rom.data, ROOT / "data", base)
    intro = install_intro(rom.data, base, ROOT)
    checksum = rom.fix_checksum()
    output = rom.to_bytes()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.patch.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    patch = encode_ips(base, output)
    args.patch.write_bytes(patch)
    report = {
        "scope": (
            "EN Thai story, battle quotes, Spirit and Part descriptions, title logo, and "
            "opening crawl; original English unit/pilot/weapon names"
        ),
        "story_repack": {"blocks": full.blocks, "records": full.records,
                          "bytes": full.bytes, "relocated_fields": full.relocated_fields,
                          "banks": list(full.banks)},
        "router": {"origin": f"0x{router.origin:06X}", "bytes": router.bytes},
        "renderer": {"bytes": renderer.bytes, "code_bytes": renderer.renderer_bytes},
        "catalogs": {
            "unit_records": catalogs.unit_records,
            "pilot_records": catalogs.pilot_records,
            "battle_pilot_records": catalogs.battle_pilot_records,
            "weapon_records": catalogs.weapon_records,
            "spirit_name_records": catalogs.spirit_name_records,
            "spirit_help_records": catalogs.spirit_help_records,
            "data_bytes": catalogs.data_bytes,
            "adapter_bytes": catalogs.adapter_bytes,
            "route_bytes": catalogs.route_bytes,
            "ordinary_renderer_bytes": catalogs.ordinary_renderer_bytes,
            "battle_info_labels": catalogs.battle_info_labels,
        },
        "part_effects": {
            "records": len(part_effects["records"]),
            "routes": sum(len(spans) for spans in part_routes.values()),
            "translation": "data/translations/part-effects.th.json",
        },
        "title": title,
        "intro": intro,
        "output": {"path": _report_path(args.output), "sha256": sha256(output),
                   "checksum": f"0x{checksum:04X}", "bytes": len(output)},
        "patch": {"format": "IPS", "path": _report_path(args.patch),
                  "sha256": sha256(patch), "bytes": len(patch),
                  "base_sha256": EN_SHA256},
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "schema": "srw4-en-th-dialogue-patch/1",
            "scope": report["scope"],
            "base": {"sha256": EN_SHA256, "bytes": len(base)},
            "patch": report["patch"],
            "result": report["output"],
        }
        args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
