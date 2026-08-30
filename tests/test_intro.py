import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.allocation import AllocationMap
from srw4.en_intro import EN_INTRO_REGION_END, EN_INTRO_REGION_START, install
from srw4.intro import EN_PAGES, HOOK_AT, HOOK_EXPECTED, PAGES, build
from srw4.pipeline import Pipeline


def test_intro_pages_compile_to_fixed_overlay_resources():
    clean = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
    result = build(ROOT, clean.read_bytes(), Pipeline.load(ROOT, clean), AllocationMap.load(ROOT / "data/config/allocation-map.json"))
    assert len(result.writes) == len(PAGES) * 2
    assert len(result.hook_code) < 0x800
    assert HOOK_EXPECTED == bytes.fromhex("B7 1A 29 FF 00")


def test_existing_intro_translation_installs_on_english_rom():
    english = (ROOT / "rom" / "Dai-4-ji Super Robot Taisen English.sfc").read_bytes()
    image = bytearray(english)

    report = install(image, english, ROOT)

    assert len(report["pages"]) == len(EN_PAGES) == 5
    assert [page["lines"] for page in report["pages"]] == [16, 16, 13, 6, 6]
    start, end = EN_PAGES[0][2:4]
    assert report["pages"][0]["source_sha256"] == hashlib.sha256(
        english[start:end]
    ).hexdigest()
    assert image[HOOK_AT] == 0x5C
    assert image[EN_INTRO_REGION_START:EN_INTRO_REGION_END] != bytes(
        english[EN_INTRO_REGION_START:EN_INTRO_REGION_END]
    )
    page4_tiles = EN_INTRO_REGION_START + 3 * 0x3000
    page4_used = report["pages"][3]["glyphs"] * 64
    assert image[page4_tiles + page4_used:page4_tiles + 0x2000] == bytes(
        0x2000 - page4_used
    )
