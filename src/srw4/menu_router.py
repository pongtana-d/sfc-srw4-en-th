"""Ordinary-parser routes for the private command-label stream."""

from __future__ import annotations


def parser_source(*, alternate: bool = False, cell_prepare_entry: int | None = None) -> str:
    """Route only `$FA` direct and extended glyphs to the ordinary raster path.

    At these parser entries `$1A-$1C` names the byte just consumed.  The stock
    interpreter reserves `$F0-$F5` for controls, while our catalog encoder uses
    `$F0-$F3` as four extended glyph pages.  Consume the page byte here and
    hand `$0100 + index` to the normal glyph continuation; every actual engine
    control remains on its stock route.
    """
    cutoff = "$00F6" if alternate else "$00F0"
    direct = "$818414" if alternate else "$81842A"
    prepare = (
        f"  jsl ${cell_prepare_entry:06X}\n" if cell_prepare_entry is not None else ""
    )
    return f"""; Catalog-13 `$FA` parser route.
.a16
.i16
menu_parser:
  pha
  sep #$20
  lda $1C
  cmp #$FA
  bne stock
  rep #$20
  pla
  cmp #$00EC
  bcc glyph_direct
  cmp #$00F0
  bcc stock_code
  cmp #$00F4
  bcs stock_code
glyph_extended:
  sec
  sbc #$00F0
  xba
  clc
  adc #$0100
  pha
  ldy #$0000
  lda [$1A],y
  and #$00FF
  clc
  adc $01,s
  ply
  inc $1A
{prepare.rstrip()}
  jml $818456
glyph_direct:
{prepare.rstrip()}
  jml $818456
stock:
  rep #$20
  pla
stock_code:
  cmp #{cutoff}
  bcc direct_original
  jml $818407
direct_original:
  jml {direct}
"""


def native_command_source(
    *, table_address: int, index_table: int, menu_active: int, record_count: int,
    records: int, max_records: int, row_tile: int, row_pending: int, row_stride: int,
    current_record: int, first_token: int, row_rendered: int, selection_entry: int,
    fallback_entry: int, menu_entry: int,
    active_cookie: int,
    stream_base: int = 0, overlay_records: int = 0,
    row_count_address: int = 0x7E0E3B,
    recovery_flag: int = 0,
    frame_ptr: int = 0, tilemap: int = 0x7EA000,
    frame_top_left: int = 0x0011, frame_bottom_left: int = 0x0013,
) -> str:
    """Map only the pre-advanced native command pointers into `$FA`.

    The command records occupy `$D2:8613..865D` in fixed five-byte slots.  At
    the parser boundary the source pointer has already consumed the first
    byte, so the first legal pointer is `$8614`.  The sparse table is indexed
    by that offset; zero rows deliberately fall straight back to the normal
    naming/stock parser.
    """
    return f"""; Native command record route, entered before the shared parser.
.a16
.i16
native_command_parser:
  php
  rep #$20
  pha
  phx
  phy
  lda.l ${menu_active:06X}
  cmp #${active_cookie:04X}
  beq routing_active
  ; A nested selector (Spirit with multiple pilots) deliberately retires the
  ; command cookie while its own shorter list is live.  B restores the stock
  ; command row count/frame but does not revisit the command-open hook.  On
  ; the first subsequent cursor parser call, reacquire ownership only when
  ; both independent stock facts match the cached command surface.  Process
  ; this triggering record through stock, then mirror the palette.
  lda.l ${record_count:06X}
  beq inactive_fallback
  cmp #${max_records + 1:04X}
  bcs inactive_fallback
  sep #$20
  lda.l ${row_count_address:06X}
  rep #$20
  and #$00FF
  cmp.l ${record_count:06X}
  bne inactive_fallback
  lda.l ${frame_ptr:06X}
  tax
  lda.l ${tilemap:06X},x
  and #$03FF
  cmp #${frame_top_left:04X}
  bne inactive_fallback
  ; The nested pilot selector leaves the command top edge visible but covers
  ; its lower rows.  Require the dynamic bottom-left corner as proof that B
  ; has actually restored the complete command frame before resynchronising.
  lda.l ${record_count:06X}
  asl a
  inc a
  asl a
  asl a
  asl a
  asl a
  asl a
  asl a
  clc
  adc.l ${frame_ptr:06X}
  tax
  lda.l ${tilemap:06X},x
  and #$03FF
  cmp #${frame_bottom_left:04X}
  bne inactive_fallback
  lda #${active_cookie:04X}
  sta.l ${menu_active:06X}
  brl active_fallback
inactive_fallback:
  brl fallback
routing_active:
  sep #$20
  lda $1C
  cmp #$D2
  beq bank_d2
  cmp #$FA
  beq active_menu_bank
  brl active_fallback
active_menu_bank:
  rep #$20
  ply
  plx
  pla
  plp
  jml ${menu_entry:06X}
bank_d2:
  rep #$20
  lda $1A
  sec
  sbc #$8614
  bcs native_lower_ok
  brl active_fallback
native_lower_ok:
  cmp #$0047
  bcc native_range_ok
  brl cached_route_try
native_range_ok:
  asl
  tax
  lda.l ${table_address:06X},x
  bne route_found
  brl cached_route_try
route_found:
  pha
  txa
  lsr
  tax
  sep #$20
  lda.l ${index_table:06X},x
  rep #$20
  and #$00FF
  sta.l ${current_record:06X}
  bra route_allocate
cached_route_try:
  ; Some destination screens reuse the command-list source slot.  On return,
  ; stock can offer that unrelated D2 record (e.g. a pilot ability name) for
  ; a row that was already identified on the prior clean open.  Recover only
  ; while one of the stock-declared rows is still missing, and only from a
  ; validated cached command index.
  lda.l ${recovery_flag:06X}
  beq cached_route_disabled
  lda.l ${record_count:06X}
  cmp #${max_records:04X}
  bcc cached_count_room
  brl active_fallback
cached_count_room:
  tax
  sep #$20
  lda.l ${row_count_address:06X}
  rep #$20
  and #$00FF
  cmp.l ${record_count:06X}
  beq cached_route_invalid
  bcc cached_route_invalid
  sep #$20
  lda.l ${records:06X},x
  cmp #${overlay_records:02X}
  bcs cached_route_invalid_8
  rep #$20
  and #$00FF
  sta.l ${current_record:06X}
  sta.l ${row_tile:06X}
  asl a
  asl a
  asl a
  sec
  sbc.l ${row_tile:06X}       ; seven-byte private stream per command
  clc
  adc #${stream_base:04X}
  pha
  bra route_allocate
cached_route_invalid_8:
  rep #$20
cached_route_invalid:
  brl active_fallback
cached_route_disabled:
  brl active_fallback
route_allocate:
  ; `$D0` belongs to the stock renderer and is deliberately preserved across
  ; a cursor move.  It therefore cannot tell us whether this redraw is at its
  ; first command: using it here resumed the allocation after stale rows and
  ; left old English tiles visible.  The command record counter is reset by
  ; the command lifecycle and advances exactly once per routed record.
  ; Derive allocation from the authoritative record index.  `row_tile` is
  ; also scratch for the frame/highlight mapper, so incrementing its previous
  ; value aliases two owners and skips VRAM rows after a redraw.
  lda.l ${record_count:06X}
  asl a                       ; 2n
  sta.l ${row_tile:06X}
  asl a                       ; 4n
  asl a                       ; 8n
  asl a                       ; 16n
  sec
  sbc.l ${row_tile:06X}       ; 14n = MENU_ROW_STRIDE * record index
row_ready:
  sta.l ${row_tile:06X}
  sta $D0
  lda #$0001
  sta.l ${row_pending:06X}
  lda #$0000
  sta.l ${row_rendered:06X}
  lda.l ${record_count:06X}
  cmp #${max_records:04X}
  bcs record_full
  tax
  sep #$20
  lda.l ${current_record:06X}
  sta.l ${records:06X},x
  rep #$20
  txa
  inc
  sta.l ${record_count:06X}
  bra record_done
record_full:
record_done:
  pla
  sta $1A
  sep #$20
  lda #$FA
  sta $1C
  rep #$20
  ldy #$0000
  lda [$1A],y
  and #$00FF
  inc $1A
  sta.l ${first_token:06X}
  ply
  plx
  pla                         ; discard first token from the native record
  plp
  rep #$20
  lda.l ${first_token:06X}
  jml ${menu_entry:06X}
active_fallback:
  rep #$20
  ply
  plx
  pla
  plp
  ; Stock owns selection bookkeeping and the upload request.  Mirror the
  ; palette only after it returns; the sync routine validates the live frame.
  jsl ${fallback_entry:06X}
  pha
  jsl ${selection_entry:06X}
  pla
  rtl
fallback:
  rep #$20
  ply
  plx
  pla
  plp
  jml ${fallback_entry:06X}
"""


def command_width_source(*, fallback_entry: int) -> str:
    """Reflow the three measured stock-writer row origins into our surface."""
    return f"""; Command-menu tilemap ownership before `$81:848E`.
.a16
.i16
command_width:
  php
  rep #$30
  pha
  sep #$20
  lda $1C
  cmp #$FA
  bne done
  rep #$20
  lda $18
  cmp #$2298
  beq row0
  cmp #$231A
  beq row1
  cmp #$23A0
  bne done
  lda #$241C
  bra set_cursor
row0:
  lda #$231C
  bra set_cursor
row1:
  lda #$239C
set_cursor:
  sta $18
done:
  rep #$20
  pla
  plp
  jml ${fallback_entry:06X}
"""
