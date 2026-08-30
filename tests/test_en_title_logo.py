import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_title import (  # noqa: E402
    EN_LOGO_SPRITES,
    EN_TITLE_LOGO_PC,
    EN_TITLE_LOGO_SIZE,
    build_en_title_logo,
)


def test_en_title_logo_uses_english_logo_page_only():
    base = (ROOT / "rom/Dai-4-ji Super Robot Taisen English.sfc").read_bytes()
    payload, report = build_en_title_logo(ROOT / "data", base)
    assert len(payload) == EN_TITLE_LOGO_SIZE
    assert payload != base[EN_TITLE_LOGO_PC:EN_TITLE_LOGO_PC + EN_TITLE_LOGO_SIZE]
    assert report["text"] == "ซูเปอร์โรบอตวอร์ส 4"
    assert report["menu_preserved"] is True


def test_en_logo_oam_has_all_fifteen_sprites_per_row():
    assert len(EN_LOGO_SPRITES) == 60
    assert [x for x, y, _ in EN_LOGO_SPRITES if y == 48] == [
        *range(16, 193, 16), 200, 216, 232
    ]
