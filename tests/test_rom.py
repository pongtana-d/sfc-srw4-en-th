"""P0 tests: address maths, checksum, expansion, allocation, determinism."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from srw4.allocation import AllocationMap  # noqa: E402
from srw4.asm65816 import assemble  # noqa: E402
from srw4.rom import (  # noqa: E402
    CLEAN_SHA256,
    CLEAN_SIZE,
    EXPANDED_SIZE,
    Rom,
    RomError,
    compute_checksum,
    cpu_to_pc,
    mirrored_sum,
    sha256,
)

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
ALLOCATION_MAP = ROOT / "data" / "config" / "allocation-map.json"


@pytest.fixture(scope="module")
def clean() -> Rom:
    return Rom.load_clean(CLEAN_ROM)


def test_cpu_to_pc_matches_the_documented_example():
    assert cpu_to_pc(0xD2, 0x9009) == 0x129009
    assert cpu_to_pc(0xC1, 0x83FB) == 0x0183FB
    assert cpu_to_pc(0xFA, 0x0000) == 0x3A0000
    # The $80/$81 mirror lands on the same PC offset as $C0/$C1.
    assert cpu_to_pc(0x81, 0x8402) == cpu_to_pc(0xC1, 0x8402)


def test_cpu_to_pc_rejects_out_of_range():
    with pytest.raises(RomError):
        cpu_to_pc(0xC1, 0x10000)


def test_clean_rom_identity(clean):
    assert clean.size == CLEAN_SIZE
    assert sha256(clean.to_bytes()) == CLEAN_SHA256


def test_load_rejects_a_modified_rom(tmp_path):
    bad = bytearray(CLEAN_ROM.read_bytes())
    bad[0x1000] ^= 0xFF
    path = tmp_path / "bad.sfc"
    path.write_bytes(bytes(bad))
    with pytest.raises(RomError, match="sha256 mismatch"):
        Rom.load_clean(path)


def test_load_rejects_a_truncated_rom(tmp_path):
    path = tmp_path / "short.sfc"
    path.write_bytes(CLEAN_ROM.read_bytes()[:-1])
    with pytest.raises(RomError, match="must be"):
        Rom.load_clean(path)


def test_computed_checksum_reproduces_the_stored_one(clean):
    assert compute_checksum(clean.to_bytes()) == clean.stored_checksum() == 0x93B3


def test_mirrored_sum_is_a_plain_sum_for_a_power_of_two():
    data = bytes(range(256)) * 4
    assert mirrored_sum(data) == sum(data) & 0xFFFF


def test_expansion_gives_a_4mb_image_and_leaves_the_stock_bytes_alone(clean):
    rom = Rom.load_clean(CLEAN_ROM)
    rom.expand()
    assert rom.size == EXPANDED_SIZE
    assert rom.read_at(0, CLEAN_SIZE) == clean.to_bytes()
    assert set(rom.read_at(CLEAN_SIZE, EXPANDED_SIZE - CLEAN_SIZE)) == {0xFF}


def test_expansion_keeps_the_declared_rom_size_byte_big_enough(clean):
    rom = Rom.load_clean(CLEAN_ROM)
    rom.expand()
    declared_kb = 1 << rom.read_at(0xFFD7, 1)[0]
    assert declared_kb * 1024 >= EXPANDED_SIZE


def test_fix_checksum_is_self_consistent():
    rom = Rom.load_clean(CLEAN_ROM)
    rom.expand()
    checksum = rom.fix_checksum()
    assert rom.stored_checksum() == checksum
    # Recomputing over the written image must return the same value.
    assert compute_checksum(rom.to_bytes()) == checksum
    complement = rom.read_at(0xFFDC, 2)
    assert (complement[0] | complement[1] << 8) == checksum ^ 0xFFFF


def test_writes_outside_the_image_are_refused():
    rom = Rom.load_clean(CLEAN_ROM)
    with pytest.raises(RomError, match="outside the ROM"):
        rom.write_at(CLEAN_SIZE - 1, b"\x00\x00")


def test_allocation_hands_out_space_and_records_it():
    alloc = AllocationMap.load(ALLOCATION_MAP)
    first = alloc.allocate("glyph_atlas", "atlas.page0", 4096)
    second = alloc.allocate("glyph_atlas", "atlas.page1", 4096)
    assert first == 0x390000
    assert second == first + 4096
    assert alloc.used("glyph_atlas") == 8192
    owners = [a["owner"] for a in alloc.report()["allocations"]]
    assert owners == ["atlas.page0", "atlas.page1"]


def test_allocation_respects_alignment():
    alloc = AllocationMap.load(ALLOCATION_MAP)
    alloc.allocate("renderer_code", "blitter", 3)
    aligned = alloc.allocate("renderer_code", "decoder", 16, align=0x100)
    assert aligned % 0x100 == 0


def test_allocation_fails_loudly_when_a_region_is_full():
    alloc = AllocationMap.load(ALLOCATION_MAP)
    with pytest.raises(RomError, match="is full"):
        alloc.allocate("glyph_atlas", "too_big", 0x10001)


def test_allocation_rejects_an_unknown_region():
    alloc = AllocationMap.load(ALLOCATION_MAP)
    with pytest.raises(RomError, match="unknown region"):
        alloc.allocate("nowhere", "x", 1)


def test_build_is_deterministic_and_touches_only_the_checksum():
    from build import build  # tools/build.py

    first, report = build()
    second, _ = build()
    assert sha256(first) == sha256(second)
    assert len(first) == EXPANDED_SIZE
    # 0xFFDC-0xFFDF: complement and checksum.
    assert report["stock_bytes_changed"] == ["0x00ffdc", "0x00ffdd", "0x00ffde", "0x00ffdf"]


def test_command_menu_keeps_shared_descriptors_stock_while_installing_native_parser_route():
    from build import build  # tools/build.py

    payload, report = build(relocation="thai", command_menu=True)
    command = report["renderer"]["command_menu"]
    assert command["pool"] == {"bank": "$FA", "address": "$0000", "end": "$09D9"}
    assert payload[0x0900FF:0x090102] == bytes((0x03, 0x81, 0xD2))
    assert payload[0x090108:0x09010B] == bytes((0xC3, 0x82, 0xD2))
    assert command["runtime_enabled"] is True
    assert command["descriptor_hook"] is None
    assert command["open_hook"] is not None
    assert command["selection_hook"] is not None
    assert payload[0x02843B] == 0x22
    assert payload[0x0389F5] == 0x22
    assert payload[0x0183DA:0x0183DE] == bytes((0xBF, 0xD8, 0x00, 0xC9))


def test_shared_raster_preserves_the_glyph_id_while_routing_fa():
    from build import shared_raster_source  # tools/build.py

    program = assemble(
        shared_raster_source(default_entry=0xFB1234, menu_entry=0xFC5678),
        0xFD0000,
    )
    assert program.code == bytes((
        0x08, 0xC2, 0x30, 0x48, 0xE2, 0x20, 0xA5, 0x1C, 0xC9, 0xFA,
        0xF0, 0x08, 0xC2, 0x20, 0x68, 0x28, 0x5C, 0x34, 0x12, 0xFB,
        0xC2, 0x20, 0x68, 0x28, 0x5C, 0x78, 0x56, 0xFC,
    ))


def test_menu_parser_keeps_all_four_extended_pages_distinct():
    from srw4.menu_router import parser_source

    program = assemble(parser_source(), 0xFD0000)
    page_decode = bytes((
        0xE9, 0xF0, 0x00,       # sbc #$00F0
        0xEB,                   # xba: page -> high byte
        0x18,
        0x69, 0x00, 0x01,       # adc #$0100
        0x48,
        0xA0, 0x00, 0x00,
        0xB7, 0x1A,
        0x29, 0xFF, 0x00,
        0x18,
        0x63, 0x01,             # adc $01,s
        0x7A,
        0xE6, 0x1A,
    ))
    assert page_decode in program.code


def test_route_only_command_stage_leaves_lifecycle_and_width_owners_stock():
    from build import build  # tools/build.py

    payload, report = build(
        relocation="thai",
        naming_presets=True,
        command_menu=True,
        command_stage="route",
    )
    command = report["renderer"]["command_menu"]
    assert command["stage"] == "route"
    assert command["activation_hook"] is None
    assert command["open_hook"] is None
    assert command["selection_hook"] is None
    assert command["width_hook"] is None
    assert payload[0x02843B:0x02843F] == bytes((0x22, 0xC6, 0x83, 0x81))
    assert payload[0x0284BB:0x0284C0] == bytes((0xA9, 0xFF, 0x00, 0x1C, 0x26))
    assert payload[0x0389F5:0x0389F9] == bytes((0x22, 0xC6, 0x83, 0x81))
