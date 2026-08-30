"""Regression evidence extracted from the English reference ROM."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.reference import ReferenceError, analyze_reference, contiguous_ranges  # noqa: E402

CLEAN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
REFERENCE_ROM = ROOT / "rom" / "en-sample.sfc"


def _report(pointer_example_limit=128):
    return analyze_reference(
        CLEAN_ROM.read_bytes(),
        REFERENCE_ROM.read_bytes(),
        hooks=json.loads((ROOT / "data/config/hooks.json").read_text()),
        rom_map=json.loads((ROOT / "data/config/rom-map.json").read_text()),
        script=json.loads((ROOT / "data/translations/script.source.json").read_text()),
        pointer_example_limit=pointer_example_limit,
    )


def test_contiguous_ranges_are_start_inclusive_end_exclusive():
    assert contiguous_ranges([1, 2, 3, 7, 9, 10]) == [(1, 4), (7, 8), (9, 11)]


def test_reference_rejects_images_that_are_not_exactly_4mb():
    with pytest.raises(ReferenceError, match="reference ROM must be"):
        analyze_reference(
            bytes(3_145_728),
            bytes(123),
            hooks={"hooks": []},
            rom_map={},
            script={},
        )


def test_english_reference_identity_and_diff_are_locked():
    report = _report(pointer_example_limit=0)
    reference = report["input"]["reference"]
    assert reference["sha256"] == "7cac9fc9c092c82cb753ebc8c8af6de25c2957ee4fbdee0f10676f1d0a661f2c"
    assert reference["title"] == "SUPER ROBOT WARS 4"
    assert reference["checksum_valid"] is True
    assert report["stock_diff"]["changed_bytes"] == 343_314
    assert report["stock_diff"]["changed_runs"] == 9_119
    assert report["expansion_payload"]["non_ff_bytes"] == 785_702


def test_english_reference_confirms_both_stock_rasteriser_call_sites():
    report = _report(pointer_example_limit=0)
    candidates = {
        (item["cpu"], item["opcode"], item["target"])
        for item in report["hooks"]["long_transfer_candidates"]
    }
    assert ("$C1:84E4", "JSL", "$F0:E045") in candidates
    assert ("$C1:9238", "JSL", "$F0:E045") in candidates


def test_known_battle_hook_is_reported_as_a_novel_reference_replacement():
    report = _report(pointer_example_limit=0)
    hooks = {item["id"]: item for item in report["hooks"]["known"]}
    battle = hooks["battle_renderer_dispatch"]
    assert battle["classification"] == "novel_replacement"
    assert battle["control_transfer"]["target"] == "$F0:E045"


def test_pointer_results_are_explicitly_heuristic_and_capped():
    report = _report(pointer_example_limit=3)
    pointers = report["pointers"]
    assert pointers["method"].startswith("heuristic:")
    assert pointers["total"] > 3
    assert pointers["examples_truncated"] is True
    assert len(pointers["examples"]) == 3


def test_story_changes_are_classified_from_the_extracted_block_map():
    story = _report(pointer_example_limit=0)["script_and_catalog_regions"]["story_blocks"]
    assert story["changed_blocks"] > 0
    assert story["changed_bytes"] > 0
