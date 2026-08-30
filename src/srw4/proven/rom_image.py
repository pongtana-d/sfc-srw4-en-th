"""ROM contract and safe byte-level operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path


def cpu_to_pc(cpu: int) -> int:
    bank = (cpu >> 16) & 0xFF
    address = cpu & 0xFFFF
    if bank < 0xC0:
        raise ValueError(f"expected a HiROM CPU address in $C0-$FF, got ${bank:02X}:{address:04X}")
    return ((bank & 0x3F) << 16) | address


def pc_to_cpu(pc: int) -> int:
    if not 0 <= pc < 0x400000:
        raise ValueError(f"PC address is outside a 4 MiB HiROM image: {pc:#x}")
    return ((0xC0 + (pc >> 16)) << 16) | (pc & 0xFFFF)


@dataclass(frozen=True)
class RomContract:
    size: int
    sha256: str


@dataclass
class RomImage:
    data: bytearray
    claims: list[tuple[int, int, str]] = field(default_factory=list)

    @classmethod
    def read(cls, path: Path) -> "RomImage":
        return cls(bytearray(path.read_bytes()))

    @property
    def digest(self) -> str:
        return sha256(self.data).hexdigest()

    def verify(self, contract: RomContract) -> None:
        if len(self.data) != contract.size:
            raise ValueError(f"ROM size mismatch: got {len(self.data)}, expected {contract.size}")
        if self.digest != contract.sha256:
            raise ValueError(f"ROM SHA-256 mismatch: got {self.digest}, expected {contract.sha256}")

    def expand(self, size: int, fill: int = 0xFF) -> None:
        if not 0 <= fill <= 0xFF:
            raise ValueError(f"invalid expansion fill byte: {fill}")
        if size < len(self.data):
            raise ValueError(f"cannot shrink ROM from {len(self.data)} to {size} bytes")
        self.data.extend(bytes((fill,)) * (size - len(self.data)))

    def claim(self, start: int, end: int, owner: str) -> None:
        if not 0 <= start < end <= len(self.data):
            raise ValueError(f"claim outside ROM: {owner} {start:#x}-{end:#x}")
        for old_start, old_end, old_owner in self.claims:
            if start < old_end and old_start < end:
                raise ValueError(
                    f"overlapping ROM claims: {owner} {start:#x}-{end:#x} and "
                    f"{old_owner} {old_start:#x}-{old_end:#x}"
                )
        self.claims.append((start, end, owner))

    def patch(self, offset: int, expected: bytes, replacement: bytes, owner: str) -> None:
        if len(expected) != len(replacement):
            raise ValueError(f"patch length mismatch for {owner}")
        end = offset + len(expected)
        actual = bytes(self.data[offset:end])
        if actual != expected:
            raise ValueError(
                f"source-byte mismatch for {owner} at {offset:#x}: "
                f"got {actual.hex(' ')}, expected {expected.hex(' ')}"
            )
        self.claim(offset, end, owner)
        self.data[offset:end] = replacement

    def place(self, offset: int, payload: bytes, owner: str, expected_fill: int = 0xFF) -> None:
        end = offset + len(payload)
        actual = bytes(self.data[offset:end])
        expected = bytes((expected_fill,)) * len(payload)
        if actual != expected:
            raise ValueError(f"allocation for {owner} is not filled with {expected_fill:#04x}")
        self.claim(offset, end, owner)
        self.data[offset:end] = payload

    def repair_checksum(self, header: int = 0xFFC0) -> tuple[int, int]:
        if header + 0x20 > len(self.data):
            raise ValueError("ROM is too small to contain the HiROM header")
        self.data[header + 0x1C : header + 0x20] = b"\xFF\xFF\x00\x00"
        checksum = sum(self.data) & 0xFFFF
        complement = checksum ^ 0xFFFF
        self.data[header + 0x1C : header + 0x1E] = complement.to_bytes(2, "little")
        self.data[header + 0x1E : header + 0x20] = checksum.to_bytes(2, "little")
        return checksum, complement

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.data)
