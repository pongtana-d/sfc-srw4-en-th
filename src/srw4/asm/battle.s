; Battle-only VWF state adapter, ported from the last proven pre-renewal path.
;
; The battle compositor owns tilemap placement and DMA.  Unlike the ordinary
; story adapter, it keeps an open 16x16 pair across calls, parks $D0 beyond the
; pair and its spill, and rebases $D2 when a new message resets $D0 backwards.
; That last rule prevents the compositor's D0-D2 upload length from underflowing
; into unrelated WRAM (the source of the checkerboard HUD corruption).

.a16
.i16

; Replacement for `$C1:9219-$921D`.  The stock engine adds two width units per
; source glyph; Thai adds them only when the open pen crosses an 8px cell.
battle_width_gate:
  rep #$30
  sta $02
  sep #$20
  lda $CD
  cmp #SCRIPT_BANK_FIRST
  bcc battle_width_stock
  cmp #SCRIPT_BANK_LAST+1
  bcs battle_width_stock
  rep #$20
  lda $02
  cmp #$0100
  bcc battle_width_id_ready
  sec
  sbc #$0100
  clc
  adc #GLYPH_DIRECT_SLOTS
battle_width_id_ready:
  tax
  lda BATTLE_SIGNATURE
  cmp #BATTLE_SIGNATURE_VALUE
  bne battle_width_fresh
  lda $D0
  cmp BATTLE_EXPECT
  bne battle_width_fresh
  lda BATTLE_PEN
  bra battle_width_have_pen
battle_width_fresh:
  lda #$0000
battle_width_have_pen:
  sta BATTLE_WORD
  sep #$20
  lda ADVANCE_TABLE,x
  rep #$20
  and #$00FF
  clc
  adc BATTLE_WORD
  cmp #$0008
  bcs battle_width_crossed
  jml $819236                ; enough room: draw without stock width increment
battle_width_crossed:
  jml $81921E                ; preserve CMP carry into stock ADC/wrap logic

battle_width_stock:
  rep #$20
  lda $02
  cmp #$0100
  jml $81921E

; in: X = current Thai glyph id, DB already $7E. out: stock-visible A/D0 state.
draw_battle_glyph:
  php
  rep #$30
  txa
  sta BATTLE_GLYPH

  lda BATTLE_SIGNATURE
  cmp #BATTLE_SIGNATURE_VALUE
  bne battle_first_run
  lda $D0
  cmp BATTLE_EXPECT
  bne battle_restart
  bra battle_carry

battle_first_run:
  lda $D0
  sta $D2                    ; a native savestate has no renderer DMA baseline
  bra battle_initialize

battle_restart:
  ; Only a backwards message reset with D2 still ahead can underflow the DMA.
  lda $D0
  cmp BATTLE_EXPECT
  bcs battle_initialize
  cmp $D2
  bcs battle_initialize
  sta $D2

battle_initialize:
  lda #BATTLE_SIGNATURE_VALUE
  sta BATTLE_SIGNATURE
  lda $D0
  and #$03FF
  sta BATTLE_CELL
  lda #$FFFF
  sta BATTLE_CLEARED
  lda #$0000
  sta BATTLE_PEN

  lda BATTLE_CELL
  jsr battle_clear_cell
  lda BATTLE_CELL
  clc
  adc #$0002
  jsr battle_clear_cell
  lda BATTLE_CELL
  clc
  adc #$0004
  jsr battle_clear_cell

battle_carry:
  ; Token -> deduplicated bitmap offset.
  lda BATTLE_GLYPH
  asl a
  tax
  lda SLOT_TABLE,x
  sta BATTLE_BITMAP
  lda BATTLE_CELL
  asl a
  asl a
  asl a
  asl a
  asl a
  sta BATTLE_TILE
  lda #$0008
  sta BATTLE_ROWS
  lda #$0000
  sta BATTLE_ROW

battle_row_loop:
  lda BATTLE_BITMAP
  clc
  adc BATTLE_ROW
  tax
  sep #$20
  lda GLYPH_BASE,x
  rep #$20
  and #$00FF
  xba
  pha
  lda BATTLE_PEN
  tay
  pla
  beq battle_top_shifted
battle_top_shift:
  lsr a
  dey
  bne battle_top_shift
battle_top_shifted:
  xba
  sta BATTLE_WORD

  lda BATTLE_TILE
  tax
  sep #$20
  lda BATTLE_WORD
  ora ARENA_BASE,x
  sta ARENA_BASE,x
  lda BATTLE_WORD+1
  ora ARENA_BASE+$40,x
  sta ARENA_BASE+$40,x
  rep #$20

  lda BATTLE_BITMAP
  clc
  adc BATTLE_ROW
  adc #$0008
  tax
  sep #$20
  lda GLYPH_BASE,x
  rep #$20
  and #$00FF
  xba
  pha
  lda BATTLE_PEN
  tay
  pla
  beq battle_bottom_shifted
battle_bottom_shift:
  lsr a
  dey
  bne battle_bottom_shift
battle_bottom_shifted:
  xba
  sta BATTLE_WORD

  lda BATTLE_TILE
  tax
  sep #$20
  lda BATTLE_WORD
  ora ARENA_BASE+$20,x
  sta ARENA_BASE+$20,x
  lda BATTLE_WORD+1
  ora ARENA_BASE+$60,x
  sta ARENA_BASE+$60,x
  lda $FD
  sta ARENA_BASE+1,x
  sta ARENA_BASE+$21,x
  sta ARENA_BASE+$41,x
  sta ARENA_BASE+$61,x
  rep #$20
  lda $FE
  sta ARENA_BASE+$10,x
  sta ARENA_BASE+$30,x
  sta ARENA_BASE+$50,x
  sta ARENA_BASE+$70,x

  lda BATTLE_TILE
  clc
  adc #$0002
  sta BATTLE_TILE
  lda BATTLE_ROW
  inc a
  sta BATTLE_ROW
  lda BATTLE_ROWS
  dec a
  sta BATTLE_ROWS
  beq battle_rows_done
  brl battle_row_loop
battle_rows_done:

  lda BATTLE_GLYPH
  tax
  sep #$20
  lda ADVANCE_TABLE,x
  rep #$20
  and #$00FF
  clc
  adc BATTLE_PEN
  cmp #$0008
  bcc battle_same_cell
  sec
  sbc #$0008
  sta BATTLE_PEN
  lda BATTLE_CELL
  clc
  adc #$0002
  and #$03FF
  sta BATTLE_CELL
  bra battle_park
battle_same_cell:
  sta BATTLE_PEN

battle_park:
  lda BATTLE_CELL
  clc
  adc #$0004
  and #$03FF
  sta $D0
  sta BATTLE_EXPECT
  jsr battle_clear_cell
  lda $D0
  clc
  adc #$0002
  jsr battle_clear_cell
  lda $D0
  plp
  rts

; in: A = pair id. Clears plane zero of its 16x16 dynamic-tile pair once.
battle_clear_cell:
  php
  rep #$30
  and #$03FF
  asl a
  asl a
  asl a
  asl a
  asl a
  cmp BATTLE_CLEARED
  beq battle_clear_done
  sta BATTLE_CLEARED
  tax
  ldy #$0008
battle_clear_loop:
  sep #$20
  lda #$00
  sta ARENA_BASE,x
  sta ARENA_BASE+$20,x
  sta ARENA_BASE+$40,x
  sta ARENA_BASE+$60,x
  lda #$00
  sta ARENA_BASE+1,x
  sta ARENA_BASE+$21,x
  sta ARENA_BASE+$41,x
  sta ARENA_BASE+$61,x
  rep #$20
  lda #$0000
  sta ARENA_BASE+$10,x
  sta ARENA_BASE+$30,x
  sta ARENA_BASE+$50,x
  sta ARENA_BASE+$70,x
  inx
  inx
  dey
  bne battle_clear_loop
battle_clear_done:
  plp
  rts
