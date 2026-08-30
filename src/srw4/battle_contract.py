"""Audited static contract of the battle-safe renderer milestone."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


class BattleContractError(ValueError):
    pass


def _hex_bytes(value: str) -> bytes:
    return bytes.fromhex(value)


@dataclass(frozen=True)
class BattleHook:
    id: str
    pc: int
    clean: bytes
    proven: bytes


@dataclass(frozen=True)
class BattleAdapter:
    id: str
    pc: int
    cpu: int
    bytes: int
    dependency_cpu: int
    sha256: str


@dataclass(frozen=True)
class BattleContract:
    source_revision: str
    hooks: tuple[BattleHook, ...]
    renderer_pc: int
    renderer_bytes: int
    renderer_sha256: str
    renderer_inputs: tuple[tuple[str, int], ...]
    adapters: tuple[BattleAdapter, ...]
    private_wram: tuple[tuple[str, int, int], ...]
    invariants: tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> "BattleContract":
        document = json.loads(path.read_text())
        if document.get("schema_version") != 1:
            raise BattleContractError("unsupported battle contract schema")
        hooks = tuple(
            BattleHook(row["id"], int(row["pc"], 16), _hex_bytes(row["clean"]),
                       _hex_bytes(row["proven"]))
            for row in document["hooks"]
        )
        renderer = document["renderer"]
        renderer_inputs = tuple(
            (name, int(value, 16)) for name, value in renderer["inputs"].items()
        )
        adapters = tuple(
            BattleAdapter(
                row["id"], int(row["pc"], 16), int(row["cpu"], 16),
                int(row["bytes"]), int(row["dependency_cpu"], 16), row["sha256"],
            )
            for row in document["adapters"]
        )
        private_wram = tuple(
            (name, int(bounds[0], 16), int(bounds[1], 16))
            for name, bounds in document["private_wram"].items()
        )
        result = cls(
            document["source_revision"], hooks, int(renderer["pc"], 16),
            int(renderer["bytes"]), renderer["sha256"], renderer_inputs,
            adapters, private_wram,
            tuple(document["invariants"]),
        )
        result.validate_structure()
        return result

    def validate_structure(self) -> None:
        if len({hook.id for hook in self.hooks}) != len(self.hooks):
            raise BattleContractError("battle hook id is duplicated")
        if {adapter.id for adapter in self.adapters} != {"stock_fb", "width", "dispatch"}:
            raise BattleContractError("battle adapter set must be stock_fb + width + dispatch")
        required_inputs = {
            "source_base", "advance", "lock", "mark_dx", "mark_y", "mark_size",
            "base_ink", "raised_y", "shorthand_first", "shorthand_second",
            "shorthand_third", "upper_overlay", "upper_dx", "upper_dy", "upper_size",
        }
        if {name for name, _ in self.renderer_inputs} != required_inputs:
            raise BattleContractError("battle renderer input set changed")
        ordered = sorted(self.private_wram, key=lambda row: row[1])
        for name, start, end in ordered:
            if not 0x7E0000 <= start < end <= 0x7F0000:
                raise BattleContractError(f"{name} is outside bank $7E")
        for left, right in zip(ordered, ordered[1:]):
            if left[2] > right[1]:
                raise BattleContractError(f"{left[0]} overlaps {right[0]}")
        if not self.invariants:
            raise BattleContractError("battle contract has no documented invariants")

    def verify_clean(self, image: bytes) -> None:
        for hook in self.hooks:
            actual = image[hook.pc:hook.pc + len(hook.clean)]
            if actual != hook.clean:
                raise BattleContractError(
                    f"clean {hook.id} changed: expected {hook.clean.hex(' ')}, got {actual.hex(' ')}"
                )

    def verify_proven(self, image: bytes) -> None:
        for hook in self.hooks:
            actual = image[hook.pc:hook.pc + len(hook.proven)]
            if actual != hook.proven:
                raise BattleContractError(
                    f"proven {hook.id} changed: expected {hook.proven.hex(' ')}, got {actual.hex(' ')}"
                )
        renderer = image[self.renderer_pc:self.renderer_pc + self.renderer_bytes]
        digest = hashlib.sha256(renderer).hexdigest()
        if digest != self.renderer_sha256:
            raise BattleContractError(
                f"battle renderer changed: expected {self.renderer_sha256}, got {digest}"
            )
        for adapter in self.adapters:
            payload = image[adapter.pc:adapter.pc + adapter.bytes]
            digest = hashlib.sha256(payload).hexdigest()
            if digest != adapter.sha256:
                raise BattleContractError(
                    f"battle {adapter.id} changed: expected {adapter.sha256}, got {digest}"
                )
