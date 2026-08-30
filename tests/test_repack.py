"""P6 tests: the Thai script in the expanded banks, and the hook that draws it."""

import json
import sys
from pathlib import Path

import pytest

# 9,382 after the nine mis-split records were merged with their tails; see
# the note in data/translations/script.source.json.
RECORDS = 9382

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from srw4.blitter import build as build_blitter  # noqa: E402
from srw4.blitter import constants  # noqa: E402
from srw4.repack import containing, owner_of, quote_tables, stock_fields  # noqa: E402
from srw4.rom import Rom  # noqa: E402
from srw4.script import BANK_SIZE, cpu_to_pc  # noqa: E402

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
SOURCE = ROOT / "data" / "translations" / "script.source.json"


@pytest.fixture(scope="module")
def report() -> dict:
    from build import build as build_rom  # tools/build.py

    return build_rom("thai")[1]


@pytest.fixture(scope="module")
def messages() -> list[dict]:
    return json.loads(SOURCE.read_text())["messages"]


# --- what the repack produced ----------------------------------------------


def test_almost_every_record_is_in_thai(report):
    script = report["script"]
    assert script["records_in_thai"] + script["records_copied_through"] == RECORDS
    assert script["records_copied_through"] < 40, script["copied_through"][:5]


def test_no_pointer_was_left_behind(report):
    assert report["script"]["stranded_pointers"] == []


def test_every_address_field_was_rewritten(report):
    # Ten branch tables of eight, plus the single-address fields.
    assert report["script"]["address_fields_rewritten"] >= 100


def test_the_script_stays_inside_the_banks_it_was_given(report):
    banks = report["script"]["banks"]
    assert banks == [f"${bank:02X}" for bank in range(0xF0, 0xF0 + len(banks))]


def test_the_layout_places_every_message_once():
    layout = json.loads((ROOT / "build" / "reports" / "script-layout.json").read_text())
    assert len(layout) == RECORDS
    seen = {(entry["bank"], entry["offset"]) for entry in layout.values()}
    assert len(seen) == len(layout)


def test_no_record_runs_past_the_end_of_its_bank():
    layout = json.loads((ROOT / "build" / "reports" / "script-layout.json").read_text())
    for mid, entry in layout.items():
        assert entry["offset"] + entry["bytes"] <= BANK_SIZE, mid


# --- finding the addresses records carry ------------------------------------


def test_a_record_is_found_from_any_byte_inside_it(messages):
    spans = containing(messages)
    first = next(m for m in messages if m["block"] == 0)
    start = int(first["offset"], 16)
    assert owner_of(spans[0], start) == (first["id"], 0)
    assert owner_of(spans[0], start + 1) == (first["id"], 1)
    assert owner_of(spans[0], 0) is None


def test_a_branch_table_is_read_out_of_the_stock_bytes(messages):
    branchy = next(m for m in messages if "FC 08" in m["source_hex"])
    fields = stock_fields(b"", branchy, None)
    assert len(fields) >= 8
    offsets = [offset for offset, _ in fields]
    assert offsets == sorted(offsets)


def test_an_address_after_fb_is_read_out_of_the_stock_bytes(messages):
    pointy = next(
        m for m in messages
        if any(
            m["source_hex"].startswith(prefix) or f" {prefix}" in m["source_hex"]
            for prefix in ("FB F0 0C", "FB F1 0C")
        )
    )
    assert stock_fields(b"", pointy, None)


# --- the hook ---------------------------------------------------------------


def test_the_hook_replaces_the_call_the_story_loop_makes(report):
    hooked = report["renderer"]["hooked_up"]
    assert hooked["at"] == "0x019238"
    assert hooked["was"] == "jsl $8184EB"


def test_the_hook_is_absent_unless_the_thai_script_is_in():
    from build import build as build_rom

    assert build_rom("none")[1]["renderer"]["hooked_up"] is None


def test_the_stock_call_is_still_where_we_think_it_is():
    rom = Rom.load_clean(CLEAN_ROM).to_bytes()
    assert rom[0x019238:0x01923C] == bytes([0x22, 0xEB, 0x84, 0x81])


def test_the_adapter_knows_which_banks_are_ours():
    values = constants(0xC5C0, {"glyphs": 0, "slots": 0, "advances": 0, "operands": 0}, 629)
    assert values["SCRIPT_BANK_FIRST"] == 0xF0
    assert values["ARENA_BASE"] == 0x7F8000
    assert values["STOCK_RASTERISER"] == 0x8184EB


def test_the_adapter_and_the_blitter_are_assembled_together():
    program = build_blitter(
        0xFB0000,
        0xC5C0,
        {"glyphs": 0xF98000, "slots": 0xF99000, "advances": 0xF9A000, "operands": 0xF9A400},
        629,
        with_adapter=True,
    )
    assert "draw_thai_glyph" in program.labels
    assert "blit_glyph" in program.labels
    assert program.labels["draw_thai_glyph"] > program.labels["blit_glyph"]


# --- the battle-quote dispatch area ------------------------------------------


def test_a_quote_table_yields_every_target_with_its_offset():
    # `$FC:01 $FA 02` then two addresses, then another table of one.
    data = bytes.fromhex("fc01fa02 3412 7856 fc01fa01 aabb".replace(" ", ""))
    assert quote_tables(data) == [(4, 0x1234), (6, 0x5678), (12, 0xBBAA)]


def test_bytes_that_only_look_like_a_table_are_left_alone():
    assert quote_tables(bytes.fromhex("fc05fa0000")) == []
    assert quote_tables(b"\xfc\x01") == []


def test_the_seven_record_blocks_carry_their_dispatch_area(messages):
    """Slots 20-26 hold 13,884 bytes of quote tables before their first text.

    They are not messages and never were, so nothing else in the pipeline
    would notice them going missing -- only a battle would, by drawing from
    an address that no longer names anything.
    """
    summary = json.loads((ROOT / "data" / "translations" / "script.source.json").read_text())
    blocks = {b["slot"]: b for b in summary["summary"]["blocks"] if b.get("kind") == "record"}
    assert sorted(blocks) == [20, 21, 22, 23, 24, 25, 26]
    assert sum(b["record_bytes"] for b in blocks.values()) == 13884

    by_block = {}
    for message in messages:
        by_block.setdefault(message["block"], []).append(message)
    for slot, block in blocks.items():
        base = int(block["pc"], 16) & 0xFFFF
        first = min(int(m["offset"], 16) for m in by_block[slot])
        assert first - (base + block["pointers"] * 2) == block["record_bytes"], slot


def test_every_quote_table_target_was_rewritten(report):
    script = report["script"]
    assert script["quote_table_targets_rewritten"] > 3000
    # Before the area travelled with its block, every one of these collapsed
    # onto the block end and came out as an empty slot.
    assert script["empty_slots"] < 400
