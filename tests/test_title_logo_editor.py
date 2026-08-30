import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from title_logo_editor import HEIGHT, WIDTH, LogoDocument, validate_rows  # noqa: E402


def test_editor_loads_the_exact_game_ready_geometry():
    logo = LogoDocument()
    state = logo.state()
    assert (state["width"], state["height"]) == (200, 64)
    assert len(state["rows"]) == HEIGHT
    assert {len(row) for row in state["rows"]} == {WIDTH}
    assert len(state["palette_bgr555"]) == 16


def test_editor_rejects_wrong_geometry_and_palette_values():
    with pytest.raises(ValueError, match="64 rows"):
        validate_rows(["0" * WIDTH])
    bad = ["0" * WIDTH for _ in range(HEIGHT)]
    bad[3] = "Z" + bad[3][1:]
    with pytest.raises(ValueError, match="outside palette"):
        validate_rows(bad)


def test_editor_save_is_atomic_and_reload_returns_the_saved_pixel(tmp_path):
    source = json.loads((ROOT / "data/assets/title-logo.json").read_text(encoding="utf-8"))
    path = tmp_path / "title-logo.json"
    path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    logo = LogoDocument(path)
    rows = list(logo.state()["rows"])
    replacement = "1" if rows[0][0] != "1" else "2"
    rows[0] = replacement + rows[0][1:]
    logo.save(rows)
    reloaded = LogoDocument(path)
    assert reloaded.state()["rows"][0][0] == replacement
    assert reloaded.document["manual_edit"] is True
    assert not list(tmp_path.glob("*.tmp"))
