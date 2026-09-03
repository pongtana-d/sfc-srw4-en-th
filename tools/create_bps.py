#!/usr/bin/env python3
"""Create and verify a standard BPS patch using SourceRead and TargetRead.

The emitted patch is compatible with BPS web patchers.  It intentionally uses
only the two sequential operations, which makes its behaviour easy to audit.
"""
from __future__ import annotations

import argparse
import binascii
import hashlib
import json
from pathlib import Path


MAGIC = b"BPS1"
SOURCE_READ = 0
TARGET_READ = 1


def encode_number(value: int) -> bytes:
    if value < 0:
        raise ValueError("BPS numbers cannot be negative")
    encoded = bytearray()
    while True:
        part = value & 0x7F
        value >>= 7
        if value == 0:
            encoded.append(part | 0x80)
            return bytes(encoded)
        encoded.append(part)
        value -= 1


def decode_number(data: bytes, cursor: int) -> tuple[int, int]:
    value = 0
    shift = 1
    while True:
        if cursor >= len(data):
            raise ValueError("truncated BPS number")
        part = data[cursor]
        cursor += 1
        value += (part & 0x7F) * shift
        if part & 0x80:
            return value, cursor
        shift <<= 7
        value += shift


def create(source: bytes, target: bytes) -> bytes:
    patch = bytearray(MAGIC)
    patch.extend(encode_number(len(source)))
    patch.extend(encode_number(len(target)))
    patch.extend(encode_number(0))  # no metadata
    offset = 0
    while offset < len(target):
        same = offset < len(source) and source[offset] == target[offset]
        end = offset + 1
        while end < len(target) and ((end < len(source) and source[end] == target[end]) == same):
            end += 1
        length = end - offset
        patch.extend(encode_number(((length - 1) << 2) | (SOURCE_READ if same else TARGET_READ)))
        if not same:
            patch.extend(target[offset:end])
        offset = end
    patch.extend(binascii.crc32(source).to_bytes(4, "little"))
    patch.extend(binascii.crc32(target).to_bytes(4, "little"))
    patch.extend(binascii.crc32(patch).to_bytes(4, "little"))
    return bytes(patch)


def apply(source: bytes, patch: bytes) -> bytes:
    if not patch.startswith(MAGIC) or len(patch) < 16:
        raise ValueError("not a valid BPS patch")
    if int.from_bytes(patch[-12:-8], "little") != binascii.crc32(source):
        raise ValueError("source ROM CRC32 does not match BPS patch")
    if int.from_bytes(patch[-4:], "little") != binascii.crc32(patch[:-4]):
        raise ValueError("BPS patch CRC32 is invalid")
    cursor = 4
    source_size, cursor = decode_number(patch, cursor)
    target_size, cursor = decode_number(patch, cursor)
    metadata_size, cursor = decode_number(patch, cursor)
    cursor += metadata_size
    if source_size != len(source) or cursor > len(patch) - 12:
        raise ValueError("BPS source size or metadata is invalid")
    target = bytearray()
    while len(target) < target_size:
        command, cursor = decode_number(patch, cursor)
        length, action = (command >> 2) + 1, command & 3
        if action == SOURCE_READ:
            start = len(target)
            end = start + length
            if end > len(source):
                raise ValueError("BPS SourceRead exceeds source ROM")
            target.extend(source[start:end])
        elif action == TARGET_READ:
            end = cursor + length
            if end > len(patch) - 12:
                raise ValueError("BPS TargetRead is truncated")
            target.extend(patch[cursor:end])
            cursor = end
        else:
            raise ValueError("unsupported BPS copy operation")
    if len(target) != target_size or cursor != len(patch) - 12:
        raise ValueError("BPS target length or command stream is invalid")
    if int.from_bytes(patch[-8:-4], "little") != binascii.crc32(target):
        raise ValueError("BPS target CRC32 is invalid")
    return bytes(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    source, target = args.source.read_bytes(), args.target.read_bytes()
    patch = create(source, target)
    if apply(source, patch) != target:
        raise SystemExit("internal BPS round-trip verification failed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patch)
    report = {
        "schema": "srw4-bps/1",
        "format": "BPS1",
        "source": {"path": str(args.source), "bytes": len(source),
                   "sha256": hashlib.sha256(source).hexdigest()},
        "target": {"path": str(args.target), "bytes": len(target),
                   "sha256": hashlib.sha256(target).hexdigest()},
        "patch": {"path": str(args.output), "bytes": len(patch),
                  "sha256": hashlib.sha256(patch).hexdigest()},
        "verification": "BPS apply round-trip passed",
    }
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
