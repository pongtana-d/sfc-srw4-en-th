#!/usr/bin/env python3
"""Verify title, protagonist preset/confirm, and intro from isolated cold boot."""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
MESEN = Path("/Applications/Mesen.app/Contents/MacOS/Mesen")
DEFAULT_ROM = ROOT / "build" / "srw4-th-test.sfc"
TITLE_LUA = ROOT / "tools" / "lua" / "cold-title-menu.lua"
FLOW_LUA = ROOT / "tools" / "lua" / "cold-naming-settle.lua"

GOLDEN = {
    "title-0900": "51a8f5c84c3cb27c84636c42a86268e2b1f4364893085adc0d693a6d453d1717",
    # Static title/tabs crop; face and preset values are intentionally random.
    "flow-0900-static": "ee79296777d0544e47b356ae87cf4e5eab3e1ca6e29221d4e1f4207423796b49",
    "flow-2000": "e2ae965fd97666fdefed7d8137d97f3520e069c4b54fdd1bf94e93a1b7c89dfa",
    "flow-2400": "c5b0f49f30af937a9289addb9566200d28ce17b05a23d4c3a4cacbe96874df71",
    "flow-3200": "fa023ffcfa1c44be7a67ce53a00a009c5bad8f4fa966b5c1e0e4804846111f15",
}


def run_route(rom: Path, script: Path, prefix: Path) -> None:
    run = subprocess.run(
        [
            str(MESEN), "--testRunner", "--testRunnerTimeout=600", "--noAudio",
            str(rom), str(script),
        ],
        env=dict(os.environ, SRW4_PREFIX=str(prefix)),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if run.returncode:
        raise SystemExit(
            f"Mesen cold route failed with exit code {run.returncode}\n{run.stdout[-4000:]}"
        )


def digest(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"cold runtime screenshot missing: {path.name}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def crop_digest(path: Path, box: tuple[int, int, int, int]) -> str:
    if not path.is_file():
        raise SystemExit(f"cold runtime screenshot missing: {path.name}")
    with Image.open(path) as image:
        pixels = image.convert("RGBA").crop(box).tobytes()
    return hashlib.sha256(pixels).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    args = parser.parse_args()
    source = args.rom.resolve()
    for path, label in ((MESEN, "Mesen"), (source, "ROM")):
        if not path.is_file():
            raise SystemExit(f"{label} is missing: {path}")

    with tempfile.TemporaryDirectory(prefix="srw4-cold-runtime-") as temporary:
        work = Path(temporary)
        title_rom = work / "isolated-title.sfc"
        flow_rom = work / "isolated-flow.sfc"
        shutil.copy2(source, title_rom)
        shutil.copy2(source, flow_rom)
        run_route(title_rom, TITLE_LUA, work / "title")
        run_route(flow_rom, FLOW_LUA, work / "flow")

        actual = {
            "title-0900": digest(work / "title-0900.png"),
            "flow-0900-static": crop_digest(
                work / "flow-0900.png", (0, 32, 256, 78)
            ),
            "flow-2000": digest(work / "flow-2000.png"),
            "flow-2400": digest(work / "flow-2400.png"),
            "flow-3200": digest(work / "flow-3200.png"),
        }
        failures = [
            f"{name}: expected {GOLDEN[name]}, got {value}"
            for name, value in actual.items() if value != GOLDEN[name]
        ]
        if failures:
            raise SystemExit("cold runtime gate failed\n  " + "\n  ".join(failures))

    print("cold runtime gate passed: title, Thai preset/confirm, and intro redraws")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
