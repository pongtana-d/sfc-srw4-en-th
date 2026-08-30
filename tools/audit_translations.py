#!/usr/bin/env python3
"""Run every translation file past the tokenizer, not just the script.

The files do not share a schema, so nothing here assumes one. The tree is
walked, each string is judged on what it contains, and anything skipped is
counted and named -- an audit that quietly ignored half the corpus would be
worse than no audit at all.

  tools/audit_translations.py                  Thai/control summary
  tools/audit_translations.py --include-ascii  production glyph census
  tools/audit_translations.py --verbose        every finding
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.stockfont import derive_table  # noqa: E402
from srw4.text import Tokenizer, load_stock_codes  # noqa: E402
from srw4.tokens import EncodingError, TokenMap  # noqa: E402

FONT_DIR = ROOT / "data" / "font"
TRANSLATIONS = ROOT / "data" / "translations"
SCRIPT_SOURCE = TRANSLATIONS / "script.source.json"
REPORT = ROOT / "build" / "reports" / "translations.json"

# Keys whose values record the Japanese original or bookkeeping, never our text.
SKIP_KEYS = {
    "address", "end", "pc", "offset", "bank", "size", "slots", "sha256",
    "source", "source_hex", "source_sha256", "source_pointer", "source_pc", "source_end",
    "pointer", "post_read_pointer", "master_entry_pc", "master_entry_hex", "record_extent",
    "method", "width_evidence", "note", "notes", "comment", "screen", "font", "bytes",
    "kind", "id", "key", "schema", "game", "language", "status",
}
HEX_DUMP = re.compile(r"^[0-9A-Fa-f]{2}(?: [0-9A-Fa-f]{2})+$")
THAI = re.compile(r"[฀-๿]")
JAPANESE = re.compile(r"[　-ヿ一-鿿＀-￯]")
ESCAPE = re.compile(r"<[^<>]+>")


def walk(node, path: str = ""):
    """Every string in the tree, with the path that leads to it."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key.startswith("_") or key in SKIP_KEYS:
                continue
            yield from walk(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}[{index}]")
    elif isinstance(node, str):
        yield path, node


def classify(text: str) -> str:
    """Ours to check, or someone else's string."""
    if not text.strip():
        return "empty"
    if HEX_DUMP.match(text):
        return "hex dump"
    stripped = ESCAPE.sub("", text)
    if THAI.search(stripped):
        return "check"
    if JAPANESE.search(stripped):
        return "japanese original"
    if ESCAPE.search(text):
        return "check"          # escapes with no Thai are still ours to explain
    if stripped.isascii():
        return "ascii only"
    return "check"


def audit(verbose: bool, *, include_ascii: bool = False) -> dict:
    token_map = TokenMap.load(FONT_DIR / "renewal-clusters.json")
    icons = set(json.loads((FONT_DIR / "renewal-icons.json").read_text())["glyphs"])
    stock_codes = load_stock_codes(FONT_DIR / "renewal-stock.json")
    stock_font, _ = derive_table(json.loads(SCRIPT_SOURCE.read_text())["messages"])

    files: list[dict] = []
    leftovers: list[dict] = []
    outside: list[dict] = []
    broken: list[dict] = []
    used = Counter()
    skipped_overall = Counter()

    for path in sorted(TRANSLATIONS.glob("*.th.json")):
        document = json.loads(path.read_text())
        # A file says which engine reads it; the leads mean different things.
        tokenizer = Tokenizer(
            icons,
            stock_codes,
            engine=(document.get("_engine", "story") if isinstance(document, dict) else "story"),
        )
        checked = 0
        skipped = Counter()
        file_leftovers = 0

        for where, text in walk(document):
            verdict = classify(text)
            # The historical Thai audit deliberately skipped ASCII.  P2 needs
            # a stricter production census: English labels and runtime values
            # must prove they belong to the new atlas as well.
            if verdict == "ascii only" and include_ascii:
                verdict = "check"
            if verdict != "check":
                skipped[verdict] += 1
                skipped_overall[verdict] += 1
                continue
            checked += 1
            location = f"{path.name}:{where}"

            try:
                result = tokenizer.tokenize(text, where=location)
            except EncodingError as exc:
                broken.append({"at": location, "error": str(exc), "text": text[:60]})
                continue

            for folding in result.foldings:
                if folding.token is None:
                    file_leftovers += 1
                    leftovers.append(
                        {
                            "at": location,
                            "byte": f"{folding.byte:#04x}",
                            "draws": stock_font.get(folding.byte),
                            "kind": "after a command" if folding.after_command else "inside text",
                            "text": text[:60],
                        }
                    )

            missing = sorted(
                {p.token for p in result.pieces if hasattr(p, "token") and p.token not in token_map}
            )
            if missing:
                outside.append({"at": location, "tokens": missing})
            for piece in result.pieces:
                if hasattr(piece, "token") and piece.token in token_map:
                    used[piece.token] += 1

        files.append(
            {
                "file": path.name,
                "strings_checked": checked,
                "strings_skipped": dict(skipped),
                "leftover_bytes": file_leftovers,
            }
        )

    return {
        "stage": "P2 (whole corpus)",
        "include_ascii": include_ascii,
        "files": len(files),
        "strings_checked": sum(entry["strings_checked"] for entry in files),
        "strings_skipped": dict(skipped_overall),
        "leftover_japanese_bytes": len(leftovers),
        "by_kind": dict(Counter(entry["kind"] for entry in leftovers)),
        "tokens_outside_manifest": len(outside),
        "unreadable_strings": len(broken),
        "tokens_used": len(used),
        "per_file": files,
        "findings": {
            "leftover_japanese": leftovers,
            "tokens_outside_manifest": outside,
            "unreadable": broken,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--include-ascii", action="store_true")
    args = parser.parse_args()

    report = audit(args.verbose, include_ascii=args.include_ascii)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    print(f"{report['files']} translation files, {report['strings_checked']:,} strings checked")
    print(f"skipped: " + ", ".join(f"{n} {why}" for why, n in sorted(report["strings_skipped"].items())))
    print(f"tokens used {report['tokens_used']}, outside the manifest {report['tokens_outside_manifest']}")
    print(f"leftover Japanese bytes: {report['leftover_japanese_bytes']}")
    for kind, count in sorted(report["by_kind"].items()):
        note = " (an operand we do not know about would look like this)" if kind == "after a command" else ""
        print(f"    {count:>3} {kind}{note}")
    print(f"strings the tokenizer could not read: {report['unreadable_strings']}")

    worst = sorted(report["per_file"], key=lambda entry: -entry["leftover_bytes"])
    for entry in worst[:8]:
        if entry["leftover_bytes"]:
            print(f"   {entry['file']:<32} {entry['leftover_bytes']:>3} leftover")

    if args.verbose:
        for name, items in report["findings"].items():
            if items:
                print(f"\n{name} ({len(items)}):")
                for item in items[:40]:
                    print("  ", item)

    blocking = report["leftover_japanese_bytes"] + report["tokens_outside_manifest"]
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
