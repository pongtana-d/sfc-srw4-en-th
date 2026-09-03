"""Regression contracts for the English-ROM Thai dialogue adapter."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_ff_router import (  # noqa: E402
    DEFAULT_STORY_BANKS,
    ENTRY,
    ORIGIN,
    ROUTER_ACTIVE_STATE,
    WIDTH_MASK_PCS,
    install as install_router,
)
from srw4.en_th_renderer import (  # noqa: E402
    CATALOG_BATTLE_PAGE_STATE,
    CATALOG_BATTLE_RENDERER_PC,
    CATALOG_CLUSTER_ADVANCE_PC,
    CATALOG_CLUSTER_PAGE_PC,
    CATALOG_FIXED_BASE,
    CATALOG_FIXED_LIMIT,
    CONTEXTUAL_UPPER_DIRECT_PC,
    CONTEXTUAL_UPPER_FAMILY_PC,
    CONTEXTUAL_UPPER_OVERLAY_PC,
    CONTEXTUAL_UPPER_PAIRS_PC,
    CATALOG_INTERNAL_BASE,
    DRAW_HOOK_PC,
    EN_FONT_PAGE_PC,
    EN_WIDTH_TABLE_PC,
    ADVANCE_PC,
    PAGE_PC,
    STOCK_ADVANCE_PC,
    STOCK_PAGE_PC,
    SUPPLEMENT_ADVANCE_PC,
    SUPPLEMENT_PAGE_PC,
    SUPPLEMENT_STOCK_WIDTH_PC,
    THAI_STOCK_WIDTH_PC,
    _entry,
    _width_entry,
    _stock_widths,
    _true_advances,
    install as install_renderer,
)
from srw4.proven.renderer65816 import pc_to_cpu  # noqa: E402
from srw4.atlas import AtlasBuilder  # noqa: E402
from srw4.en_dialogue_font import (  # noqa: E402
    BATTLE_QUOTE_PADDING_SLOT,
    CATALOG_CLUSTER_SUPPLEMENT_SLOTS,
    SLOT,
    WEAPON_ATTRIBUTE_SLOTS,
    build_page_two,
)
from srw4.proven.text.upper_stacks import build_contextual_upper_stack_assets  # noqa: E402


BASE = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (English combo).sfc"


def test_live_dialogue_latin_glyphs_are_installed_on_the_thai_page():
    clean = BASE.read_bytes()
    image = bytearray(clean)
    install_renderer(image)
    layout = json.loads((ROOT / "data" / "font" / "encoding.json").read_text())
    atlas = AtlasBuilder(ROOT / "data" / "font", clean)

    for char in layout["dialogue_primary_glyphs"]:
        code = layout["codes"][char]
        glyph = atlas.build(f"char:{char}")
        start = PAGE_PC + code * 16
        assert image[start:start + 16] == bytes(glyph.rows)
        assert image[ADVANCE_PC + code] == glyph.advance


def test_contextual_upper_stack_for_ng_sara_a_tone_matches_editor_bitmap():
    """`งั้` is the regression that exposed the generic EN mark placement."""
    clean = BASE.read_bytes()
    image = bytearray(clean)
    install_renderer(image)
    model = json.loads((ROOT / "data" / "font" / "thai.json").read_text())
    layout = json.loads((ROOT / "data" / "font" / "encoding.json").read_text())
    assets = build_contextual_upper_stack_assets(model, layout)
    atlas = AtlasBuilder(ROOT / "data" / "font", clean)

    pair = 0 * 5 + 1  # `ั` (D0) followed by `้` (DB)
    stack = assets["thai-contextual-upper-pairs.bin"][pair]
    assert stack != 0xFF
    assert image[CONTEXTUAL_UPPER_PAIRS_PC + pair] == stack
    assert image[CONTEXTUAL_UPPER_DIRECT_PC + layout["codes"]["ั"]] != 0xFF
    assert image[CONTEXTUAL_UPPER_FAMILY_PC + layout["codes"]["ง"]] == 0

    overlay = image[
        CONTEXTUAL_UPPER_OVERLAY_PC + stack * 16:
        CONTEXTUAL_UPPER_OVERLAY_PC + (stack + 1) * 16
    ]
    base = atlas.build("cluster:ง").rows
    assert tuple(a | b for a, b in zip(base, overlay)) == atlas.build("cluster:งั้").rows


def test_supplement_page_contains_only_declared_live_glyphs():
    clean = BASE.read_bytes()
    page, advances = build_page_two(ROOT / "data" / "font", clean)
    live = {
        *SLOT.values(),
        *WEAPON_ATTRIBUTE_SLOTS.values(),
        *CATALOG_CLUSTER_SUPPLEMENT_SLOTS.values(),
    }

    for code in range(0x100):
        glyph = page[code * 16:(code + 1) * 16]
        assert (glyph != bytes(16) or advances[code] != 0) == (code in live)


def test_battle_quote_padding_is_invisible_and_zero_advance_on_primary_page():
    clean = BASE.read_bytes()
    image = bytearray(clean)
    install_renderer(image)
    start = PAGE_PC + BATTLE_QUOTE_PADDING_SLOT * 16

    assert image[start:start + 16] == bytes(16)
    assert image[ADVANCE_PC + BATTLE_QUOTE_PADDING_SLOT] == 0


def test_weapon_badges_use_fixed_supplement_slots_with_authored_bitmaps():
    clean = BASE.read_bytes()
    image = bytearray(clean)
    install_renderer(image)
    atlas = AtlasBuilder(ROOT / "data" / "font", clean)
    assert len(set(WEAPON_ATTRIBUTE_SLOTS.values())) == 4
    for name, code in WEAPON_ATTRIBUTE_SLOTS.items():
        glyph = atlas.build(f"icon:{name}")
        start = SUPPLEMENT_PAGE_PC + code * 16
        assert image[start:start + 16] == bytes(glyph.rows)
        assert image[SUPPLEMENT_ADVANCE_PC + code] == glyph.advance


def test_en_tail_widths_encode_zero_advance_without_cursor_motion():
    source = bytes((0, 1, 4, 8)) + bytes(0xFC)
    widths = _stock_widths(source)
    assert widths[:4] == bytes((0xFF, 0, 3, 7))
    assert len(widths) == 0x100


def test_stock_en_widths_are_restored_to_true_advances():
    widths = bytes((0xFF, 0, 3, 7)) + bytes(0xFC)
    advances = _true_advances(widths)
    assert advances[:4] == bytes((0, 1, 4, 8))
    assert len(advances) == 0x100


def test_dispatch_does_not_let_restored_glyph_flags_choose_the_page():
    code = _entry(DEFAULT_STORY_BANKS)
    # Old code did PHA; LDA page; CMP #3; PLA; BEQ, so glyph $00 selected the
    # supplement renderer regardless of the actual page.
    assert bytes.fromhex("48 AF DC FF 7E C9 03 00 68 F0") not in code
    # Custom renderers already own the battle tile allocation.  Re-entering
    # the EN raster tail applies width/tile movement a second time.
    assert bytes.fromhex("5C 2D E1 F0") not in code
    assert bytes.fromhex("5C 00 A0 FF") in code
    assert bytes.fromhex("5C 00 B0 FF") in code
    assert bytes.fromhex("5C 00 C0 FF") in code
    # Runtime-name glyphs no longer enter the independent stock rasterizer.
    assert bytes.fromhex("5C 49 E0 F0") not in code
    assert CATALOG_INTERNAL_BASE.to_bytes(2, "little") in code


def test_private_supplement_width_loads_glyph_index_before_advance_lookup():
    code = _width_entry(DEFAULT_STORY_BANKS)
    load_private_index = bytes.fromhex("A5 02 29 FF 00 C9 C0 00")

    # Thai and supplement pages each validate and load their own glyph index;
    # page 3 must not branch straight into an advance lookup with stale X/A.
    assert code.count(load_private_index) == 2


def test_catalog_width_keeps_internal_tag_for_draw_dispatch():
    code = _width_entry(DEFAULT_STORY_BANKS)
    # Decode to X for width measurement, but never overwrite $02 with the raw
    # glyph: the draw dispatcher still needs the $0Axx catalog tag.
    assert bytes.fromhex("38 E9 00 0A AA") in code
    assert bytes.fromhex("38 E9 00 0A 85 02") not in code


def test_battle_catalog_fixed_tag_selects_the_supplement_page():
    draw = _entry(DEFAULT_STORY_BANKS)
    width = _width_entry(DEFAULT_STORY_BANKS)

    assert CATALOG_FIXED_BASE.to_bytes(2, "little") in draw
    assert CATALOG_FIXED_LIMIT.to_bytes(2, "little") in draw
    assert (CATALOG_CLUSTER_PAGE_PC & 0xFFFF).to_bytes(2, "little") in draw
    assert CATALOG_BATTLE_PAGE_STATE.to_bytes(3, "little") in draw
    assert pc_to_cpu(CATALOG_BATTLE_RENDERER_PC).to_bytes(3, "little") in draw
    assert CATALOG_FIXED_BASE.to_bytes(2, "little") in width
    assert CATALOG_FIXED_LIMIT.to_bytes(2, "little") in width
    assert bytes.fromhex("38 E9 00 0B AA A9 03 00") in width
    assert pc_to_cpu(CATALOG_CLUSTER_ADVANCE_PC).to_bytes(3, "little") in width


def test_installed_router_preserves_private_mark_sentinel_for_en_tail():
    image = bytearray(BASE.read_bytes())
    install_renderer(image)
    install_router(image, font_hooks=True, alt_hook=False, width_hooks=True)
    assert image[THAI_STOCK_WIDTH_PC + 0xDA] == 0xFF
    assert image[SUPPLEMENT_STOCK_WIDTH_PC:SUPPLEMENT_STOCK_WIDTH_PC + 0x100] != bytes(0x100)
    assert all(image[pc:pc + 3] == bytes.fromhex("EA EA EA") for pc in WIDTH_MASK_PCS)
    # The public entry is now a long jump to the sign-extending adapter.
    assert image[ORIGIN + ENTRY["glyph_width"]] == 0x5C
    finish = ORIGIN + ENTRY["finish_width"] + 4
    assert image[finish:finish + 10] == (
        b"\x48\xA9\x00\x00\x8F"
        + ROUTER_ACTIVE_STATE.to_bytes(3, "little")
        + b"\x68\x6B"
    )
    assert image[DRAW_HOOK_PC:DRAW_HOOK_PC + 4] != bytes.fromhex("22 45 E0 F0")
    base = BASE.read_bytes()
    assert image[STOCK_PAGE_PC:STOCK_PAGE_PC + 0x1000] == (
        base[EN_FONT_PAGE_PC:EN_FONT_PAGE_PC + 0x1000]
    )
    assert image[STOCK_ADVANCE_PC:STOCK_ADVANCE_PC + 0x100] == _true_advances(
        base[EN_WIDTH_TABLE_PC:EN_WIDTH_TABLE_PC + 0x100]
    )
    # Shared EN rasterizer entry remains pristine for menus and status screens.
    assert image[0x30E045:0x30E049] == bytes.fromhex("85 00 A5 D0")


def test_primary_dialogue_colon_glyph_is_installed_and_visible():
    image = bytearray(BASE.read_bytes())
    install_renderer(image)
    layout = json.loads((ROOT / "data" / "font" / "encoding.json").read_text())
    code = layout["codes"][":"]
    glyph = image[PAGE_PC + code * 16:PAGE_PC + (code + 1) * 16]

    assert code == 86
    assert glyph == bytes.fromhex("00 00 00 00 00 00 00 80 00 00 00 00 80 00 00 00")
