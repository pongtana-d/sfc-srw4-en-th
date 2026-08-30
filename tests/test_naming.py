from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
sys.path.insert(0, str(ROOT / "src"))

from srw4.naming import (  # noqa: E402
    NAMING_FIXED_RANGES,
    NAMING_LABEL_RANGES,
    NAMING_POINTER_DP,
    NAMING_RASTER_CALL,
    NAMING_RASTER_EXPECTED,
    PRESET_COUNT,
    PRESET_POOL_END,
    PRESET_POOL_START,
    preset_writes,
)
from srw4.pipeline import Pipeline  # noqa: E402


def test_thai_name_presets_preserve_the_fixed_pool_contract():
    clean = CLEAN_ROM.read_bytes()
    pipeline = Pipeline.load(ROOT, CLEAN_ROM)

    writes, report = preset_writes(ROOT, clean, pipeline)

    assert len(writes) == 2
    assert len(report["presets"]) == PRESET_COUNT
    assert report["pool"]["capacity"] == PRESET_POOL_END - PRESET_POOL_START
    assert report["pool"]["used"] <= report["pool"]["capacity"]
    assert all(entry["bytes"] <= entry["byte_limit"] for entry in report["presets"])

    rebuilt = bytearray(clean)
    for write in writes:
        assert rebuilt[write.pc:write.pc + len(write.expected)] == write.expected
        rebuilt[write.pc:write.pc + len(write.payload)] = write.payload
    assert rebuilt[PRESET_POOL_START:PRESET_POOL_END].endswith(b"\xFF")


def test_naming_adapter_contract_comes_from_the_live_trace():
    clean = CLEAN_ROM.read_bytes()

    assert NAMING_POINTER_DP == 0x1A
    assert clean[NAMING_RASTER_CALL:NAMING_RASTER_CALL + 4] == NAMING_RASTER_EXPECTED
    assert NAMING_FIXED_RANGES[0xCC] == ((0xAB5E, 0xABE3), (0xAC53, 0xAC8B))
    assert (0xACC2, 0xACC3) in NAMING_LABEL_RANGES[0xCC]
