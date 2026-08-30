#!/usr/bin/env python3
"""Verify the current expanded command menu through native Mesen input routes."""
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
DEFAULT_STATE = ROOT / "save" / "cmdmenu.mss"

SCENARIOS = {
    # The canonical state intentionally predates the current command surface.
    # Close and reopen it first so every golden proves a genuine redraw rather
    # than accepting the PPU cache embedded in the savestate.
    # The first visible frame must already match the settled surface.  This
    # catches the obsolete three-cell footer before the later cleanup DMA.
    "open-first-visible": ("20:b,80:a", 89, "c193fd0051cd3b87d2af380c8125511cdbaf82e85d1f7a4f1c8d856d8b3d220b"),
    "open": ("20:b,80:a", 160, "c193fd0051cd3b87d2af380c8125511cdbaf82e85d1f7a4f1c8d856d8b3d220b"),
    "down": ("20:b,80:a,150:down", 200, "9a4a550c1d28d910cc5722562c1da095b48c02090e51bdf682a630cf9c0bfdb0"),
    "wrap": ("20:b,80:a,150:up", 200, "fea73d1d18f33a9588cfd78671d59c65aef4565b77d549553adb0f4289aaa8fc"),
    "reentry": ("20:b,80:a,150:b,210:a", 290, "c193fd0051cd3b87d2af380c8125511cdbaf82e85d1f7a4f1c8d856d8b3d220b"),
    "spirit": ("20:b,80:a,150:down,210:a", 300, "72cdff74e848b2b467127ad8fca0758321dade1f92e3fcdcf0738b8babc563ae"),
}


def has_complete_command_frame(path: Path, rows: int = 3) -> bool:
    """Require all four borders, not merely a screenshot with readable text."""
    raw = path.read_bytes()
    words = [int.from_bytes(raw[at:at + 2], "little") & 0x03FF
             for at in range(0, len(raw), 2)]
    height = rows * 2 + 2
    for y in range(28 - height + 1):
        for x in range(25):
            top = words[y * 32 + x:y * 32 + x + 8]
            if top != [0x11] + [0x19] * 6 + [0x12]:
                continue
            if any(words[(y + dy) * 32 + x] != 0x1B
                   or words[(y + dy) * 32 + x + 7] != 0x1C
                   for dy in range(1, height - 1)):
                continue
            bottom = words[(y + height - 1) * 32 + x:(y + height - 1) * 32 + x + 8]
            if bottom != [0x13] + [0x1A] * 6 + [0x14]:
                continue
            outside = list(range(max(0, x - 2), x))
            outside += list(range(x + 8, min(32, x + 10)))
            if all(words[(y + dy) * 32 + xx] == 0x10
                   for dy in range(height) for xx in outside):
                return True
    return False


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
    with tempfile.TemporaryDirectory(prefix="srw4-command-") as temporary:
        root = Path(temporary)
        for name, (presses, end_at, expected) in SCENARIOS.items():
            shot = root / f"{name}.png"
            tilemap = root / f"{name}.bin"
            run = subprocess.run(
                [str(MESEN), "--testRunner", "--testRunnerTimeout=120", "--noAudio",
                 str(rom), str(LUA)],
                env=dict(os.environ, SRW4_STATE=str(state), SRW4_SHOT=str(shot),
                         SRW4_TILEMAP=str(tilemap), SRW4_OPEN_AT="0",
                         SRW4_END_AT=str(end_at), SRW4_PRESS=presses),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            if run.returncode:
                failures.append(f"{name}: Mesen exited {run.returncode}")
                continue
            if not shot.is_file():
                failures.append(f"{name}: screenshot missing")
                continue
            actual = hashlib.sha256(shot.read_bytes()).hexdigest()
            if actual != expected:
                failures.append(f"{name}: expected {expected}, got {actual}")
            if name != "spirit" and not has_complete_command_frame(tilemap):
                failures.append(f"{name}: command frame border is incomplete")
        for name, presses, end_at, expected in (
            ("four-row-open", "20:b,50:right,70:right,110:a", 200,
             "d31663582e8e19cfeeef0f67f6d7225fb35e8d9d70554378cfae226423c5ca88"),
            ("four-row-down", "20:b,50:right,70:right,110:a,170:down", 210,
             "ccbaa1e5be2cb8518520b88b0d4c461b9e97d2f670ba9440699fe1b671a528a9"),
        ):
            shot = root / f"{name}.png"
            tilemap = root / f"{name}.bin"
            run = subprocess.run(
                [str(MESEN), "--testRunner", "--testRunnerTimeout=120", "--noAudio",
                 str(rom), str(LUA)],
                env=dict(os.environ, SRW4_STATE=str(state),
                         SRW4_SHOT=str(shot), SRW4_TILEMAP=str(tilemap),
                         SRW4_OPEN_AT="0", SRW4_END_AT=str(end_at), SRW4_PRESS=presses),
                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
            )
            if run.returncode or not shot.is_file():
                failures.append(f"{name}: Mesen failed or screenshot missing")
                continue
            actual = hashlib.sha256(shot.read_bytes()).hexdigest()
            if actual != expected:
                failures.append(f"{name}: expected {expected}, got {actual}")
            if not has_complete_command_frame(tilemap, rows=4):
                failures.append(f"{name}: command frame border is incomplete")
    if failures:
        raise SystemExit("command runtime gate failed\n  " + "\n  ".join(failures))
    print("command runtime gate passed: fixed/dynamic open, down, wrap, reentry, and Spirit branch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
