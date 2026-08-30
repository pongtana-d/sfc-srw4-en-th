; Fixture harness: run the blitter on hardware, with no game around it.
;
; Every fixture is a token stream sitting in ROM. For each one the harness
; clears the canvas, runs blit_stream over it, and copies the canvas and the
; renderer state into a dump area where the emulator script can read them. It
; then sets a marker and parks, so the script knows the run finished rather
; than guessing from a frame count.
;
; Constants from the build: FIXTURES FIXTURE_COUNT DUMP_BASE DUMP_STRIDE
;                           DUMP_SPAN CANVAS_LONG MARKER COUNTER DUMP_OFF

.a16
.i16
.org $008000

reset:
  sei
  clc
  xce                        ; native mode
  rep #$30
  ldx #$1FFF
  txs
  sep #$20
  lda #$7E
  pha
  plb                        ; the blitter works with the data bank on $7E
  rep #$30

  stz COUNTER
  stz DUMP_OFF
  lda #$0001
  sta GUARD_STATUS
  lda #$FFFF
  sta GUARD_INDEX

fixture_loop:
  lda COUNTER
  cmp #FIXTURE_COUNT
  bcs all_done

  ; Descriptors are eight bytes each, so the index shifts rather than multiplies.
  asl a
  asl a
  asl a
  tax
  lda FIXTURES,x
  sta SRC
  sep #$20
  lda FIXTURES+2,x
  sta SRC+2
  rep #$20
  lda FIXTURES+3,x
  sta LEN

  jsr setup_guards
  jsr clear_line
  jsl blit_stream
  jsr check_guards

  ; Copy the canvas and the state out. The source is read long so the data
  ; bank can point at the dump instead. Y is loaded first, while the data bank
  ; still points at the block that holds it.
  ldy DUMP_OFF
  ldx #0
  sep #$20
  lda #$7F
  pha
  plb
  rep #$30
copy_loop:
  lda CANVAS_LONG,x
  sta $0000,y
  inx
  inx
  iny
  iny
  cpx #DUMP_SPAN
  bne copy_loop
  sep #$20
  lda #$7E
  pha
  plb
  rep #$30

  lda DUMP_OFF
  clc
  adc #DUMP_STRIDE
  sta DUMP_OFF
  lda COUNTER
  inc a
  sta COUNTER
  bra fixture_loop

all_done:
  jsr clear_tilemap
  lda #$02DA                 ; (x=13, y=11) in a 32-column word tilemap
  sta FRAME_CURSOR
  lda #8
  sta FRAME_WIDTH
  lda #10
  sta FRAME_HEIGHT
  jsr draw_window_frame
  lda #$005A                 ; (x=13, y=1), kept clear of the 8x10 menu frame
  sta FRAME_CURSOR
  lda #14                    ; P4's measured Thai long-label frame
  sta FRAME_WIDTH
  lda #4
  sta FRAME_HEIGHT
  jsr draw_window_frame
  jsr copy_tilemap
  sep #$20
  lda #$7F
  pha
  plb
  rep #$30
  lda #$BEEF
  sta MARKER
park:
  bra park

; The isolated ROM has no game state to corrupt, so surround the entire
; declared dialogue context with canaries.  A bad offset in the renderer must
; be a fixture failure, never an invisible write into adjacent WRAM.
setup_guards:
  ldx #0
  lda #$A55A
guard_fill:
  sta GUARD_BEFORE,x
  sta GUARD_AFTER,x
  inx
  inx
  cpx #GUARD_BYTES
  bne guard_fill
  rts

check_guards:
  ldx #0
  lda #$A55A
guard_check:
  cmp GUARD_BEFORE,x
  bne guard_broken
  cmp GUARD_AFTER,x
  bne guard_broken
  inx
  inx
  cpx #GUARD_BYTES
  bne guard_check
  rts
guard_broken:
  lda #$0000
  sta GUARD_STATUS
  txa
  sta GUARD_INDEX
  rts

; The command-menu proof writes its frame into the same shape of shadow map
; (`$7E:A000`, 32x32 words) that P1 captured.  The fixture clears it first so
; the checker can compare every cell, not merely the border cells it expects.
clear_tilemap:
  ldx #0
tilemap_clear_loop:
  stz TILEMAP,x
  inx
  inx
  cpx #$0800
  bne tilemap_clear_loop
  rts

; Copy the full shadow map to the dump bank.  Reads are long because DB is
; switched to `$7F` for the destination.
copy_tilemap:
  ldx #0
  ldy #TILEMAP_DUMP
  sep #$20
  lda #$7F
  pha
  plb
  rep #$30
tilemap_copy_loop:
  lda.l TILEMAP_LONG,x
  sta $0000,y
  inx
  inx
  iny
  iny
  cpx #$0800
  bne tilemap_copy_loop
  sep #$20
  lda #$7E
  pha
  plb
  rep #$30
  rts
