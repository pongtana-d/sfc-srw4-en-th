"""FF-stream router for English-ROM story and battle dialogue.

The EN renderer calls the shared dispatcher at $C1:9238 for both map/event
text and battle quotes.  This adapter reserves $C0-$C2 as private Thai page
leads only while the source bank is $F1, $F7, or $FF.  `$C2 $EB` is the
documented split escape: it switches to an FF-bank relocated stream.
"""
from __future__ import annotations

from dataclasses import dataclass

from .asm65816 import assemble
from .proven.assembler import pc_to_cpu
from .proven.renderer65816 import BATTLE_STATE_BASE, STATE_SIGNATURE


ORIGIN = 0x3F9000
# The final word in the shared story renderer's persistent block is reserved
# for the stream page.  The old address, $7E:C000, is the first word after the
# stock tilemap buffer and is cleared by the English dialogue compositor.
ROUTER_PAGE_STATE = BATTLE_STATE_BASE + 0x1C
ROUTER_ACTIVE_STATE = BATTLE_STATE_BASE + 0x1E
_LEGACY_PAGE_STATE = 0x7EC000
# The EN tail adds one to every width byte.  These are therefore dedicated
# stock-format tables (advance - 1, with $FF representing zero-advance marks),
# not the renderer's true advance tables at $FF:5000/$FF:7000.
THAI_WIDTH_TABLE_CPU = 0xFF7100
SUPPLEMENT_WIDTH_TABLE_CPU = 0xFF7200
_TRAMPOLINE_TEMPLATE = bytes.fromhex(
    "5adaa00000a51c29ff00c9ff00d025b71a29ff00c9c0009017c9c300b012"
    "38e9c0001a8f00c07ee61aa934128ffcff7f5cade4f082f9ffa5cd29ff00c9"
    "ec00f009c9ed00f0045cb3283fa50229ff00c9c200d0385aa000"
    "00b7cb29ff00c9eb00d029a00300b7cb29ff00e22085cdc220e6cba7cb85cb"
    "a7cb29ff008502e6cb7aa934128ffcff7fad2a0e6b7ac9c0009022c9c300b0"
    "1d38e9c0001a8f00c07ea7cb29ff008502e6cba934128ffcff7fad2a0e6ba5"
    "0229ff00c9c0009014c9d000b00fa934128ffcff7fc6cba7cbe6cb8502ad2a"
    "0e6baf00c07ec90100f010c90200f011c90300f012bf0000fd8010bf0040ff"
    "800abf0050ff8004bf0060ff29ff008504af00c07ec90100f010c90200f011"
    "c90300f012bf0800fd8010bf0840ff800abf0850ff8004bf0860ff29ff0085"
    "066baf00c07ec90100f00fc90200f00fc90300f00fbf00f0f06bbf0070ff6b"
    "bf0071ff6bbf0072ff6b8ff0ff7f48a900008f00c07e686b"
)
_finish_page_clear = bytes.fromhex("48a900008f00c07e686b")
if _TRAMPOLINE_TEMPLATE.count(_finish_page_clear) != 1:
    raise AssertionError("EN router finish-width contract changed")
# Page selection belongs to the whole private record because the dialogue width
# check runs before the story router can reassert it for the next glyph.  The
# separate active word is transient: it prevents a stale private page/source
# bank from leaking into menu/status calls that share the EN rasterizer tail.
_finish_active_clear = b"\x48" + bytes.fromhex("a90000") + bytes((0x8F,)) + (
    ROUTER_ACTIVE_STATE.to_bytes(3, "little")
) + b"\x68\x6B"
if len(_finish_active_clear) != len(_finish_page_clear):
    raise AssertionError("EN router active-clear replacement changed size")
_TRAMPOLINE_TEMPLATE = _TRAMPOLINE_TEMPLATE.replace(
    _finish_page_clear, _finish_active_clear
)
if _TRAMPOLINE_TEMPLATE.count(THAI_WIDTH_TABLE_CPU.to_bytes(3, "little")) != 1:
    raise AssertionError("EN router Thai-width table contract changed")
if _TRAMPOLINE_TEMPLATE.count(SUPPLEMENT_WIDTH_TABLE_CPU.to_bytes(3, "little")) != 1:
    raise AssertionError("EN router supplement-width table contract changed")
_legacy_state = _LEGACY_PAGE_STATE.to_bytes(3, "little")
if _TRAMPOLINE_TEMPLATE.count(_legacy_state) != 5:
    raise AssertionError("EN router trampoline page-state contract changed")
TRAMPOLINE = _TRAMPOLINE_TEMPLATE.replace(
    _legacy_state, ROUTER_PAGE_STATE.to_bytes(3, "little")
)

# Offsets inside TRAMPOLINE. Kept named because every hook below relies on
# these public entry contracts, rather than on a hidden byte position.
ENTRY = {
    "ordinary_fetch": 0x000,
    "story_dispatch": 0x037,
    "alternate_source": 0x0D5,
    "glyph_width": 0x132,
    "finish_width": 0x159,
}

DEFAULT_STORY_BANKS = (0xEB, *range(0xF1, 0xFD))


def _story_dispatch(story_banks: tuple[int, ...]) -> bytes:
    """Return the story-side router, with one-byte Thai glyphs enabled."""
    if not story_banks or any(not 0x80 <= bank <= 0xFF for bank in story_banks):
        raise ValueError("invalid private story bank set")
    checks = "\n".join(
        f"  cmp #${bank:04X}\n  beq story_private" for bank in sorted(set(story_banks))
    )
    source = f""".a16
.i16
story_dispatch:
  lda $CD
  and #$00FF
{checks}
  lda #$0000
  sta.l ${ROUTER_PAGE_STATE:06X}
  jml stock_story
story_private:
  lda $02
  and #$00FF
  cmp #$00C0
  bcs story_page
  brl stock_story
story_page:
  cmp #$00C2
  bne story_page_lead
  phy
  ldy #$0000
  lda [$CB],y
  and #$00FF
  cmp #$00EB
  bne story_not_split
  ldy #$0003
  lda [$CB],y
  and #$00FF
.a8
  sep #$20
  sta $CD
  rep #$20
.a16
  inc $CB
  lda [$CB]
  sta $CB
  lda [$CB]
  and #$00FF
  sta $02
  inc $CB
  ply
  lda #$1234
  sta $7FFFFC
  lda $0E2A
  rtl
story_not_split:
  ply
story_page_lead:
  cmp #$00C0
  bcc stock_story
  cmp #$00C3
  bcs stock_story
  sec
  sbc #$00C0
  inc a
  sta.l ${ROUTER_PAGE_STATE:06X}
  lda [$CB]
  and #$00FF
  sta $02
  inc $CB
  lda #$1234
  sta $7FFFFC
  lda $0E2A
  rtl
stock_story:
  lda $02
  and #$00FF
  cmp #$00C0
  bcc story_done
  cmp #$00D0
  bcs story_done
  lda #$1234
  sta $7FFFFC
  dec $CB
  lda [$CB]
  inc $CB
  sta $02
story_done:
  lda $0E2A
  rtl
"""
    return assemble(source, ORIGIN + len(TRAMPOLINE)).code


def _glyph_width(origin: int) -> bytes:
    """Return an EN-tail width, preserving $FFFF for zero-advance marks.

    The stock callers used to mask every result to one byte before adding one,
    which turns the private $FF sentinel into $00FF + 1 = $0100.  This routine
    normalizes ordinary widths itself and sign-extends only private-page $FF.
    """
    return assemble(f""".a16
.i16
glyph_width:
  lda.l ${ROUTER_ACTIVE_STATE:06X}
  cmp #${STATE_SIGNATURE:04X}
  bne stock
  lda.l ${ROUTER_PAGE_STATE:06X}
  cmp #$0001
  beq page_one
  cmp #$0002
  beq thai
  cmp #$0003
  beq supplement
stock:
  lda.l $F0F000,x
  and #$00FF
  rtl
page_one:
  lda.l $FF7000,x
  bra private
thai:
  lda.l ${THAI_WIDTH_TABLE_CPU:06X},x
  bra private
supplement:
  lda.l ${SUPPLEMENT_WIDTH_TABLE_CPU:06X},x
private:
  and #$00FF
  cmp #$00FF
  bne done
  lda #$FFFF
done:
  rtl
""", origin).code

HOOK_PC = 0x30E4A8
HOOK_EXPECTED = bytes.fromhex("5A DA A0 00 00")
ALT_SOURCE_PC = 0x30E0C7
ALT_SOURCE_EXPECTED = bytes.fromhex("BF 00 00 FD 29 FF 00 85 04 BF 08 00 FD 29 FF 00 85 06")
STORY_DISPATCH_PC = 0x30E023
STORY_DISPATCH_EXPECTED = bytes.fromhex(
    "A5 02 29 FF 00 C9 C0 00 90 14 C9 D0 00 B0 0F A9 34 12 8F FC FF 7F"
    "C6 CB A7 CB E6 CB 85 02 AD 2A 0E 6B"
)
WIDTH_PCS = (0x30E13B, 0x30E14C, 0x30E163)
WIDTH_EXPECTED = bytes.fromhex("BF 00 F0 F0")
WIDTH_MASK_PCS = (0x30E13F, 0x30E150, 0x30E167)
WIDTH_MASK_EXPECTED = bytes.fromhex("29 FF 00")
FINAL_WIDTH_PC = 0x30E170
FINAL_WIDTH_EXPECTED = bytes.fromhex("8F F0 FF 7F")


@dataclass(frozen=True)
class RouterReport:
    bytes: int
    origin: int


def _jsl(pc: int) -> bytes:
    cpu = pc_to_cpu(pc)
    return bytes((0x22, cpu & 0xFF, (cpu >> 8) & 0xFF, cpu >> 16))


def _jml(pc: int) -> bytes:
    cpu = pc_to_cpu(pc)
    return bytes((0x5C, cpu & 0xFF, (cpu >> 8) & 0xFF, cpu >> 16))


def _replace(image: bytearray, pc: int, expected: bytes, replacement: bytes) -> None:
    if image[pc:pc + len(expected)] != expected:
        raise ValueError(f"EN router contract changed at {pc:#08x}")
    if len(replacement) > len(expected):
        raise ValueError(f"router hook at {pc:#08x} overflows its contract")
    image[pc:pc + len(expected)] = replacement + bytes((0xEA,)) * (len(expected) - len(replacement))


def install(image: bytearray, story_banks: tuple[int, ...] = DEFAULT_STORY_BANKS,
            *, hooks: bool = True, story_hook: bool = True, font_hooks: bool = True,
            alt_hook: bool = True, width_hooks: bool = True) -> RouterReport:
    """Install the tested EN router into pristine `$FF` fill space."""
    extension = _story_dispatch(story_banks)
    code = bytearray(TRAMPOLINE)
    extension_pc = ORIGIN + len(code)
    code[ENTRY["story_dispatch"]:ENTRY["story_dispatch"] + 5] = _jml(extension_pc) + b"\xEA"
    glyph_width_pc = extension_pc + len(extension)
    glyph_width = _glyph_width(glyph_width_pc)
    code[ENTRY["glyph_width"]:ENTRY["glyph_width"] + 5] = _jml(glyph_width_pc) + b"\xEA"
    total = len(code) + len(extension) + len(glyph_width)
    if image[ORIGIN:ORIGIN + total] != b"\xFF" * total:
        raise ValueError("EN FF router region is occupied")
    image[ORIGIN:ORIGIN + len(code)] = code
    image[extension_pc:extension_pc + len(extension)] = extension
    image[glyph_width_pc:glyph_width_pc + len(glyph_width)] = glyph_width
    if hooks and story_hook:
        # Story map/event and battle both enter through STORY_DISPATCH_PC.
        # Leaving the ordinary fetch path intact avoids title, naming and menus.
        # This hook replaces a complete RTL-terminated routine.  Returning only
        # from the router's JSL would resume in the NOP padding and fall through
        # into the rasterizer at $F0:E045, drawing every glyph twice.
        _replace(
            image,
            STORY_DISPATCH_PC,
            STORY_DISPATCH_EXPECTED,
            _jsl(ORIGIN + ENTRY["story_dispatch"]) + b"\x6B",
        )
    if hooks and font_hooks and alt_hook:
        _replace(image, ALT_SOURCE_PC, ALT_SOURCE_EXPECTED, _jsl(ORIGIN + ENTRY["alternate_source"]))
    if hooks and font_hooks and width_hooks:
        for pc in WIDTH_PCS:
            _replace(image, pc, WIDTH_EXPECTED, _jsl(ORIGIN + ENTRY["glyph_width"]))
        for pc in WIDTH_MASK_PCS:
            _replace(image, pc, WIDTH_MASK_EXPECTED, b"\xEA\xEA\xEA")
        _replace(image, FINAL_WIDTH_PC, FINAL_WIDTH_EXPECTED, _jsl(ORIGIN + ENTRY["finish_width"]))
    return RouterReport(bytes=total, origin=ORIGIN)
