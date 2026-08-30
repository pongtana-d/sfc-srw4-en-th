#!/usr/bin/env python3
"""P5: compare the 65816 blitter against the Python reference, pixel by pixel.

  tools/check_blitter.py            build, run and compare
  tools/check_blitter.py --art      also print any fixture that differs
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
sys.path.insert(0, str(ROOT / "tools"))

from srw4.blitter import CANVAS_BYTES, CANVAS_STRIDE  # noqa: E402
from srw4.pipeline import Pipeline  # noqa: E402
from srw4.render import CANVAS_WIDTH  # noqa: E402
from srw4.window import BorderTiles, WindowSpec, menu_layout  # noqa: E402

MESEN = Path("/Applications/Mesen.app/Contents/MacOS/Mesen")
CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
FIXTURE_DIR = ROOT / "build" / "fixture"
LUA = ROOT / "tools" / "lua" / "fixture-dump.lua"
REPORT = ROOT / "build" / "reports" / "blitter.json"
ROW_BYTES = CANVAS_WIDTH // 8


def expected_command_tilemap() -> list[int]:
    """The P1 frame plus the P4 long-label width case, from one contract."""
    config = json.loads((ROOT / "data" / "config" / "window-specs.json").read_text())["command_menu"]
    spec = WindowSpec(
        *config["anchor_tiles"],
        config["min_outer_width_tiles"],
        *config["content_padding_tiles"],
        config["item_height_tiles"],
        *config["cursor_anchor_tiles"],
        BorderTiles(**config["border"]),
    )
    words = [0] * (32 * 32)

    def put(frame_spec: WindowSpec, widths: list[int]) -> None:
        layout = menu_layout(frame_spec, widths)
        for y, row in enumerate(layout.tilemap):
            for x, word in enumerate(row):
                if word is not None:
                    words[(frame_spec.anchor_y_tiles + y) * 32 + frame_spec.anchor_x_tiles + x] = word

    put(spec, [0] * len(config["labels"]))
    put(
        WindowSpec(
            spec.anchor_x_tiles, 1, spec.min_outer_width_tiles,
            spec.padding_left_tiles, spec.padding_right_tiles, spec.item_height_tiles,
            spec.cursor_x_tiles, spec.cursor_y_tiles, spec.border,
        ),
        [75],
    )
    return words


def run_emulator(manifest: dict) -> bytes:
    dump = FIXTURE_DIR / "dump.bin"
    if dump.exists():
        dump.unlink()
    needed = manifest["dump"]["stride"] * len(manifest["fixtures"])
    env = dict(
        os.environ,
        SRW4_OUT=str(dump),
        SRW4_BYTES=str(max(needed, 0xF002)),
        SRW4_MARKER=str(int(manifest["dump"]["marker"], 16)),
    )
    result = subprocess.run(
        [str(MESEN), "--testRunner", "--testRunnerTimeout=120", "--noAudio",
         str((FIXTURE_DIR / "blitter.sfc").resolve()), str(LUA.resolve())],
        env=env,
    )
    if not dump.exists():
        raise SystemExit("the emulator wrote no dump at all")
    if result.returncode != 0:
        raise SystemExit("the harness never set its marker: the blitter did not finish")
    return dump.read_bytes()


def rows_from_dump(block: bytes) -> list[int]:
    """The canvas as one integer per row, matching the Python renderer's shape."""
    out = []
    for row in range(16):
        start = row * CANVAS_STRIDE
        value = int.from_bytes(block[start : start + ROW_BYTES], "big")
        out.append(value)
    return out


def art(rows: list[int], width: int) -> list[str]:
    return [
        "".join("#" if row >> (CANVAS_WIDTH - 1 - x) & 1 else "." for x in range(width))
        for row in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--art", action="store_true")
    args = parser.parse_args()

    from build_fixture_rom import FIXTURES, build  # tools/build_fixture_rom.py

    manifest = build()
    dump = run_emulator(manifest)
    guard_offset = int(manifest["guard"]["status"], 16) - int(manifest["dump"]["base"], 16)
    guard_ok = int.from_bytes(dump[guard_offset : guard_offset + 2], "little") == 1
    guard_index_offset = int(manifest["guard"]["index"], 16) - int(manifest["dump"]["base"], 16)
    guard_index = int.from_bytes(dump[guard_index_offset : guard_index_offset + 2], "little")
    tilemap_offset = int(manifest["command_frames"][0]["tilemap_dump"], 16) - int(manifest["dump"]["base"], 16)
    tilemap = list(memoryview(dump)[tilemap_offset : tilemap_offset + 0x800].cast("H"))
    expected_tilemap = expected_command_tilemap()
    tilemap_differing = [index for index, (got, want) in enumerate(zip(tilemap, expected_tilemap)) if got != want]

    pipeline = Pipeline.load(ROOT, CLEAN_ROM)
    stride = manifest["dump"]["stride"]
    results = []
    failures = 0

    for entry in manifest["fixtures"]:
        name, index = entry["name"], entry["index"]
        block = dump[index * stride : index * stride + stride]
        hardware = rows_from_dump(block)
        pen = int.from_bytes(block[544:546], "little")
        dirty_first = int.from_bytes(block[546:548], "little")
        dirty_last = int.from_bytes(block[548:550], "little")
        overflow = int.from_bytes(block[550:552], "little")

        drawn = pipeline.draw(FIXTURES[name], where=name)
        reference = drawn.lines[0]
        expected = reference.canvas.rows

        differing = [row for row in range(16) if hardware[row] != expected[row]]
        same_pen = pen == reference.canvas.pen
        same_dirty = (
            dirty_first == (reference.canvas.dirty_first if reference.canvas.dirty_first is not None else 0xFFFF)
            and dirty_last == (reference.canvas.dirty_last or 0)
        )
        same_overflow = overflow == reference.canvas.overflow
        ok = not differing and same_pen and same_dirty and same_overflow
        failures += 0 if ok else 1

        results.append(
            {
                "fixture": name,
                "match": ok,
                "rows_differing": differing,
                "pen": {"rom": pen, "reference": reference.canvas.pen},
                "dirty": {
                    "rom": [dirty_first, dirty_last],
                    "reference": [reference.canvas.dirty_first, reference.canvas.dirty_last],
                },
                "overflow": {"rom": overflow, "reference": reference.canvas.overflow},
            }
        )

        status = "ok" if ok else f"DIFFERS on {len(differing)} row(s)"
        print(f"{name:<16} pen {pen:>3}  dirty {dirty_first}-{dirty_last}  {status}")
        if args.art and not ok:
            width = max(pen, reference.canvas.pen, 8)
            for got, want in zip(art(hardware, width), art(expected, width)):
                print(f"  rom {got}")
                print(f"  ref {want}{'   <--' if got != want else ''}")

    report = {
        "stage": "P5",
        "rom": manifest["rom"],
        "rom_sha256": manifest["sha256"],
        "code_bytes": manifest["code_bytes"],
        "fixtures": len(results),
        "matching": len(results) - failures,
        "guard": manifest["guard"] | {"match": guard_ok, "first_bad_offset": None if guard_ok else guard_index},
        "command_frame": {"frames": manifest["command_frames"]} | {
            "matching_words": len(expected_tilemap) - len(tilemap_differing),
            "words": len(expected_tilemap),
            "differing_words": tilemap_differing,
        },
        "results": results,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    print(f"\n{report['matching']}/{report['fixtures']} fixtures match the reference renderer")
    print("context guard ok" if guard_ok else f"context guard CORRUPTED at +{guard_index:#04x}")
    print(f"command frame {len(expected_tilemap) - len(tilemap_differing)}/{len(expected_tilemap)} tilemap words match")
    return 1 if failures or not guard_ok or tilemap_differing else 0


if __name__ == "__main__":
    raise SystemExit(main())
