"""Locked identity and integrity checks for the English-combo base ROM."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .rom import (
    HEADER_BASE,
    OFF_CHECKSUM,
    OFF_COMPLEMENT,
    OFF_MAP_MODE,
    compute_checksum,
)

EN_SIZE = 4_194_304
EN_SHA256 = "a66dd3c3349ab7f7718f033537c134354b881a6d72ab618df696403a25829408"

EN_TITLE = "SUPER ROBOT WARS 4"
EN_MAP_MODE = 0x31
IPS_HEADER = b"PATCH"
IPS_EOF = b"EOF"


class BaselineError(ValueError):
    """An input is not the exact artifact locked by P0."""


@dataclass(frozen=True)
class IpsResult:
    image: bytes
    records: int
    rle_records: int


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_identity(label: str, data: bytes, size: int, digest: str) -> None:
    if len(data) != size:
        raise BaselineError(f"{label} must be {size} bytes, got {len(data)}")
    actual = _sha256(data)
    if actual != digest:
        raise BaselineError(
            f"{label} sha256 mismatch: expected {digest}, got {actual}"
        )


def apply_ips(source: bytes, patch: bytes) -> IpsResult:
    """Apply a standard IPS patch, rejecting truncated or trailing data."""
    if not patch.startswith(IPS_HEADER):
        raise BaselineError("IPS header is not PATCH")

    image = bytearray(source)
    cursor = len(IPS_HEADER)
    records = 0
    rle_records = 0

    while True:
        if cursor + len(IPS_EOF) > len(patch):
            raise BaselineError("IPS patch has no EOF marker")
        if patch[cursor : cursor + len(IPS_EOF)] == IPS_EOF:
            cursor += len(IPS_EOF)
            break
        if cursor + 5 > len(patch):
            raise BaselineError("IPS record header is truncated")

        offset = int.from_bytes(patch[cursor : cursor + 3], "big")
        size = int.from_bytes(patch[cursor + 3 : cursor + 5], "big")
        cursor += 5
        if size:
            end = cursor + size
            if end > len(patch):
                raise BaselineError("IPS literal record is truncated")
            payload = patch[cursor:end]
            cursor = end
        else:
            if cursor + 3 > len(patch):
                raise BaselineError("IPS RLE record is truncated")
            run_length = int.from_bytes(patch[cursor : cursor + 2], "big")
            if run_length == 0:
                raise BaselineError("IPS RLE record has zero length")
            payload = bytes((patch[cursor + 2],)) * run_length
            cursor += 3
            rle_records += 1

        end = offset + len(payload)
        if end > len(image):
            image.extend(b"\x00" * (end - len(image)))
        image[offset:end] = payload
        records += 1

    trailing = patch[cursor:]
    if trailing:
        if len(trailing) != 3:
            raise BaselineError(f"IPS has {len(trailing)} unsupported trailing bytes")
        truncate_size = int.from_bytes(trailing, "big")
        del image[truncate_size:]

    return IpsResult(bytes(image), records, rle_records)


def _header_report(image: bytes) -> dict[str, object]:
    title = image[HEADER_BASE : HEADER_BASE + 21].decode("ascii").rstrip()
    stored_complement = int.from_bytes(
        image[OFF_COMPLEMENT : OFF_COMPLEMENT + 2], "little"
    )
    stored_checksum = int.from_bytes(
        image[OFF_CHECKSUM : OFF_CHECKSUM + 2], "little"
    )
    computed_checksum = compute_checksum(image)
    return {
        "title": title,
        "map_mode": f"0x{image[OFF_MAP_MODE]:02X}",
        "stored_checksum": f"0x{stored_checksum:04X}",
        "stored_complement": f"0x{stored_complement:04X}",
        "computed_checksum": f"0x{computed_checksum:04X}",
        "checksum_valid": stored_checksum == computed_checksum,
        "complement_valid": (stored_checksum ^ stored_complement) == 0xFFFF,
        "copier_header": False,
    }


def verify_baseline(english: bytes) -> dict[str, object]:
    """Validate the one canonical English-combo build input."""
    _require_identity("English-combo ROM", english, EN_SIZE, EN_SHA256)

    header = _header_report(english)
    if header["title"] != EN_TITLE:
        raise BaselineError(
            f"English-combo title mismatch: expected {EN_TITLE!r}, got {header['title']!r}"
        )
    if english[OFF_MAP_MODE] != EN_MAP_MODE:
        raise BaselineError(
            f"English-combo map mode must be 0x{EN_MAP_MODE:02X}, "
            f"got 0x{english[OFF_MAP_MODE]:02X}"
        )
    if not header["checksum_valid"] or not header["complement_valid"]:
        raise BaselineError("English-combo checksum/complement is invalid")

    return {
        "schema": "srw4.en-th-dialogue-baseline.v2",
        "scope": {
            "story_blocks": 47,
            "includes": [
                "map dialogue",
                "event dialogue",
                "battle quotes",
                "objective/game-over/system records in the story corpus",
            ],
            "excludes": ["catalog/UI outside the story corpus"],
            "runtime_catalog_names": "English",
        },
        "inputs": {
            "english_combo": {"bytes": len(english), "sha256": _sha256(english)},
        },
        "english_combo_header": header,
        "source_roms_modified": False,
        "p0_pass": True,
    }
