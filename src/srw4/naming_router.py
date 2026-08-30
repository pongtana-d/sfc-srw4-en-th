"""Parser routes for Thai bytes owned by the naming screen.

The normal naming interpreter turns a source byte into a Japanese glyph before
calling its rasteriser.  These two small trampolines mark only the live name
buffers and the preset pool as our private glyph range, so the stock loop still
owns controls, cursor movement and all Japanese screen labels.
"""

from __future__ import annotations


TAG_BASE = 0x0A00
TAG_LIMIT = 0x0AEC

# Parser source pointers have already advanced by one byte.
RUNTIME_RANGES = {
    0xD2: ((0x88EE, 0x897E),),
    # `$F8 06` leaves the outer pointer at one of these three positions while
    # it emits bytes from the active name buffer.
    0xCC: ((0xACC2, 0xACC3), (0xACC5, 0xACC6), (0xACCA, 0xACCB)),
}


def parser_source(*, alternate: bool = False) -> str:
    """Return a parser-1 trampoline source for one of the two entry paths."""
    original_cutoff = "$00F6" if alternate else "$00F0"
    direct = "$818414" if alternate else "$81842A"
    return f"""; Naming-only parser route.  A is a 16-bit raw engine code.
.a16
.i16
naming_parser:
  pha
  sep #$20
  lda $1C
  cmp #$D2
  beq bank_d2
  cmp #$CC
  beq bank_cc
  brl original
bank_d2:
  rep #$20
  lda $1A
  cmp #$88EE
  bcc original
  cmp #$897E
  bcs original
  brl thai
bank_cc:
  rep #$20
  lda $1A
  cmp #$ACC2
  beq thai
  cmp #$ACC5
  beq thai
  cmp #$ACCA
  beq thai
  brl original
thai:
  pla
  cmp #$00EC
  bcs original_direct
  ora #$0A00
  jml $818456
original:
  rep #$20
original_direct:
  pla
  cmp #{original_cutoff}
  bcc direct_original
  jml $818407
direct_original:
  jml {direct}
"""


def width_source() -> str:
    """Keep tagged Thai glyphs on the naming engine's one-cell path."""
    return """; Naming-only width route, replacing STA $26 / CMP #$0100.
.a16
.i16
naming_width:
  sta $26
  cmp #$0A00
  bcc original
  cmp #$0AEC
  bcs original
  jml $81845D
original:
  cmp #$0100
  jml $81845B
"""
