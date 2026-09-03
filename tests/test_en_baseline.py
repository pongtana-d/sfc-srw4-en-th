"""P0 locks the canonical English-combo base."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_baseline import BaselineError, apply_ips, verify_baseline  # noqa: E402

EN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (English combo).sfc"


def test_english_combo_baseline_is_locked():
    english = EN_ROM.read_bytes()
    report = verify_baseline(english)

    assert report["p0_pass"] is True
    assert report["english_combo_header"] == {
        "title": "SUPER ROBOT WARS 4",
        "map_mode": "0x31",
        "stored_checksum": "0x5D91",
        "stored_complement": "0xA26E",
        "computed_checksum": "0x5D91",
        "checksum_valid": True,
        "complement_valid": True,
        "copier_header": False,
    }


def test_baseline_rejects_a_modified_english_rom():
    english = bytearray(EN_ROM.read_bytes())
    english[0x1000] ^= 0xFF
    with pytest.raises(BaselineError, match="English-combo ROM sha256 mismatch"):
        verify_baseline(bytes(english))


def test_ips_parser_rejects_a_truncated_record():
    with pytest.raises(BaselineError, match="truncated"):
        apply_ips(b"", b"PATCH\x00\x00\x01\x00\x02\xAA")
