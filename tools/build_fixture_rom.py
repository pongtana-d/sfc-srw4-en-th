#!/usr/bin/env python3
"""P5: build a small ROM that runs the blitter with no game around it.

The point is a fair comparison. The same token streams that the Python
renderer draws in P4 are assembled into a bare ROM, the real 65816 blitter
draws them on the emulator, and the two canvases are compared pixel by pixel.
Anything the game would otherwise contribute -- its engine, its state, its
timing -- is simply not there.

  tools/build_fixture_rom.py    -> build/fixture/blitter.sfc + manifest
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.asm65816 import assemble  # noqa: E402
from srw4.blitter import (  # noqa: E402
    CANVAS_BYTES,
    OFF_CANVAS,
    OFF_LEN,
    OFF_OVERFLOW,
    OFF_SRC,
    build_tables,
    constants,
)
from srw4.pipeline import Pipeline  # noqa: E402
from srw4.rom import sha256  # noqa: E402

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
TRANSLATION = ROOT / "data" / "translations" / "script.th.json"
ASM_DIR = ROOT / "src" / "srw4" / "asm"
OUT_DIR = ROOT / "build" / "fixture"

# LoROM: bank $00:8000 is file 0x0000, bank $01:8000 is file 0x8000.
ROM_SIZE = 0x10000
BANK0 = 0x008000
BANK1 = 0x018000
HEADER = 0x7FC0

CONTEXT_BASE = 0xC5C0          # the dialogue block from data/config/wram-map.json
DUMP_BASE = 0x7F0000
DUMP_STRIDE = 0x240            # 576, comfortably past the 552 bytes copied
DUMP_SPAN = OFF_OVERFLOW + 2   # canvas plus pen, dirty range and overflow
MARKER = 0xF000
COUNTER = 0xC000               # fixture scratch, outside the context block
DUMP_OFF = 0xC002
# These live in the dump bank, not the fixture's `$7E` scratch bank, so the
# Lua reader observes exactly the status that the 65816 wrote.
GUARD_STATUS = 0x7FC004
GUARD_INDEX = 0x7FC006
GUARD_BYTES = 16
GUARD_BEFORE = CONTEXT_BASE - GUARD_BYTES
GUARD_AFTER = CONTEXT_BASE + 0x320  # dialogue context end, exclusive
TILEMAP_DUMP = 0x3000
TILEMAP_LONG = 0x7EA000

# The streams the blitter is judged on. Anything the renderer can be wrong
# about should be in here.
FIXTURES: dict[str, str] = {
    "plain": "ก<ENDFF>",
    "word": "ไม่ยอมรับ<ENDFF>",
    "stacked-marks": "ฮึดสู้เต็มที่<ENDFF>",
    "digits": "LV12 100%<ENDFF>",
    "icons": "<AiL><AiR><B><P><ENDFF>",
    "engine-bytes": "<FC:05>ก<FE:21:00>ข<FB:1E80>ค<ENDFF>",
    "high-engine-controls": "<F4:00>ก<F5:00>ข<ENDFF>",
    "pointer-field": "<FB:F00C><73><07>นานะ<ENDFF>",
    # The other shapes a command can carry: an address of its own, a branch
    # table, and one more plain operand. Drawing any of them would be visible.
    "address-after-fc07": "<FC:07><44><08>นานะ<ENDFF>",
    "branch-table": "<FC:08><10><08><12><08><14><08><16><08>"
                    "<18><08><1A><08><1C><08><1E><08>นานะ<ENDFF>",
    "second-operand": "<FC:00><01>นานะ<ENDFF>",
    "line-break": "กข\nคง<ENDFF>",
    "extended-glyph": "ซึ่งซื่อ<ENDFF>",
    "edge-of-canvas": "ทดสอบขอบขวาของจอให้ชนพอดีกับกรอบที่มีอยู่จริงนะครับ<ENDFF>",
    "every-shift": "ก ก  ก   ก    ก<ENDFF>",
    "leading-space": "  ก<ENDFF>",
    "space-only": " <ENDFF>",
    "past-the-edge": "ทดสอบขอบขวาของจอให้ชนพอดีกับกรอบที่มีอยู่จริงนะครับ และยังพิมพ์ต่อไปอีก<ENDFF>",
}


def build() -> dict:
    pipeline = Pipeline.load(ROOT, CLEAN_ROM)
    tables = build_tables(pipeline.token_map, pipeline.atlas)

    # Streams and tables both live in bank $01.
    blob = bytearray()
    table_base: dict[str, int] = {}
    for name, payload in tables.blocks:
        table_base[name] = BANK1 + len(blob)
        blob += payload
        if len(blob) % 2:
            blob += b"\x00"

    streams: dict[str, bytes] = {}
    descriptors = bytearray()
    stream_blob = bytearray()
    for name, text in FIXTURES.items():
        record = pipeline.compile(text, where=name)
        streams[name] = record.data

    stream_base = BANK1 + len(blob) + len(FIXTURES) * 8
    for name in FIXTURES:
        data = streams[name]
        address = stream_base + len(stream_blob)
        descriptors += address.to_bytes(3, "little")
        descriptors += len(data).to_bytes(2, "little")
        descriptors += b"\x00\x00\x00"
        stream_blob += data

    fixtures_at = BANK1 + len(blob)
    blob += descriptors + stream_blob

    symbols = constants(CONTEXT_BASE, table_base, len(pipeline.token_map.tokens))
    symbols.update(
        {
            "FIXTURES": fixtures_at,
            "FIXTURE_COUNT": len(FIXTURES),
            "DUMP_BASE": DUMP_BASE,
            "DUMP_STRIDE": DUMP_STRIDE,
            "DUMP_SPAN": DUMP_SPAN,
            "CANVAS_LONG": 0x7E0000 + CONTEXT_BASE + OFF_CANVAS,
            "MARKER": MARKER,
            "COUNTER": COUNTER,
            "DUMP_OFF": DUMP_OFF,
            "GUARD_STATUS": GUARD_STATUS,
            "GUARD_INDEX": GUARD_INDEX,
            "GUARD_BEFORE": GUARD_BEFORE,
            "GUARD_AFTER": GUARD_AFTER,
            "GUARD_BYTES": GUARD_BYTES,
            "TILEMAP_DUMP": TILEMAP_DUMP,
            "TILEMAP_LONG": TILEMAP_LONG,
        }
    )

    source = (
        (ASM_DIR / "fixture.s").read_text()
        + "\n" + (ASM_DIR / "blitter.s").read_text()
        + "\n" + (ASM_DIR / "window.s").read_text()
    )
    program = assemble(source, BANK0, symbols)

    rom = bytearray(b"\x00" * ROM_SIZE)
    rom[0 : len(program.code)] = program.code
    rom[0x8000 : 0x8000 + len(blob)] = blob

    title = b"SRW4 BLITTER FIXTURE "[:21].ljust(21, b" ")
    rom[HEADER : HEADER + 21] = title
    rom[HEADER + 0x15] = 0x20      # LoROM, slow
    rom[HEADER + 0x16] = 0x00      # ROM only
    rom[HEADER + 0x17] = 0x06      # 64 KB
    rom[HEADER + 0x19] = 0x00
    reset = program.labels["reset"] & 0xFFFF
    for vector in (0x7FFC, 0x7FEC):    # emulation reset, native reset-ish
        rom[vector : vector + 2] = reset.to_bytes(2, "little")

    checksum = sum(rom) & 0xFFFF
    rom[0x7FDE : 0x7FE0] = checksum.to_bytes(2, "little")
    rom[0x7FDC : 0x7FDE] = (checksum ^ 0xFFFF).to_bytes(2, "little")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "blitter.sfc").write_bytes(bytes(rom))
    (OUT_DIR / "blitter.lst").write_text(
        "\n".join(f"{a:06X}  {c.hex(' '):<14} {t}" for a, c, t in program.listing) + "\n"
    )

    manifest = {
        "rom": "blitter.sfc",
        "sha256": sha256(bytes(rom)),
        "code_bytes": len(program.code),
        "table_bytes": sum(len(payload) for _, payload in tables.blocks),
        "context_base": f"{CONTEXT_BASE:#06x}",
        "dump": {
            "base": f"{DUMP_BASE:#08x}",
            "stride": DUMP_STRIDE,
            "span": DUMP_SPAN,
            "marker": f"{DUMP_BASE + MARKER:#08x}",
        },
        "canvas": {"bytes": CANVAS_BYTES, "state_at": {"pen": 544, "dirty": 546, "overflow": 550}},
        "guard": {
            "before": f"{0x7E0000 + GUARD_BEFORE:#08x}",
            "after": f"{0x7E0000 + GUARD_AFTER:#08x}",
            "bytes": GUARD_BYTES,
            "status": f"{GUARD_STATUS:#08x}",
            "index": f"{GUARD_INDEX:#08x}",
        },
        "command_frames": [
          {
            "tilemap_dump": f"{DUMP_BASE + TILEMAP_DUMP:#08x}",
            "width": 8,
            "height": 10,
            "anchor_tiles": [13, 11],
          },
          {
            "width": 14,
            "height": 4,
            "anchor_tiles": [13, 1],
            "case": "long-label",
          },
        ],
        "fixtures": [
            {"name": name, "index": index, "text": FIXTURES[name], "stream_bytes": len(streams[name])}
            for index, name in enumerate(FIXTURES)
        ],
        "labels": {name: f"{value:#08x}" for name, value in sorted(program.labels.items())},
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    return manifest


def main() -> int:
    manifest = build()
    print(f"build/fixture/blitter.sfc  sha256 {manifest['sha256'][:16]}...")
    print(f"blitter {manifest['code_bytes']} bytes of code, "
          f"{manifest['table_bytes']:,} bytes of tables")
    print(f"{len(manifest['fixtures'])} fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
