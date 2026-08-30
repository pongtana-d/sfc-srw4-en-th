#!/usr/bin/env python3
"""Replay the reported EN battle state and lock its quote lifecycle frames."""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MESEN = Path("/Applications/Mesen.app/Contents/MacOS/Mesen")
LUA = ROOT / "tools" / "lua" / "wram-snapshots.lua"
STATE_ROM_SHA256 = "824f093378607a7cd98b42ec2f77cd40f6f432b24fe13d6315586b084b393787"
FRAMES = (240, 500, 700, 900, 1100)
GOLDEN = {
    240: "6ce9c6c6d1997d3e18c7280aed0d2b75dc10fe1d21aacbf5e496c99aedd1f1e5",
    500: "ae9bbe6f5e9fc201ec7b45910496590cb14f91e55b83b07999702d5d7db3bd02",
    700: "5297c26903adf820868147a01c03753b186101a86fff989525c21be4917eae5f",
    900: "2af8d01a6b82d9eacf0f20325a26c55eda5fc8df46d5336ce47cd88754c90c29",
    1100: "30b016bf2271c93cfb7de4388c8914d5fac3079236d7cd0fb66449d82effb622",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=ROOT / "build" / "srw4-en-th.sfc")
    parser.add_argument(
        "--state", type=Path, default=ROOT / "save" / "en-battle-quote.mss"
    )
    args = parser.parse_args()
    rom, state = args.rom.resolve(), args.state.resolve()
    for path in (MESEN, LUA, rom, state):
        if not path.is_file():
            raise SystemExit(f"required battle gate input is missing: {path}")
    actual_rom_sha256 = hashlib.sha256(rom.read_bytes()).hexdigest()
    if actual_rom_sha256 != STATE_ROM_SHA256:
        raise SystemExit(
            "EN battle quote state is stale for this ROM: "
            f"state expects {STATE_ROM_SHA256}, ROM is {actual_rom_sha256}"
        )

    with tempfile.TemporaryDirectory(prefix="srw4-en-battle-") as temporary:
        prefix = Path(temporary) / "battle"
        run = subprocess.run(
            [str(MESEN), "--testRunner", "--testRunnerTimeout=300", "--noAudio",
             str(rom), str(LUA)],
            env=dict(
                os.environ,
                SRW4_STATE=str(state),
                SRW4_OUT=str(prefix),
                SRW4_PRESS="5:a",
                SRW4_SHOTS=",".join(map(str, FRAMES)),
                SRW4_FRAMES="1105",
            ),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        if run.returncode:
            raise SystemExit(f"Mesen battle gate failed with exit code {run.returncode}")
        failures = []
        for frame in FRAMES:
            shot = Path(f"{prefix}-{frame:04d}.png")
            if not shot.is_file():
                failures.append(f"frame {frame}: screenshot missing")
                continue
            actual = hashlib.sha256(shot.read_bytes()).hexdigest()
            if actual != GOLDEN[frame]:
                failures.append(f"frame {frame}: expected {GOLDEN[frame]}, got {actual}")
        if failures:
            raise SystemExit("EN battle quote runtime gate failed\n  " + "\n  ".join(failures))

    print("EN battle quote runtime gate passed: quotes, animation, and map return")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
