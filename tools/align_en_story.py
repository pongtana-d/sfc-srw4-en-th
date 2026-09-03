#!/usr/bin/env python3
"""Build the conservative structural JP/Thai-to-English story mapping."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_baseline import EN_SHA256  # noqa: E402
from srw4.en_story_align import align_story  # noqa: E402
from srw4.en_story_extract import extract_story  # noqa: E402
from srw4.rom import CLEAN_SHA256, RomError, sha256  # noqa: E402

JP_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
EN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (English combo).sfc"
JP_SOURCE = ROOT / "data" / "translations" / "script.source.json"
OUT = ROOT / "data" / "mappings" / "jp-en-story-map.json"
REPORT = ROOT / "build" / "reports" / "jp-en-story-alignment.md"


def _write_report(document: dict, path: Path) -> None:
    """Write the bounded manual-audit queue; full data remains in the JSON map."""
    summary = document["summary"]
    mappings = document["mappings"]
    split = [item for item in mappings if item["reason"].startswith("same JP pointer identity splits")]
    lines = [
        "# JP/Thai → English story structural alignment",
        "",
        "This report is structural only: it does not use prose or inferred EN record boundaries.",
        "",
        "## Summary",
        "",
        f"- Source messages: {summary['source_messages']}",
        f"- A (direct pointer + alias topology): {summary['confidence'].get('A', 0)}",
        f"- B (direct pointer, changed alias topology): {summary['confidence'].get('B', 0)}",
        f"- Unresolved: {summary['confidence'].get('UNRESOLVED', 0)}",
        f"- Alias topology rows matching: {summary['alias_topology_match_rows']}/{summary['pointer_rows']}",
        f"- Changed alias rows: {summary['alias_topology_different_rows']} (all in slot 48)",
        "",
        "## Split targets carried to every EN target",
        "",
    ]
    if split:
        lines.extend(["| Source ID | JP pointer rows | EN candidates |", "| --- | --- | --- |"])
        for item in split:
            candidates = ", ".join(candidate["record"] for candidate in item["targets"])
            lines.append(
                f"| {item['source_id']} | {', '.join(item['source_pointer_rows'])} | {candidates} |"
            )
    else:
        lines.append("None.")
    lines.extend(["", "## Slot 48 alias-topology changes", "", "| Pointer row | JP aliases | EN aliases |", "| --- | --- | --- |"])
    for item in document["topology_differences"]:
        lines.append(
            f"| {item['row']} | {', '.join(item['jp_alias_rows'])} | {', '.join(item['en_alias_rows'])} |"
        )
    lines.extend(
        [
            "",
            "The complete per-source mapping and unresolved control-flow audit queue are in `data/mappings/jp-en-story-map.json`.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jp-rom", type=Path, default=JP_ROM)
    parser.add_argument("--en-rom", type=Path, default=EN_ROM)
    parser.add_argument("--source", type=Path, default=JP_SOURCE)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()
    try:
        jp_rom = args.jp_rom.read_bytes()
        en_rom = args.en_rom.read_bytes()
        if sha256(jp_rom) != CLEAN_SHA256:
            raise RomError("JP ROM hash does not match the locked Rev 1 base")
        if sha256(en_rom) != EN_SHA256:
            raise RomError("English-combo ROM hash does not match the locked base")
        jp_source = json.loads(args.source.read_text(encoding="utf-8"))
        en_source = extract_story(en_rom, jp_source["summary"]["blocks"])
        document = align_story(jp_rom, en_rom, jp_source, en_source)
    except (KeyError, OSError, ValueError, RomError) as exc:
        print(f"EN story alignment failed: {exc}", file=sys.stderr)
        return 1

    output = args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = args.report.resolve()
    _write_report(document, report)
    summary = document["summary"]
    print(
        "aligned "
        f"{summary['source_messages']} source messages: "
        f"A={summary['confidence'].get('A', 0)}, "
        f"B={summary['confidence'].get('B', 0)}, "
        f"UNRESOLVED={summary['confidence'].get('UNRESOLVED', 0)}"
    )
    print(
        f"alias topology: {summary['alias_topology_match_rows']}/"
        f"{summary['pointer_rows']} rows match; source: {output}; report: {report}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
