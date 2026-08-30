import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.proven.title import LOGO_SPRITES, MENU_ROWS, build_title_data  # noqa: E402


def sprite_tiles(tile: int) -> set[int]:
    return {tile, tile + 1, tile + 0x10, tile + 0x11}


def test_thai_title_asset_fits_the_stock_sprite_surface_and_palette():
    art = json.loads((ROOT / "data/assets/title-logo.json").read_text(encoding="utf-8"))
    assert art["text"] == "ซูเปอร์โรบอตวอร์ส 4"
    assert art["screen_box"] == {"x": 24, "y": 48, "width": 200, "height": 64}
    assert len(art["rows"]) == 64
    assert {len(row) for row in art["rows"]} == {200}
    assert set("".join(art["rows"])) <= set("0123456789ABCDEF")


def test_thai_logo_tiles_do_not_overlap_the_english_menu_tiles():
    logo = set().union(*(sprite_tiles(tile) for _, _, tile in LOGO_SPRITES))
    menu = set().union(*(
        sprite_tiles(tile)
        for _, sprites in MENU_ROWS
        for _, _, tile in sprites
    ))
    assert logo.isdisjoint(menu)


def test_title_build_reports_the_approved_thai_logo():
    clean_path = ROOT / "rom/Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
    writes, report = build_title_data(ROOT / "data", clean_path.read_bytes(), 0x3A0600)
    assert report["logo"] == "ซูเปอร์โรบอตวอร์ส 4"
    assert {write.owner for write in writes} == {
        "title-obj-payload", "title-resource-pointer"
    }
