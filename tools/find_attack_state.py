#!/usr/bin/env python3
"""Sweep map cursor offsets in Mesen until command record 1 (Attack) appears."""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MESEN = Path("/Applications/Mesen.app/Contents/MacOS/Mesen")
LUA = ROOT / "tools" / "lua" / "command-record-probe.lua"


def schedule(dx: int, dy: int) -> tuple[str, int]:
    buttons = (["left"] * -dx if dx < 0 else ["right"] * dx)
    buttons += (["up"] * -dy if dy < 0 else ["down"] * dy)
    presses = [f"{10 + index * 12}:{button}" for index, button in enumerate(buttons)]
    open_at = 10 + len(buttons) * 12 + 24
    presses.append(f"{open_at}:a")
    return ",".join(presses), open_at + 90


def run_one(state: Path, rom: Path, root: Path, dx: int, dy: int):
    out = root / f"x{dx:+d}-y{dy:+d}.log"
    presses, frames = schedule(dx, dy)
    run = subprocess.run(
        [str(MESEN), "--testRunner", "--testRunnerTimeout=120", "--noAudio",
         str(rom), str(LUA)],
        env=dict(os.environ, SRW4_STATE=str(state), SRW4_OUT=str(out),
                 SRW4_PRESS=presses, SRW4_FRAMES=str(frames),
                 SRW4_CLEAR_AT=str(frames - 94)),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    text = out.read_text() if run.returncode == 0 and out.is_file() else ""
    records = tuple(
        int(line.split("=", 1)[1]) for line in text.splitlines()
        if line.startswith("record[")
    )
    return dx, dy, records, presses


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--state-dir", type=Path,
                        help="first census every .mss in this directory at dx=dy=0")
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--radius-x", type=int, default=6)
    parser.add_argument("--radius-y", type=int, default=5)
    args = parser.parse_args()
    if bool(args.state) == bool(args.state_dir):
        parser.error("provide exactly one of --state or --state-dir")
    rom = args.rom.resolve()
    if args.state_dir:
        states = sorted(args.state_dir.resolve().glob("*.mss"))
        with tempfile.TemporaryDirectory(prefix="srw4-attack-states-") as temporary:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(run_one, state, rom, Path(temporary), 0, 0): state
                    for state in states
                }
                menus = []
                for future in concurrent.futures.as_completed(futures):
                    state = futures[future]
                    _dx, _dy, records, presses = future.result()
                    if records:
                        menus.append((state.name, records))
                    if 1 in records:
                        print(f"attack found: state={state} records={records}")
                        print(f"presses={presses}")
                        return 0
        print(f"attack not found; command states={sorted(menus)}")
        return 1
    state = args.state.resolve()
    positions = [
        (x, y)
        for distance in range(args.radius_x + args.radius_y + 1)
        for y in range(-args.radius_y, args.radius_y + 1)
        for x in range(-args.radius_x, args.radius_x + 1)
        if abs(x) + abs(y) == distance
    ]
    menus = []
    with tempfile.TemporaryDirectory(prefix="srw4-attack-census-") as temporary:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(run_one, state, rom, Path(temporary), x, y): (x, y)
                for x, y in positions
            }
            for future in concurrent.futures.as_completed(futures):
                dx, dy, records, presses = future.result()
                if records:
                    menus.append((dx, dy, records))
                if 1 in records:
                    print(f"attack found: dx={dx} dy={dy} records={records}")
                    print(f"presses={presses}")
                    for pending in futures:
                        pending.cancel()
                    return 0
    print(f"attack not found; command menus={sorted(menus)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
