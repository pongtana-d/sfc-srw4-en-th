#!/usr/bin/env python3
"""Compare what the game drew with what the reference renderer says it should.

The blitter is already checked against the reference in a fixture ROM. This is
the same check on the real thing: play until a message has finished, read the
tile arena straight out of the machine, and hold it against the picture the
Python renderer produces for that record.

  tools/check_dialogue.py
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.pipeline import Pipeline  # noqa: E402
from srw4.png import write_greyscale  # noqa: E402

MESEN = Path("/Applications/Mesen.app/Contents/MacOS/Mesen")
ROM = ROOT / "build" / "srw4-th-thai.sfc"
LUA = ROOT / "tools" / "lua" / "dump-arena.lua"
LAYOUT = ROOT / "build" / "reports" / "script-layout.json"
DUMP = ROOT / "build" / "reports" / "arena.bin"
REPORT = ROOT / "build" / "reports" / "dialogue.json"
SHOT = ROOT / "build" / "reports" / "dialogue.png"
CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
TRANSLATION = ROOT / "data" / "translations" / "script.th.json"

CELL_BYTES = 64


def run(after: int, every: int, skip: int) -> tuple[bytes, dict]:
    for path in (DUMP, DUMP.with_suffix(".bin.txt"), SHOT):
        if path.exists():
            path.unlink()
    env = dict(
        os.environ,
        SRW4_OUT=str(DUMP),
        SRW4_AFTER=str(after),
        SRW4_EVERY=str(every),
        SRW4_SKIP=str(skip),
        SRW4_SHOT=str(SHOT),
    )
    subprocess.run(
        [str(MESEN), "--testRunner", "--testRunnerTimeout=300", "--noAudio",
         str(ROM.resolve()), str(LUA.resolve())],
        env=env,
        check=True,
    )
    if not DUMP.exists() or not SHOT.exists():
        raise SystemExit("the emulator did not write the arena dump and screenshot")
    meta = {}
    for line in (DUMP.with_suffix(".bin.txt")).read_text().splitlines():
        key, _, value = line.partition(" ")
        meta[key] = value
    return DUMP.read_bytes(), meta


def cell_rows(data: bytes, cell: int) -> list[int]:
    base = cell * CELL_BYTES
    return [data[base + r * 2] for r in range(8)] + [data[base + 0x20 + r * 2] for r in range(8)]


def find_record(layout: dict, pointer: int) -> str | None:
    bank, offset = pointer >> 16, pointer & 0xFFFF
    for mid, entry in layout.items():
        if entry["bank"] == bank and entry["offset"] <= offset < entry["offset"] + entry["bytes"]:
            return mid
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--after", type=int, default=20, help="glyphs before we start waiting")
    parser.add_argument("--every", type=int, default=90, help="frames between button presses")
    parser.add_argument("--skip", type=int, default=0, help="let this many records go by first")
    args = parser.parse_args()

    if not ROM.exists() or not LAYOUT.exists():
        raise SystemExit("build the Thai ROM first: tools/build.py --relocate thai --out ...")

    data, meta = run(args.after, args.every, args.skip)
    layout = json.loads(LAYOUT.read_text())
    pointer = int(meta.get("first", "0"), 16)
    mid = find_record(layout, pointer)
    if mid is None:
        raise SystemExit(f"nothing in the layout holds the pointer {pointer:#08x}")

    pipeline = Pipeline.load(ROOT, CLEAN_ROM)
    text = json.loads(TRANSLATION.read_text())["messages"][mid]
    drawn = pipeline.draw(text, where=mid)

    # Where each line starts is not a fixed stride: the engine decides, and a
    # window lower down the screen begins much further into the arena. The
    # adapter records the base it used for each line, so use those.
    bases = [int(value, 16) for value in meta.get("bases", "").split(",") if value]
    if len(bases) < len(drawn.lines):
        raise SystemExit(
            f"{mid} draws {len(drawn.lines)} lines but only {len(bases)} line bases were seen"
        )

    rows = []
    mismatches = []
    for number, line in enumerate(drawn.lines):
        expected = line.canvas.to_rows()
        cells = max(1, (line.width + 7) // 8)
        for cell in range(cells):
            got = cell_rows(data, bases[number] // 2 + cell)
            want = [expected[row][cell] for row in range(16)]
            if got != want:
                mismatches.append({"line": number, "cell": cell, "rom": got, "reference": want})
        rows.append(
            {"line": number, "cells": cells, "width": line.width, "base": f"{bases[number]:#06x}"}
        )

    report = {
        "record": mid,
        "text": text,
        "pointer": f"{pointer:#08x}",
        "lines": rows,
        "cells_compared": sum(entry["cells"] for entry in rows),
        "cells_differing": len(mismatches),
        "mismatches": mismatches[:8],
        "screenshot": str(SHOT.relative_to(ROOT)) if SHOT.exists() else None,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    print(f"record {mid}: {text[:60]!r}")
    print(f"{report['cells_compared']} cells compared, {report['cells_differing']} differ")
    for entry in mismatches[:4]:
        print(f"   line {entry['line']} cell {entry['cell']}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
