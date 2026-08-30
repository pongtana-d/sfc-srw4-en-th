#!/usr/bin/env python3
"""Summarize English story byte-fetch traces without modifying ROM/state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_story_trace import trace_report  # noqa: E402
from srw4.rom import RomError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--story", type=Path, default=ROOT / "build" / "en-trace" / "byte-trace" / "story.txt")
    parser.add_argument("--battle", type=Path, default=ROOT / "build" / "en-trace" / "byte-trace" / "battle.txt")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "reports" / "en-story-runtime-trace.json")
    args = parser.parse_args()
    try:
        document = trace_report({"map_dialogue": args.story, "battle_quote": args.battle})
    except (OSError, RomError) as exc:
        print(f"EN story trace analysis failed: {exc}", file=sys.stderr)
        return 1
    output = args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    for name, context in document["contexts"].items():
        print(f"{name}: {context['fetches']} fetches; {len(context['nonsequential_transitions'])} transitions")
    print(f"report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
