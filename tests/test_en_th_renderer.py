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
    THAI_RENDERER_PC,
    _entry,
    _renderer_assets,
    _width_entry,
    _stock_widths,
    _true_advances,
    install as install_renderer,
)
from srw4.en_precomposed import (  # noqa: E402
    ADVANCE_PC as PRECOMPOSED_ADVANCE_PC,
    PAGE_BYTES as PRECOMPOSED_PAGE_BYTES,
    PAGE_PC as PRECOMPOSED_PAGE_PC,
    PAGE_STATES as PRECOMPOSED_PAGE_STATES,
    SOURCE_BANK as PRECOMPOSED_SOURCE_BANK,
    WIDTH_PC as PRECOMPOSED_WIDTH_PC,
    build_assets as build_precomposed_assets,
    slot_for_token,
)
from srw4.proven.renderer65816 import pc_to_cpu  # noqa: E402
from srw4.atlas import AtlasBuilder  # noqa: E402
from srw4.en_dialogue_font import (  # noqa: E402
    BATTLE_QUOTE_PADDING,
    BATTLE_QUOTE_PADDING_TOKEN,
    CATALOG_CLUSTER_SUPPLEMENT_SLOTS,
    SLOT,
    WEAPON_ATTRIBUTE_SLOTS,
    build_page_two,
)


BASE = ROOT / "rom" / "Dai-4-ji Super Robot Taisen English.sfc"


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


def test_every_story_and_battle_token_uses_its_saved_precomposed_bitmap_and_advance():
    clean = BASE.read_bytes()
    image = bytearray(clean)
    install_renderer(image)
    assets = build_precomposed_assets(clean)

    for token in assets.token_map.tokens:
        page, slot = slot_for_token(assets.token_map, token)
        glyph_at = PRECOMPOSED_PAGE_PC + page * PRECOMPOSED_PAGE_BYTES + slot * 16
        assert image[glyph_at:glyph_at + 16] == assets.pages[page][slot * 16:(slot + 1) * 16]
        assert image[PRECOMPOSED_ADVANCE_PC + page * 0x100 + slot] == assets.advances[page][slot]
        assert image[PRECOMPOSED_WIDTH_PC + page * 0x100 + slot] == assets.widths[page][slot]


def test_precomposed_renderer_reads_glyphs_and_metrics_across_banks():
    _placements, thai, _supplement, _stock = _renderer_assets(BASE.read_bytes())

    # Shift tables remain in bank $FF, so the dynamic `$EA:xxxx` source must be
    # read with long-indexed opcodes rather than by changing DB to `$EA`.
    assert b"\x8B\xA9\xFF\x48\xAB" in thai
    assert b"\xBB\xBF" + (PRECOMPOSED_SOURCE_BANK << 16).to_bytes(3, "little") in thai
    for page in range(5):
        metric_cpu = pc_to_cpu(PRECOMPOSED_ADVANCE_PC + page * 0x100)
        assert b"\xBF" + metric_cpu.to_bytes(3, "little") in thai


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


def test_battle_quote_padding_is_the_precomposed_zero_advance_pad_glyph():
    clean = BASE.read_bytes()
    image = bytearray(clean)
    install_renderer(image)
    assets = build_precomposed_assets(clean)
    assert BATTLE_QUOTE_PADDING == assets.token_map.encode_glyph(BATTLE_QUOTE_PADDING_TOKEN)
    assert len(BATTLE_QUOTE_PADDING) == 2
    page, slot = slot_for_token(assets.token_map, BATTLE_QUOTE_PADDING_TOKEN)
    start = PRECOMPOSED_PAGE_PC + page * PRECOMPOSED_PAGE_BYTES + slot * 16

    assert image[start:start + 16] == bytes(16)
    assert image[PRECOMPOSED_ADVANCE_PC + page * 0x100 + slot] == 0
    assert image[PRECOMPOSED_WIDTH_PC + page * 0x100 + slot] == 0xFF


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


def test_dispatch_selects_one_of_the_five_precomposed_pages_from_the_engine_code():
    code = _entry(DEFAULT_STORY_BANKS)
    assert bytes.fromhex("C9 D0 00") in code
    assert bytes.fromhex("C9 00 05") in code
    for state in PRECOMPOSED_PAGE_STATES:
        assert state.to_bytes(2, "little") in code
    assert pc_to_cpu(THAI_RENDERER_PC).to_bytes(3, "little") in code
    assert CATALOG_INTERNAL_BASE.to_bytes(2, "little") in code


def test_precomposed_width_path_loads_the_engine_glyph_index_before_page_metrics():
    code = _width_entry(DEFAULT_STORY_BANKS)

    assert bytes.fromhex("A5 02 29 FF 00 AA") in code
    for page in range(5):
        assert pc_to_cpu(PRECOMPOSED_ADVANCE_PC + page * 0x100).to_bytes(3, "little") in code


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


def test_installed_router_preserves_precomposed_pages_and_en_tail_contracts():
    image = bytearray(BASE.read_bytes())
    install_renderer(image)
    install_router(image, font_hooks=True, alt_hook=False, width_hooks=True)
    assets = build_precomposed_assets(BASE.read_bytes())
    for page in range(5):
        page_at = PRECOMPOSED_PAGE_PC + page * PRECOMPOSED_PAGE_BYTES
        assert image[page_at:page_at + PRECOMPOSED_PAGE_BYTES] == assets.pages[page]
        assert image[PRECOMPOSED_ADVANCE_PC + page * 0x100:PRECOMPOSED_ADVANCE_PC + (page + 1) * 0x100] == assets.advances[page]
        assert image[PRECOMPOSED_WIDTH_PC + page * 0x100:PRECOMPOSED_WIDTH_PC + (page + 1) * 0x100] == assets.widths[page]
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


def test_precomposed_colon_glyph_is_installed_and_visible():
    image = bytearray(BASE.read_bytes())
    install_renderer(image)
    assets = build_precomposed_assets(BASE.read_bytes())
    page, slot = slot_for_token(assets.token_map, "char::")
    at = PRECOMPOSED_PAGE_PC + page * PRECOMPOSED_PAGE_BYTES + slot * 16
    glyph = image[at:at + 16]

    assert glyph == bytes.fromhex("00 00 00 00 00 00 00 80 00 00 00 00 80 00 00 00")
