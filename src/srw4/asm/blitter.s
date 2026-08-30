; SRW4 Thai renderer -- the blitter.
;
; A glyph is 8 pixels wide, 16 rows tall, one bit per pixel, bit 7 leftmost.
; The pen is a pixel column rather than a cell, so a glyph almost always
; straddles two canvas bytes. That is the whole trick here: put the glyph byte
; in the high half of A, shift the pair right by (pen & 7), and the two halves
; fall out already aligned, one for each byte.
;
; Rows sit CANVAS_STRIDE bytes apart instead of the 32 a 256-pixel line needs.
; The spare bytes are what a glyph at the right-hand edge spills into, so a
; word write can never reach the row below.
;
; Nothing here knows about vowels, tone marks or spacing. Every glyph arrives
; composed and measured; the blitter shifts and ORs, and that is all.
;
; Long-indexed reads can only use X on this CPU, so X belongs to the ROM tables
; and Y to the canvas throughout.
;
; Constants come from the build:
;   CANVAS PEN DIRTY_FIRST DIRTY_LAST OVERFLOW SRC LEN TMP   -- bank $7E
;   GLYPH_BASE ADVANCE_TABLE SLOT_TABLE OPERAND_TABLE        -- 24-bit, in ROM
;   CANVAS_STRIDE CANVAS_ROWS CANVAS_BYTES CANVAS_WIDTH
;   GLYPH_COUNT GLYPH_DIRECT_SLOTS GLYPH_EXTENDED_PAGES

.a16
.i16

; TMP+0 bitmap offset   TMP+2 shift   TMP+4 canvas offset   TMP+6 rows left
; TMP+8 glyph id        TMP+10 stream scratch   TMP+12 ink seen
; TMP+14 last operand   TMP+16 command lead

; ---------------------------------------------------------------------------
; clear_line -- blank the canvas, reset the pen and the dirty range.
; ---------------------------------------------------------------------------
clear_line:
  php
  rep #$30
  ldx #0
clear_loop:
  stz CANVAS,x
  inx
  inx
  cpx #CANVAS_BYTES
  bne clear_loop
  stz PEN
  stz OVERFLOW
  lda #$FFFF
  sta DIRTY_FIRST
  stz DIRTY_LAST
  plp
  rts

; ---------------------------------------------------------------------------
; blit_glyph -- draw one glyph at the pen, then move the pen along.
;   in: X = glyph id. DB = $7E.
; ---------------------------------------------------------------------------
blit_glyph:
  php
  rep #$30

  ; A glyph id past the end of the token map means the stream is broken.
  cpx #GLYPH_COUNT
  bcc glyph_in_range
  plp
  rts
glyph_in_range:
  stx TMP+8

  ; Two tokens may share one bitmap, so the id goes through a slot table.
  txa
  asl a
  tax
  lda SLOT_TABLE,x
  sta TMP+0

  ; A glyph that starts past the right-hand edge is counted and dropped: the
  ; canvas has two spare bytes per row, not another cell to draw in.
  lda PEN
  cmp #CANVAS_WIDTH
  bcc pen_on_canvas
  lda OVERFLOW
  clc
  adc #8
  sta OVERFLOW
  bra advance_pen
pen_on_canvas:

  ; A glyph that only half fits still draws; the pixels past the edge are
  ; counted so nobody has to guess later why a line looked short.
  lda PEN
  clc
  adc #8
  cmp #CANVAS_WIDTH+1
  bcc no_spill
  sec
  sbc #CANVAS_WIDTH
  clc
  adc OVERFLOW
  sta OVERFLOW
no_spill:

  ; The pen splits into a byte column and a shift inside that byte.
  lda PEN
  and #$0007
  sta TMP+2
  lda PEN
  lsr a
  lsr a
  lsr a
  sta TMP+4

  stz TMP+12
  lda #CANVAS_ROWS
  sta TMP+6

row_loop:
  ldx TMP+0
  sep #$20
  lda GLYPH_BASE,x
  rep #$20
  and #$00FF
  pha
  ora TMP+12
  sta TMP+12                 ; remember whether this glyph drew anything at all
  pla
  xba                        ; A = row << 8

  ldx TMP+2
  beq no_shift
shift_loop:
  lsr a
  dex
  bne shift_loop
no_shift:
  xba                        ; low half -> this byte, high half -> the spill

  ldy TMP+4
  ora CANVAS,y
  sta CANVAS,y

  inc TMP+0
  lda TMP+4
  clc
  adc #CANVAS_STRIDE
  sta TMP+4
  dec TMP+6
  bne row_loop

  ; A glyph with no ink -- the space -- must not widen the dirty range, or the
  ; ROM would upload cells the reference renderer never touched.
  lda TMP+12
  beq advance_pen
  jsr mark_dirty

advance_pen:
  ; Move the pen on, and keep whatever ran off the edge instead of losing it.
  ldx TMP+8
  sep #$20
  lda ADVANCE_TABLE,x
  rep #$20
  and #$00FF
  clc
  adc PEN
  sta PEN
glyph_done:
  plp
  rts

; ---------------------------------------------------------------------------
; mark_dirty -- widen the touched-cell range to cover the glyph at the pen.
; ---------------------------------------------------------------------------
mark_dirty:
  lda PEN
  lsr a
  lsr a
  lsr a
  cmp DIRTY_FIRST
  bcs keep_first
  sta DIRTY_FIRST
keep_first:
  lda PEN
  clc
  adc #7
  cmp #CANVAS_WIDTH
  bcc last_on_canvas
  lda #CANVAS_WIDTH-1        ; a glyph at the edge stops at the last real cell
last_on_canvas:
  lsr a
  lsr a
  lsr a
  cmp DIRTY_LAST
  bcc keep_last
  sta DIRTY_LAST
keep_last:
  rts

; ---------------------------------------------------------------------------
; blit_stream -- draw one line, deciding byte by byte who owns each byte.
;   in: SRC = 24-bit stream pointer, LEN = bytes available. DB = $7E.
;   out: canvas, pen and dirty range. Stops at a line break, at the end of the
;        run, or at a byte in the $D4-$EB gap, which belongs to nobody.
;
; The stream pointer lives on the stack while this runs, with the direct page
; pointed at it, because that is the only way to reach [dp],y without taking a
; slice of the low WRAM mirror for ourselves.
; ---------------------------------------------------------------------------
blit_stream:
  php
  rep #$30
  phd
  sep #$20
  lda SRC+2
  pha                        ; bank first, so the three bytes read as a pointer
  rep #$20
  lda SRC
  pha
  tsc
  tcd                        ; direct page now sits on that pointer
  brl stream_loop

; The loop has more exits than a short branch can reach from its far end, so
; they all hop through here.
leave_stream:
  brl stream_done            ; too far for a short branch

stream_loop:
  lda LEN
  beq leave_stream
  jsr next_byte

  cmp #$00D0
  bcs not_direct
  ; $00-$CF: the byte is the glyph id itself. The common case goes first and
  ; stays next to the top of the loop, where a short branch can still reach it.
  tax
  jsr blit_glyph
  brl stream_loop

not_direct:
  cmp #$00EC
  bcc leave_stream           ; $D0-$EB belongs to nobody: stop, do not draw
  cmp #$00F0
  bcc engine_command         ; $EC-$EF are the engine's
  cmp #$00F0+GLYPH_EXTENDED_PAGES
  bcs high_engine_byte

  ; $F0-$F3: the engine's own two-byte glyph escape, which is how everything
  ; past the direct block is written. The lead picks a page, the byte after it
  ; is the index.
  sec
  sbc #$00F0
  xba                        ; page * 256
  sta TMP+10
  lda LEN
  beq leave_stream           ; a lead with no index is a broken stream
  jsr next_byte
  clc
  adc TMP+10
  clc
  adc #GLYPH_DIRECT_SLOTS
  tax
  jsr blit_glyph
  brl stream_loop

high_engine_byte:
  cmp #$00F6
  beq leave_stream           ; a line break ends the line

engine_command:
  ; From $EC up the byte is the stock engine's. Step over it and its operands.
  tax
  stx TMP+16
  sep #$20
  lda OPERAND_TABLE,x
  rep #$20
  and #$00FF
  beq back_to_loop
  sta TMP+10

skip_operand:
  lda LEN
  beq far_exit
  jsr next_byte
  sta TMP+14
  dec TMP+10
  bne skip_operand

  ; A command can carry more than its operand count declares, and what it
  ; carries is decided by the lead together with its last operand. None of it
  ; is text: reading these as glyphs would draw nonsense and then swallow the
  ; rest of the line. The same three shapes live in text.py's follows().
  lda TMP+16
  cmp #$00FB
  bne lead_not_fb
  lda TMP+14
  cmp #$000C                 ; $FB xx 0C -- a runtime name plus an address
  beq skip_two
  bra back_to_loop
lead_not_fb:
  cmp #$00FC
  bne back_to_loop
  lda TMP+14
  cmp #$0007                 ; $FC 07 -- an address
  beq skip_two
  cmp #$0008                 ; $FC 08 -- eight branch targets
  beq skip_sixteen
  cmp #$0000                 ; $FC 00 -- one more plain operand
  beq skip_one
  bra back_to_loop

skip_sixteen:
  lda #16
  bra skip_extra
skip_two:
  lda #2
  bra skip_extra
skip_one:
  lda #1
skip_extra:
  sta TMP+10

skip_address:
  lda LEN
  beq far_exit
  jsr next_byte
  dec TMP+10
  bne skip_address

back_to_loop:
  brl stream_loop

far_exit:
  brl stream_done

stream_done:
  tdc
  tcs                        ; drop the pointer we parked on the stack
  pla
  sep #$20
  pla
  rep #$30
  pld
  plp
  rtl

; ---------------------------------------------------------------------------
; next_byte -- read one byte and step the pointer. A = byte, high half clear.
; ---------------------------------------------------------------------------
next_byte:
  ldy #0
  sep #$20
  lda [$01],y
  rep #$20
  and #$00FF
  pha
  lda $01
  inc a
  sta $01
  bne same_bank
  sep #$20
  lda $03
  inc a
  sta $03
  rep #$20
same_bank:
  dec LEN
  pla
  rts
