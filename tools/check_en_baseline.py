#!/usr/bin/env python3
"""Verify the locked English-combo ROM baseline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_baseline import BaselineError, verify_baseline  # noqa: E402

EN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (English combo).sfc"
OUT = ROOT / "build" / "reports" / "en-th-dialogue-baseline.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--english-combo", type=Path, default=EN_ROM)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    try:
        report = verify_baseline(args.english_combo.read_bytes())
    except (OSError, BaselineError) as exc:
        print(f"baseline failed: {exc}", file=sys.stderr)
        return 1

    output = args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"P0 PASS: English-combo identity is {report['inputs']['english_combo']['sha256']}")
    print(f"report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
