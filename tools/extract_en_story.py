#!/usr/bin/env python3
"""Extract the English story source map; this command never writes a ROM."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_baseline import EN_SHA256  # noqa: E402
from srw4.en_story_extract import extract_story  # noqa: E402
from srw4.rom import RomError, sha256  # noqa: E402

ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (English combo).sfc"
SUMMARY = ROOT / "data" / "translations" / "script.source.json"
OUT = ROOT / "data" / "reference" / "en-story.source.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=ROM)
    parser.add_argument("--summary", type=Path, default=SUMMARY)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    try:
        rom = args.rom.read_bytes()
        if sha256(rom) != EN_SHA256:
            raise RomError("English-combo ROM hash does not match the locked base")
        summary = json.loads(args.summary.read_text(encoding="utf-8"))["summary"]["blocks"]
        document = extract_story(rom, summary)
    except (KeyError, OSError, ValueError, RomError) as exc:
        print(f"EN story extraction failed: {exc}", file=sys.stderr)
        return 1

    output = args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    result = document["summary"]
    print(
        f"extracted {result['text_blocks']} text + {result['record_blocks']} record blocks; "
        f"{result['pointer_slots']} pointers; {result['pointer_reachable_records']} reachable records"
    )
    print(f"source: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
