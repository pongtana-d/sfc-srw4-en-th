"""P4: dynamic frame/reference geometry for the command-menu pilot."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.window import BorderTiles, WindowSpec, menu_layout  # noqa: E402
from srw4.pipeline import Pipeline  # noqa: E402


def command_spec() -> WindowSpec:
    data = json.loads((ROOT / "data" / "config" / "window-specs.json").read_text())["command_menu"]
    return WindowSpec(
        *data["anchor_tiles"],
        data["min_outer_width_tiles"],
        *data["content_padding_tiles"],
        data["item_height_tiles"],
        *data["cursor_anchor_tiles"],
        BorderTiles(**data["border"]),
    )


def test_en_command_menu_geometry_is_reproduced():
    layout = menu_layout(command_spec(), [20, 30, 30, 30])
    assert (layout.outer_width_tiles, layout.outer_height_tiles) == (8, 10)
    assert layout.tilemap[0] == (0x2011, *([0x2019] * 6), 0x2012)
    assert layout.tilemap[-1] == (0x2013, *([0x201A] * 6), 0x2014)
    assert all(row[0] == 0x201B and row[-1] == 0x201C for row in layout.tilemap[1:-1])
    assert layout.label_positions_px == ((112, 96), (112, 112), (112, 128), (112, 144))
    assert layout.cursor_positions_px == ((104, 96), (104, 112), (104, 128), (104, 144))


def test_frame_expands_from_measured_content_without_changing_row_step():
    layout = menu_layout(command_spec(), [48])
    assert layout.outer_width_tiles == 10
    assert layout.outer_height_tiles == 4
    assert layout.cursor_positions_px == ((104, 96),)


def test_measured_en_labels_fit_the_evidence_frame():
    pipeline = Pipeline.load(ROOT, ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc")
    labels = json.loads((ROOT / "data" / "config" / "window-specs.json").read_text())["command_menu"]["labels"]
    widths = [pipeline.draw(label + "<ENDFF>", where=label).lines[0].width for label in labels]
    assert widths == [22, 32, 29, 32]
    assert menu_layout(command_spec(), widths).outer_width_tiles == 8


def test_thai_long_label_expands_the_frame_from_its_measured_width():
    pipeline = Pipeline.load(ROOT, ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc")
    width = pipeline.draw("ตั้งค่าการควบคุม<ENDFF>", where="long-command-label").lines[0].width
    assert width == 75
    layout = menu_layout(command_spec(), [width])
    assert layout.outer_width_tiles == 14
    assert layout.label_positions_px == ((112, 96),)


def test_command_menu_fixture_covers_english_thai_mixed_and_a_long_name():
    """The P4 pilot is measured from the production atlas, never character count.

    These are deliberately separate menu runs: a real command surface measures
    every visible item before it writes its frame, so an item must never borrow
    width from an unrelated test string.
    """
    pipeline = Pipeline.load(ROOT, ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc")
    fixtures = {
        "en": ["Move", "Attack", "Spirit", "Status"],
        "th": ["เดิน", "โจมตี", "วิญญาณ", "สถานะ"],
        "mixed": ["Move LV12", "โจมตี A", "Spirit 100%", "สถานะ B"],
        "long-name": ["อาคิ (LV12)", "โจมตี", "วิญญาณ", "สถานะ"],
    }

    for name, labels in fixtures.items():
        lines = [pipeline.draw(label + "<ENDFF>", where=f"command-{name}").lines[0] for label in labels]
        assert all(line.canvas.overflow == 0 for line in lines)
        layout = menu_layout(command_spec(), [line.width for line in lines])
        assert layout.outer_height_tiles == 10
        assert layout.outer_width_tiles >= 8
        assert len(layout.label_positions_px) == len(labels)
        assert len(layout.cursor_positions_px) == len(labels)
