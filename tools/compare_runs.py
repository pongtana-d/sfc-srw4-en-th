#!/usr/bin/env python3
"""Run two builds down the same route and compare what they put on screen.

A change that is supposed to be invisible -- moving the script to another bank,
say -- has to be proved invisible, and the only proof that counts is the screen
during a live run. Both builds boot cold, take the same inputs, and are
photographed at the same frames.

  tools/compare_runs.py build/srw4-th.sfc build/srw4-th-mirror.sfc
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MESEN = Path("/Applications/Mesen.app/Contents/MacOS/Mesen")
MESEN_SAVES = Path.home() / "Library" / "Application Support" / "Mesen2" / "Saves"
STOCK_SRM = MESEN_SAVES / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).srm"
LUA = ROOT / "tools" / "lua" / "route-shots.lua"
OUT_DIR = ROOT / "build" / "route"
REPORT = ROOT / "build" / "reports" / "route-compare.json"


def pulses(first: int, last: int, button: str, period: int = 30, width: int = 2) -> str:
    return ",".join(f"{f}:{f + width}:{button}" for f in range(first, last, period))


# Boot, load DATA1, take "next map" from the intermission, then keep pressing A
# through the scenario card and the conversation that follows it.
ROUTE = ",".join(
    [
        pulses(60, 900, "start"),
        "950:955:a",
        pulses(1700, 1990, "down", 40),
        "2040:2045:a",
        pulses(2100, 4980, "a", 45),
    ]
)
SHOTS = [900, 1600, 2500, 2600, 2700, 2800, 3000, 3100, 3700, 4100, 4500, 4900]
LAST = 5000
# A blank transition frame matches trivially and says nothing, so it does not
# count as evidence either.
BLANK_BYTES = 400


def digests(shots: list[Path]) -> list[str]:
    return [hashlib.sha256(shot.read_bytes()).hexdigest() for shot in shots]


def run(rom: Path, prefix: str) -> list[Path]:
    # Mesen looks for a battery save named after the ROM.
    srm = MESEN_SAVES / (rom.stem + ".srm")
    if not srm.exists() and STOCK_SRM.exists():
        shutil.copy(STOCK_SRM, srm)

    for stale in OUT_DIR.glob(f"{prefix}-*.png"):
        stale.unlink()

    env = dict(
        os.environ,
        SRW4_PRESS=ROUTE,
        SRW4_SHOTS=",".join(str(frame) for frame in SHOTS),
        SRW4_PREFIX=str(OUT_DIR / prefix),
        SRW4_LAST=str(LAST),
    )
    subprocess.run(
        [str(MESEN), "--testRunner", "--testRunnerTimeout=300", "--noAudio",
         str(rom.resolve()), str(LUA.resolve())],
        env=env,
        check=True,
    )
    return sorted(OUT_DIR.glob(f"{prefix}-*.png"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="how many times to run each build (the emulator is not repeatable)",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # The emulator does not start from the same RAM twice, and a frame caught
    # mid-scroll can land a pixel apart because of it. So each build is run
    # several times and it is the *set* of pictures a frame produces that gets
    # compared: two builds agree when their sets overlap, and only a frame
    # where they never coincide is a real difference.
    reference = [digests(run(args.reference, f"reference{i}")) for i in range(args.repeats)]
    candidate = [digests(run(args.candidate, f"candidate{i}")) for i in range(args.repeats)]
    for name, runs in (("reference", reference), ("candidate", candidate)):
        for shots in runs:
            if len(shots) != len(SHOTS):
                raise SystemExit(f"{name}: expected {len(SHOTS)} screenshots, got {len(shots)}")

    sizes = [shot.stat().st_size for shot in sorted(OUT_DIR.glob("candidate0-*.png"))]

    rows = []
    differing = 0
    skipped = 0
    for index, frame in enumerate(SHOTS):
        if sizes[index] < BLANK_BYTES:
            skipped += 1
            rows.append({"frame": frame, "compared": False, "why": "blank screen"})
            print(f"frame {frame:>5}  blank, not compared")
            continue

        left = {shots[index] for shots in reference}
        right = {shots[index] for shots in candidate}
        same = bool(left & right)
        differing += 0 if same else 1
        rows.append(
            {
                "frame": frame,
                "compared": True,
                "same": same,
                "reference_values": len(left),
                "candidate_values": len(right),
            }
        )
        spread = "" if len(left | right) == 1 else f"  ({len(left)}/{len(right)} variants)"
        print(f"frame {frame:>5}  {'same' if same else 'DIFFERENT'}{spread}")

    report = {
        "reference": str(args.reference),
        "candidate": str(args.candidate),
        "repeats": args.repeats,
        "frames": rows,
        "differing": differing,
        "not_compared": skipped,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n")

    compared = len(SHOTS) - skipped
    print(f"\n{compared - differing}/{compared} comparable frames agree"
          f" ({skipped} blank frames left out, {args.repeats} runs each)")
    if compared < 3:
        print("too few comparable frames to conclude anything", file=sys.stderr)
        return 1
    return 1 if differing else 0


if __name__ == "__main__":
    raise SystemExit(main())
