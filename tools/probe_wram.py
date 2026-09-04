#!/usr/bin/env python3
"""P1: find the parts of WRAM the game never writes, one context at a time.

The game clears all of WRAM at boot, so "never written" only means anything
once the context has been entered. Each run therefore boots (or loads a state
this build made), settles, resets Mesen's access counters, and only then
records what gets written while the context is exercised.

  tools/probe_wram.py --list
  tools/probe_wram.py boot map
  tools/probe_wram.py --all
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

MESEN = Path("/Applications/Mesen.app/Contents/MacOS/Mesen")
ROM = ROOT / "build" / "srw4-en-th.sfc"
LUA = ROOT / "tools" / "lua" / "wram-probe.lua"
STATE_DIR = ROOT / "build" / "states"
OUT_DIR = ROOT / "build" / "wram"
REPORT = ROOT / "build" / "reports" / "wram.json"
WRAM_MAP = ROOT / "data" / "config" / "wram-map.json"

WRAM_BASE = 0x7E0000
WRAM_SIZE = 0x20000
# Everything below $7E:2000 is mirrored into banks $00-$3F, so a write through
# the mirror lands there without ever naming $7E. Our own state stays above it
# rather than trying to prove the mirror is quiet as well.
SAFE_FLOOR = 0x7E2000

def pulses(first: int, last: int, button: str, period: int = 30, width: int = 2) -> str:
    """Tap a button repeatedly. A held button is one press to the game."""
    return ",".join(
        f"{frame}:{frame + width}:{button}" for frame in range(first, last, period)
    )


# The cold-boot route from docs/08-verification.md, split per context. Frames
# are wall-clock in the emulator, so each context gets a settle window before
# the counters are reset.
CONTEXTS: dict[str, dict] = {
    "boot": {
        "last": 400,
        "reset_at": 200,
        "press": "",
        "note": "logo and boot code, no input at all",
    },
    "title": {
        "last": 1300,
        "reset_at": 900,
        "press": pulses(60, 900, "start"),
        "note": "title and the load menu",
    },
    "load-save": {
        "last": 1600,
        "reset_at": 1300,
        "press": pulses(60, 900, "start") + ",950:955:a",
        "save": "1580:" + str(STATE_DIR / "intermission.mss"),
        "note": "boot, load DATA1, land on the intermission screen",
    },
    "intermission": {
        "load": str(STATE_DIR / "intermission.mss"),
        "last": 700,
        "reset_at": 120,
        "press": pulses(150, 650, "down", 40),
        "note": "moving the intermission cursor so panels really redraw",
    },
    "scenario": {
        "load": str(STATE_DIR / "intermission.mss"),
        "last": 2600,
        "reset_at": 900,
        "press": pulses(150, 440, "down", 40) + ",520:525:a," + pulses(600, 2580, "a", 45),
        "save": "2580:" + str(STATE_DIR / "map.mss"),
        "note": "next map, the scenario card, the opening conversation, then the map",
    },
    "map": {
        "load": str(STATE_DIR / "map.mss"),
        "last": 700,
        "reset_at": 120,
        "press": pulses(150, 300, "right", 30) + "," + pulses(320, 500, "down", 30)
        + "," + pulses(520, 650, "left", 30),
        "note": "moving the map cursor around",
    },
    "dialogue": {
        "load": str(STATE_DIR / "map.mss"),
        "last": 700,
        "reset_at": 120,
        "press": pulses(150, 250, "a", 40) + "," + pulses(300, 500, "down", 30) + "," + pulses(550, 650, "b", 40),
        "note": "the story window drawing text over the map, portrait and all",
    },
}


def run(name: str, spec: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    dump = OUT_DIR / f"{name}.bin"
    shot = OUT_DIR / f"{name}.png"

    env = dict(
        os.environ,
        SRW4_OUT=str(dump),
        SRW4_SHOT=str(shot),
        SRW4_LAST=str(spec["last"]),
        SRW4_RESET_AT=str(spec["reset_at"]),
        SRW4_PRESS=spec.get("press", ""),
    )
    if "load" in spec:
        env["SRW4_LOAD"] = spec["load"]
    if "save" in spec:
        env["SRW4_SAVE"] = spec["save"]

    subprocess.run(
        [
            str(MESEN),
            "--testRunner",
            f"--testRunnerTimeout={max(120, spec['last'] // 4)}",
            "--noAudio",
            str(ROM.resolve()),
            str(LUA.resolve()),
        ],
        env=env,
        check=True,
    )
    if not dump.exists():
        raise SystemExit(f"{name}: Mesen exited without writing {dump}")
    return dump


def spans(written: bytes, floor: int) -> list[tuple[int, int]]:
    """Contiguous ranges that were never written, as absolute PC addresses."""
    out: list[tuple[int, int]] = []
    start = None
    for offset in range(floor - WRAM_BASE, WRAM_SIZE):
        if written[offset] == 0:
            if start is None:
                start = offset
        elif start is not None:
            out.append((WRAM_BASE + start, WRAM_BASE + offset))
            start = None
    if start is not None:
        out.append((WRAM_BASE + start, WRAM_BASE + WRAM_SIZE))
    return out


def reserved_spans() -> list[tuple[str, int, int]]:
    document = json.loads(WRAM_MAP.read_text())
    out = []
    for region in document["regions"]:
        for context in region.get("contexts", []):
            out.append((context["id"], int(context["start"], 16), int(context["end"], 16)))
        arena = region.get("arena")
        if arena:
            out.append((f"{region['id']}.arena", int(arena["start"], 16), int(arena["end"], 16)))
    return out


def verify() -> int:
    """Every reserved byte must be untouched in every run that produced evidence."""
    if not REPORT.exists():
        raise SystemExit("no build/reports/wram.json yet: probe some contexts first")
    report = json.loads(REPORT.read_text())
    counted = report["quiet_in_every_context"].get("contexts_counted", [])
    if not counted:
        raise SystemExit("the report has no context with evidence in it")

    problems = []
    for name in counted:
        written = (OUT_DIR / f"{name}.bin").read_bytes()
        for owner, start, end in reserved_spans():
            hits = [
                address
                for address in range(start, end)
                if written[address - WRAM_BASE]
            ]
            if hits:
                problems.append(
                    {"context": name, "owner": owner, "first_hit": f"{hits[0]:#08x}", "hits": len(hits)}
                )

    total = sum(end - start for _, start, end in reserved_spans())
    print(f"{total:,} reserved bytes checked against {len(counted)} context(s): {', '.join(counted)}")
    if not problems:
        print("clean: the game never wrote into any of them")
        return 0
    for problem in problems:
        print(
            f"  {problem['context']} wrote into {problem['owner']} "
            f"({problem['hits']} bytes, first at {problem['first_hit']})"
        )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contexts", nargs="*", help="which contexts to run")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="check the reserved spans in data/config/wram-map.json against the dumps",
    )
    args = parser.parse_args()

    if args.list:
        for name, spec in CONTEXTS.items():
            print(f"{name:<10} {spec['note']}")
        return 0

    if args.verify:
        return verify()

    names = list(CONTEXTS) if args.all else args.contexts
    if not names:
        parser.error("name at least one context, or pass --all")
    if not ROM.exists():
        raise SystemExit(
            f"no build to probe: run tools/build_en_th_full_dialogue.py first ({ROM})"
        )

    results = {}
    for name in names:
        spec = CONTEXTS.get(name)
        if spec is None:
            raise SystemExit(f"unknown context: {name}")
        print(f"--- {name}: {spec['note']}")
        written = run(name, spec).read_bytes()
        quiet = spans(written, SAFE_FLOOR)
        total = sum(end - start for start, end in quiet)
        touched = sum(1 for value in written[SAFE_FLOOR - WRAM_BASE :] if value)
        results[name] = {
            # A run that wrote nothing at all proves nothing: the game was idle,
            # or the input never reached it. Say so instead of counting it.
            "no_evidence": touched == 0,
            "bytes_written": touched,
            "note": spec["note"],
            "frames": spec["last"],
            "counters_reset_at": spec["reset_at"],
            "quiet_bytes": total,
            "largest_span": max((end - start for start, end in quiet), default=0),
            "spans": [
                {"start": f"{s:#08x}", "end": f"{e:#08x}", "bytes": e - s}
                for s, e in quiet
                if e - s >= 64
            ],
        }
        if touched == 0:
            print("    NO EVIDENCE: nothing was written; this run does not count")
        else:
            print(f"    quiet above {SAFE_FLOOR:#08x}: {total:,} bytes in {len(quiet)} spans")

    # What is quiet in every context that actually produced evidence.
    counted = [name for name in names if not results[name]["no_evidence"]]
    common = None
    for name in counted:
        written = (OUT_DIR / f"{name}.bin").read_bytes()
        touched = {i for i, value in enumerate(written) if value}
        common = touched if common is None else common | touched
    quiet_everywhere = spans(
        bytes(1 if i in common else 0 for i in range(WRAM_SIZE)), SAFE_FLOOR
    )

    report = {
        "stage": "P1",
        "rom": {
            "path": str(ROM.relative_to(ROOT)),
            "note": "built by tools/build_en_th_full_dialogue.py",
        },
        "mirror_floor": f"{SAFE_FLOOR:#08x}",
        "contexts": results,
        "quiet_in_every_context": {
            "bytes": sum(e - s for s, e in quiet_everywhere),
            "spans": [
                {"start": f"{s:#08x}", "end": f"{e:#08x}", "bytes": e - s}
                for s, e in quiet_everywhere
                if e - s >= 256
            ],
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n")

    report["quiet_in_every_context"]["contexts_counted"] = counted
    report["quiet_in_every_context"]["contexts_ignored"] = [
        name for name in names if name not in counted
    ]
    REPORT.write_text(json.dumps(report, indent=2) + "\n")

    quiet = report["quiet_in_every_context"]
    print(f"\nquiet in all {len(counted)} context(s) with evidence: {quiet['bytes']:,} bytes")
    if quiet["contexts_ignored"]:
        print(f"ignored (no writes at all): {', '.join(quiet['contexts_ignored'])}")
    for span in quiet["spans"][:10]:
        print(f"    {span['start']}-{span['end']}  {span['bytes']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
