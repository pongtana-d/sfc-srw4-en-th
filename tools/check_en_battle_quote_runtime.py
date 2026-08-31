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
ROM_SHA256 = "9cf335b68afe051a9ec3c6058c894abcfcaa047bc89f58a341c73face774e2b9"
STATE_SHA256 = "d3102a5c156f735f73495a315b99fff9302bcd4b04dc6017ec08d12756356526"
FRAMES = (240, 500, 700, 900, 1200)
GOLDEN = {
    240: "19f7e36dc0b3b2f937974e23c8f3b8300b53a76d46ab902221d78d71939de555",
    500: "28579ba5863182d5711dd7b51658d7c6483def521ebfdf4e784485f37fc4728b",
    700: "0d798f0d12df4d0e385fba5905e3b79d36e460bf6c84394d2c0ce57ced531e7d",
    900: "886f220d7f857b19dfbb0809e22f62b5069cd7ca37097ecb2ae43d7b9c6f36fd",
    1200: "4981d56d88de75911b6fbfbeac519431534e7c8a3f07f4127fdbbf87c2144ad3",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=ROOT / "build" / "srw4-en-th.sfc")
    parser.add_argument(
        "--state", type=Path, default=ROOT / "save" / "battle.mss"
    )
    args = parser.parse_args()
    rom, state = args.rom.resolve(), args.state.resolve()
    for path in (MESEN, LUA, rom, state):
        if not path.is_file():
            raise SystemExit(f"required battle gate input is missing: {path}")
    actual_rom_sha256 = hashlib.sha256(rom.read_bytes()).hexdigest()
    if actual_rom_sha256 != ROM_SHA256:
        raise SystemExit(
            "EN battle quote gate expects the verified ROM: "
            f"expected {ROM_SHA256}, got {actual_rom_sha256}"
        )
    actual_state_sha256 = hashlib.sha256(state.read_bytes()).hexdigest()
    if actual_state_sha256 != STATE_SHA256:
        raise SystemExit(
            "EN battle quote gate expects the verified state: "
            f"expected {STATE_SHA256}, got {actual_state_sha256}"
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
                SRW4_FRAMES="1205",
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
