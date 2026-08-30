#!/usr/bin/env python3
"""Build a current-translation candidate on the verified cumulative shell."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from build_proven_full import DEFAULT_CLEAN, build_proven  # noqa: E402
from srw4.story_migration import apply  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_CLEAN)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "build" / "srw4-th-current-story.sfc")
    parser.add_argument("--report", type=Path,
                        default=ROOT / "build" / "reports" / "current-story.json")
    args = parser.parse_args()
    shell_report = args.report.with_name("current-story-shell.json")
    build_proven(args.input, args.output, shell_report)
    cumulative = json.loads(shell_report.read_text())
    payload, report = apply(args.output.read_bytes(), cumulative)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        f"{args.output.resolve()}  {len(payload)} bytes  "
        f"{report['story']['translated']} current story records  "
        f"sha256 {report['output']['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
