#!/usr/bin/env python3
"""Build the uninstalled catalog-13 pool and its per-slot report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.catalog13 import build  # noqa: E402
from srw4.pipeline import Pipeline  # noqa: E402

CLEAN = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "build/catalog-13.pool.bin")
    parser.add_argument("--report", type=Path, default=ROOT / "build/reports/catalog-13.json")
    args = parser.parse_args()

    result = build(ROOT, CLEAN.read_bytes(), Pipeline.load(ROOT, CLEAN))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(result.pool.payload)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result.report, ensure_ascii=False, indent=2) + "\n")
    print(f"{args.out.relative_to(ROOT)}  {len(result.pool.payload):,} bytes")
    print(f"{args.report.relative_to(ROOT)}  {len(result.report['records'])} slots, "
          f"{result.report['unique_records']} unique records")


if __name__ == "__main__":
    main()
