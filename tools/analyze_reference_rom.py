#!/usr/bin/env python3
"""Analyze an external translated ROM as evidence, never as a build input.

  python3 tools/analyze_reference_rom.py
  python3 tools/analyze_reference_rom.py --reference rom/en-sample.sfc
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.reference import ReferenceError, analyze_reference  # noqa: E402

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
REFERENCE_ROM = ROOT / "rom" / "en-sample.sfc"
HOOKS = ROOT / "data" / "config" / "hooks.json"
ROM_MAP = ROOT / "data" / "config" / "rom-map.json"
SCRIPT = ROOT / "data" / "translations" / "script.source.json"
OUT = ROOT / "build" / "reports" / "en-reference.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", type=Path, default=CLEAN_ROM)
    parser.add_argument("--reference", type=Path, default=REFERENCE_ROM)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--pointer-examples",
        type=int,
        default=128,
        help="maximum heuristic pointer examples retained in JSON",
    )
    args = parser.parse_args()

    try:
        report = analyze_reference(
            args.clean.read_bytes(),
            args.reference.read_bytes(),
            hooks=json.loads(HOOKS.read_text()),
            rom_map=json.loads(ROM_MAP.read_text()),
            script=json.loads(SCRIPT.read_text()),
            pointer_example_limit=args.pointer_examples,
        )
    except (OSError, json.JSONDecodeError, ReferenceError) as exc:
        print(f"reference analysis failed: {exc}", file=sys.stderr)
        return 1

    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")

    reference = report["input"]["reference"]
    stock = report["stock_diff"]
    hooks = report["hooks"]
    pointers = report["pointers"]
    expansion = report["expansion_payload"]
    story = report["script_and_catalog_regions"]["story_blocks"]
    print(f"reference {reference['title']!r} sha256 {reference['sha256']}")
    print(
        f"stock: {stock['changed_bytes']:,} changed bytes in "
        f"{stock['changed_runs']:,} runs"
    )
    print(
        f"hooks: {hooks['known_changed']} known-hook changes, "
        f"{len(hooks['long_transfer_candidates'])} long-transfer candidates"
    )
    print(
        f"pointers: {pointers['total']:,} heuristic candidates; "
        f"story: {story['changed_blocks']} changed blocks"
    )
    print(
        f"expansion: {expansion['non_ff_bytes']:,} non-FF bytes "
        f"({expansion['non_ff_percent']:.2f}%)"
    )
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
