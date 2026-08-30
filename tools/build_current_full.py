#!/usr/bin/env python3
"""Build the cumulative ROM entirely from source and data in this workspace."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from srw4.battle_placement import place_current_battle  # noqa: E402
from srw4.cumulative import build_intro_stage  # noqa: E402
from srw4.p7_cumulative import apply as apply_current_commands  # noqa: E402
from srw4.rom import Rom, sha256  # noqa: E402

DEFAULT_CLEAN = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
EXPECTED_SHA256 = "374189c25adbfeab321861e0bf91924811b5ea225b4b76d5da08a4b2f3c56956"


def build_current(clean: Path, output: Path, report_path: Path) -> str:
    """Build current story plus cumulative UI without reading a Git revision."""
    image, report = build_intro_stage(clean)
    payload, battle_placement = place_current_battle(
        bytes(image.data), clean.read_bytes()
    )
    payload, command_placement = apply_current_commands(payload, clean.read_bytes())
    rom = Rom(bytearray(payload))
    checksum = rom.fix_checksum()
    final = rom.to_bytes()
    digest = sha256(final)
    if digest != EXPECTED_SHA256:
        raise SystemExit(
            f"current full ROM changed: expected {EXPECTED_SHA256}, got {digest}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(final)
    report.update({
        "output_sha256": digest,
        "checksum": f"0x{checksum:04X}",
        "complement": f"0x{checksum ^ 0xFFFF:04X}",
        "current_source": {
            "owner": "src/srw4/cumulative.py",
            "git_archive": False,
            "story_records": report["story"]["translated"],
            "battle_placement": battle_placement,
            "command_placement": command_placement,
            "compatibility_sources": [],
        },
    })
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_CLEAN)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "build" / "srw4-th-current-full.sfc"
    )
    parser.add_argument(
        "--report", type=Path,
        default=ROOT / "build" / "reports" / "current-full.json",
    )
    args = parser.parse_args()
    digest = build_current(args.input, args.output, args.report)
    print(f"built current full ROM: {args.output.resolve()} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
