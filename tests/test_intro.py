import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.allocation import AllocationMap
from srw4.intro import HOOK_EXPECTED, PAGES, build
from srw4.pipeline import Pipeline


def test_intro_pages_compile_to_fixed_overlay_resources():
    clean = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
    result = build(ROOT, clean.read_bytes(), Pipeline.load(ROOT, clean), AllocationMap.load(ROOT / "data/config/allocation-map.json"))
    assert len(result.writes) == len(PAGES) * 2
    assert len(result.hook_code) < 0x800
    assert HOOK_EXPECTED == bytes.fromhex("B7 1A 29 FF 00")
