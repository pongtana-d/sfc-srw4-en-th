"""Fixed Thai player-name preset data and its original-ROM contract.

This module deliberately handles only the preset list.  It does not claim to
support keyboard input: that needs its own renderer/context and must not be
enabled by merely replacing bytes in the stock list.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .pipeline import Pipeline
from .rom import RomError


PRESET_POINTERS = 0x128347
PRESET_POINTER_COUNT = 27
PRESET_POOL_START = 0x1288ED
PRESET_POOL_END = 0x12897D
PRESET_COUNT = 25

# Mesen evidence E-008: the naming screen reaches its rasteriser through this
# JSL and its already-advanced source pointer is in direct-page $1A-$1C.
NAMING_RASTER_CALL = 0x0184E4
NAMING_RASTER_EXPECTED = bytes((0x22, 0xEB, 0x84, 0x81))
NAMING_POINTER_DP = 0x1A
NAMING_FIXED_RANGES = {
    0xCC: ((0xAB5E, 0xABE3), (0xAC53, 0xAC8B)),
}
NAMING_LABEL_RANGES = {
    0xCC: ((0xABE6, 0xABEA), (0xAC45, 0xAC50), (0xAC97, 0xACA2),
           (0xACC2, 0xACC3), (0xACC5, 0xACC6), (0xACCA, 0xACCB)),
}


def adapter_source() -> str:
    """Overlay a tagged Thai glyph onto a stock-initialised dynamic tile.

    The naming screen does not have a verified free 544-byte canvas.  The
    stock rasteriser allocates and colours a blank tile; this adapter replaces
    plane 0 with an 8x16 Thai glyph using eight bytes from the established
    private WRAM tail.
    """
    return """; Tagged `$0Axx` is a Thai token; all other glyphs stay stock.
draw_naming_glyph:
  php
  rep #$30
  sta.l $7EFFE0
  cmp #$0A00
  bcs tagged_or_above
  brl not_our_text
tagged_or_above:
  cmp #$0AEC
  bcc tagged
  brl not_our_text
tagged:
  lda $D0
  and #$03FF
  asl a
  asl a
  asl a
  asl a
  asl a
  sta.l $7EFFE2

  ; Stock owns tile allocation and colour planes. Code zero is the blank
  ; plane-0 image which is replaced immediately after this call.
  lda #$0000
  jsl STOCK_RASTERISER

  lda.l $7EFFE0
  sec
  sbc #$0A00
  asl a
  tax
  lda SLOT_TABLE,x
  sta.l $7EFFE4
  lda #$0008
  sta.l $7EFFE6
copy_rows:
  lda.l $7EFFE4
  tax
  sep #$20
  lda GLYPH_BASE,x
  sta.l $7EFFE8
  rep #$20
  lda.l $7EFFE2
  tax
  sep #$20
  lda.l $7EFFE8
  sta.l $7F8000,x
  rep #$20
  lda.l $7EFFE4
  clc
  adc #$0008
  tax
  sep #$20
  lda GLYPH_BASE,x
  sta.l $7EFFE8
  rep #$20
  lda.l $7EFFE2
  tax
  sep #$20
  lda.l $7EFFE8
  sta.l $7F8020,x
  rep #$20
  lda.l $7EFFE4
  inc a
  sta.l $7EFFE4
  lda.l $7EFFE2
  inc a
  inc a
  sta.l $7EFFE2
  lda.l $7EFFE6
  dec a
  sta.l $7EFFE6
  bne copy_rows
  plp
  rtl

not_our_text:
  rep #$30
  plp
  jml STOCK_RASTERISER
"""


@dataclass(frozen=True)
class Write:
    """An asserted replacement for a fixed naming-ROM range."""

    pc: int
    expected: bytes
    payload: bytes
    owner: str


def preset_writes(root: Path, clean: bytes, pipeline: Pipeline) -> tuple[list[Write], dict]:
    """Compile the 25 supplied Thai presets into the existing pointer pool.

    The first four records feed nine-byte unit buffers; all remaining records
    feed six-byte pilot buffers.  The limits exclude the trailing ``$FF``.
    They are original-ROM contracts, not layout guesses.
    """
    document = json.loads((root / "data" / "translations" / "naming-screen.th.json").read_text())
    presets = document["presets"]
    if len(presets) != PRESET_COUNT:
        raise RomError(f"naming preset count is {len(presets)}, expected {PRESET_COUNT}")

    source_pool = clean[PRESET_POOL_START:PRESET_POOL_END]
    if len(source_pool) != PRESET_POOL_END - PRESET_POOL_START:
        raise RomError("naming preset pool lies outside the clean ROM")
    original_pointers = [
        int.from_bytes(clean[PRESET_POINTERS + 2 * index:PRESET_POINTERS + 2 * index + 2], "little")
        for index in range(PRESET_POINTER_COUNT)
    ]

    payload = bytearray()
    relocated: dict[int, int] = {}
    report = []
    source_pc = PRESET_POOL_START
    for index, entry in enumerate(presets):
        expected = bytes.fromhex(str(entry["source_hex"]))
        actual = clean[source_pc:source_pc + len(expected)]
        if actual != expected:
            raise RomError(
                f"naming preset {entry['source']!r} differs from the asserted clean-ROM bytes"
            )
        translated = pipeline.compile(str(entry["translation"]), where=f"naming preset {index}").data
        limit = 9 if index < 4 else 6
        if len(translated) > limit:
            raise RomError(
                f"naming preset {entry['translation']!r} needs {len(translated)} bytes; limit is {limit}"
            )
        pointer = (PRESET_POOL_START + len(payload)) & 0xFFFF
        relocated[source_pc & 0xFFFF] = pointer
        payload.extend(translated)
        payload.append(0xFF)
        report.append({
            "source": entry["source"],
            "translation": entry["translation"],
            "pointer": f"0x{pointer:04X}",
            "bytes": len(translated),
            "byte_limit": limit,
        })
        source_pc += len(expected)

    if source_pc != PRESET_POOL_END:
        raise RomError("naming preset source records do not exactly fill their pool")
    if len(payload) > len(source_pool):
        raise RomError("Thai naming preset pool overflows its original allocation")

    pointer_payload = b"".join(
        relocated[pointer].to_bytes(2, "little") for pointer in original_pointers
    )
    pool_payload = bytes(payload).ljust(len(source_pool), b"\xFF")
    return [
        Write(
            PRESET_POINTERS,
            clean[PRESET_POINTERS:PRESET_POINTERS + len(pointer_payload)],
            pointer_payload,
            "naming-preset-pointers",
        ),
        Write(PRESET_POOL_START, source_pool, pool_payload, "naming-preset-pool"),
    ], {
        "presets": report,
        "pool": {
            "start": f"0x{PRESET_POOL_START:06X}",
            "end": f"0x{PRESET_POOL_END:06X}",
            "capacity": len(source_pool),
            "used": len(payload),
        },
    }
