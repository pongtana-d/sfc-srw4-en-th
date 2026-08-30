"""Current-build generators for the proven battle width and draw adapters."""
from __future__ import annotations

from .asm65816 import assemble


INTERNAL_BASE = 0x0A00
INTERNAL_LIMIT = 0x0AEC
BATTLE_STATE = 0x7EFFC0
STATE_SIGNATURE = 0xA55A
STATE_PEN = BATTLE_STATE + 2
STATE_EXPECT = BATTLE_STATE + 4


def build_dispatch(origin: int, renderer: int) -> bytes:
    """Route internal Thai ids to the battle renderer and all else to stock."""
    source = f""".a16
.i16
battle_dispatch:
  cmp #${INTERNAL_BASE:04X}
  bcc stock
  cmp #${INTERNAL_LIMIT:04X}
  bcs stock
  sec
  sbc #${INTERNAL_BASE:04X}
  jml ${renderer:06X}
stock:
  jsl $8184EB
  rtl
"""
    return assemble(source, origin).code


def build_width(origin: int, advance_table: int) -> bytes:
    """Reproduce battle width accounting without sharing ordinary VWF state."""
    source = f""".a16
.i16
battle_width:
  sta $02
  cmp #${INTERNAL_BASE:04X}
  bcc original_jump
  cmp #${INTERNAL_LIMIT:04X}
  bcc thai
  bra original_jump
original_jump:
  brl original
thai:
  sec
  sbc #${INTERNAL_BASE:04X}
  and #$00FF
  tax
  lda.l ${BATTLE_STATE:06X}
  cmp #${STATE_SIGNATURE:04X}
  bne fresh
  lda $D0
  cmp.l ${STATE_EXPECT:06X}
  bne fresh
  sep #$20
  lda.l ${STATE_PEN:06X}
  bra pen
fresh:
  sep #$20
  lda #$00
pen:
  clc
  adc.l ${advance_table:06X},x
  cmp #$08
  rep #$20
  bcc free
  clc
  jml $81921E
free:
  jml $819236
original:
  cmp #$0100
  jml $81921E
"""
    return assemble(source, origin).code
