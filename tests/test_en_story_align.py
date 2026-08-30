"""P3 alignment must stay structural and deliberately conservative."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_story_align import align_story  # noqa: E402
from srw4.en_story_extract import extract_story  # noqa: E402


def test_structural_alignment_covers_every_source_message_without_guessing():
    jp_rom = (ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc").read_bytes()
    en_rom = (ROOT / "rom" / "Dai-4-ji Super Robot Taisen English.sfc").read_bytes()
    source = json.loads((ROOT / "data" / "translations" / "script.source.json").read_text())
    en_source = extract_story(en_rom, source["summary"]["blocks"])
    document = align_story(jp_rom, en_rom, source, en_source)

    assert document["schema"] == "srw4.jp-en-story-map.v1"
    assert document["summary"] == {
        "source_messages": 9_382,
        "direct_pointer_messages": 7_876,
        "confidence": {"A": 7_830, "B": 708, "UNRESOLVED": 844},
        "unresolved_reasons": {
            "alias_topology_changed": 41,
            "dispatch_shape_match": 662,
            "direct_alias_match": 7_830,
            "no_direct_pointer_or_dispatch_target": 844,
            "split_target": 5,
        },
        "pointer_rows": 10_439,
        "alias_topology_match_rows": 10_375,
        "alias_topology_different_rows": 64,
        "alias_topology_differences_by_slot": {"48": 64},
        "fixed_dispatch": {"blocks": 7, "records": 1_269, "pointer_fields": 3_623, "source_messages": 664},
    }
    assert len(document["mappings"]) == 9_382
    assert all(item["confidence"] != "C" for item in document["mappings"])
    assert all(
        item["source_block"] == 48
        for item in document["mappings"]
        if item["reason"] == "same pointer identity; EN alias topology differs (manual block 48 audit required)"
    )
