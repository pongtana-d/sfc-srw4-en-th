#!/usr/bin/env python3
"""Bring glyph edits made in a font editor back into the build.

Every glyph in the edited BDF is compared with what the atlas builds today.
Anything that differs becomes an entry in `renewal-overrides.json`, which the
atlas builder honours -- and which it refuses to accept without a reason.

  tools/import_font.py edited.bdf                     show what changed
  tools/import_font.py edited.bdf --reason "..." -w   write the overrides
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.atlas import AtlasBuilder  # noqa: E402
from srw4.bdf import BdfError, codepoint_for, read  # noqa: E402
from srw4.rom import Rom  # noqa: E402
from srw4.tokens import TokenMap  # noqa: E402

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
FONT_DIR = ROOT / "data" / "font"
OVERRIDES = FONT_DIR / "renewal-overrides.json"


def art(rows: tuple[int, ...]) -> list[str]:
    return ["".join("#" if row >> (7 - x) & 1 else "." for x in range(8)) for row in rows]


def diff(path: Path) -> list[dict]:
    token_map = TokenMap.load(FONT_DIR / "renewal-clusters.json")
    builder = AtlasBuilder(FONT_DIR, Rom.load_clean(CLEAN_ROM).to_bytes())
    edited = read(path.read_text())

    changes = []
    for token in token_map.tokens:
        codepoint = codepoint_for(token, token_map.index(token))
        incoming = edited.get(codepoint)
        if incoming is None:
            continue  # the editor may hold only part of the set
        current = builder.build(token)
        if incoming.rows == current.rows and incoming.advance == current.advance:
            continue
        changes.append(
            {
                "token": token,
                "codepoint": codepoint,
                "rows": list(incoming.rows),
                "advance": incoming.advance,
                "was_advance": current.advance,
                "before": art(current.rows),
                "after": art(incoming.rows),
            }
        )
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bdf", type=Path)
    parser.add_argument("--reason", help="why these glyphs were changed by hand")
    parser.add_argument("-w", "--write", action="store_true", help="apply to renewal-overrides.json")
    args = parser.parse_args()

    try:
        changes = diff(args.bdf)
    except (BdfError, OSError) as exc:
        print(f"cannot read {args.bdf}: {exc}", file=sys.stderr)
        return 1

    if not changes:
        print(f"{args.bdf}: no glyph differs from the current atlas")
        return 0

    print(f"{len(changes)} glyph(s) changed:")
    for change in changes:
        print(f"\n  {change['token']}  advance {change['was_advance']} -> {change['advance']}")
        for before, after in zip(change["before"], change["after"]):
            marker = "  " if before == after else " *"
            print(f"    {before}  {after}{marker}")

    if not args.write:
        print("\nnothing written; rerun with --reason \"...\" --write to keep these")
        return 0
    if not args.reason:
        print("\n--write needs --reason: an override without one fails the build", file=sys.stderr)
        return 1

    document = json.loads(OVERRIDES.read_text())
    for change in changes:
        document["overrides"][change["token"]] = {
            "rows": change["rows"],
            "advance": change["advance"],
            "reason": args.reason,
            "sample": f"{args.bdf.name}:{change['codepoint']}",
        }
    OVERRIDES.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(changes)} override(s) to {OVERRIDES.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
