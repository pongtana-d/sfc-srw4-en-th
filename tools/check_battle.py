#!/usr/bin/env python3
"""P7: run a battle from a save state and name every record it draws.

The map route cannot reach a battle in a reasonable number of frames, so the
position comes from a save state -- but the state was made by another build,
so nothing already on its screen means anything. Only what the machine draws
after the state is loaded counts, which is what this reads: the stream pointer
at every glyph, turned back into record ids through the layout.

  tools/check_battle.py                       the stock battle state
  tools/check_battle.py --state saves/states/battle-animation.mss
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
ROM = ROOT / "build" / "srw4-th-thai.sfc"
LUA = ROOT / "tools" / "lua" / "from-state.lua"
LAYOUT = ROOT / "build" / "reports" / "script-layout.json"
TRANSLATION = ROOT / "data" / "translations" / "script.th.json"
REPORT = ROOT / "build" / "reports" / "battle.json"
OUT = ROOT / "build" / "battle" / "shot"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path,
                        default=ROOT / "saves" / "states" / "battle-in-range.mss")
    parser.add_argument("--press", default="60:a")
    parser.add_argument("--shots", default="300,480,660,860")
    args = parser.parse_args()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pointers = Path(f"{OUT}-pointers.txt")
    if pointers.exists():
        pointers.unlink()
    subprocess.run(
        [str(MESEN), "--testRunner", "--testRunnerTimeout=300", "--noAudio",
         str(ROM.resolve()), str(LUA.resolve())],
        env=dict(os.environ, SRW4_STATE=str(args.state.resolve()), SRW4_OUT=str(OUT),
                 SRW4_PRESS=args.press, SRW4_SHOTS=args.shots),
    )
    if not pointers.exists():
        raise SystemExit("the battle drew nothing: the state never reached the loop")

    layout = json.loads(LAYOUT.read_text())
    translations = json.loads(TRANSLATION.read_text())["messages"]
    spans = [(e["bank"], e["offset"], e["offset"] + e["bytes"], mid)
             for mid, e in layout.items()]

    drawn, unknown = [], 0
    for line in pointers.read_text().splitlines():
        value, _, when = line.partition(" @")
        p = int(value, 16)
        bank, offset = p >> 16, p & 0xFFFF
        found = next((mid for b, lo, hi, mid in spans if b == bank and lo <= offset < hi), None)
        entry = {"pointer": value, "frame": int(when), "id": found,
                 "text": translations.get(found, "") if found else None}
        # A pointer outside the script is the game's own text -- a catalog name
        # drawn by the stock rasteriser -- not something we got wrong.
        entry["ours"] = 0xF0 <= bank <= 0xF8
        if entry["ours"] and found is None:
            unknown += 1
        drawn.append(entry)

    REPORT.write_text(json.dumps({"state": str(args.state.relative_to(ROOT)),
                                  "drawn": drawn, "unplaced": unknown},
                                 indent=2, ensure_ascii=False) + "\n")
    for e in drawn:
        where = e["id"] or ("NOT IN THE LAYOUT" if e["ours"] else "the game's own")
        print(f"  @{e['frame']:>4}  ${e['pointer']}  {where}")
        if e["text"]:
            print(f"          {e['text'][:64]!r}")
    print(f"\n{len(drawn)} records drawn, {unknown} of ours land nowhere")
    return 1 if unknown else 0


if __name__ == "__main__":
    raise SystemExit(main())
