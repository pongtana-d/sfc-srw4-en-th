#!/usr/bin/env python3
"""Verify UNIT, PILOT and WEAPON status tabs through native Mesen inputs."""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MESEN = Path("/Applications/Mesen.app/Contents/MacOS/Mesen")
LUA = ROOT / "tools" / "lua" / "command-smoke.lua"
DEFAULT_ROM = ROOT / "build" / "srw4-th-test.sfc"
DEFAULT_STATE = ROOT / "build" / "repro" / "current-command-canonical.mss"
DEFAULT_SHIELD_STATE = ROOT / "save" / "shield.mss"
BASE = "80:down,120:down,160:a"
SCENARIOS = {
    "unit": (BASE, 240, "21972f6b291e7768c6050fec7ad976e08e2036925f8e3f9be40f2ab9b1924053"),
    "pilot": (BASE + ",220:right,260:a", 350,
              "09720160370fb80c2d6f07958d0c09c02272b7ab9909bb49eefda354de12ebf6"),
    "weapon": (BASE + ",220:right,260:right,300:a", 400,
               "c8a97bec3fd86c2ebccf5b4d69ad4a526d9d7ed30b1cca8fe123fc36d20f475c"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--shield-state", type=Path, default=DEFAULT_SHIELD_STATE)
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    args = parser.parse_args()
    state, shield_state, rom = (
        args.state.resolve(), args.shield_state.resolve(), args.rom.resolve()
    )
    failures = []
    with tempfile.TemporaryDirectory(prefix="srw4-status-") as temporary:
        root = Path(temporary)
        for name, (presses, end_at, expected) in SCENARIOS.items():
            shot, tilemap = root / f"{name}.png", root / f"{name}.bin"
            run = subprocess.run(
                [str(MESEN), "--testRunner", "--testRunnerTimeout=120", "--noAudio",
                 str(rom), str(LUA)],
                env=dict(os.environ, SRW4_STATE=str(state), SRW4_SHOT=str(shot),
                         SRW4_TILEMAP=str(tilemap), SRW4_OPEN_AT="0",
                         SRW4_END_AT=str(end_at), SRW4_PRESS=presses),
                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
            )
            if run.returncode or not shot.is_file():
                failures.append(f"{name}: Mesen failed or screenshot missing")
                continue
            actual = hashlib.sha256(shot.read_bytes()).hexdigest()
            if actual != expected:
                failures.append(f"{name}: expected {expected}, got {actual}")
        shield_shot, shield_tilemap = root / "shield.png", root / "shield.bin"
        run = subprocess.run(
            [str(MESEN), "--testRunner", "--testRunnerTimeout=120", "--noAudio",
             str(rom), str(LUA)],
            env=dict(os.environ, SRW4_STATE=str(shield_state),
                     SRW4_SHOT=str(shield_shot), SRW4_TILEMAP=str(shield_tilemap),
                     SRW4_OPEN_AT="100", SRW4_END_AT="160", SRW4_PRESS="40:b"),
            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        )
        expected_shield = "13c7f208f8276366be2a7c9799f23ade7074df8d0c04aed28a24598f89ade4da"
        if run.returncode or not shield_shot.is_file():
            failures.append("shield: Mesen failed or screenshot missing")
        else:
            actual = hashlib.sha256(shield_shot.read_bytes()).hexdigest()
            if actual != expected_shield:
                failures.append(
                    f"shield: expected {expected_shield}, got {actual}"
                )
    if failures:
        raise SystemExit("status runtime gate failed\n  " + "\n  ".join(failures))
    print("status runtime gate passed: UNIT, PILOT, WEAPON, and shield genuine redraws")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
