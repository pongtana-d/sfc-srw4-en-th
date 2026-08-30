"""Release bridge: the battle-safe cumulative milestone stays reproducible."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from build_proven_full import (  # noqa: E402
    DEFAULT_CLEAN,
    EXPECTED_SHA256,
    PROVEN_REVISION,
    build_proven,
)


def test_proven_full_build_is_hash_locked_and_reports_runtime_gates(tmp_path):
    output = tmp_path / "proven.sfc"
    report = tmp_path / "proven.json"

    digest = build_proven(DEFAULT_CLEAN, output, report)

    assert digest == EXPECTED_SHA256
    assert output.stat().st_size == 4 * 1024 * 1024
    document = json.loads(report.read_text())
    assert document["proven_source"]["revision"] == PROVEN_REVISION
    assert document["proven_source"]["sha256"] == EXPECTED_SHA256
    assert len(document["proven_source"]["runtime_gates"]) == 4
    placement = document["proven_source"]["battle_placement"]
    assert placement == {
        "owner": "current modules",
        "assets": 14,
        "renderer_bytes": 1796,
        "adapters": ["stock_fb", "width", "dispatch"],
        "hooks": ["glyph_width_2", "battle_renderer_dispatch", "battle_stock_fb"],
    }
