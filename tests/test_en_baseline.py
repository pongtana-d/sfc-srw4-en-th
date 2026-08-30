"""P0 locks the English base and verifies both supplied patch routes."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.en_baseline import BaselineError, apply_ips, verify_baseline  # noqa: E402

JP_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
EN_ROM = ROOT / "rom" / "Dai-4-ji Super Robot Taisen English.sfc"
IPS = ROOT / "rom" / "srw4e.ips"
XDELTA = ROOT / "rom" / "srw4e.xdelta"


def test_english_baseline_and_ips_route_are_locked():
    jp = JP_ROM.read_bytes()
    english = EN_ROM.read_bytes()
    report = verify_baseline(
        jp,
        english,
        IPS.read_bytes(),
        XDELTA.read_bytes(),
        english,
    )

    assert report["p0_pass"] is True
    assert report["english_header"] == {
        "title": "SUPER ROBOT WARS 4",
        "map_mode": "0x31",
        "stored_checksum": "0xC494",
        "stored_complement": "0x3B6B",
        "computed_checksum": "0xC494",
        "checksum_valid": True,
        "complement_valid": True,
        "copier_header": False,
    }
    assert report["reproduction"]["ips"]["records"] == 1_962
    assert report["reproduction"]["ips"]["rle_records"] == 910
    assert report["reproduction"]["ips"]["byte_identical"] is True
    assert report["reproduction"]["xdelta"]["byte_identical"] is True


def test_baseline_rejects_a_modified_english_rom():
    english = bytearray(EN_ROM.read_bytes())
    english[0x1000] ^= 0xFF
    with pytest.raises(BaselineError, match="English ROM sha256 mismatch"):
        verify_baseline(
            JP_ROM.read_bytes(),
            bytes(english),
            IPS.read_bytes(),
            XDELTA.read_bytes(),
            EN_ROM.read_bytes(),
        )


def test_ips_parser_rejects_a_truncated_record():
    with pytest.raises(BaselineError, match="truncated"):
        apply_ips(b"", b"PATCH\x00\x00\x01\x00\x02\xAA")
