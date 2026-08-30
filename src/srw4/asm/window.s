; Dynamic window-frame bridge shared by every surface adapter.
;
; The caller gives a byte cursor into the 32x32 shadow tilemap plus an outer
; width and height in tiles.  This routine only owns border cells; text and
; fill cells remain the surface's responsibility.  That keeps it usable for
; the command menu and for windows whose content is already written by the
; game loop.

; FRAME_CURSOR  byte offset into TILEMAP (even, 0..$07FE)
; FRAME_WIDTH   outer width in tiles, minimum 3
; FRAME_HEIGHT  outer height in tiles, minimum 3

.a16
.i16

draw_window_frame:
  php
  rep #$30
  lda FRAME_WIDTH
  cmp #3
  bcs frame_width_ok
  brl frame_done
frame_width_ok:
  lda FRAME_HEIGHT
  cmp #3
  bcs frame_height_ok
  brl frame_done
frame_height_ok:

  ; Values derived once so all three rows use exactly the same geometry.
  lda FRAME_WIDTH
  dec a
  dec a
  sta FRAME_INNER            ; cells between left and right borders
  lda FRAME_HEIGHT
  dec a
  dec a
  sta FRAME_ROWS             ; rows between top and bottom borders
  lda FRAME_WIDTH
  asl a
  sta FRAME_WIDTH_BYTES
  dec a
  dec a
  sta FRAME_RIGHT_DELTA      ; left cell -> right cell
  lda #$0042                 ; 64-byte row stride + one right-hand cell
  sec
  sbc FRAME_WIDTH_BYTES
  sta FRAME_NEXT_DELTA       ; right cell -> next row's left cell

  ; Top edge.
  ldx FRAME_CURSOR
  lda #FRAME_TOP_LEFT
  sta TILEMAP,x
  inx
  inx
  ldy FRAME_INNER
frame_top_loop:
  lda #FRAME_TOP
  sta TILEMAP,x
  inx
  inx
  dey
  bne frame_top_loop
  lda #FRAME_TOP_RIGHT
  sta TILEMAP,x

  ; Each middle row is left/right only.  The frame must not erase text that a
  ; surface might already have put into its content cells.
  txa
  clc
  adc FRAME_NEXT_DELTA
  tax
  ldy FRAME_ROWS
frame_middle_loop:
  lda #FRAME_LEFT
  sta TILEMAP,x
  txa
  clc
  adc FRAME_RIGHT_DELTA
  tax
  lda #FRAME_RIGHT
  sta TILEMAP,x
  txa
  clc
  adc FRAME_NEXT_DELTA
  tax
  dey
  bne frame_middle_loop

  ; Bottom edge. X now names its left cell.
  lda #FRAME_BOTTOM_LEFT
  sta TILEMAP,x
  inx
  inx
  ldy FRAME_INNER
frame_bottom_loop:
  lda #FRAME_BOTTOM
  sta TILEMAP,x
  inx
  inx
  dey
  bne frame_bottom_loop
  lda #FRAME_BOTTOM_RIGHT
  sta TILEMAP,x
frame_done:
  plp
  rts
