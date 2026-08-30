"""ROM loading, expansion, checksum and writing.

Everything here is deterministic: the same clean ROM plus the same set of
writes must always produce a byte-identical output file.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

CLEAN_SIZE = 3_145_728
CLEAN_SHA256 = "efd72094b2727c4903924cf9296b3946b95a354f639b600e1d76d9ec6b9ca18b"
EXPANDED_SIZE = 4_194_304

# SNES header (HiROM, no file header): at ROM offset 0xFFC0.
HEADER_BASE = 0xFFC0
OFF_MAP_MODE = HEADER_BASE + 0x15
OFF_ROM_SIZE = HEADER_BASE + 0x17
OFF_COMPLEMENT = HEADER_BASE + 0x1C
OFF_CHECKSUM = HEADER_BASE + 0x1E

FILL_BYTE = 0xFF


class RomError(Exception):
    """Anything that means the build must stop rather than guess."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cpu_to_pc(bank: int, address: int) -> int:
    """HiROM address conversion: pc = ((bank & 0x3F) << 16) | address."""
    if not 0x00 <= bank <= 0xFF:
        raise RomError(f"bank out of range: {bank:#04x}")
    if not 0x0000 <= address <= 0xFFFF:
        raise RomError(f"address out of range: {address:#06x}")
    return ((bank & 0x3F) << 16) | address


def mirrored_sum(data: bytes) -> int:
    """SNES checksum sum, with the odd tail mirrored up to the next power of two.

    A 3 MB ROM is summed as (first 2 MB) + 2 x (last 1 MB); a 4 MB ROM is a
    plain sum. Verified against the clean ROM's stored checksum 0x93B3.
    """
    size = len(data)
    if size == 0:
        raise RomError("cannot checksum an empty ROM")
    if size & (size - 1) == 0:
        return sum(data) & 0xFFFF

    power = 1 << (size.bit_length() - 1)
    head = sum(data[:power])
    tail_len = size - power
    tail = sum(data[power:])
    # Mirror the remainder until it fills a block the size of the tail's own
    # next-lower power of two boundary, i.e. repeat it to reach `power` bytes.
    if power % tail_len:
        raise RomError(f"unsupported ROM size for mirroring: {size}")
    return (head + tail * (power // tail_len)) & 0xFFFF


def compute_checksum(data: bytes) -> int:
    """Checksum with the four header checksum bytes neutralised.

    The stored complement and checksum always sum to 0x1FE, so the result does
    not depend on what is currently in those bytes.
    """
    buf = bytearray(data)
    buf[OFF_COMPLEMENT : OFF_COMPLEMENT + 4] = b"\x00\x00\x00\x00"
    return (mirrored_sum(bytes(buf)) + 0x1FE) & 0xFFFF


@dataclass
class Rom:
    """A mutable ROM image under construction."""

    data: bytearray

    @classmethod
    def load_clean(cls, path: Path) -> "Rom":
        raw = path.read_bytes()
        if len(raw) != CLEAN_SIZE:
            raise RomError(
                f"clean ROM must be {CLEAN_SIZE} bytes, got {len(raw)}: {path}"
            )
        digest = sha256(raw)
        if digest != CLEAN_SHA256:
            raise RomError(
                f"clean ROM sha256 mismatch\n  expected {CLEAN_SHA256}\n  got      {digest}"
            )
        if raw[OFF_MAP_MODE] != 0x31:
            raise RomError(
                f"expected HiROM+FastROM map mode 0x31, got {raw[OFF_MAP_MODE]:#04x}"
            )
        return cls(bytearray(raw))

    @property
    def size(self) -> int:
        return len(self.data)

    def expand(self, size: int = EXPANDED_SIZE) -> None:
        """Grow the image to `size`, filling new space with a constant byte."""
        if size < self.size:
            raise RomError(f"cannot shrink ROM from {self.size} to {size}")
        if size == self.size:
            return
        if size & (size - 1):
            raise RomError(f"expanded size must be a power of two, got {size}")
        self.data.extend(bytes([FILL_BYTE]) * (size - self.size))
        # ROM size byte is log2(kilobytes); the clean ROM already declares 4 MB.
        declared = 1 << self.data[OFF_ROM_SIZE]
        if declared * 1024 < size:
            self.data[OFF_ROM_SIZE] = (size // 1024).bit_length() - 1

    def write_at(self, pc: int, payload: bytes) -> None:
        end = pc + len(payload)
        if pc < 0 or end > self.size:
            raise RomError(f"write [{pc:#08x},{end:#08x}) is outside the ROM")
        self.data[pc:end] = payload

    def read_at(self, pc: int, length: int) -> bytes:
        end = pc + length
        if pc < 0 or end > self.size:
            raise RomError(f"read [{pc:#08x},{end:#08x}) is outside the ROM")
        return bytes(self.data[pc:end])

    def fix_checksum(self) -> int:
        """Recompute and store checksum + complement. Returns the checksum."""
        checksum = compute_checksum(bytes(self.data))
        complement = checksum ^ 0xFFFF
        self.data[OFF_COMPLEMENT] = complement & 0xFF
        self.data[OFF_COMPLEMENT + 1] = complement >> 8
        self.data[OFF_CHECKSUM] = checksum & 0xFF
        self.data[OFF_CHECKSUM + 1] = checksum >> 8
        return checksum

    def stored_checksum(self) -> int:
        return self.data[OFF_CHECKSUM] | (self.data[OFF_CHECKSUM + 1] << 8)

    def to_bytes(self) -> bytes:
        return bytes(self.data)

    def save(self, path: Path) -> str:
        payload = self.to_bytes()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return sha256(payload)
