"""Mixed Thai/English VWF adapter for the English dialogue compositor."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .asm65816 import assemble
from .en_dialogue_font import build_page_two, overlay_primary_dialogue_glyphs
from .en_ff_router import (
    DEFAULT_STORY_BANKS,
    ROUTER_PAGE_STATE,
    SUPPLEMENT_WIDTH_TABLE_CPU,
    THAI_WIDTH_TABLE_CPU,
)
from .proven.assembler import pc_to_cpu
from .proven.renderer65816 import (
    BATTLE_STATE_BASE,
    ORDINARY_STATE_BASE,
    build_renderer,
    shift_tables,
)
from .proven.text.font import build_page
from .proven.text.upper_stacks import build_upper_stack_assets


ROOT = Path(__file__).resolve().parents[2]
FONT = ROOT / "data" / "font"
# Hook the dialogue engine's callsite, not the shared rasterizer entry.  Status,
# menus and other EN surfaces also call $F0:E045 and must remain stock-owned.
DRAW_HOOK_PC = 0x019238
DRAW_HOOK_EXPECTED = bytes.fromhex("22 45 E0 F0")
WIDTH_HOOK_PC = 0x019219
WIDTH_HOOK_EXPECTED = bytes.fromhex("85 02 C9 00 01")

# Owned bank-$FF layout. The VWF reads assets with DB=$FF, so these addresses
# are deliberately explicit and validated as pristine before installation.
SHIFT_RIGHT_PC = 0x3F3000
SHIFT_LEFT_PC = 0x3F3800
PAGE_PC = 0x3F4000
ADVANCE_PC = 0x3F5000
LOCK_PC = 0x3F5100
MARK_DX_PC = 0x3F5200
MARK_Y_PC = 0x3F5300
MARK_SIZE_PC = 0x3F5400
BASE_INK_PC = 0x3F5500
RAISED_Y_PC = 0x3F5600
SHORTHAND_1_PC = 0x3F5700
SHORTHAND_2_PC = 0x3F5800
SHORTHAND_3_PC = 0x3F5900
UPPER_OVERLAY_PC = 0x3F5A00
UPPER_DX_PC = 0x3F5C00
UPPER_DY_PC = 0x3F5D00
UPPER_SIZE_PC = 0x3F5E00
SUPPLEMENT_PAGE_PC = 0x3F6000
SUPPLEMENT_ADVANCE_PC = 0x3F7000
THAI_STOCK_WIDTH_PC = 0x3F7100
SUPPLEMENT_STOCK_WIDTH_PC = 0x3F7200
# Runtime names reached through `$FB` live outside the relocated story banks.
# Keep their original EN glyph codes, but draw them through the same persistent
# VWF run as the adjacent Thai text so the first Thai glyph cannot clear them.
EN_FONT_PAGE_PC = 0x2E8000
EN_WIDTH_TABLE_PC = 0x30F000
STOCK_PAGE_PC = 0x3F7300
STOCK_ADVANCE_PC = 0x3F8300
WIDTH_ENTRY_PC = 0x3F8500
ENTRY_PC = 0x3F8800
THAI_RENDERER_PC = 0x3FA000
SUPPLEMENT_RENDERER_PC = 0x3FB000
STOCK_RENDERER_PC = 0x3FC000
ORDINARY_RENDERER_PC = 0x3FD000

# Catalog parsers tag Thai bytes so they cannot be confused with the stock
# direct page.  The dialogue adapter consumes the same public tag contract as
# the ordinary catalog renderer.
CATALOG_INTERNAL_BASE = 0x0A00
CATALOG_INTERNAL_LIMIT = 0x0AEC
CATALOG_FIXED_BASE = 0x0B00
CATALOG_FIXED_LIMIT = 0x0BEC
CATALOG_CLUSTER_PAGE_PC = 0x3FE000
CATALOG_CLUSTER_ADVANCE_PC = 0x3FF100
CATALOG_BATTLE_RENDERER_PC = 0x3FF410
CATALOG_BATTLE_PAGE_STATE = ORDINARY_STATE_BASE + 0x1C

if pc_to_cpu(THAI_STOCK_WIDTH_PC) != THAI_WIDTH_TABLE_CPU:
    raise AssertionError("Thai EN-width/router table layout differs")
if pc_to_cpu(SUPPLEMENT_STOCK_WIDTH_PC) != SUPPLEMENT_WIDTH_TABLE_CPU:
    raise AssertionError("supplement EN-width/router table layout differs")


@dataclass(frozen=True)
class RendererReport:
    bytes: int
    renderer_bytes: int


def _place_fill(image: bytearray, pc: int, data: bytes, owner: str) -> None:
    if image[pc:pc + len(data)] != b"\xFF" * len(data):
        raise ValueError(f"{owner} overlaps occupied ROM bytes at {pc:#08x}")
    image[pc:pc + len(data)] = data


def _jml(pc: int) -> bytes:
    cpu = pc_to_cpu(pc)
    return bytes((0x5C, cpu & 0xFF, (cpu >> 8) & 0xFF, cpu >> 16))


def _jsl(pc: int) -> bytes:
    cpu = pc_to_cpu(pc)
    return bytes((0x22, cpu & 0xFF, (cpu >> 8) & 0xFF, cpu >> 16))


def _stock_widths(advances: bytes) -> bytes:
    """Convert true pixel advances to the EN tail's width-minus-one format."""
    if len(advances) != 0x100:
        raise ValueError("EN dialogue advance table must contain 256 entries")
    return bytes(0xFF if advance == 0 else advance - 1 for advance in advances)


def _true_advances(widths: bytes) -> bytes:
    """Convert the EN renderer's width-minus-one table to true advances."""
    if len(widths) != 0x100:
        raise ValueError("EN dialogue width table must contain 256 entries")
    return bytes(0 if width == 0xFF else width + 1 for width in widths)


def _entry(story_banks: tuple[int, ...]) -> bytes:
    checks = "\n".join(
        f"  cmp #${bank:04X}\n  beq private" for bank in sorted(set(story_banks))
    )
    return assemble(f""".a16
.i16
entry:
  sta $00
  rep #$30
  lda $00
  cmp #${CATALOG_INTERNAL_BASE:04X}
  bcc source_route
  cmp #${CATALOG_INTERNAL_LIMIT:04X}
  bcc catalog_thai
  cmp #${CATALOG_FIXED_BASE:04X}
  bcc source_route
  cmp #${CATALOG_FIXED_LIMIT:04X}
  bcs source_route
  sec
  sbc #${CATALOG_FIXED_BASE:04X}
  pha
  lda #${SUPPLEMENT_PAGE_PC & 0xFFFF:04X}
  sta.l ${CATALOG_BATTLE_PAGE_STATE:06X}
  pla
  jml ${pc_to_cpu(CATALOG_BATTLE_RENDERER_PC):06X}
catalog_thai:
  sec
  sbc #${CATALOG_INTERNAL_BASE:04X}
  pha
  lda #${CATALOG_CLUSTER_PAGE_PC & 0xFFFF:04X}
  sta.l ${CATALOG_BATTLE_PAGE_STATE:06X}
  pla
  jml ${pc_to_cpu(CATALOG_BATTLE_RENDERER_PC):06X}
source_route:
  lda $CD
  and #$00FF
{checks}
stock:
  ; `$FB` runtime names switch the source pointer to WRAM.  Drawing them with
  ; the stock renderer and then starting the Thai renderer clears their tiles.
  ; Feed the original EN glyph id to a stock-atlas copy of the same VWF instead
  ; so English and Thai remain one run.  This callsite is dialogue-only; shared
  ; menu/status calls to $F0:E045 remain untouched.
  lda $00
  and #$00FF
  jml ${pc_to_cpu(STOCK_RENDERER_PC):06X}
private:
  lda.l ${ROUTER_PAGE_STATE:06X}
  cmp #$0002
  beq thai
  cmp #$0003
  beq supplement
  ; A battle savestate can resume after its C1/C2 lead has already been
  ; consumed.  All relocated private story/battle streams are Thai page one
  ; unless an explicit C2 lead selected the supplement page, so recover page
  ; one here instead of handing raw Thai slots to the stock renderer.
  bra thai
thai:
  lda $00
  and #$00FF
  jml ${pc_to_cpu(THAI_RENDERER_PC):06X}
supplement:
  lda $00
  and #$00FF
  jml ${pc_to_cpu(SUPPLEMENT_RENDERER_PC):06X}
""", ENTRY_PC).code


def _width_entry(story_banks: tuple[int, ...]) -> bytes:
    checks = "\n".join(
        f"  cmp #${bank:04X}\n  beq private" for bank in sorted(set(story_banks))
    )
    state = BATTLE_STATE_BASE
    return assemble(f""".a16
.i16
width_entry:
  sta $02
  cmp #${CATALOG_INTERNAL_BASE:04X}
  bcc source_route
  cmp #${CATALOG_INTERNAL_LIMIT:04X}
  bcc catalog_thai
  cmp #${CATALOG_FIXED_BASE:04X}
  bcc source_route
  cmp #${CATALOG_FIXED_LIMIT:04X}
  bcs source_route
  sec
  sbc #${CATALOG_FIXED_BASE:04X}
  tax
  lda #$0003
  sta.l ${ROUTER_PAGE_STATE:06X}
  brl index_ready
catalog_thai:
  sec
  sbc #${CATALOG_INTERNAL_BASE:04X}
  tax
  lda #$0004
  sta.l ${ROUTER_PAGE_STATE:06X}
  brl index_ready
source_route:
  lda $CD
  and #$00FF
{checks}
stock:
  lda $02
  cmp #$0100
  jml $81921E
private:
  lda.l ${ROUTER_PAGE_STATE:06X}
  cmp #$0002
  beq thai
  cmp #$0003
  beq supplement
  ; Match the draw-side stale-page recovery above.  Width runs before draw;
  ; charging this as stock would advance the battle compositor before the
  ; Thai renderer gets a chance to restore its persistent run.
  bra thai
supplement:
  lda $02
  and #$00FF
  cmp #$00C0
  bcs stock
  tax
  brl index_ready
thai:
  lda $02
  and #$00FF
  cmp #$00C0
  bcs stock
  tax
index_ready:
  lda.l ${state:06X}
  cmp #$A55A
  bne fresh
  lda $D0
  cmp.l ${state + 4:06X}
  bne fresh
  sep #$20
  lda.l ${state + 2:06X}
  bra pen
fresh:
  sep #$20
  lda #$00
pen:
  clc
  pha
  lda.l ${ROUTER_PAGE_STATE:06X}
  cmp #$03
  pla
  beq supplement_page
  pha
  lda.l ${ROUTER_PAGE_STATE:06X}
  cmp #$04
  pla
  beq catalog_page
  adc.l ${pc_to_cpu(ADVANCE_PC):06X},x
  bra measured
supplement_page:
  adc.l ${pc_to_cpu(SUPPLEMENT_ADVANCE_PC):06X},x
  bra measured
catalog_page:
  adc.l ${pc_to_cpu(CATALOG_CLUSTER_ADVANCE_PC):06X},x
measured:
  cmp #$08
  rep #$20
  bcc free
  clc
  jml $81921E
free:
  jml $819236
""", WIDTH_ENTRY_PC).code


def _renderer_assets(
    en_rom: bytes,
) -> tuple[list[tuple[int, bytes, str]], bytes, bytes, bytes]:
    model = json.loads((FONT / "thai.json").read_text(encoding="utf-8"))
    layout = json.loads((FONT / "encoding.json").read_text(encoding="utf-8"))
    assets = build_page(model, layout)
    assets = overlay_primary_dialogue_glyphs(assets, layout, FONT, en_rom)
    assets.update(build_upper_stack_assets(model, layout))
    supplement_page, supplement_advance = build_page_two(FONT, en_rom)
    stock_page = en_rom[EN_FONT_PAGE_PC:EN_FONT_PAGE_PC + 0x1000]
    stock_widths = en_rom[EN_WIDTH_TABLE_PC:EN_WIDTH_TABLE_PC + 0x100]
    if len(stock_page) != 0x1000:
        raise ValueError("EN dialogue stock glyph page is truncated")
    stock_advance = _true_advances(stock_widths)
    thai_advance = assets["thai-advance.bin"]
    shr, shl = shift_tables()
    placements = [
        (SHIFT_RIGHT_PC, shr, "Thai shift-right table"),
        (SHIFT_LEFT_PC, shl, "Thai shift-left table"),
        (PAGE_PC, assets["thai-page.bin"], "Thai glyph page"),
        (ADVANCE_PC, thai_advance, "Thai advance table"),
        (LOCK_PC, bytes(0x100), "Thai grid-lock table"),
        (MARK_DX_PC, assets["thai-mark-dx.bin"], "Thai mark dx table"),
        (MARK_Y_PC, assets["thai-mark-y.bin"], "Thai mark y table"),
        (MARK_SIZE_PC, assets["thai-mark-size.bin"], "Thai mark size table"),
        (BASE_INK_PC, assets["thai-base-ink.bin"], "Thai base ink table"),
        (RAISED_Y_PC, assets["thai-raised-y.bin"], "Thai raised-y table"),
        (SHORTHAND_1_PC, assets["thai-shorthand-1.bin"], "Thai shorthand table 1"),
        (SHORTHAND_2_PC, assets["thai-shorthand-2.bin"], "Thai shorthand table 2"),
        (SHORTHAND_3_PC, assets["thai-shorthand-3.bin"], "Thai shorthand table 3"),
        (UPPER_OVERLAY_PC, assets["thai-upper-stack-overlay.bin"], "Thai upper overlay"),
        (UPPER_DX_PC, assets["thai-upper-stack-dx.bin"], "Thai upper dx table"),
        (UPPER_DY_PC, assets["thai-upper-stack-dy.bin"], "Thai upper dy table"),
        (UPPER_SIZE_PC, assets["thai-upper-stack-size.bin"], "Thai upper size table"),
        (SUPPLEMENT_PAGE_PC, supplement_page, "Thai dialogue supplement page"),
        (SUPPLEMENT_ADVANCE_PC, supplement_advance, "Thai dialogue supplement advances"),
        (THAI_STOCK_WIDTH_PC, _stock_widths(thai_advance), "Thai EN width table"),
        (SUPPLEMENT_STOCK_WIDTH_PC, _stock_widths(supplement_advance),
         "Thai dialogue supplement EN widths"),
        (STOCK_PAGE_PC, stock_page, "Dialogue-local copy of EN glyph page"),
        (STOCK_ADVANCE_PC, stock_advance, "Dialogue-local EN advances"),
    ]
    common = dict(
        lock=LOCK_PC,
        state_base=BATTLE_STATE_BASE,
        battle=True,
        shift_tables_base=(SHIFT_RIGHT_PC, SHIFT_LEFT_PC),
    )
    thai = build_renderer(
        THAI_RENDERER_PC,
        source_base=PAGE_PC & 0xFFFF,
        advance=ADVANCE_PC,
        combining={
            "mark_dx": MARK_DX_PC, "mark_y": MARK_Y_PC,
            "mark_size": MARK_SIZE_PC, "base_ink": BASE_INK_PC,
            "raised_y": RAISED_Y_PC,
        },
        shorthand={
            "first": SHORTHAND_1_PC, "second": SHORTHAND_2_PC,
            "third": SHORTHAND_3_PC,
        },
        upper_stacks={
            "overlay": UPPER_OVERLAY_PC, "dx": UPPER_DX_PC,
            "dy": UPPER_DY_PC, "size": UPPER_SIZE_PC,
        },
        **common,
    )
    supplement = build_renderer(
        SUPPLEMENT_RENDERER_PC,
        source_base=SUPPLEMENT_PAGE_PC & 0xFFFF,
        advance=SUPPLEMENT_ADVANCE_PC,
        **common,
    )
    stock = build_renderer(
        STOCK_RENDERER_PC,
        source_base=STOCK_PAGE_PC & 0xFFFF,
        advance=STOCK_ADVANCE_PC,
        **common,
    )
    return placements, thai, supplement, stock


def build_ordinary_renderer() -> bytes:
    """Build the ordinary/menu renderer against the installed EN font assets."""
    return build_renderer(
        ORDINARY_RENDERER_PC,
        source_base=PAGE_PC & 0xFFFF,
        advance=ADVANCE_PC,
        lock=LOCK_PC,
        state_base=ORDINARY_STATE_BASE,
        battle=False,
        shift_tables_base=(SHIFT_RIGHT_PC, SHIFT_LEFT_PC),
        combining={
            "mark_dx": MARK_DX_PC, "mark_y": MARK_Y_PC,
            "mark_size": MARK_SIZE_PC, "base_ink": BASE_INK_PC,
            "raised_y": RAISED_Y_PC,
        },
        shorthand={
            "first": SHORTHAND_1_PC, "second": SHORTHAND_2_PC,
            "third": SHORTHAND_3_PC,
        },
        upper_stacks={
            "overlay": UPPER_OVERLAY_PC, "dx": UPPER_DX_PC,
            "dy": UPPER_DY_PC, "size": UPPER_SIZE_PC,
        },
    )


def build_ordinary_supplement_renderer(origin: int) -> bytes:
    """Build the ordinary VWF for Thai-authored Latin and digit glyphs."""
    return build_renderer(
        origin,
        source_base=SUPPLEMENT_PAGE_PC & 0xFFFF,
        advance=SUPPLEMENT_ADVANCE_PC,
        lock=LOCK_PC,
        state_base=ORDINARY_STATE_BASE,
        battle=False,
        shift_tables_base=(SHIFT_RIGHT_PC, SHIFT_LEFT_PC),
    )


def install(
    image: bytearray,
    *,
    story_banks: tuple[int, ...] = DEFAULT_STORY_BANKS,
    draw_hook: bool = True,
) -> RendererReport:
    """Install the story-only Thai VWF without changing English UI drawing."""
    placements, thai, supplement, stock = _renderer_assets(bytes(image))
    renderer_bytes = 0
    if draw_hook:
        entry = _entry(story_banks)
        width_entry = _width_entry(story_banks)
        placements.extend((
            (WIDTH_ENTRY_PC, width_entry, "English-dialogue Thai VWF width adapter"),
            (ENTRY_PC, entry, "English-dialogue Thai VWF dispatcher"),
            (THAI_RENDERER_PC, thai, "English-dialogue Thai VWF"),
            (SUPPLEMENT_RENDERER_PC, supplement, "English-dialogue supplement VWF"),
            (STOCK_RENDERER_PC, stock, "English-dialogue stock-glyph VWF"),
        ))
        renderer_bytes = len(thai) + len(supplement) + len(stock)
    for pc, data, owner in placements:
        _place_fill(image, pc, data, owner)
    if draw_hook:
        if image[DRAW_HOOK_PC:DRAW_HOOK_PC + 4] != DRAW_HOOK_EXPECTED:
            raise ValueError("EN dialogue draw contract changed")
        image[DRAW_HOOK_PC:DRAW_HOOK_PC + 4] = _jsl(ENTRY_PC)
        if image[WIDTH_HOOK_PC:WIDTH_HOOK_PC + 5] != WIDTH_HOOK_EXPECTED:
            raise ValueError("EN dialogue width contract changed")
        image[WIDTH_HOOK_PC:WIDTH_HOOK_PC + 5] = _jml(WIDTH_ENTRY_PC) + b"\xEA"
    return RendererReport(sum(len(data) for _, data, _ in placements), renderer_bytes)
