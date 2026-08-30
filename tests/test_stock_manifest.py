"""Production stock-font controls use one explicit, globally consistent ID set."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.proven.text.stock import (  # noqa: E402
    LOCKED_RUNS,
    StockCatalog,
    discover_runs,
    encode_stock,
)


def test_locked_manifest_covers_proven_and_current_corpora():
    catalog = StockCatalog.locked()
    proven = set(discover_runs(ROOT / "data" / "proven" / "full" / "translations"))
    current = set(discover_runs(ROOT / "data" / "translations"))

    assert LOCKED_RUNS == ROOT / "data" / "proven" / "stock-runs.json"
    assert len(catalog.runs) == 169
    assert proven <= set(catalog.runs)
    assert current <= set(catalog.runs)


def test_locked_pointer_table_round_trips_every_run():
    catalog = StockCatalog.locked()
    pool_pc = 0x3A0300
    table, pool, report = catalog.assets(pool_pc)

    assert len(table) == 256 * 3
    assert len(report) == len(catalog.runs)
    cursor = 0
    for index, run in enumerate(catalog.runs):
        cpu = int.from_bytes(table[index * 3:index * 3 + 3], "little")
        expected_cpu = 0xFA0000 | (pool_pc + cursor & 0xFFFF)
        encoded = encode_stock(run) + b"\xFF"
        assert cpu == expected_cpu
        assert pool[cursor:cursor + len(encoded)] == encoded
        assert catalog.control(run) == bytes((0xFB, index, 0xFE))
        cursor += len(encoded)
