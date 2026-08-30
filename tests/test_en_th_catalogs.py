"""Contracts for Thai unit and pilot names on the pinned English ROM."""

import sys
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_ff_router import install as install_router  # noqa: E402
from srw4.en_dialogue_font import SLOT as SUPPLEMENT_SLOT  # noqa: E402
from srw4.en_dialogue_font import (  # noqa: E402
    WEAPON_ATTRIBUTE_SLOTS,
    build_page_two,
)
from srw4.en_th_catalogs import (  # noqa: E402
    ADAPTER_BASE_PC,
    EN_BATTLE_PILOT_TABLE_PC,
    EN_CATALOG_PAGE_STATE,
    EN_CATALOG_RENDERER_PC,
    EN_CLUSTER_ADVANCE_PC,
    EN_CLUSTER_PAGE_PC,
    EN_CLUSTER_RENDERER_PC,
    EN_CLUSTER_WIDTH_PC,
    EN_SPIRIT_COUNT,
    EN_SPIRIT_NAME_ADVANCE_PC,
    EN_SPIRIT_NAME_COUNT,
    EN_SPIRIT_NAME_FIELD_WIDTH,
    EN_SPIRIT_NAME_PAGE_PC,
    EN_SPIRIT_NAME_POOL_END_PC,
    EN_SPIRIT_NAME_POOL_PC,
    EN_SPIRIT_NAME_RENDERER_PC,
    EN_SPIRIT_NAME_SHIFT_LEFT_PC,
    EN_SPIRIT_NAME_SHIFT_RIGHT_PC,
    EN_SPIRIT_NAME_TABLE_PC,
    EN_SPIRIT_NAME_WIDTH_PC,
    EN_SPIRIT_POINTER_TABLE_PC,
    EN_SPIRIT_POOL_END_PC,
    EN_SPIRIT_POOL_PC,
    EN_UNIT_TABLE_PC,
    EN_WEAPON_POOL_END_PC,
    EN_WEAPON_POOL_PC,
    EN_WEAPON_TABLE_PC,
    ORDINARY_RENDERER_PC,
    ROUTE_TABLE_PC,
    STOCK_TABLE_PC,
    EN_SUPPLEMENT_RENDERER_PC,
    _ClusterCatalogEncoder,
    _SpiritNameEncoder,
    _build_cluster_page_dispatch,
    _build_catalog_renderer,
    _build_battle_catalog_renderer,
    _build_en_spirit_names,
    _build_en_spirit_help,
    _build_battle_info_labels,
    _build_spirit_name_renderer,
    _battle_name,
    _catalog_layout,
    install as install_catalogs,
)
from srw4.en_th_renderer import (  # noqa: E402
    CATALOG_BATTLE_RENDERER_PC,
    EN_FONT_PAGE_PC,
    PAGE_PC,
    build_ordinary_renderer,
    install as install_renderer,
)
from srw4.proven.catalogs import ATTRIBUTE_ICONS, CatalogEncoder  # noqa: E402
from srw4.proven.renderer65816 import (  # noqa: E402
    ORDINARY_STATE_BASE,
    renderer_memory,
)
from srw4.proven.text.stock import StockCatalog  # noqa: E402


BASE = ROOT / "rom" / "Dai-4-ji Super Robot Taisen English.sfc"


def test_en_catalogs_install_all_unit_and_pilot_id_tables():
    clean = BASE.read_bytes()
    image = bytearray(clean)
    install_renderer(image)
    install_router(image, font_hooks=True, alt_hook=False, width_hooks=True)
    report = install_catalogs(image, clean)

    assert report.unit_records == 295
    assert report.pilot_records == 290
    assert report.battle_pilot_records == 285
    assert report.weapon_records == 503
    assert report.spirit_name_records == 30
    assert report.spirit_help_records == 29
    assert report.battle_info_labels == 5
    assert image[STOCK_TABLE_PC:STOCK_TABLE_PC + 3] != b"\xFF" * 3
    assert image[ADAPTER_BASE_PC] != 0xFF
    assert image[ROUTE_TABLE_PC:ROUTE_TABLE_PC + report.route_bytes] != b"\xFF" * report.route_bytes
    assert image[ORDINARY_RENDERER_PC] != 0xFF
    assert image[EN_CLUSTER_PAGE_PC:EN_CLUSTER_PAGE_PC + 0x1000] != b"\xFF" * 0x1000
    assert image[
        EN_CLUSTER_RENDERER_PC:EN_CLUSTER_RENDERER_PC + len(_build_cluster_page_dispatch())
    ] == _build_cluster_page_dispatch()
    # The supplement entry still selects the shared persistent catalog body.
    target = bytes((0x5C, 0x00, 0xF8, 0xFF))
    assert image[
        EN_SUPPLEMENT_RENDERER_PC + 9:EN_SUPPLEMENT_RENDERER_PC + 13
    ] == target
    renderer = _build_catalog_renderer()
    assert image[
        EN_CATALOG_RENDERER_PC:EN_CATALOG_RENDERER_PC + len(renderer)
    ] == renderer
    battle_renderer = _build_battle_catalog_renderer()
    assert image[
        CATALOG_BATTLE_RENDERER_PC:CATALOG_BATTLE_RENDERER_PC + len(battle_renderer)
    ] == battle_renderer
    assert EN_CATALOG_RENDERER_PC + len(renderer) <= 0x400000
    spirit_renderer = _build_spirit_name_renderer()
    assert image[
        EN_SPIRIT_NAME_RENDERER_PC:EN_SPIRIT_NAME_RENDERER_PC + len(spirit_renderer)
    ] == spirit_renderer
    assert EN_SPIRIT_NAME_RENDERER_PC + len(spirit_renderer) <= EN_SPIRIT_NAME_PAGE_PC
    # The current EN battle renderer hooks stay owned by en_th_renderer.
    assert image[0x019219] == 0x5C
    assert image[0x019238] == 0x22


def test_en_battle_info_labels_are_thai_and_exactly_fill_the_runtime_spans():
    clean = BASE.read_bytes()
    encoder = _ClusterCatalogEncoder(clean, StockCatalog.locked())
    patches, thai, supplement = _build_battle_info_labels(clean, encoder)

    assert [pc for pc, _payload, _owner in patches] == [
        0x3E2FCD, 0x3E301E, 0x3ED788, 0x3E3004, 0x3E3055,
    ]
    assert [len(payload) for _pc, payload, _owner in patches] == [5, 5, 13, 13, 13]
    assert patches[0][1] == patches[1][1] == bytes.fromhex("7F AE E3 BD AE")
    assert patches[2][1] == bytes.fromhex(
        "E5 4A 00 AF 69 E7 98 E7 40 1B 1B 1B 1B"
    )
    assert patches[3][1] == patches[4][1] == bytes.fromhex(
        "E4 98 60 9A E2 1B 1B 1B 1B 1B 1B 1B 1B"
    )
    assert 0xFE in thai and 0xFE in supplement
    assert sum(end - start for start, end in thai[0xFE]) == 27
    assert sum(end - start for start, end in supplement[0xFE]) == 22


def test_en_weapon_catalog_uses_reviewed_thai_names_and_fits_its_pool():
    clean = BASE.read_bytes()
    image = bytearray(clean)
    install_renderer(image)
    install_router(image, font_hooks=True, alt_hook=False, width_hooks=True)
    install_catalogs(image, clean)

    # Weapon ID 1 is Beam Saber / บีมเซเบอร์.
    at = EN_WEAPON_TABLE_PC + 2
    pointer = int.from_bytes(image[at:at + 2], "little") + 0x3E0000
    reviewed = json.loads(
        (ROOT / "data" / "translations" / "weapons.th.json").read_text()
    )
    entry = next(item for item in reviewed if 1 in item["weapon_ids"])
    expected, _, _ = _ClusterCatalogEncoder(clean, StockCatalog.locked()).weapon(entry)
    assert image[pointer:pointer + len(expected)] == expected
    assert EN_WEAPON_POOL_PC <= pointer < EN_WEAPON_POOL_END_PC


def test_mixed_catalog_text_uses_thai_authored_proportional_latin_and_digits():
    clean = BASE.read_bytes()
    encoder = _ClusterCatalogEncoder(clean, StockCatalog.locked())
    payload, width, routes = encoder.visible("A120มม.")

    expected_chars = "A120"
    assert payload[:len(expected_chars)] == bytes(
        encoder.supplement_codes[char] for char in expected_chars
    )
    assert routes[:len(expected_chars)] == (2,) * len(expected_chars)
    assert 1 in routes[len(expected_chars):]
    assert width == sum(encoder.supplement_widths[char] for char in expected_chars) + (
        encoder.widths[encoder.codes["cluster:ม"]] + 1
    ) * 2 + encoder.supplement_widths["."]


def test_cluster_renderer_has_true_advances_beside_stock_widths():
    clean = BASE.read_bytes()
    encoder = _ClusterCatalogEncoder(clean, StockCatalog.locked())
    image = bytearray(clean)
    install_renderer(image)
    install_router(image, font_hooks=True, alt_hook=False, width_hooks=True)
    install_catalogs(image, clean)

    for code in encoder.codes.values():
        assert encoder.advances[code] == encoder.widths[code] + 1
    assert image[EN_CLUSTER_ADVANCE_PC:EN_CLUSTER_ADVANCE_PC + 0x100] == (
        encoder.advances
    )
    assert image[EN_CLUSTER_WIDTH_PC:EN_CLUSTER_WIDTH_PC + 0x100] == encoder.widths


def test_catalog_renderer_reuses_its_live_cell_for_the_callers_next_glyph():
    renderer = _build_catalog_renderer()
    memory = renderer_memory(ORDINARY_STATE_BASE)
    entry = b"\xA5\x18\x8F" + memory.col.to_bytes(3, "little")
    reuse = (
        b"\xAF" + memory.col.to_bytes(3, "little")
        + b"\x8F" + memory.expect_col.to_bytes(3, "little")
    )
    ordinary_entry = b"\xA5\x18\x3A\x3A\x8F" + memory.col.to_bytes(3, "little")
    assert entry in renderer
    assert reuse in renderer
    assert ordinary_entry in build_ordinary_renderer()
    assert EN_CATALOG_PAGE_STATE == ORDINARY_STATE_BASE + 0x1C


def test_weapon_attribute_badges_are_exact_en_glyphs_and_stay_in_the_payload():
    clean = BASE.read_bytes()
    encoder = _ClusterCatalogEncoder(clean, StockCatalog.locked())
    supplement_page, supplement_advances = build_page_two(
        ROOT / "data" / "font", clean
    )
    for source_code, markup in ATTRIBUTE_ICONS.items():
        name = markup[1:-1]
        code = WEAPON_ATTRIBUTE_SLOTS[name]
        expected = clean[
            EN_FONT_PAGE_PC + source_code * 16:
            EN_FONT_PAGE_PC + (source_code + 1) * 16
        ]
        assert supplement_page[code * 16:(code + 1) * 16] == expected
        assert supplement_advances[code] == 8
        assert f"icon:{name}" not in encoder.codes

    entries = json.loads(
        (ROOT / "data" / "translations" / "weapons.th.json").read_text()
    )
    for suffix in ("<MAP_L><MAP_R><B>", "<P>"):
        entry = next(item for item in entries if item["source"].endswith(suffix))
        payload, _width, routes = encoder.weapon(entry)
        expected = bytes(WEAPON_ATTRIBUTE_SLOTS[name] for name in (
            token[1:-1] for token in suffix.replace("><", ">|<").split("|")
        ))
        assert payload[-len(expected) - 1:-1] == expected
        assert routes[-len(expected) - 1:-1] == (2,) * len(expected)

    # Cover every translated weapon, not just one example per badge shape.
    # This catches a future encoder change that drops a trailing MAP/B/P byte
    # while the supplement artwork itself remains valid.
    for entry in entries:
        source = bytes.fromhex(entry["source_hex"])
        attributes = []
        cursor = len(source) - 2
        while cursor >= 0 and source[cursor] in ATTRIBUTE_ICONS:
            attributes.append(source[cursor])
            cursor -= 1
        attributes.reverse()
        payload, _width, routes = encoder.weapon(entry)
        expected = bytes(
            WEAPON_ATTRIBUTE_SLOTS[ATTRIBUTE_ICONS[code][1:-1]]
            for code in attributes
        )
        if expected:
            assert payload[-len(expected) - 1:-1] == expected
            assert routes[-len(expected) - 1:-1] == (2,) * len(expected)


def test_retired_thai_glyph_slots_are_blank_without_renumbering_live_codes():
    model = json.loads((ROOT / "data" / "font" / "thai.json").read_text())
    layout = json.loads((ROOT / "data" / "font" / "encoding.json").read_text())
    assert all(char not in model["bases"] for char in "ฦฯๅ")
    assert all(char not in layout["codes"] for char in "ฦฯๅ")
    assert layout["retired_spacing_slots"] == [38, 65, 67]
    assert layout["codes"]["ล"] == 37
    assert layout["codes"]["ว"] == 39
    assert layout["codes"]["ๆ"] == 66

    image = bytearray(BASE.read_bytes())
    install_renderer(image)
    for code in layout["retired_spacing_slots"]:
        assert image[PAGE_PC + code * 16:PAGE_PC + (code + 1) * 16] == bytes(16)


def test_en_spirit_help_repoints_all_live_english_records_to_thai():
    clean = BASE.read_bytes()
    encoder = _ClusterCatalogEncoder(clean, StockCatalog.locked())
    catalog = _build_en_spirit_help(clean, encoder)
    assert catalog.records == EN_SPIRIT_COUNT
    assert catalog.pool_pc == EN_SPIRIT_POOL_PC
    assert len(catalog.pool) == EN_SPIRIT_POOL_END_PC - EN_SPIRIT_POOL_PC

    reviewed = json.loads(
        (ROOT / "data" / "translations" / "spirit-descriptions.th.json").read_text()
    )["script_messages"]
    for item in reviewed:
        spirit_id = int(item["spirit_id"])
        at = (spirit_id - 1) * 2
        pointer = int.from_bytes(catalog.table[at:at + 2], "little") + 0x3E0000
        assert EN_SPIRIT_POOL_PC <= pointer < EN_SPIRIT_POOL_END_PC
        payload = bytearray()
        for index, line in enumerate(item["translation"].split("\n")):
            encoded, _routes, _width, _guards, _stock = encoder.spirit_line(line)
            payload.extend(encoded)
            if index + 1 < len(item["translation"].split("\n")):
                payload.append(0xF6)
        payload.append(0xFF)
        offset = pointer - catalog.pool_pc
        assert catalog.pool[offset:offset + len(payload)] == payload

    image = bytearray(clean)
    install_renderer(image)
    install_router(image, font_hooks=True, alt_hook=False, width_hooks=True)
    install_catalogs(image, clean)
    assert image[EN_SPIRIT_POINTER_TABLE_PC + 2:EN_SPIRIT_POINTER_TABLE_PC + 60] == (
        catalog.table
    )


def test_en_spirit_names_use_a_dedicated_exact_cluster_page_and_fit_en_width():
    clean = BASE.read_bytes()
    encoder = _SpiritNameEncoder(clean)
    catalog = _build_en_spirit_names(clean, encoder)
    assert catalog.records == EN_SPIRIT_NAME_COUNT
    assert catalog.pool_pc == EN_SPIRIT_NAME_POOL_PC
    assert len(catalog.pool) == EN_SPIRIT_NAME_POOL_END_PC - EN_SPIRIT_NAME_POOL_PC

    reviewed = json.loads(
        (ROOT / "data" / "translations" / "spirit-descriptions.th.json").read_text()
    )["spirits"]
    expected_names = {
        1: "ใจสู้", 2: "ใจสู้สุด", 3: "เติมเสบียง", 4: "มิตรภาพ",
        5: "เชื่อใจ", 6: "ความรัก", 7: "พิโรธ", 8: "ฮึกเหิม",
        9: "เร่ง", 10: "เลือดร้อน", 11: "แม่นยำ", 12: "ไหวพริบ",
        13: "โชคดี", 14: "ตื่นตัว", 15: "ข่มขวัญ", 16: "ยั้งมือ",
        17: "จดจ่อ", 18: "ปลุกใจ", 19: "ยิงซ้ำ", 20: "คืนชีพ",
        21: "ซ่อนกาย", 22: "หมดแรง", 23: "พลีชีพ", 24: "ค้นหา",
        25: "โซ่ตรวน", 26: "ก่อกวน", 27: "สอดแนม", 28: "กำแพง",
        29: "วิญญาณ", 30: "ปาฏิหาริย์",
    }
    assert {int(item["id"]): item["translation"] for item in reviewed} == expected_names
    for item in reviewed:
        payload, width, _routes = encoder.name(item)
        assert width <= EN_SPIRIT_NAME_FIELD_WIDTH
        at = (int(item["id"]) - 1) * 2
        pointer = int.from_bytes(catalog.table[at:at + 2], "little") + 0x3E0000
        offset = pointer - catalog.pool_pc
        assert catalog.pool[offset:offset + len(payload)] == payload

    image = bytearray(clean)
    install_renderer(image)
    install_router(image, font_hooks=True, alt_hook=False, width_hooks=True)
    install_catalogs(image, clean)
    assert image[
        EN_SPIRIT_NAME_TABLE_PC:EN_SPIRIT_NAME_TABLE_PC + EN_SPIRIT_NAME_COUNT * 2
    ] == catalog.table
    assert image[EN_SPIRIT_NAME_PAGE_PC:EN_SPIRIT_NAME_PAGE_PC + 0x1000] == encoder.page
    assert image[EN_SPIRIT_NAME_WIDTH_PC:EN_SPIRIT_NAME_WIDTH_PC + 0x100] == encoder.widths
    assert image[
        EN_SPIRIT_NAME_ADVANCE_PC:EN_SPIRIT_NAME_ADVANCE_PC + 0x100
    ] == encoder.advances
    from srw4.proven.renderer65816 import shift_tables
    shift_right, shift_left = shift_tables()
    assert image[
        EN_SPIRIT_NAME_SHIFT_RIGHT_PC:EN_SPIRIT_NAME_SHIFT_RIGHT_PC + len(shift_right)
    ] == shift_right
    assert image[
        EN_SPIRIT_NAME_SHIFT_LEFT_PC:EN_SPIRIT_NAME_SHIFT_LEFT_PC + len(shift_left)
    ] == shift_left


def test_battle_catalog_uses_reviewed_short_name_file_exactly():
    clean = BASE.read_bytes()
    image = bytearray(clean)
    install_renderer(image)
    install_router(image, font_hooks=True, alt_hook=False, width_hooks=True)
    install_catalogs(image, clean)
    reviewed = json.loads(
        (ROOT / "data" / "translations" / "pilot-short-names.th.json").read_text()
    )
    cluster_encoder = _ClusterCatalogEncoder(clean, StockCatalog.locked())
    for entry in reviewed:
        encoded = _battle_name(entry, cluster_encoder)
        expected = encoded[0]
        for pilot_id in entry["battle_pilot_ids"]:
            at = EN_BATTLE_PILOT_TABLE_PC + pilot_id * 2
            pointer = int.from_bytes(image[at:at + 2], "little") + 0x3E0000
            assert image[pointer:pointer + len(expected)] == expected


def test_garada_k7_unit_name_keeps_canonical_word_boundaries():
    clean = BASE.read_bytes()
    image = bytearray(clean)
    install_renderer(image)
    install_router(image, font_hooks=True, alt_hook=False, width_hooks=True)
    install_catalogs(image, clean)

    reviewed = json.loads(
        (ROOT / "data" / "translations" / "units.th.json").read_text()
    )
    entry = next(item for item in reviewed if 150 in item["unit_ids"])
    assert entry["translation"] == "อสูรกล การาดา K7"

    encoder = _ClusterCatalogEncoder(clean, StockCatalog.locked())
    expected, width, routes = encoder.name(entry)
    assert width == 84
    assert routes[:-1].count(2) == 4
    at = EN_UNIT_TABLE_PC + 150 * 2
    pointer = int.from_bytes(image[at:at + 2], "little") + 0x3E0000
    assert image[pointer:pointer + len(expected)] == expected


def test_koji_battle_name_uses_literal_ji_components():
    clean = BASE.read_bytes()
    image = bytearray(clean)
    install_renderer(image)
    install_router(image, font_hooks=True, alt_hook=False, width_hooks=True)
    install_catalogs(image, clean)

    at = EN_BATTLE_PILOT_TABLE_PC + 85 * 2
    assert int.from_bytes(image[at:at + 2], "little") == 0xA55D
    pointer = int.from_bytes(image[at:at + 2], "little") + 0x3E0000
    expected = _ClusterCatalogEncoder(clean, StockCatalog.locked()).name(
        {"translation": "โคจิ"}
    )[0]
    assert expected == bytes.fromhex("E5 0E 1C FF")
    assert image[pointer:pointer + len(expected)] == expected


def test_reviewed_ele_names_keep_later_en_pool_addresses_stable():
    clean = BASE.read_bytes()
    image = bytearray(clean)
    install_renderer(image)
    install_router(image, font_hooks=True, alt_hook=False, width_hooks=True)
    install_catalogs(image, clean)

    # The 202 AI speaker pointer was cached by save/en-battle-quote.mss before
    # エレ was shortened.  The compatibility reservation must keep it fixed.
    at = EN_BATTLE_PILOT_TABLE_PC + 202 * 2
    assert int.from_bytes(image[at:at + 2], "little") == 0xA86B


def test_enemy_ai_battle_name_uses_the_reviewed_literal_label():
    clean = BASE.read_bytes()
    image = bytearray(clean)
    install_renderer(image)
    install_router(image, font_hooks=True, alt_hook=False, width_hooks=True)
    install_catalogs(image, clean)

    at = EN_BATTLE_PILOT_TABLE_PC + 202 * 2
    pointer = int.from_bytes(image[at:at + 2], "little") + 0x3E0000
    expected, _width, routes = _ClusterCatalogEncoder(clean, StockCatalog.locked()).name(
        {"translation": "AI"}
    )
    assert expected == bytes.fromhex("01 09 FF")
    assert routes == (2, 2, 0)
    assert image[pointer:pointer + len(expected)] == expected
