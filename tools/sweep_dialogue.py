#!/usr/bin/env python3
"""Draw records from every block on the machine and check them against P4.

`check_dialogue.py` only ever sees what the opening scene happens to show. The
pass mark for P6 is every block, so the record under test is substituted into
the running engine instead: at `$C1:9366` the message pointer is already
resolved and sitting in `$CB-$CD`, one instruction before drawing starts.

  tools/sweep_dialogue.py                 one record from each block
  tools/sweep_dialogue.py --per-block 3   three, spread through the block
  tools/sweep_dialogue.py --ids 14_6F0F   named records
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

MESEN = Path("/Applications/Mesen.app/Contents/MacOS/Mesen")
ROM = Path(os.environ.get("SRW4_SWEEP_ROM", ROOT / "build" / "srw4-th-thai.sfc"))
LUA = ROOT / "tools" / "lua" / "sweep-records.lua"
LAYOUT = ROOT / "build" / "reports" / "script-layout.json"
DUMP = ROOT / "build" / "reports" / "sweep.bin"
REPORT = ROOT / "build" / "reports" / "sweep.json"
CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
TRANSLATION = ROOT / "data" / "translations" / "script.th.json"

CELL_BYTES = 64
SPAN = 16384


def cell_rows(data: bytes, cell: int) -> list[int]:
    base = cell * CELL_BYTES
    return [data[base + r * 2] for r in range(8)] + [data[base + 0x20 + r * 2] for r in range(8)]


def pick(layout: dict, translations: dict, per_block: int,
         blocks: range | None = None) -> list[str]:
    """Records worth drawing: spread through each block, text-bearing, short.

    A record that ends in `$F7` waits for the next one instead of closing the
    window, and a record whose text is empty proves nothing, so neither is
    chosen. Nor is one too tall for its window: the engine pages, and the
    arena then holds only the last page. Being choosy here is fine -- the
    point is coverage across blocks, not a census.
    """
    windows = json.loads((ROOT / "data" / "config" / "text-windows.json").read_text())["windows"]
    by_block: dict[int, list[str]] = {}
    for mid, entry in layout.items():
        text = translations.get(mid, "")
        if not entry["thai"] or "<ENDFF>" not in text:
            continue
        if len(text) < 30 or text.count("\n") >= 3:
            continue
        by_block.setdefault(int(mid.split("_")[0]), []).append(mid)

    chosen: list[str] = []
    for block in sorted(by_block):
        if blocks is not None and block not in blocks:
            continue
        ids = sorted(by_block[block])
        step = max(1, len(ids) // (per_block + 1))
        chosen += [ids[min(len(ids) - 1, step * (n + 1))] for n in range(per_block)]
    return chosen


NAME_TABLE = 0x018E6E          # $C1:8E6E, three bytes per `$FB xx 80` id


def name_buffers(pairs: list[str], pipeline: Pipeline) -> tuple[dict[int, str], dict[str, str]]:
    """Runtime names to hold in WRAM, and what to put in the reference.

    `$FB xx 80` does not carry a name -- it sends the engine to a buffer that
    the game fills at runtime. Nothing in the record says what will be in it,
    so a record using one can only be checked if we decide what the buffer
    holds and tell the reference the same thing.
    """
    rom = CLEAN_ROM.read_bytes()
    buffers: dict[int, str] = {}
    expansions: dict[str, str] = {}
    for pair in pairs:
        key, _, text = pair.partition("=")
        index = int(key, 16)
        at = NAME_TABLE + index
        address = rom[at] | rom[at + 1] << 8
        bank = rom[at + 2]
        if bank != 0x00:
            raise SystemExit(f"name {key} lives in bank {bank:#04x}, not low WRAM")
        data = pipeline.compile(text, where=f"name {key}").data + b"\xff"
        if len(data) > 7:
            raise SystemExit(f"{text!r} is {len(data)} bytes; the buffer holds seven")
        buffers[address] = data.hex().upper()
        expansions[f"<FB:{index:02X}80>"] = text
    return buffers, expansions


def run(pointers: list[int], every: int, names: dict[int, str]) -> tuple[bytes, list[str]]:
    for path in (DUMP, DUMP.with_suffix(".bin.txt")):
        if path.exists():
            path.unlink()
    env = dict(
        os.environ,
        SRW4_OUT=str(DUMP),
        SRW4_TARGETS=",".join(f"{p:06X}" for p in pointers),
        SRW4_SPAN=str(SPAN),
        SRW4_EVERY=str(every),
        SRW4_NAMES=",".join(f"{at:04X}:{hex_}" for at, hex_ in sorted(names.items())),
    )
    subprocess.run(
        [str(MESEN), "--testRunner", "--testRunnerTimeout=1800", "--noAudio",
         str(ROM.resolve()), str(LUA.resolve())],
        env=env,
    )
    if not DUMP.exists():
        raise SystemExit("the emulator wrote no dump at all")
    return DUMP.read_bytes(), Path(str(DUMP) + ".txt").read_text().splitlines()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-block", type=int, default=1)
    parser.add_argument("--every", type=int, default=45)
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--blocks", help="only these blocks, as FIRST-LAST")
    parser.add_argument(
        "--name",
        action="append",
        default=[],
        metavar="ID=TEXT",
        help="hold a runtime name buffer, e.g. 1E=เจส; the escape is expanded "
             "in the reference too, so the two can be compared",
    )
    args = parser.parse_args()

    layout = json.loads(LAYOUT.read_text())
    translations = json.loads(TRANSLATION.read_text())["messages"]
    blocks = None
    if args.blocks:
        first, _, last = args.blocks.partition("-")
        blocks = range(int(first), int(last or first) + 1)
    ids = args.ids or pick(layout, translations, args.per_block, blocks)
    pointers = [(layout[mid]["bank"] << 16) | layout[mid]["offset"] for mid in ids]
    print(f"{len(ids)} records from {len({i.split('_')[0] for i in ids})} blocks")

    pipeline = Pipeline.load(ROOT, CLEAN_ROM)
    names, expansions = name_buffers(args.name, pipeline)
    data, lines = run(pointers, args.every, names)

    results, drawn_count, bad = [], 0, 0
    skipped: list[str] = []
    for index, line in enumerate(lines):
        parts = line.split()
        if len(parts) < 2 or len(parts[0]) != 6 or line.startswith("--"):
            continue                                  # notes and the status line
        try:
            int(parts[0], 16)
        except ValueError:
            continue
        mid = ids[index]
        bases = [int(v, 16) for v in (parts[2].split(",") if len(parts) > 2 else [])]
        block = data[index * SPAN : (index + 1) * SPAN]
        text = translations[mid]
        for escape, name in expansions.items():
            text = text.replace(escape, name)
        drawn = pipeline.draw(text, where=mid)
        entry = {"id": mid, "pointer": parts[0], "glyphs": int(parts[1]),
                 "lines": len(drawn.lines), "bases": [f"{b:#06x}" for b in bases]}
        # One base per line, or the record moved the cursor itself: `$FC:05`
        # and friends reposition mid-line, and the adapter starts a fresh line
        # wherever the engine puts the cursor. The reference draws one flat
        # line, so there is nothing to hold those against -- say so rather
        # than call it a failure.
        # A base that goes backwards means the window filled and the engine
        # started a new page over the top of the old one, so the arena no
        # longer holds the whole record. That happens when a record written
        # for the nine-line profile frame is put in the three-line one.
        paged = any(b <= a for a, b in zip(bases, bases[1:]))
        if len(bases) != len(drawn.lines) or paged:
            why = "paged" if paged else "repositions"
            entry["result"] = f"{why}: {len(bases)} bases for {len(drawn.lines)} lines"
            skipped.append(mid)
            results.append(entry)
            continue
        compared = differing = 0
        for number, rendered in enumerate(drawn.lines):
            expected = rendered.canvas.to_rows()
            for cell in range((rendered.width + 7) // 8):
                compared += 1
                got = cell_rows(block, bases[number] // 2 + cell)
                if got != [expected[row][cell] for row in range(16)]:
                    differing += 1
        entry.update(result="ok" if not differing else "differs",
                     cells=compared, differing=differing)
        drawn_count += 1
        bad += 1 if differing else 0
        results.append(entry)

    report = {"stage": "P6 sweep", "requested": len(ids), "drawn": len(results),
              "compared": drawn_count, "failing": bad,
              "not_comparable": skipped, "records": results}
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    for entry in results:
        result = entry.get("result", "")
        flag = "ok  " if result == "ok" else ("--  " if result.startswith(("repositions", "paged")) else "FAIL")
        print(f"  {flag} {entry['id']:<10} {entry.get('cells', 0):>3} cells"
              f"  {entry.get('differing', '-')} differ  {entry.get('result')}")
    print(f"\n{drawn_count}/{len(ids)} records drawn and compared, {bad} failing"
          + (f", {len(skipped)} not comparable (repositioned or paged)"
             if skipped else ""))
    return 1 if bad or drawn_count + len(skipped) < len(ids) else 0


if __name__ == "__main__":
    raise SystemExit(main())
