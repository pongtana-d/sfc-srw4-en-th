"""Runtime evidence parser must preserve pointer jumps without overclaiming."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_story_trace import summarize_trace  # noqa: E402


def test_trace_summary_keeps_nonsequential_control_flow_explicit():
    report = summarize_trace(
        [
            {"frame": 1, "pointer": 0xF1246D, "byte": 0xFB},
            {"frame": 1, "pointer": 0x00101E, "byte": 0x1E},
            {"frame": 1, "pointer": 0x00101F, "byte": 0xA1},
            {"frame": 2, "pointer": 0x001020, "byte": 0xFF},
            {"frame": 2, "pointer": 0xF12470, "byte": 0xAB},
        ]
    )
    assert report["fetches"] == 5
    assert report["control_leads_before_transition"] == {"FB": 1, "FF": 1}
    assert report["nonsequential_transitions"] == [
        {"from": "$F1:246D", "lead": "$FB", "to": "$00:101E", "frame_from": 1, "frame_to": 1},
        {"from": "$00:1020", "lead": "$FF", "to": "$F1:2470", "frame_from": 2, "frame_to": 2},
    ]
