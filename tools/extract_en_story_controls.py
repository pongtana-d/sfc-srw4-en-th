#!/usr/bin/env python3
"""Extract the EN story control dispatch contract; does not modify a ROM."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_baseline import EN_SHA256  # noqa: E402
from srw4.en_story_controls import story_control_contract  # noqa: E402
from srw4.rom import RomError, sha256  # noqa: E402

ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (English).sfc"
OUT = ROOT / "data" / "reference" / "en-story-control-contract.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=ROM)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    try:
        rom = args.rom.read_bytes()
        if sha256(rom) != EN_SHA256:
            raise RomError("English ROM hash does not match the P0-locked base")
        document = story_control_contract(rom)
    except (OSError, RomError) as exc:
        print(f"EN story control extraction failed: {exc}", file=sys.stderr)
        return 1
    output = args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"extracted {len(document['dispatch'])} indirect handlers: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
