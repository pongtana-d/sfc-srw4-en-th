#!/usr/bin/env python3
"""P4: draw lines with the reference renderer and freeze them as fixtures.

The fixtures are what the 65816 blitter will be judged against in P5, so they
cover the cases that make a renderer wrong: a line break, an icon, digits from
the game's own font, a runtime name, stacked marks, and a line long enough to
run off the canvas.

  tools/render_lines.py                     render the fixture set
  tools/render_lines.py --update-golden     rewrite tests/golden/*.txt
  tools/render_lines.py --message 00_011C   draw one message from the script
  tools/render_lines.py --sweep             draw every message and report overflow
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.pipeline import Pipeline  # noqa: E402
from srw4.png import write_greyscale  # noqa: E402
from srw4.render import CANVAS_WIDTH  # noqa: E402

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
TRANSLATION = ROOT / "data" / "translations" / "script.th.json"
GOLDEN_DIR = ROOT / "tests" / "golden"
OUT_DIR = ROOT / "build" / "render"
SWEEP_REPORT = ROOT / "build" / "reports" / "render.json"
WINDOWS = ROOT / "data" / "config" / "text-windows.json"
SCALE = 2

# name -> either a script message id, or a line written here for a case the
# script does not contain.
FIXTURES: dict[str, dict] = {
    "plain": {"message": "00_011C"},
    "line-break": {"message": "00_04C7"},
    "digits": {"message": "01_07DF"},
    "runtime-name": {"message": "02_0CAB"},
    "stacked-marks": {"message": "03_31EB"},
    "long-line": {"message": "48_8080"},
    "icons": {"text": "<AiL><AiR><B><P>ก<ENDFF>"},
    "mixed-sources": {"text": "LV12 ก 100%<ENDFF>"},
    "narrow-canvas": {"text": "ทดสอบขอบจอที่แคบมาก<ENDFF>", "width": 64},
}


def sheet(lines: list[list[str]]) -> list[list[int]]:
    """Stack rendered lines into one image, one pixel row per canvas row."""
    width = max((len(row) for line in lines for row in line), default=1)
    canvas: list[list[int]] = []
    for line in lines:
        for row in line:
            padded = row.ljust(width, ".")
            pixels = [0 if char == "#" else 255 for char in padded]
            for _ in range(SCALE):
                canvas.append([value for value in pixels for _ in range(SCALE)])
        canvas.append([200] * (width * SCALE))  # separator between lines
    return canvas or [[255]]


def render_all(pipeline: Pipeline, translations: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name, spec in FIXTURES.items():
        where = spec.get("message", name)
        text = translations[spec["message"]] if "message" in spec else spec["text"]
        drawn = pipeline.draw(text, where=where, width=spec.get("width", CANVAS_WIDTH))
        out[name] = {
            "source": spec.get("message", "(written for this fixture)"),
            "text": text,
            "report": drawn.report(),
            "art": [line.canvas.art() for line in drawn.lines],
        }
    return out


def as_text(name: str, entry: dict) -> str:
    lines = [
        f"# {name}",
        f"# source: {entry['source']}",
        f"# text: {entry['text']}".replace("\n", "\\n"),
        f"# report: {json.dumps(entry['report'], sort_keys=True)}",
    ]
    for index, art in enumerate(entry["art"]):
        lines.append(f"--- line {index}")
        lines += art
    return "\n".join(lines) + "\n"


def window_for(block: int, windows: dict) -> tuple[str, dict]:
    """Which frame a block's text is drawn in.

    A block is named by a window or it falls to the default. Being wrong here
    is only ever generous or strict by eight pixels, and the report says which
    window it judged a line against, so a wrong answer is visible.
    """
    for name, window in windows.items():
        if isinstance(window["blocks"], list) and block in window["blocks"]:
            return name, window
    default = next(n for n, w in windows.items() if w["blocks"] == "*")
    return default, windows[default]


def sweep(pipeline: Pipeline, translations: dict) -> int:
    """Draw every line and report the ones the engine would clip.

    The canvas is 256px wide but no window is: the engine wraps at `$0E2C`,
    and it does so *before* drawing, so a line one pixel too long loses the
    glyph that crossed the edge. The budget therefore comes from the measured
    windows, not from the canvas.
    """
    windows = json.loads(WINDOWS.read_text())["windows"]
    over: list[dict] = []
    too_tall: list[dict] = []
    failed: list[dict] = []
    widths: list[int] = []
    lines = 0

    for mid, text in sorted(translations.items()):
        block = int(mid.split("_")[0])
        name, window = window_for(block, windows)
        try:
            drawn = pipeline.draw(text, where=mid)
        except Exception as exc:  # a record the compiler already flags
            failed.append({"id": mid, "error": str(exc)})
            continue
        if len(drawn.lines) > window["lines"]:
            too_tall.append(
                {"id": mid, "window": name, "lines": len(drawn.lines),
                 "allowed": window["lines"]}
            )
        for number, line in enumerate(drawn.lines):
            lines += 1
            widths.append(line.width)
            budget = window["width"] - (window["indent"] if number else 0)
            if line.canvas.overflow or line.width > budget:
                over.append(
                    {
                        "id": mid,
                        "window": name,
                        "line": number,
                        "width": line.width,
                        "budget": budget,
                        "over_by": line.width - budget,
                    }
                )

    over.sort(key=lambda entry: -entry["over_by"])
    report = {
        "stage": "P4",
        "canvas_width": CANVAS_WIDTH,
        "windows": windows,
        "messages": len(translations),
        "lines": lines,
        "widest": max(widths, default=0),
        "average_width": round(sum(widths) / len(widths), 1) if widths else 0,
        "over_the_window": len(over),
        "over_the_line_count": len(too_tall),
        "unrenderable": len(failed),
        "findings": {"too_wide": over[:200], "too_tall": too_tall[:200], "failed": failed},
    }
    SWEEP_REPORT.parent.mkdir(parents=True, exist_ok=True)
    SWEEP_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    print(f"{lines:,} lines from {len(translations):,} messages")
    print(f"widest {report['widest']} px, average {report['average_width']} px")
    print(f"over the window: {len(over)}   too many lines: {len(too_tall)}"
          f"   unrenderable: {len(failed)}")
    for entry in over[:10]:
        print(f"   +{entry['over_by']:>2}px  {entry['id']} line {entry['line']}"
              f"  {entry['width']}px > {entry['budget']} ({entry['window']})")
    return 1 if over or too_tall or failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-golden", action="store_true")
    parser.add_argument("--message", help="render one message id instead of the fixtures")
    parser.add_argument("--sweep", action="store_true", help="render the whole script")
    args = parser.parse_args()

    pipeline = Pipeline.load(ROOT, CLEAN_ROM)
    translations = json.loads(TRANSLATION.read_text())["messages"]

    if args.message:
        text = translations[args.message]
        drawn = pipeline.draw(text, where=args.message)
        print(f"{args.message}: {text}")
        print(json.dumps(drawn.report(), sort_keys=True))
        for line in drawn.lines:
            print("\n".join(line.canvas.art()))
        return 0

    if args.sweep:
        return sweep(pipeline, translations)

    rendered = render_all(pipeline, translations)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    changed = []
    for name, entry in rendered.items():
        write_greyscale(OUT_DIR / f"{name}.png", sheet(entry["art"]))
        path = GOLDEN_DIR / f"{name}.txt"
        text = as_text(name, entry)
        if args.update_golden:
            if not path.exists() or path.read_text() != text:
                path.write_text(text)
                changed.append(name)
        elif not path.exists() or path.read_text() != text:
            changed.append(name)

    for name, entry in rendered.items():
        report = entry["report"]
        print(
            f"{name:<15} lines {report['lines']}  widths {report['widths']}  "
            f"tiles {report['tiles']}  overflow {sum(report['overflow'])}"
        )

    if args.update_golden:
        print(f"\ngolden files written: {len(changed)}")
        return 0
    if changed:
        print(f"\ndiffers from golden: {', '.join(changed)}")
        return 1
    print("\nall fixtures match their golden files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
