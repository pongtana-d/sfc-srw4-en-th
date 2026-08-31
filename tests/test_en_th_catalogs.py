"""Contracts for mixed Thai catalogs on the pinned English ROM."""

import sys
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_ff_router import install as install_router  # noqa: E402
from srw4.en_dialogue_streams import compile_text  # noqa: E402
from srw4.en_dialogue_font import SLOT as SUPPLEMENT_SLOT  # noqa: E402
from srw4.en_dialogue_font import (  # noqa: E402
    CATALOG_CLUSTER_SUPPLEMENT_SLOTS,
    WEAPON_ATTRIBUTE_SLOTS,
    build_page_two,
)
from srw4.en_th_catalogs import (  # noqa: E402
    ADAPTER_BASE_PC,
    EN_BATTLE_PILOT_COUNT,
    EN_BATTLE_PILOT_POOL_END_PC,
    EN_BATTLE_PILOT_POOL_PC,
    EN_BATTLE_PILOT_TABLE_PC,
    EN_CATALOG_PAGE_STATE,
    EN_CATALOG_RENDERER_PC,
    EN_CLUSTER_ADVANCE_PC,
    EN_CLUSTER_PAGE_PC,
    EN_CLUSTER_RENDERER_PC,
    EN_CLUSTER_WIDTH_PC,
    EN_PILOT_COUNT,
    EN_PILOT_POOL_END_PC,
    EN_PILOT_POOL_PC,
    EN_PILOT_TABLE_PC,
    EN_SPIRIT_COUNT,
    EN_SPIRIT_NAME_COUNT,
    EN_SPIRIT_NAME_POOL_END_PC,
    EN_SPIRIT_NAME_POOL_PC,
    EN_SPIRIT_NAME_TABLE_PC,
    EN_SPIRIT_POINTER_TABLE_PC,
    EN_SPIRIT_POOL_END_PC,
    EN_SPIRIT_POOL_PC,
    EN_UNIT_COUNT,
    EN_UNIT_POOL_END_PC,
    EN_UNIT_POOL_PC,
    EN_UNIT_TABLE_PC,
    EN_WEAPON_COUNT,
    EN_WEAPON_POOL_END_PC,
    EN_WEAPON_POOL_PC,
    EN_WEAPON_TABLE_PC,
    ORDINARY_RENDERER_PC,
    ROUTE_TABLE_PC,
    STOCK_TABLE_PC,
    EN_SUPPLEMENT_RENDERER_PC,
    _ClusterCatalogEncoder,
    _build_cluster_page_dispatch,
    _build_catalog_renderer,
    _build_battle_catalog_renderer,
    _preserve_en_spirit_names,
    _build_en_spirit_help,
    _build_battle_info_labels,
    _catalog_layout,
    _preserve_en_name_catalog,
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

    assert report.unit_records == EN_UNIT_COUNT
    assert report.pilot_records == EN_PILOT_COUNT
    assert report.battle_pilot_records == EN_BATTLE_PILOT_COUNT
    assert report.weapon_records == EN_WEAPON_COUNT
    assert report.spirit_name_records == 30
    assert report.spirit_help_records == 29
    assert report.battle_info_labels == 1
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
    # Spirit names stay on the original English renderer and data path.
    assert image[EN_SPIRIT_NAME_POOL_PC:EN_SPIRIT_NAME_POOL_END_PC] == clean[
        EN_SPIRIT_NAME_POOL_PC:EN_SPIRIT_NAME_POOL_END_PC
    ]
    for table_pc, count, pool_pc, pool_end_pc in (
        (EN_UNIT_TABLE_PC, EN_UNIT_COUNT, EN_UNIT_POOL_PC, EN_UNIT_POOL_END_PC),
        (EN_PILOT_TABLE_PC, EN_PILOT_COUNT, EN_PILOT_POOL_PC, EN_PILOT_POOL_END_PC),
        (
            EN_BATTLE_PILOT_TABLE_PC,
            EN_BATTLE_PILOT_COUNT,
            EN_BATTLE_PILOT_POOL_PC,
            EN_BATTLE_PILOT_POOL_END_PC,
        ),
        (
            EN_WEAPON_TABLE_PC,
            EN_WEAPON_COUNT,
            EN_WEAPON_POOL_PC,
            EN_WEAPON_POOL_END_PC,
        ),
    ):
        assert image[table_pc:table_pc + count * 2] == clean[
            table_pc:table_pc + count * 2
        ]
        assert image[pool_pc:pool_end_pc] == clean[pool_pc:pool_end_pc]
    # The current EN battle renderer hooks stay owned by en_th_renderer.
    assert image[0x019219] == 0x5C
    assert image[0x019238] == 0x22


def test_en_battle_info_preserves_level_and_accuracy_and_translates_counter():
    clean = BASE.read_bytes()
    encoder = _ClusterCatalogEncoder(clean, StockCatalog.locked())
    patches, thai, supplement = _build_battle_info_labels(clean, encoder)

    assert [pc for pc, _payload, _owner in patches] == [0x3ED788]
    assert [len(payload) for _pc, payload, _owner in patches] == [13]
    counter, _width, _routes = encoder.visible("โต้กลับไม่ได้")
    assert patches[0][1] == counter + bytes((encoder.supplement_codes[" "],)) * 4
    for pc, source_hex in (
        (0x3E2FCD, "21 94 A5 94 9B"),
        (0x3E301E, "21 94 A5 94 9B"),
        (0x3E3004, "16 92 92 A4 A1 90 92 A8 43 27 90 A3 94"),
        (0x3E3055, "16 92 92 A4 A1 90 92 A8 43 27 90 A3 94"),
    ):
        expected = bytes.fromhex(source_hex)
        assert clean[pc:pc + len(expected)] == expected
    assert 0xFE in thai and 0xFE in supplement
    assert sum(end - start for start, end in thai[0xFE]) == 9
    assert sum(end - start for start, end in supplement[0xFE]) == 4


def test_en_weapon_catalog_preserves_english_source_exactly():
    clean = BASE.read_bytes()
    image = bytearray(clean)
    install_renderer(image)
    install_router(image, font_hooks=True, alt_hook=False, width_hooks=True)
    install_catalogs(image, clean)

    assert image[
        EN_WEAPON_TABLE_PC:EN_WEAPON_TABLE_PC + EN_WEAPON_COUNT * 2
    ] == clean[
        EN_WEAPON_TABLE_PC:EN_WEAPON_TABLE_PC + EN_WEAPON_COUNT * 2
    ]
    assert image[EN_WEAPON_POOL_PC:EN_WEAPON_POOL_END_PC] == clean[
        EN_WEAPON_POOL_PC:EN_WEAPON_POOL_END_PC
    ]


def test_battle_quote_weapon_insertions_remain_fc03_over_english_catalog():
    messages = json.loads(
        (ROOT / "data" / "translations" / "script.th.json").read_text()
    )["messages"]
    layout = json.loads(
        (ROOT / "data" / "font" / "encoding.json").read_text()
    )
    weapon_quotes = {
        record_id: text
        for record_id, text in messages.items()
        if "<FC:03>" in text
    }

    assert weapon_quotes
    assert all(record_id.startswith("22_") for record_id in weapon_quotes)
    for text in weapon_quotes.values():
        encoded = compile_text(text, layout)
        assert encoded.count(b"\xFC\x03") == text.count("<FC:03>")


def test_mixed_catalog_text_uses_thai_authored_proportional_latin_and_digits():
    clean = BASE.read_bytes()
    encoder = _ClusterCatalogEncoder(
        clean, StockCatalog.locked(), include_weapon_reference=True
    )
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


def test_new_spirit_help_clusters_use_explicit_supplement_slots():
    clean = BASE.read_bytes()
    encoder = _ClusterCatalogEncoder(clean, StockCatalog.locked())
    supplement_page, supplement_advances = build_page_two(
        ROOT / "data" / "font", clean
    )

    assert set(CATALOG_CLUSTER_SUPPLEMENT_SLOTS).isdisjoint(encoder.codes)
    for token, code in CATALOG_CLUSTER_SUPPLEMENT_SLOTS.items():
        payload, routes, width, _, _ = encoder.spirit_line(token.removeprefix("cluster:"))
        assert payload == bytes((code,))
        assert routes == [2]
        assert width == supplement_advances[code]
        assert supplement_page[code * 16:(code + 1) * 16] != bytes(16)


def test_preserved_english_name_files_do_not_allocate_catalog_glyphs():
    clean = BASE.read_bytes()
    encoder = _ClusterCatalogEncoder(clean, StockCatalog.locked())
    weapon_reference = _ClusterCatalogEncoder(
        clean, StockCatalog.locked(), include_weapon_reference=True
    )

    assert set(encoder.codes) < set(weapon_reference.codes)
    for unused_name_cluster in (
        "cluster:ซุ", "cluster:ฌ", "cluster:ฌุ", "cluster:ณ",
        "cluster:ดุ", "cluster:ตึ", "cluster:ผู้", "cluster:ม้",
        "cluster:ยี", "cluster:รุ่", "cluster:ห่", "cluster:ฮุ",
    ):
        assert unused_name_cluster not in encoder.codes
        assert unused_name_cluster not in CATALOG_CLUSTER_SUPPLEMENT_SLOTS


def test_every_declared_supplement_text_glyph_is_used_or_primary_owned():
    clean = BASE.read_bytes()
    encoder = _ClusterCatalogEncoder(
        clean, StockCatalog.locked(), include_weapon_reference=True
    )
    layout = json.loads((ROOT / "data" / "font" / "encoding.json").read_text())
    slot_codes = set(SUPPLEMENT_SLOT.values())
    used: set[int] = set()

    messages = json.loads(
        (ROOT / "data" / "translations" / "script.th.json").read_text()
    )["messages"]
    for text in messages.values():
        plain = re.sub(r"<[^>]+>", "", text)
        used.update(
            SUPPLEMENT_SLOT[char]
            for char in plain
            if char not in layout["codes"] and char in SUPPLEMENT_SLOT
        )

    for entry in json.loads(
        (ROOT / "data" / "translations" / "weapons.th.json").read_text()
    ):
        if entry.get("kind") == "non_text_sentinel":
            continue
        payload, _width, routes = encoder.weapon(entry)
        used.update(byte for byte, route in zip(payload, routes) if route == 2)

    spirit = json.loads(
        (ROOT / "data" / "translations" / "spirit-descriptions.th.json").read_text()
    )
    for entry in spirit["script_messages"]:
        for line in entry["translation"].split("\n"):
            payload, routes, *_rest = encoder.spirit_line(line)
            used.update(byte for byte, route in zip(payload, routes) if route == 2)

    battle_info = json.loads(
        (ROOT / "data" / "translations" / "en-battle-info.th.json").read_text()
    )
    for field in battle_info["fields"]:
        if field.get("keep_original"):
            continue
        payload, _width, routes = encoder.visible(field["translation"])
        used.update(byte for byte, route in zip(payload, routes) if route == 2)

    primary_owned = {
        SUPPLEMENT_SLOT[char]
        for char in SUPPLEMENT_SLOT
        if char in layout["codes"]
    }
    assert (used | primary_owned) & slot_codes == slot_codes


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
    encoder = _ClusterCatalogEncoder(
        clean, StockCatalog.locked(), include_weapon_reference=True
    )
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


def test_retired_thai_glyph_slots_are_reused_by_primary_dialogue_glyphs():
    model = json.loads((ROOT / "data" / "font" / "thai.json").read_text())
    layout = json.loads((ROOT / "data" / "font" / "encoding.json").read_text())
    assert all(char not in model["bases"] for char in "ฦฯๅ")
    assert all(char not in layout["codes"] for char in "ฦฯๅ")
    assert layout["retired_spacing_slots"] == []
    assert layout["codes"]["ล"] == 37
    assert layout["codes"]["ว"] == 39
    assert layout["codes"]["ๆ"] == 66

    assert {layout["codes"][char] for char in layout["dialogue_primary_glyphs"]}.issuperset(
        {38, 65, 67}
    )


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


def test_en_spirit_names_remain_byte_identical_to_english_rom():
    clean = BASE.read_bytes()
    catalog = _preserve_en_spirit_names(clean)
    assert catalog.records == EN_SPIRIT_NAME_COUNT
    assert catalog.pool_pc == EN_SPIRIT_NAME_POOL_PC
    assert len(catalog.pool) == EN_SPIRIT_NAME_POOL_END_PC - EN_SPIRIT_NAME_POOL_PC
    assert catalog.thai_routes == ()
    assert catalog.supplement_routes == ()
    assert catalog.table == clean[
        EN_SPIRIT_NAME_TABLE_PC:EN_SPIRIT_NAME_TABLE_PC + EN_SPIRIT_NAME_COUNT * 2
    ]
    assert catalog.pool == clean[EN_SPIRIT_NAME_POOL_PC:EN_SPIRIT_NAME_POOL_END_PC]

    image = bytearray(clean)
    install_renderer(image)
    install_router(image, font_hooks=True, alt_hook=False, width_hooks=True)
    install_catalogs(image, clean)
    assert image[
        EN_SPIRIT_NAME_TABLE_PC:EN_SPIRIT_NAME_TABLE_PC + EN_SPIRIT_NAME_COUNT * 2
    ] == catalog.table
    assert image[EN_SPIRIT_NAME_POOL_PC:EN_SPIRIT_NAME_POOL_END_PC] == clean[
        EN_SPIRIT_NAME_POOL_PC:EN_SPIRIT_NAME_POOL_END_PC
    ]


def test_unit_pilot_battle_and_weapon_name_catalogs_preserve_english_source_exactly():
    clean = BASE.read_bytes()
    for owner, table_pc, count, pool_pc, pool_end_pc in (
        ("English unit names", EN_UNIT_TABLE_PC, EN_UNIT_COUNT,
         EN_UNIT_POOL_PC, EN_UNIT_POOL_END_PC),
        ("English pilot names", EN_PILOT_TABLE_PC, EN_PILOT_COUNT,
         EN_PILOT_POOL_PC, EN_PILOT_POOL_END_PC),
        ("English battle pilot names", EN_BATTLE_PILOT_TABLE_PC,
         EN_BATTLE_PILOT_COUNT, EN_BATTLE_PILOT_POOL_PC,
         EN_BATTLE_PILOT_POOL_END_PC),
        ("English weapon names", EN_WEAPON_TABLE_PC, EN_WEAPON_COUNT,
         EN_WEAPON_POOL_PC, EN_WEAPON_POOL_END_PC),
    ):
        catalog = _preserve_en_name_catalog(
            clean,
            owner=owner,
            count=count,
            table_pc=table_pc,
            pool_pc=pool_pc,
            pool_end_pc=pool_end_pc,
        )
        assert catalog.records == count
        assert catalog.thai_routes == ()
        assert catalog.supplement_routes == ()
        assert catalog.table == clean[table_pc:table_pc + count * 2]
        assert catalog.pool == clean[pool_pc:pool_end_pc]
