import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_endings import encode_source, load  # noqa: E402
from srw4.en_intro import install  # noqa: E402


BASE = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (English combo).sfc"
DATA = ROOT / "data" / "translations" / "ending-narratives.th.json"


def test_ending_narrative_sources_match_pinned_en_rom():
    clean = BASE.read_bytes()
    for row in load(DATA):
        pc = int(row["pc"], 0)
        source = encode_source(row["source"])
        assert clean[pc:pc + len(source)] == source


def test_ending_overlays_preserve_stock_streams_and_include_both_variants():
    clean = BASE.read_bytes()
    records = load(DATA)
    image = bytearray(clean)
    result = install(image, clean, ROOT)
    assert len(result["endings"]) == 2
    assert all(row["glyphs"] > 0 for row in result["endings"])
    assert result["hook_bytes"] <= 0x800
    for row in records:
        pc = int(row["pc"], 0)
        source = encode_source(row["source"])
        assert image[pc:pc + len(source)] == source
