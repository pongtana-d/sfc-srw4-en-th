#!/usr/bin/env python3
"""Build the small Thai dialogue vertical slice on the English ROM."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_baseline import EN_SHA256  # noqa: E402
from srw4.en_vertical_slice import apply  # noqa: E402
from srw4.rom import Rom, sha256  # noqa: E402


BASE = ROOT / "rom" / "Dai-4-ji Super Robot Taisen English.sfc"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=BASE)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "build" / "srw4-en-th-dialogue-slice.sfc")
    parser.add_argument("--report", type=Path,
                        default=ROOT / "build" / "reports" / "en-th-dialogue-slice.json")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.report = args.report.resolve()
    base = args.input.read_bytes()
    if sha256(base) != EN_SHA256:
        raise SystemExit("input is not the pinned English base ROM")
    built, report = apply(base)
    rom = Rom(bytearray(built))
    checksum = rom.fix_checksum()
    final = rom.to_bytes()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(final)
    report["output"] = {
        "path": str(args.output.relative_to(ROOT)), "sha256": sha256(final),
        "checksum": f"0x{checksum:04X}", "bytes": len(final),
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"built {args.output.resolve()} sha256={report['output']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
