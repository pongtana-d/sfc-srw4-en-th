import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from rebuild_title_logo_shadow import DEFAULT_DEPTH, rebuild  # noqa: E402


def test_production_title_shadow_is_the_complete_deterministic_extrusion():
    document = json.loads(
        (ROOT / "data/assets/title-logo.json").read_text(encoding="utf-8")
    )
    assert document["shadow_rebuild"] == {
        "depth": DEFAULT_DEPTH,
        "horizontal_step_every": 3,
        "palette_indices": "CDEF",
        "face_preserved": True,
    }
    assert rebuild(document["rows"], DEFAULT_DEPTH) == document["rows"]


def test_production_title_shadow_has_no_holes_along_any_face_extrusion():
    rows = json.loads(
        (ROOT / "data/assets/title-logo.json").read_text(encoding="utf-8")
    )["rows"]
    occupied = set("123456789ABCDEF")
    face = set("123456789AB")
    for y, row in enumerate(rows):
        for x, pixel in enumerate(row):
            if pixel not in face:
                continue
            for depth in range(1, DEFAULT_DEPTH + 1):
                target_x = x + (depth + 2) // 3
                target_y = y + depth
                if target_x < 200 and target_y < 64:
                    assert rows[target_y][target_x] in occupied
