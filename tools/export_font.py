#!/usr/bin/env python3
"""Export the atlas as a BDF so it can be opened in a font editor.

  tools/export_font.py             every glyph (review copy, stays local)
  tools/export_font.py --no-rom    leave out glyphs imported from the game font

The `--no-rom` set carries no pixel from the ROM, which is the set that may be
shared outside this project. The full set is for checking our own work.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.atlas import AtlasBuilder  # noqa: E402
from srw4.bdf import BdfGlyph, codepoint_for, write  # noqa: E402
from srw4.rom import Rom  # noqa: E402
from srw4.tokens import TokenMap  # noqa: E402

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
FONT_DIR = ROOT / "data" / "font"
OUT_DIR = ROOT / "build" / "font-kit"

FULL_NOTE = (
    "Review copy: includes glyph images imported from the game's own font. "
    "Do not redistribute."
)
CLEAN_NOTE = "No pixel in this file comes from the game ROM."


def collect(include_rom: bool) -> list[BdfGlyph]:
    token_map = TokenMap.load(FONT_DIR / "renewal-clusters.json")
    builder = AtlasBuilder(FONT_DIR, Rom.load_clean(CLEAN_ROM).to_bytes())

    glyphs = []
    for token in token_map.tokens:
        glyph = builder.build(token)
        if glyph.source == "stock" and not include_rom:
            continue
        glyphs.append(
            BdfGlyph(
                token=token,
                codepoint=codepoint_for(token, token_map.index(token)),
                advance=glyph.advance,
                rows=glyph.rows,
            )
        )
    return glyphs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-rom", action="store_true", help="omit glyphs taken from the ROM font")
    args = parser.parse_args()

    include_rom = not args.no_rom
    glyphs = collect(include_rom)
    name = "srw4-thai-8x16.bdf" if include_rom else "srw4-thai-8x16-no-rom.bdf"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / name).write_text(write(glyphs, note=FULL_NOTE if include_rom else CLEAN_NOTE))
    (OUT_DIR / "bdf-index.json").write_text(
        json.dumps(
            {
                "_note": "codepoint -> token, so an edited BDF can be matched back up",
                "codepoints": {str(g.codepoint): g.token for g in glyphs},
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n"
    )

    pua = sum(1 for g in glyphs if g.codepoint >= 0xE000)
    print(f"{OUT_DIR.relative_to(ROOT) / name}: {len(glyphs)} glyphs ({pua} in the private use area)")
    print("open it in FontForge, BitFontMaker2 or any editor that reads BDF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
