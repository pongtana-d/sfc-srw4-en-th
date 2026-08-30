"""The machine-readable P2 text/token contract.

Code imports these values instead of keeping a second set of byte bands.  The
manifest repeats only the fields it needs to validate its own layout, and its
loader rejects a mismatch with this contract.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = json.loads((ROOT / "data" / "config" / "text-contract.json").read_text())

if DOCUMENT["schema"] != "srw4-text-contract/1":
    raise RuntimeError(f"unsupported text contract: {DOCUMENT['schema']!r}")

_glyph = DOCUMENT["glyph"]
_bands = DOCUMENT["bands"]
_controls = DOCUMENT["controls"]

ENCODING_VERSION = DOCUMENT["encoding_version"]
DIRECT_SLOTS = _glyph["direct_slots"]
DIRECT_MAX = DIRECT_SLOTS - 1
EXTENDED_LEAD = _glyph["extended_lead"]
EXTENDED_PAGE_SIZE = _glyph["extended_page_size"]
EXTENDED_PAGES = _glyph["extended_pages"]
ENGINE_CODE_BASE = _glyph["engine_code_base"]
RESERVED_FIRST = _bands["reserved_first"]
RESERVED_LAST = _bands["reserved_last"]
ENGINE_FLOOR = _bands["engine_first"]
NEWLINE_BYTE = _controls["newline"]
TERMINATORS = tuple(_controls["terminators"])
ENGINE_OPERANDS = {int(lead, 16): count for lead, count in _controls["operands"].items()}

if RESERVED_FIRST != DIRECT_SLOTS:
    raise RuntimeError("reserved band must begin immediately after direct glyphs")
if RESERVED_LAST + 1 != ENGINE_FLOOR:
    raise RuntimeError("engine control band must follow the reserved band")
if not ENGINE_FLOOR <= EXTENDED_LEAD <= 0xFF:
    raise RuntimeError("extended lead must be an engine byte")
if EXTENDED_LEAD + EXTENDED_PAGES > NEWLINE_BYTE:
    raise RuntimeError("extended pages collide with the newline control")
