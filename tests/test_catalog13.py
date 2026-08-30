"""Catalog 13 can be compiled completely before its descriptor is repointed."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.catalog13 import build  # noqa: E402
from srw4.pipeline import Pipeline  # noqa: E402


def test_catalog_13_source_compiles_to_one_complete_variable_pool():
    clean_path = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
    result = build(ROOT, clean_path.read_bytes(), Pipeline.load(ROOT, clean_path))
    assert result.pool.bank == 0xFA
    assert result.pool.address == 0x0000
    assert result.pool.slots == 370
    assert len(result.pool.slot_pointers) == 370
    assert result.report["destination"]["end"] <= "$FFFF"
    assert all(row["overflow_px"] == 0 for row in result.report["records"])
