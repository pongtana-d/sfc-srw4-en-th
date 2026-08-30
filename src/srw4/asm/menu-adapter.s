; Catalog-13 command-menu adapter.
;
; The stock parser remains responsible for command availability and controls.
; This adapter owns only catalog-13 records moved to $FA, the expanded frame,
; and the palette-band selection mirror.  It is reached from the two measured
; callsites: $82:843B (open/redraw) and $83:89F5 (selection update).

.a16
.i16

; ---------------------------------------------------------------------------
; menu_raster_dispatch -- global $C1:84E4 replacement, but only for $FA.
; The ordinary catalog parser keeps its pointer in $1A-$1C.  The shared
; adapter uses $CB-$CD, so copy it for the call and restore it afterwards.
; ---------------------------------------------------------------------------
menu_raster_dispatch:
  php
  rep #$30
  sta.l CODE_SAVE
  lda.l MENU_ACTIVE
  cmp #MENU_ROUTING_COOKIE
  beq menu_routing_active
  lda.l CODE_SAVE
  jsl STOCK_RASTERISER
  plp
  rtl
menu_routing_active:
  sep #$20
  lda $1C
  cmp #MENU_POOL_BANK
  beq menu_pool_candidate
  cmp #$D2
  beq menu_native_command
  cmp #$FE
  beq menu_english_command
  rep #$20
  bra menu_stock
menu_pool_candidate:
  rep #$20
  lda $1A
  cmp #MENU_CELL_STREAM_FIRST
  bcc menu_stock
  cmp #MENU_CELL_STREAM_END
  bcs menu_stock
  bra menu_text
menu_native_command:
  rep #$20
  lda $1A
  cmp #$8613
  bcc menu_stock
  cmp #$865E
  bcs menu_stock
  lda.l CODE_SAVE
  plp
  rtl
menu_english_command:
  rep #$20
  lda $1A
  cmp #$D85C
  bcc menu_stock
  cmp #$D900
  bcs menu_stock
  lda.l CODE_SAVE
  plp
  rtl
menu_stock:
  lda.l CODE_SAVE
  jsl STOCK_RASTERISER
  plp
  rtl
menu_text:
  rep #$20
  jsr menu_upload_overlay_cell
  lda.l CODE_SAVE
  plp
  rtl

; Render one 8x16 cell while the untouched stock writer owns its tilemap word.
; The private command stream contains exactly six narrow padding glyphs, as in
; EN.  Each call copies the corresponding pre-rendered Thai cell to `$D0` and
; advances the stock tile allocator by one vertical tile pair.
menu_upload_overlay_cell:
  phb
  phx
  phy
  sep #$20
  lda #$7E
  pha
  plb
  rep #$30
  lda.l MENU_CURRENT_RECORD
  tax
  txa
  asl a
  asl a
  asl a
  tax
  lda.l MENU_OVERLAY+8,x
  tax
  lda.l MENU_ROW_RENDERED
  and #$00FF
  asl a
  asl a
  asl a
  asl a
  asl a
  asl a                       ; 64 bytes per 8x16 4bpp cell
  sta MENU_CELLS
  txa
  clc
  adc MENU_CELLS
  tax
  lda $D0
  and #$03FF
  asl a
  asl a
  asl a
  asl a
  asl a
  tay
  sep #$20
  lda #$7F
  pha
  plb
  rep #$30
  lda $04
  pha
  lda #$0002                  ; two unrolled 32-byte blocks
  sta $04
menu_copy_planar_cell:
  lda.l MENU_OVERLAY,x
  sta $8000,y
  lda.l MENU_OVERLAY+$0002,x
  sta $8002,y
  lda.l MENU_OVERLAY+$0004,x
  sta $8004,y
  lda.l MENU_OVERLAY+$0006,x
  sta $8006,y
  lda.l MENU_OVERLAY+$0008,x
  sta $8008,y
  lda.l MENU_OVERLAY+$000A,x
  sta $800A,y
  lda.l MENU_OVERLAY+$000C,x
  sta $800C,y
  lda.l MENU_OVERLAY+$000E,x
  sta $800E,y
  lda.l MENU_OVERLAY+$0010,x
  sta $8010,y
  lda.l MENU_OVERLAY+$0012,x
  sta $8012,y
  lda.l MENU_OVERLAY+$0014,x
  sta $8014,y
  lda.l MENU_OVERLAY+$0016,x
  sta $8016,y
  lda.l MENU_OVERLAY+$0018,x
  sta $8018,y
  lda.l MENU_OVERLAY+$001A,x
  sta $801A,y
  lda.l MENU_OVERLAY+$001C,x
  sta $801C,y
  lda.l MENU_OVERLAY+$001E,x
  sta $801E,y
  txa
  clc
  adc #$0020
  tax
  tya
  clc
  adc #$0020
  tay
  dec $04
  bne menu_copy_planar_cell
  pla
  sta $04
  sep #$20
  lda #$7E
  pha
  plb
  rep #$30
  lda.l MENU_ROW_RENDERED
  inc a
  sta.l MENU_ROW_RENDERED
  cmp #MENU_CONTENT_CELLS
  bne menu_cell_palette_done
  ; This hook runs after stock has written the sixth tilemap cell.  Extending
  ; the palette here covers both initial open and cursor redraws without
  ; intercepting the shared selection/battle callsite.
  jsr menu_expand_current_palette
menu_cell_palette_done:
  lda MENU_ROW_TILE
  clc
  adc #$000C
  sta LAST_CURSOR
  sta $D0
  plb
  ply
  plx
  rts

; Present the current cell's tile pair to the untouched stock writer.  The
; raster routine restores `$D0` to the end of the row immediately afterwards,
; preserving the same allocator/DMA contract as the proven whole-row path.
menu_prepare_overlay_cell:
  php
  rep #$30
  pha
  sep #$20
  lda $1C
  cmp #MENU_POOL_BANK
  bne menu_prepare_overlay_done_8
  rep #$20
  lda $1A
  cmp #MENU_CELL_STREAM_FIRST
  bcc menu_prepare_overlay_done
  cmp #MENU_CELL_STREAM_END
  bcs menu_prepare_overlay_done
  lda.l MENU_ROW_RENDERED
  and #$00FF
  asl a
  clc
  adc.l MENU_ROW_TILE_LONG
  sta $D0
menu_prepare_overlay_done:
  pla
  plp
  rtl
menu_prepare_overlay_done_8:
  rep #$20
  bra menu_prepare_overlay_done

; ---------------------------------------------------------------------------
; menu_activation -- replacement for `$82:84BB` through a five-byte JML.
;
; The en reference replaces the original `LDA #$FFFF` at this exact point.
; It is inside the command parser's own lifecycle, before the stock writer
; reaches `$81:84E4`; invoking `$81:83C6` again from here recursively parses
; the menu and corrupts the renderer state.  Reproduce the displaced
; `LDA #$00FF / TRB $0E26` before returning to `$82:84C1`.
; ---------------------------------------------------------------------------
menu_activation:
  php
  rep #$30
  phb
  sep #$20
  lda #$7E
  pha
  plb
  rep #$30
  lda.l MENU_ACTIVE
  cmp #MENU_ROUTING_COOKIE
  bne menu_activation_stock
  lda #MENU_ROUTING_COOKIE
  sta.l MENU_ACTIVE
menu_activation_stock:
  plb
  plp
  rep #$20
  lda #$00FF
  trb $0E26
  jml $8284C1

; ---------------------------------------------------------------------------
; menu_command_open -- guarded command-menu open/redraw owner at `$82:843B`.
; ---------------------------------------------------------------------------
menu_command_open:
  php
  rep #$30
  cmp #$0022                  ; measured current cumulative command-menu key
  beq menu_command_owned
  ; This shared parser owner is reached for the destination screen after a
  ; command is confirmed.  Retire the command-only router before handing that
  ; different catalog back to stock; otherwise a later `$D2` stream can be
  ; mistaken for one of the five command records and rasterise to black.
  pha
  lda #$0000
  sta.l MENU_ACTIVE
  sta.l MENU_CACHE_RECOVERY
  pla
  plp
  jml $8183C6                 ; preserve the original caller's return frame
menu_command_owned:
  pha                         ; parser input: catalog/id in A (measured $00AC)
  phx                         ; the continuation owns its original index state
  phy
  phb
  sep #$20
  lda #$7E
  pha
  plb
  rep #$30
  lda #MENU_ROUTING_COOKIE
  sta.l MENU_ACTIVE
  lda #$0000
  sta.l MENU_MAX_PEN
  sta.l MENU_RECORD_COUNT
  sta MENU_FRAME_PTR
  lda #$FFFF
  sta LAST_CURSOR
  lda #$0001
  sta.l MENU_CACHE_RECOVERY
  plb
  ply
  plx
  pla
  jsl $8183C6
menu_command_after_parser:
  pha                         ; preserve the stock parser's return value
  phb
  sep #$20
  lda #$7E
  pha
  plb
  rep #$30
  lda #$0000
  sta.l MENU_CACHE_RECOVERY
  lda.l MENU_RECORD_COUNT
  beq menu_command_restore
  lda #MENU_ROUTING_COOKIE
  sta.l MENU_ACTIVE
menu_command_restore:
  plb
  pla
  plp
  rtl

; ---------------------------------------------------------------------------
; menu_selection_update -- replacement JSL at $83:89F5.
;
; `$7E:0E3A` is the stock selected-row byte.  The surrounding stock routine
; updates it (and `$0E3B`, the row count) before this parser call, but the
; parser still owns the tilemap-upload request consumed by the next NMI.
; Preserve that contract, then mirror only the palette band while our
; expanded command frame is live.  This callsite is shared, so never clear or
; rebuild a surface here.
; ---------------------------------------------------------------------------
menu_selection_update:
  php
  rep #$30
  pha                         ; parser input from the original caller
  phx
  lda.l MENU_ACTIVE
  cmp #MENU_ROUTING_COOKIE
  bne menu_selection_stock
  ; A cookie can survive in old savestates or across a battle transition.
  ; Require the command frame itself before entering the custom selection
  ; path, otherwise the shared battle caller must remain entirely stock.
  ldx MENU_FRAME_PTR
  lda TILEMAP,x
  and #$03FF
  cmp #FRAME_TOP_LEFT_TILE
  beq menu_selection_owned
menu_selection_stock:
  plx
  pla
  plp
  jml $8183C6                 ; preserve the original caller's return frame
menu_selection_owned:
  plx
  pla
  phx
  phy
  ; The parser requests the BG tilemap upload as well as doing its stock
  ; bookkeeping.  Skipping it leaves WRAM correct but the visible highlight
  ; frozen in VRAM.  Preserve its return value across the scoped mirror.
  jsl $8183C6
  pha
  phb
  sep #$20
  lda #$7E
  pha
  plb
  rep #$30
  ; The stock parser can transiently clear the cookie through a shared owner.
  ; This wrapper already passed both entry guards, so restore the scoped cookie
  ; and decide liveness from the frame word after the parser has returned.
  lda #MENU_ROUTING_COOKIE
  sta.l MENU_ACTIVE
  ldx MENU_FRAME_PTR
  lda TILEMAP,x
  and #$03FF
  cmp #FRAME_TOP_LEFT_TILE
  bne menu_selection_inactive
  sep #$20
  lda $0E3A
  rep #$20
  and #$00FF
  sta MENU_SELECTED_ROW
  jsr menu_refresh_selection
  bra menu_selection_restore
menu_selection_inactive:
  lda #$0000
  sta.l MENU_ACTIVE
menu_selection_restore:
  plb
  pla
  ply
  plx
menu_selection_done:
  plp
  rtl

; Sync selection from a parser-core hook after the stock owner has updated
; its selected-row byte.  This avoids patching `$83:89F5`, whose bytes are
; also consumed as battle data in the cumulative ROM.
menu_selection_sync:
  php
  rep #$30
  phx
  phy
  phb
  sep #$20
  lda #$7E
  pha
  plb
  rep #$30
  jsr menu_find_frame
  bcc menu_selection_sync_done
  lda.l MENU_RECORD_COUNT
  beq menu_selection_sync_done
  cmp #MENU_MAX_ROWS+1
  bcc menu_selection_sync_rows_ready
  lda #MENU_MAX_ROWS
menu_selection_sync_rows_ready:
  sta MENU_ROWS
  jsr menu_find_selection
  jsr menu_refresh_palette
menu_selection_sync_done:
  plb
  ply
  plx
  plp
  rtl

; ---------------------------------------------------------------------------
; menu_surface -- find the stock-owned expanded frame, then map our rows.
; DB = $7E.
; ---------------------------------------------------------------------------
menu_surface:
  lda.l MENU_RECORD_COUNT
  bne menu_rows_nonzero
  lda #$0001
menu_rows_nonzero:
  cmp #MENU_MAX_ROWS+1
  bcc menu_rows_ready
  lda #MENU_MAX_ROWS
menu_rows_ready:
  sta MENU_ROWS
  asl a
  inc a
  inc a
  sta FRAME_HEIGHT
  jsr menu_find_frame
  bcc menu_surface_missing
  jsr menu_clear_stock_footprint
  lda MENU_FRAME_PTR
  sta FRAME_CURSOR
  lda #MENU_DRAW_OUTER
  sta FRAME_WIDTH
  sta MENU_WIDTH
  jsr draw_window_frame
  jsr menu_refresh_selection
  rts
menu_surface_missing:
  lda #$0000
  sta.l MENU_ACTIVE
  rts

; Thai records are proportional and do not contain EN's per-row padding, so
; the stock cursor can leave later sides one cell left of the selected anchor.
; Clear that dynamic footprint once, then let `draw_window_frame` publish the
; exact rectangle.  This replaces the old fixed-coordinate cleanup bug.
menu_clear_stock_footprint:
  lda MENU_FRAME_PTR
  sta FRAME_CURSOR
  lsr a
  and #$001F
  sta MENU_ROW_INDEX
  cmp #MENU_CLEAN_MARGIN
  bcc menu_clear_stock_left_ready
  lda #MENU_CLEAN_MARGIN
menu_clear_stock_left_ready:
  sta MENU_ATTR
  asl a
  sta MENU_CELLS
  lda FRAME_CURSOR
  sec
  sbc MENU_CELLS
  sta FRAME_CURSOR
  lda #MENU_DRAW_OUTER
  clc
  adc MENU_ATTR
  sta FRAME_WIDTH
  lda #MENU_TILEMAP_ROW_CELLS-MENU_DRAW_OUTER
  sec
  sbc MENU_ROW_INDEX
  cmp #MENU_CLEAN_MARGIN
  bcc menu_clear_stock_right_ready
  lda #MENU_CLEAN_MARGIN
menu_clear_stock_right_ready:
  clc
  adc FRAME_WIDTH
menu_clear_stock_width:
  sta FRAME_WIDTH
  ldy FRAME_HEIGHT
menu_clear_stock_row:
  ldx FRAME_CURSOR
  lda FRAME_WIDTH
  sta MENU_CELLS
menu_clear_stock_cell:
  lda #$0010
  sta TILEMAP,x
  inx
  inx
  dec MENU_CELLS
  bne menu_clear_stock_cell
  lda FRAME_CURSOR
  clc
  adc #$0040
  sta FRAME_CURSOR
  dey
  bne menu_clear_stock_row
  rts

; Locate the single stock-owned 8-tile frame in the visible shadow map.
; EN expands this same frame through catalog `$0022`; it never draws a second
; fixed window.  Validate the whole top edge so unrelated windows cannot be
; claimed merely because they share the top-left border tile.
menu_find_frame:
  ldx #$0000
menu_find_frame_next:
  txa
  lsr a
  and #$001F
  cmp #$0019                  ; an 8-tile frame needs x <= 24
  bcs menu_find_frame_advance
  lda TILEMAP,x
  and #$03FF
  cmp #FRAME_TOP_LEFT_TILE
  bne menu_find_frame_advance
  lda TILEMAP+$0002,x
  and #$03FF
  cmp #FRAME_TOP_TILE
  bne menu_find_frame_advance
  lda TILEMAP+$0004,x
  and #$03FF
  cmp #FRAME_TOP_TILE
  bne menu_find_frame_advance
  lda TILEMAP+$0006,x
  and #$03FF
  cmp #FRAME_TOP_TILE
  bne menu_find_frame_advance
  lda TILEMAP+$0008,x
  and #$03FF
  cmp #FRAME_TOP_TILE
  bne menu_find_frame_advance
  lda TILEMAP+$000A,x
  and #$03FF
  cmp #FRAME_TOP_TILE
  bne menu_find_frame_advance
  lda TILEMAP+$000C,x
  and #$03FF
  cmp #FRAME_TOP_TILE
  bne menu_find_frame_advance
  lda TILEMAP+$000E,x
  and #$03FF
  cmp #FRAME_TOP_RIGHT_TILE
  bne menu_find_frame_advance
  stx MENU_FRAME_PTR
  sec
  rts
menu_find_frame_advance:
  inx
  inx
  cpx #$0700                  ; visible 32x28 tile rows
  bcc menu_find_frame_next
  clc
  rts

; ---------------------------------------------------------------------------
; menu_refresh_selection -- copy stock's selected/unselected attribute from
; its legacy three-cell row into our entire dynamic row. DB = $7E.
; ---------------------------------------------------------------------------
menu_refresh_selection:
  ldx MENU_FRAME_PTR
  lda TILEMAP,x
  and #$03FF
  cmp #FRAME_TOP_LEFT_TILE
  beq menu_frame_is_live
  lda #$0000
  sta.l MENU_ACTIVE
  rts
menu_frame_is_live:
  txa
  clc
  adc #MENU_CONTENT_DELTA
  sta MENU_CONTENT_PTR
  lda #MENU_FIRST_TILE
  sta MENU_ROW_TILE
  lda #$0000
  sta MENU_ROW_INDEX
  ldy MENU_ROWS
menu_selection_row:
  lda MENU_ROW_INDEX
  cmp MENU_SELECTED_ROW
  beq menu_selected
  lda #$2100
  bra menu_attr_ready
menu_selected:
  lda #$2500
menu_attr_ready:
  sta MENU_ATTR
  ; The stock selection owner rewrites its width scratch on every move.
  ; Keep the command surface to its six cells, otherwise that stale width
  ; spills the highlight over the right border and exposes cached text.
  lda #MENU_CONTENT_CELLS
  sta MENU_CELLS
  ldx MENU_CONTENT_PTR
menu_selection_cell:
  lda MENU_ROW_TILE
  ora MENU_ATTR
  sta TILEMAP,x
  inc MENU_ROW_TILE
  inx
  inx
  lda MENU_ROW_TILE
  ora MENU_ATTR
  sta TILEMAP+$003E,x
  inc MENU_ROW_TILE
  dec MENU_CELLS
  bne menu_selection_cell
  lda MENU_CONTENT_PTR
  clc
  adc #$0080
  sta MENU_CONTENT_PTR
  lda MENU_ROW_TILE
  clc
  adc #MENU_ROW_GAP
  sta MENU_ROW_TILE
  inc MENU_ROW_INDEX
  dey
  bne menu_selection_row
  rts

; Read the selected stock row before erasing the temporary stock redraw.
; `$0E3A` is a byte and `$0E3B` is the row count, so do not load a word.
menu_find_selection:
  sep #$20
  lda $0E3A
  rep #$20
  and #$00FF
  sta MENU_SELECTED_ROW
  rts

; The border is finalised after the text parser, so it cannot anchor this
; operation yet.  Locate the just-written top tile sequence instead; its six
; exact ids identify one command row without relying on a fixed screen
; position.  Change only `$0400`, never the ids or the frame attributes.
menu_expand_current_palette:
  lda.l MENU_RECORD_COUNT
  bne menu_expand_palette_has_row
  brl menu_expand_palette_done
menu_expand_palette_has_row:
  dec a
  sta MENU_ROW_INDEX
  sep #$20
  lda $0E3A
  rep #$20
  and #$00FF
  cmp MENU_ROW_INDEX
  beq menu_expand_palette_selected
  lda #$0000
  bra menu_expand_palette_attr_ready
menu_expand_palette_selected:
  lda #$0400
menu_expand_palette_attr_ready:
  sta MENU_ATTR
  ldx #$0000
menu_expand_palette_scan:
  lda TILEMAP,x
  and #$03FF
  sec
  sbc MENU_ROW_TILE
  cmp #$0100
  bne menu_expand_palette_next
  lda TILEMAP+$0002,x
  and #$03FF
  sec
  sbc MENU_ROW_TILE
  cmp #$0102
  bne menu_expand_palette_next
  lda TILEMAP+$0004,x
  and #$03FF
  sec
  sbc MENU_ROW_TILE
  cmp #$0104
  bne menu_expand_palette_next
  lda TILEMAP+$0006,x
  and #$03FF
  sec
  sbc MENU_ROW_TILE
  cmp #$0106
  bne menu_expand_palette_next
  lda TILEMAP+$0008,x
  and #$03FF
  sec
  sbc MENU_ROW_TILE
  cmp #$0108
  bne menu_expand_palette_next
  lda TILEMAP+$000A,x
  and #$03FF
  sec
  sbc MENU_ROW_TILE
  cmp #$010A
  bne menu_expand_palette_next
  lda #MENU_CONTENT_CELLS
  sta MENU_CELLS
menu_expand_palette_cell:
  lda TILEMAP,x
  and #$FBFF
  ora MENU_ATTR
  sta TILEMAP,x
  lda TILEMAP+$0040,x
  and #$FBFF
  ora MENU_ATTR
  sta TILEMAP+$0040,x
  inx
  inx
  dec MENU_CELLS
  bne menu_expand_palette_cell
  rts
menu_expand_palette_next:
  inx
  inx
  cpx #$06F6                  ; last visible start for a six-cell row
  bcs menu_expand_palette_done
  brl menu_expand_palette_scan
menu_expand_palette_done:
  rts

; Extend the stock three-cell green band across all six command cells without
; replacing any tile number or any other attribute.  `$0400` is the single
; palette bit that distinguishes stock selected `$25xx` from normal `$21xx`.
menu_refresh_palette:
  lda MENU_FRAME_PTR
  clc
  adc #MENU_CONTENT_DELTA
  sta MENU_CONTENT_PTR
  lda #$0000
  sta MENU_ROW_INDEX
  ldy MENU_ROWS
menu_palette_row:
  lda MENU_ROW_INDEX
  cmp MENU_SELECTED_ROW
  beq menu_palette_selected
  lda #$0000
  bra menu_palette_attr_ready
menu_palette_selected:
  lda #$0400
menu_palette_attr_ready:
  sta MENU_ATTR
  lda #MENU_CONTENT_CELLS
  sta MENU_CELLS
  ldx MENU_CONTENT_PTR
menu_palette_cell:
  lda TILEMAP,x
  and #$FBFF
  ora MENU_ATTR
  sta TILEMAP,x
  lda TILEMAP+$0040,x
  and #$FBFF
  ora MENU_ATTR
  sta TILEMAP+$0040,x
  inx
  inx
  dec MENU_CELLS
  bne menu_palette_cell
  lda MENU_CONTENT_PTR
  clc
  adc #$0080
  sta MENU_CONTENT_PTR
  inc MENU_ROW_INDEX
  dey
  bne menu_palette_row
  rts
