#!/usr/bin/env python3
"""Build an isolated cumulative P7 candidate with selected lifecycle hooks."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.p7_cumulative import apply  # noqa: E402
from srw4.rom import Rom, sha256  # noqa: E402

CLEAN = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
BASE = ROOT / "build" / "srw4-th-test.sfc"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hooks", default="", help="comma-separated open,activation")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    hooks = frozenset(filter(None, args.hooks.split(",")))
    payload, _report = apply(BASE.read_bytes(), CLEAN.read_bytes(), lifecycle_hooks=hooks)
    rom = Rom(bytearray(payload))
    rom.fix_checksum()
    final = rom.to_bytes()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(final)
    print(f"built {args.out} hooks={sorted(hooks)} sha256={sha256(final)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
