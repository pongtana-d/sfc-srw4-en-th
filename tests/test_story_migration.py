"""The current audited story corpus must fit the runtime-proven shell."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from build_proven_full import DEFAULT_CLEAN, build_proven  # noqa: E402
from srw4.story_migration import ROUTE_TABLE_CAPACITY, apply  # noqa: E402


def test_current_story_repack_is_complete_and_deterministic(tmp_path):
    shell = tmp_path / "shell.sfc"
    shell_report = tmp_path / "shell.json"
    build_proven(DEFAULT_CLEAN, shell, shell_report)
    cumulative = json.loads(shell_report.read_text())

    first, first_report = apply(shell.read_bytes(), cumulative)
    second, second_report = apply(shell.read_bytes(), cumulative)

    assert first == second
    assert first_report == second_report
    assert len(first) == 4 * 1024 * 1024
    assert first_report["story"]["translated"] == 9382
    assert len(first_report["story"]["blocks"]) == 47
    assert first_report["route_table"]["bytes"] <= ROUTE_TABLE_CAPACITY
    assert first_report["output"]["sha256"] == (
        "90fb08b8720b6caa199c33c8cefcddf997e1b08c4f7c63d8218b160330c69bdd"
    )
