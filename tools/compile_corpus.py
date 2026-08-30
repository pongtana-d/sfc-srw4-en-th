#!/usr/bin/env python3
"""P2: compile the translated script into pilot streams and audit the result.

Nothing is written into the ROM here. The output is the stream for every
message, plus a report saying how big it came out, which tokens it used, and
everything that would stop it from being written later.

  tools/compile_corpus.py            compile and audit
  tools/compile_corpus.py --verbose  also list every audit finding
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.stockfont import derive_table  # noqa: E402
from srw4.stream import decode, encode  # noqa: E402
from srw4.text import Branch, Tokenizer, load_stock_codes  # noqa: E402
from srw4.tokens import EncodingError, TokenMap  # noqa: E402

MANIFEST = ROOT / "data" / "font" / "renewal-clusters.json"
ICONS = ROOT / "data" / "font" / "renewal-icons.json"
STOCK = ROOT / "data" / "font" / "renewal-stock.json"
SOURCE = ROOT / "data" / "translations" / "script.source.json"
TRANSLATION = ROOT / "data" / "translations" / "script.th.json"
OUT_STREAMS = ROOT / "build" / "streams" / "script.bin"
OUT_INDEX = ROOT / "build" / "streams" / "script-index.json"
OUT_REPORT = ROOT / "build" / "reports" / "encoding.json"


def compile_script() -> dict:
    token_map = TokenMap.load(MANIFEST)
    icons = set(json.loads(ICONS.read_text())["glyphs"])
    stock_codes = load_stock_codes(STOCK)
    tokenizer = Tokenizer(icons, stock_codes)

    source = json.loads(SOURCE.read_text())
    # What each stock font code draws, so a leftover byte can be reported as
    # the Japanese character it actually is.
    stock_font, _ = derive_table(source["messages"])
    translations = json.loads(TRANSLATION.read_text())["messages"]
    messages = source["messages"]

    # The span each block occupies: the space a repack would have to fit into,
    # and the range a $FC:08 branch target has to fall inside.
    branch_ranges: dict[int, range] = {}
    capacity: dict[int, int] = {}
    for block in source["summary"]["blocks"]:
        starts = [int(m["offset"], 16) for m in messages if m["block"] == block["slot"]]
        if not starts:
            continue
        first, last = min(starts), int(block["extent"], 16)
        branch_ranges[block["slot"]] = range(first, last + 1)
        capacity[block["slot"]] = last - first

    packed = bytearray()
    index: list[dict] = []
    used = Counter()
    blocks = Counter()
    stock_bytes = Counter()
    unmapped_stock: list[dict] = []
    unknown_tokens: list[dict] = []
    failures: list[dict] = []
    malformed: list[dict] = []
    branches: list[dict] = []
    pointers: list[dict] = []
    stock_total = 0
    untranslated: list[str] = []

    for message in messages:
        mid = message["id"]
        text = translations.get(mid)
        if text is None:
            untranslated.append(mid)
            continue

        try:
            result = tokenizer.tokenize(
                text,
                where=mid,
                branch_range=branch_ranges.get(message["block"], range(0)),
            )
        except EncodingError as exc:
            failures.append({"id": mid, "stage": "tokenize", "error": str(exc)})
            continue
        pieces, foldings = result.pieces, result.foldings

        for folding in foldings:
            stock_bytes[folding.byte] += 1
            if folding.token is None:
                unmapped_stock.append(
                    {
                        "id": mid,
                        "byte": f"{folding.byte:#04x}",
                        "draws": stock_font.get(folding.byte),
                        "context": folding.context,
                    }
                )

        if result.issues:
            # The record does not parse cleanly, so it is copied through as the
            # stock bytes rather than re-encoded. Nothing is silently dropped.
            malformed.append(
                {"id": mid, "issues": result.issues, "source_hex": message["source_hex"]}
            )
            data = bytes.fromhex(message["source_hex"])
            index.append(
                {
                    "id": mid,
                    "block": message["block"],
                    "stock_pc": message["pc"],
                    "stock_bytes": message["size"],
                    "offset": len(packed),
                    "bytes": len(data),
                    "mode": "passthrough",
                }
            )
            packed += data
            blocks[message["block"]] += len(data)
            stock_total += message["size"]
            continue

        missing = sorted(
            {p.token for p in pieces if hasattr(p, "token") and p.token not in token_map}
        )
        if missing:
            unknown_tokens.append({"id": mid, "tokens": missing})
            continue

        try:
            record = encode(pieces, token_map)
            decode(record.data, token_map, record.branch_tables)
        except EncodingError as exc:
            failures.append({"id": mid, "stage": "encode", "error": str(exc)})
            continue

        for piece in pieces:
            if hasattr(piece, "token"):
                used[piece.token] += 1

        for kind, bucket in (("branch", branches), ("pointer", pointers)):
            fields = [r for r in record.relocations if r.kind == kind]
            if fields:
                bucket.append(
                    {
                        "id": mid,
                        "block": message["block"],
                        "targets": [f"{r.stock_target:#06x}" for r in fields],
                        "field_offsets": [r.offset for r in fields],
                    }
                )

        index.append(
            {
                "id": mid,
                "block": message["block"],
                "stock_pc": message["pc"],
                "stock_bytes": message["size"],
                "offset": len(packed),
                "bytes": len(record),
                "mode": "renewal",
                "glyphs": record.glyphs,
                "engine_bytes": record.engine_bytes,
            }
        )
        packed += record.data
        blocks[message["block"]] += len(record)
        stock_total += message["size"]

    return {
        "packed": bytes(packed),
        "index": index,
        "report": {
            "stage": "P2",
            "encoding_version": token_map.encoding_version,
            "form": "pilot (glyphs $00-$D3, stock engine control raw from $EC)",
            "messages": {
                "in_source": len(messages),
                "compiled": len(index),
                "untranslated": len(untranslated),
                "failed": len(failures) + len(unknown_tokens),
            },
            "size": {
                "stream_bytes": len(packed),
                "stock_record_bytes": stock_total,
                "growth_over_records": len(packed) - stock_total,
            },
            "tokens": {
                "manifest": len(token_map.tokens),
                "used": len(used),
                "unused": len(token_map.tokens) - len(used),
                "outside_manifest": len(unknown_tokens),
            },
            "per_block": {
                str(block): {
                    "stream_bytes": size,
                    "stock_span": capacity.get(block, 0),
                    "over_by": size - capacity.get(block, 0),
                }
                for block, size in sorted(blocks.items())
            },
            "fits_in_place": {
                "stock_span_total": sum(capacity.values()),
                "over_by": len(packed) - sum(capacity.values()),
                "blocks_over": sorted(
                    block for block, size in blocks.items() if size > capacity.get(block, 0)
                ),
            },
            "stock_font_bytes_folded": {
                "occurrences": sum(stock_bytes.values()),
                "distinct": len(stock_bytes),
                "unmapped": len(unmapped_stock),
            },
            "passthrough_records": len(malformed),
            "relocations": {
                "branch_tables": len(branches),
                "pointer_fields": len(pointers),
                "note": "every target is a stock block offset; the ROM writer must rewrite them",
            },
            "findings": {
                "untranslated": untranslated,
                "unmapped_stock_bytes": unmapped_stock,
                "tokens_outside_manifest": unknown_tokens,
                "failures": failures,
                "malformed_records": malformed,
                "branch_records": branches,
                "pointer_records": pointers,
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    result = compile_script()
    report = result["report"]

    OUT_STREAMS.parent.mkdir(parents=True, exist_ok=True)
    OUT_STREAMS.write_bytes(result["packed"])
    OUT_INDEX.write_text(json.dumps(result["index"], indent=1) + "\n")
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

    msg, size, tok = report["messages"], report["size"], report["tokens"]
    print(f"compiled {msg['compiled']}/{msg['in_source']} messages, {msg['failed']} failed")
    print(
        f"stream {size['stream_bytes']:,} bytes; the same records in Japanese are "
        f"{size['stock_record_bytes']:,} ({size['growth_over_records']:+,})"
    )
    print(f"tokens used {tok['used']}/{tok['manifest']}, outside manifest {tok['outside_manifest']}")
    folded = report["stock_font_bytes_folded"]
    print(
        f"stock-font bytes folded into our glyphs: {folded['occurrences']} "
        f"({folded['distinct']} distinct, {folded['unmapped']} unmapped)"
    )
    relocations = report["relocations"]
    print(
        f"fields needing relocation: {relocations['branch_tables']} branch tables, "
        f"{relocations['pointer_fields']} pointer fields"
    )
    fits = report["fits_in_place"]
    verdict = "fits" if fits["over_by"] <= 0 else f"does NOT fit, over by {fits['over_by']:,}"
    print(
        f"stock text area is {fits['stock_span_total']:,} bytes -> {verdict} "
        f"({len(fits['blocks_over'])} of {len(report['per_block'])} blocks over)"
    )

    if args.verbose:
        for name, items in report["findings"].items():
            if items:
                print(f"\n{name} ({len(items)}):")
                for item in items[:40]:
                    print("  ", item)

    blocking = (
        report["findings"]["failures"]
        + report["findings"]["tokens_outside_manifest"]
        + report["findings"]["unmapped_stock_bytes"]  # these characters are lost
    )
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
