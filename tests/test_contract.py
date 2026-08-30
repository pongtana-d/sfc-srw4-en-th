"""P2: the text/token contract has one authoritative byte-band definition."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.contract import (  # noqa: E402
    DIRECT_MAX,
    DIRECT_SLOTS,
    ENGINE_FLOOR,
    EXTENDED_LEAD,
    EXTENDED_PAGES,
    NEWLINE_BYTE,
    RESERVED_FIRST,
    RESERVED_LAST,
    TERMINATORS,
)
from srw4.stream import TERMINATORS as STREAM_TERMINATORS  # noqa: E402
from srw4.text import ADAPTER_SPLIT, ENGINE_OPERANDS  # noqa: E402


def test_byte_bands_are_adjacent_and_non_overlapping():
    assert DIRECT_MAX + 1 == DIRECT_SLOTS == RESERVED_FIRST == ADAPTER_SPLIT
    assert RESERVED_LAST + 1 == ENGINE_FLOOR
    assert EXTENDED_LEAD + EXTENDED_PAGES <= NEWLINE_BYTE


def test_parser_and_decoder_share_control_contract():
    assert STREAM_TERMINATORS == TERMINATORS == (0xF7, 0xFF)
    assert NEWLINE_BYTE == 0xF6
    assert ENGINE_OPERANDS[0xFB] == 2
    assert ENGINE_OPERANDS[0xF4] == 1
    assert ENGINE_OPERANDS[0xF5] == 1
