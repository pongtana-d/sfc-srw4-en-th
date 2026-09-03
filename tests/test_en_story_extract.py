"""P1 extraction locks EN story topology before translation/repacking."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_story_extract import extract_story  # noqa: E402


def test_english_story_topology_matches_the_locked_corpus_shape():
    rom = (ROOT / "rom" / "Dai-4-ji Super Robot Taisen (English).sfc").read_bytes()
    summary = json.loads(
        (ROOT / "data" / "translations" / "script.source.json").read_text()
    )["summary"]["blocks"]
    document = extract_story(rom, summary)

    assert document["schema"] == "srw4.en-story.source.v2"
    assert document["master_table"] == {"cpu": "$E8:0000", "slots": 52}
    assert document["summary"] == {
        "text_blocks": 40,
        "record_blocks": 7,
        "pointer_slots": 10_439,
        "null_pointer_slots": 1,
        "pointer_reachable_records": 9_223,
        "aliased_pointer_slots": 1_215,
        "source_summary_records": 9_400,
        "source_minus_reachable_records": 177,
    }
    by_slot = {block["slot"]: block for block in document["blocks"]}
    assert by_slot[0]["bank"] == "$F1"
    assert by_slot[41]["bank"] == "$FC"
    assert by_slot[48]["bank"] == "$E9"
    assert by_slot[20]["dispatch_bytes"] == 1_828
    assert all("unresolved" in record["boundary"] for record in document["records"].values())
