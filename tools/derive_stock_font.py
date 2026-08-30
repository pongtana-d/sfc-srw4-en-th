#!/usr/bin/env python3
"""Write out the game's single-byte font table, recovered from the script.

  tools/derive_stock_font.py   -> build/reports/stock-font.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.stockfont import derive_table  # noqa: E402

SOURCE = ROOT / "data" / "translations" / "script.source.json"
STOCK = ROOT / "data" / "font" / "renewal-stock.json"
OUT = ROOT / "build" / "reports" / "stock-font.json"


def main() -> int:
    messages = json.loads(SOURCE.read_text())["messages"]
    table, report = derive_table(messages)
    imported = {entry["code"] for entry in json.loads(STOCK.read_text())["glyphs"].values()}

    document = {
        "_note": "Derived from script.source.json by walking raw bytes and decoded text together.",
        **report,
        "codes_imported_by_renewal": len(imported),
        "codes": {
            f"{code:#04x}": {
                "char": char,
                "hits": report["hits"][f"{code:#04x}"],
                "imported": code in imported,
            }
            for code, char in sorted(table.items())
        },
    }
    document.pop("hits")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n")
    print(
        f"{document['codes_seen']} font codes recovered from "
        f"{document['messages_used']:,} messages ({document['messages_skipped']} skipped)"
    )
    print(f"ambiguous codes: {len(document['ambiguous'])}")
    print(f"imported by renewal-stock.json: {document['codes_imported_by_renewal']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
