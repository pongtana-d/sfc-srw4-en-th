#!/usr/bin/env python3
"""Verify the locked English-ROM baseline and both supplied patch routes."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_baseline import BaselineError, verify_baseline  # noqa: E402

JP_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
EN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen English.sfc"
IPS = ROOT / "rom" / "srw4e.ips"
XDELTA = ROOT / "rom" / "srw4e.xdelta"
OUT = ROOT / "build" / "reports" / "en-th-dialogue-baseline.json"


def reproduce_xdelta(executable: str, jp_path: Path, patch_path: Path) -> bytes:
    with tempfile.TemporaryDirectory(prefix="srw4-en-baseline-") as directory:
        output = Path(directory) / "english.sfc"
        run = subprocess.run(
            [executable, "-d", "-s", str(jp_path), str(patch_path), str(output)],
            capture_output=True,
            text=True,
        )
        if run.returncode:
            detail = run.stderr.strip() or run.stdout.strip() or "no diagnostic"
            raise BaselineError(f"xdelta3 failed ({run.returncode}): {detail}")
        if not output.is_file():
            raise BaselineError("xdelta3 reported success but created no output")
        return output.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jp", type=Path, default=JP_ROM)
    parser.add_argument("--english", type=Path, default=EN_ROM)
    parser.add_argument("--ips", type=Path, default=IPS)
    parser.add_argument("--xdelta", type=Path, default=XDELTA)
    parser.add_argument("--xdelta3", default=shutil.which("xdelta3"))
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    if not args.xdelta3:
        print("baseline failed: xdelta3 executable is unavailable", file=sys.stderr)
        return 1
    try:
        xdelta_output = reproduce_xdelta(args.xdelta3, args.jp, args.xdelta)
        report = verify_baseline(
            args.jp.read_bytes(),
            args.english.read_bytes(),
            args.ips.read_bytes(),
            args.xdelta.read_bytes(),
            xdelta_output,
        )
    except (OSError, BaselineError) as exc:
        print(f"baseline failed: {exc}", file=sys.stderr)
        return 1

    output = args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"P0 PASS: IPS and xdelta reproduce {report['inputs']['english']['sha256']}")
    print(f"report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
