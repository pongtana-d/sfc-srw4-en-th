; The adapter: the story engine's own rasterizer call, intercepted.
;
; The engine's loop reads a byte, works out a glyph code, and calls a rasteriser
; that draws it into the tile arena at a whole-cell cursor. That last step is
; the only one we take over. Everything else -- portraits, delays, line breaks,
; branching, the terminator -- stays the engine's, so its behaviour cannot
; change no matter what our text does.
;
; Whose text it is is decided per glyph, by the bank of the stream pointer the
; engine is reading from. Records we rewrote live in the expanded banks; the
; game's own text still lives where it always did and still goes to the game's
; own rasteriser, untouched.
;
; The engine measures in cells and we measure in pixels, so after each glyph we
; write back a cell cursor for it to keep bookkeeping with, and keep the real
; pen ourselves.
;
; Its cursor runs straight on through the whole window rather than restarting
; at each line, and the engine picks where a new line begins from its own
; bookkeeping, not from where we left off. So whenever it moves the cursor
; without us, that is a new line: we take its cursor as the line's base and
; start our pen at zero from there.

; ---------------------------------------------------------------------------
; draw_thai_glyph -- entered by jsl in place of the stock rasteriser.
;   in: A = the glyph code the engine computed. Direct page is the engine's.
; ---------------------------------------------------------------------------
draw_thai_glyph:
  php
  rep #$30
  sta.l CODE_SAVE            ; long: our data bank is not set up yet

  ; The stream pointer is at $CB-$CD. Its bank tells us who owns this record,
  ; except for the runtime names: `$FB xx 80` sends the engine to one of seven
  ; seven-byte buffers in low WRAM, through a table at $C1:8E6E whose bank
  ; byte is $00. Bank $00 is most of the game's own RAM, so those have to be
  ; recognised by address as well.
  sep #$20
  lda $CD
  cmp #SCRIPT_BANK_FIRST
  bcc maybe_a_name
  cmp #SCRIPT_BANK_LAST + 1
  bcc text_is_ours
  brl not_our_text           ; too far for a short branch
maybe_a_name:
  cmp #NAME_BANK
  beq name_bank
  brl not_our_text
name_bank:
  rep #$20
  lda $CB
  cmp #NAME_FIRST
  bcc leave_to_stock
  cmp #NAME_LAST
  bcc name_is_ours
leave_to_stock:
  brl not_our_text
name_is_ours:
  sep #$20
text_is_ours:

  phb
  lda #$7E
  pha
  plb                        ; the canvas and our state live in bank $7E
  rep #$30

  ; If the engine moved the cursor without us -- a line break, a new message,
  ; a position command -- start a fresh line at wherever it now points.
  lda $D0
  and #$03FF
  sta TMP+20
  cmp LAST_CURSOR
  beq pen_is_ours
  jsr clear_line             ; blanks the canvas and puts the pen at zero
  lda TMP+20
  sta LINE_BASE              ; wherever the engine went is where this line starts
pen_is_ours:

  ; The code the engine computed becomes one of our glyph ids. Single bytes
  ; are the id itself; anything the engine read as a two-byte escape lands in
  ; the extended block.
  lda.l CODE_SAVE
  cmp #$0100
  bcc id_ready
  sec
  sbc #$0100
  clc
  adc #GLYPH_DIRECT_SLOTS
id_ready:
  tax

  lda PEN
  lsr a
  lsr a
  lsr a
  sta TMP+22                 ; the first cell this glyph can touch

  jsr blit_glyph             ; draws at the pen and moves it along

  lda PEN
  beq nothing_drawn
  dec a
  lsr a
  lsr a
  lsr a
  sta TMP+24                 ; the last cell it can have touched
  jsr flush_cells
nothing_drawn:

  ; Hand the engine a cell cursor that covers everything we drew, so its own
  ; upload and its idea of where the line has got to both stay right.
  lda PEN
  clc
  adc #7
  lsr a
  lsr a
  lsr a
  asl a                      ; cells -> tiles
  clc
  adc LINE_BASE
  sta LAST_CURSOR
  sta $D0

  ; The engine wraps the line by counting in units of four pixels, so give it
  ; our pen in the same units instead of its own per-glyph guess. One byte
  ; only: the byte above it is the engine's line counter, and a sixteen-bit
  ; store would wipe it out every glyph.
  lda PEN
  lsr a
  lsr a
  sep #$20
  sta $0E2A
  rep #$20
  plb
  plp
  rtl

not_our_text:
  rep #$30
  lda.l CODE_SAVE
  plp
  jml STOCK_RASTERISER

; ---------------------------------------------------------------------------
; flush_cells -- copy the cells a glyph touched into the tile arena.
;   in: TMP+22 first cell, TMP+24 last cell. DB = $7E.
;
; A cell is two 8x16 halves of a 4bpp tile pair, sixty-four bytes apart, laid
; out exactly as the stock rasteriser lays them out: our bitmap in plane 0, and
; the colour bytes the engine keeps at $FD and $FE in the other three. Writing
; whole cells rather than single glyphs is what lets a glyph straddle a cell
; boundary without tearing the one before it.
; ---------------------------------------------------------------------------
flush_cells:
  php
  rep #$30
  lda TMP+22
  sta TMP+26
cell_loop:
  lda TMP+26
  cmp TMP+24
  beq cell_last
  bcs cells_done
cell_last:
  cmp #CANVAS_CELLS
  bcs cells_done

  ; arena offset = the line's own base, plus this cell
  asl a
  asl a
  asl a
  asl a
  asl a
  asl a                      ; cell * 64
  sta TMP+28
  lda LINE_BASE
  asl a
  asl a
  asl a
  asl a
  asl a                      ; tiles * 32
  clc
  adc TMP+28
  sta TMP+28

  ; the top half: canvas rows 0-7
  ldx TMP+28
  lda TMP+26
  clc
  adc #CANVAS
  tay
  jsr flush_half

  ; the bottom half: canvas rows 8-15, thirty-two bytes further into the tile
  lda TMP+28
  clc
  adc #$0020
  tax
  lda TMP+26
  clc
  adc #CANVAS_ROW8
  tay
  jsr flush_half

  inc TMP+26
  bra cell_loop
cells_done:
  plp
  rts

; ---------------------------------------------------------------------------
; flush_half -- eight rows of one 8x8 tile.
;   in: X = arena offset, Y = address of the first canvas row. DB = $7E.
; ---------------------------------------------------------------------------
flush_half:
  php
  rep #$30
  lda #8
  sta TMP+30
half_row:
  sep #$20
  lda $0000,y
  sta ARENA_BASE,x           ; plane 0 is the glyph
  lda $FD
  sta ARENA_BASE + 1,x       ; plane 1 is the colour the engine chose
  rep #$20
  lda $FE
  sta ARENA_BASE + $10,x     ; planes 2 and 3
  txa
  clc
  adc #2
  tax
  tya
  clc
  adc #CANVAS_STRIDE
  tay
  dec TMP+30
  bne half_row
  plp
  rts
