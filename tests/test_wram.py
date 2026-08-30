"""P1 tests: the WRAM contract, and the maths behind the quiet-span report."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from probe_wram import (  # noqa: E402  tools/probe_wram.py
    SAFE_FLOOR,
    WRAM_BASE,
    WRAM_SIZE,
    pulses,
    reserved_spans,
    spans,
)

WRAM_MAP = ROOT / "data" / "config" / "wram-map.json"


@pytest.fixture(scope="module")
def document() -> dict:
    return json.loads(WRAM_MAP.read_text())


# --- span maths -------------------------------------------------------------


def test_quiet_spans_are_found_between_the_writes():
    written = bytearray(WRAM_SIZE)
    for address in range(0x7E3000, 0x7E3010):
        written[address - WRAM_BASE] = 1
    found = spans(bytes(written), SAFE_FLOOR)
    assert (SAFE_FLOOR, 0x7E3000) in found
    assert (0x7E3010, WRAM_BASE + WRAM_SIZE) in found


def test_nothing_below_the_mirror_floor_is_ever_offered():
    written = bytearray(WRAM_SIZE)
    for start, end in spans(bytes(written), SAFE_FLOOR):
        assert start >= SAFE_FLOOR


def test_a_fully_written_range_yields_no_span():
    assert spans(b"\x01" * WRAM_SIZE, SAFE_FLOOR) == []


def test_pulses_taps_rather_than_holds():
    script = pulses(60, 180, "start", period=30, width=2)
    assert script == "60:62:start,90:92:start,120:122:start,150:152:start"


# --- the contract -----------------------------------------------------------


def test_every_reservation_sits_above_the_mirror(document):
    for _, start, end in reserved_spans():
        assert start >= int(document["mirror_floor"], 16)
        assert end <= WRAM_BASE + WRAM_SIZE


def test_reservations_do_not_overlap_each_other():
    ordered = sorted(reserved_spans(), key=lambda entry: entry[1])
    for (_, _, end), (owner, start, _) in zip(ordered, ordered[1:]):
        assert start >= end, f"{owner} overlaps the reservation before it"


def test_reservations_stay_inside_their_region(document):
    regions = [
        (int(region["start"], 16), int(region["end"], 16)) for region in document["regions"]
    ]
    for owner, start, end in reserved_spans():
        assert any(low <= start and end <= high for low, high in regions), owner


def test_nothing_is_reserved_inside_a_range_we_agreed_to_avoid(document):
    for entry in document["avoid"]:
        low, high = int(entry["start"], 16), int(entry["end"], 16)
        for owner, start, end in reserved_spans():
            assert end <= low or start >= high, f"{owner} lands in {entry['why']}"


def test_each_context_gets_the_whole_budget(document):
    budget = document["budget_per_context"]["total"]
    for region in document["regions"]:
        for context in region.get("contexts", []):
            size = int(context["end"], 16) - int(context["start"], 16)
            assert size >= budget, f"{context['id']} has {size} bytes, needs {budget}"


def test_the_budget_adds_up(document):
    budget = document["budget_per_context"]
    parts = sum(value for key, value in budget.items() if key != "total")
    assert parts == budget["total"]


def test_the_contract_says_which_contexts_still_have_no_evidence(document):
    assert document["contexts_without_evidence"], "an empty list would claim more than we measured"
    assert "battle" in document["contexts_without_evidence"]
