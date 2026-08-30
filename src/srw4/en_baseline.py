"""Locked P0 identities and reproducibility checks for the English base ROM."""

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

JP_SIZE = 3_145_728
JP_SHA256 = "efd72094b2727c4903924cf9296b3946b95a354f639b600e1d76d9ec6b9ca18b"
EN_SIZE = 4_194_304
EN_SHA256 = "7cac9fc9c092c82cb753ebc8c8af6de25c2957ee4fbdee0f10676f1d0a661f2c"
IPS_SHA256 = "2f1e764589633a52ae914cb8ef98ba71d43fa7abe1d90f45a41d3513472f291c"
XDELTA_SHA256 = "5e00c2d541943e580325c5a63912b766697e6bdb635d6c022136d4d55821db86"
IPS_SIZE = 922_478
XDELTA_SIZE = 415_683

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


def verify_baseline(
    jp: bytes,
    english: bytes,
    ips: bytes,
    xdelta: bytes,
    xdelta_output: bytes,
) -> dict[str, object]:
    """Validate every P0 input and return a deterministic JSON-ready report."""
    _require_identity("JP Rev 1 ROM", jp, JP_SIZE, JP_SHA256)
    _require_identity("English ROM", english, EN_SIZE, EN_SHA256)
    _require_identity("English IPS", ips, IPS_SIZE, IPS_SHA256)
    _require_identity("English xdelta", xdelta, XDELTA_SIZE, XDELTA_SHA256)
    _require_identity("xdelta output", xdelta_output, EN_SIZE, EN_SHA256)

    header = _header_report(english)
    if header["title"] != EN_TITLE:
        raise BaselineError(
            f"English title mismatch: expected {EN_TITLE!r}, got {header['title']!r}"
        )
    if english[OFF_MAP_MODE] != EN_MAP_MODE:
        raise BaselineError(
            f"English map mode must be 0x{EN_MAP_MODE:02X}, "
            f"got 0x{english[OFF_MAP_MODE]:02X}"
        )
    if not header["checksum_valid"] or not header["complement_valid"]:
        raise BaselineError("English checksum/complement is invalid")

    ips_result = apply_ips(jp, ips)
    if ips_result.image != english:
        raise BaselineError(
            "IPS output is not byte-identical to the locked English ROM: "
            f"got {_sha256(ips_result.image)}"
        )
    if xdelta_output != english:
        raise BaselineError("xdelta output is not byte-identical to English ROM")

    return {
        "schema": "srw4.en-th-dialogue-baseline.v1",
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
            "jp_rev1": {"bytes": len(jp), "sha256": _sha256(jp)},
            "english": {"bytes": len(english), "sha256": _sha256(english)},
            "ips": {"bytes": len(ips), "sha256": _sha256(ips)},
            "xdelta": {"bytes": len(xdelta), "sha256": _sha256(xdelta)},
        },
        "english_header": header,
        "reproduction": {
            "ips": {
                "records": ips_result.records,
                "rle_records": ips_result.rle_records,
                "output_bytes": len(ips_result.image),
                "output_sha256": _sha256(ips_result.image),
                "byte_identical": True,
            },
            "xdelta": {
                "output_bytes": len(xdelta_output),
                "output_sha256": _sha256(xdelta_output),
                "byte_identical": True,
            },
        },
        "source_roms_modified": False,
        "p0_pass": True,
    }
