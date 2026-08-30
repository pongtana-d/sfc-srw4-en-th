#!/usr/bin/env python3
"""Cold-boot the built ROM in Mesen and save a screenshot.

Mesen's test runner needs absolute paths, and its Lua script writes the image
itself, so this wrapper just resolves paths and reports where the shot landed.

  tools/boot_check.py [--frames 900] [--out build/reports/boot.png]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MESEN = Path("/Applications/Mesen.app/Contents/MacOS/Mesen")
DEFAULT_ROM = ROOT / "build" / "srw4-th-test.sfc"
LUA = ROOT / "tools" / "lua" / "boot-check.lua"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=900)
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "reports" / "boot.png")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    if not MESEN.exists():
        print(f"Mesen not found at {MESEN}", file=sys.stderr)
        return 1
    rom = args.rom.resolve()
    if not rom.exists():
        print(f"no build to check: run tools/build.py first ({rom})", file=sys.stderr)
        return 1

    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    env = dict(os.environ, SRW4_SHOT=str(out), SRW4_FRAMES=str(args.frames))
    subprocess.run(
        [
            str(MESEN),
            "--testRunner",
            f"--testRunnerTimeout={args.timeout}",
            "--noAudio",
            str(rom),
            str(LUA.resolve()),
        ],
        env=env,
        check=True,
    )

    if not out.exists():
        print("Mesen exited without writing a screenshot", file=sys.stderr)
        return 1
    print(f"{out.relative_to(ROOT)}  {out.stat().st_size} bytes  (frame {args.frames})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
