#!/usr/bin/env python3
"""Verify UNITS, ORDER, and SYSTEM map-menu branches in native Mesen."""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MESEN = Path("/Applications/Mesen.app/Contents/MacOS/Mesen")
LUA = ROOT / "tools" / "lua" / "from-state.lua"
DEFAULT_ROM = ROOT / "build" / "srw4-th-test.sfc"
DEFAULT_STATE = ROOT / "build" / "repro" / "en-th-own-native11.mss"
OPEN = "5:up,15:up,25:up,50:a"
SCENARIOS = {
    "units": (
        OPEN + ",90:down,120:a",
        "2abe7986c14f7edf94504cf7f4e74aa4836cabeda7f64e28687ee2e55d218993",
    ),
    "order": (
        OPEN + ",80:down,90:down,100:down,110:down,140:a",
        "77eb3f13aa5626af9f8908f2db24b7114dce45fb6743608228018f54655e991b",
    ),
    "system": (
        OPEN + ",80:down,90:down,100:down,110:down,120:down,140:a",
        "c16d4416f7b29950c3a7e1cb587c45af079b6cb06c28d9e91439e7daa5c3ecc3",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    args = parser.parse_args()
    state, rom = args.state.resolve(), args.rom.resolve()
    for path, label in ((MESEN, "Mesen"), (state, "state"), (rom, "ROM")):
        if not path.is_file():
            raise SystemExit(f"{label} is missing: {path}")

    failures = []
    with tempfile.TemporaryDirectory(prefix="srw4-main-menu-") as temporary:
        root = Path(temporary)
        for name, (presses, expected) in SCENARIOS.items():
            prefix = root / name
            run = subprocess.run(
                [str(MESEN), "--testRunner", "--testRunnerTimeout=120", "--noAudio",
                 str(rom), str(LUA)],
                env=dict(os.environ, SRW4_STATE=str(state), SRW4_OUT=str(prefix),
                         SRW4_PRESS=presses, SRW4_SHOTS="199", SRW4_FRAMES="210"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            shot = Path(f"{prefix}-0199.png")
            if run.returncode or not shot.is_file():
                failures.append(f"{name}: Mesen failed or screenshot missing")
                continue
            actual = hashlib.sha256(shot.read_bytes()).hexdigest()
            if actual != expected:
                failures.append(f"{name}: expected {expected}, got {actual}")
    if failures:
        raise SystemExit("main-menu runtime gate failed\n  " + "\n  ".join(failures))
    print("main-menu runtime gate passed: UNITS, ORDER, and SYSTEM genuine redraws")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
