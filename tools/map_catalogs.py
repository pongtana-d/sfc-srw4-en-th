#!/usr/bin/env python3
"""P8: read the nineteen catalogs out of the ROM and say what they hold.

Nothing here is guessed. Slot counts come from each table's own first pointer,
and windows onto another table are recognised by their address rather than
from a list that would have to be kept in step with the ROM.

  tools/map_catalogs.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.catalog import load, read_slots, record_at  # noqa: E402

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
REPORT = ROOT / "build" / "reports" / "catalogs.json"


def main() -> int:
    rom = CLEAN_ROM.read_bytes()
    entries = load(rom)

    rows = []
    for entry in entries:
        slots = read_slots(rom, entry)
        distinct = sorted({p for p in slots if p})
        used = [p for p in distinct if p >= entry.first_record]
        unused = len(distinct) - len(used)
        # A pointer below where the records start names a byte of the table
        # itself: an unused slot, not a record.
        # A pool ends where the next table in the bank begins. A slot naming
        # that address is one past the end, not a record, and reading it would
        # walk into the table's own bytes.
        ceiling = min(
            (other.address for other in entries
             if other.bank == entry.bank and other.address > entry.first_record),
            default=0x10000,
        )
        past_the_pool = sum(1 for p in used if p >= ceiling)
        blanks = sum(
            1 for p in used if p < ceiling and record_at(rom, entry.bank, p) == b"\xff"
        )
        rows.append(
            {
                "entry": entry.index,
                "cpu": f"${entry.bank:02X}:{entry.address:04X}",
                "slots": entry.slots,
                "records": len(used),
                "distinct_pointers": len(distinct),
                "blank_records": blanks,
                "pointers_into_the_table": unused,
                "past_the_pool": past_the_pool,
                "window_of": entry.window_of,
                "from_slot": entry.from_slot if entry.window_of is not None else None,
                "first_record": f"${entry.first_record:04X}",
            }
        )

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"catalogs": rows}, indent=2, ensure_ascii=False) + "\n")

    print(f'{"#":>2} {"table":<12}{"slots":>6}{"records":>8}{"blank":>6}  window of')
    for row in rows:
        window = "" if row["window_of"] is None else f'{row["window_of"]} from slot {row["from_slot"]}'
        print(f'{row["entry"]:>2} {row["cpu"]:<12}{row["slots"]:>6}{row["records"]:>8}'
              f'{row["blank_records"]:>6}  {window}')
    print(f"\n{len(rows)} catalogs, {sum(r['records'] for r in rows):,} records, "
          f"{sum(1 for r in rows if r['window_of'] is not None)} of them windows onto another")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
