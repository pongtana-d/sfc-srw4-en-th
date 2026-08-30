"""Deterministic allocation inside declared expanded-ROM regions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path



def parse_address(value: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise ValueError(f"address must use 0x notation: {value!r}")
    return int(value, 16)


@dataclass(frozen=True)
class Region:
    id: str
    start: int
    end: int


@dataclass
class Allocation:
    owner: str
    region: str
    start: int
    end: int


@dataclass
class Allocator:
    regions: dict[str, Region]
    allocations: list[Allocation] = field(default_factory=list)
    _cursors: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path) -> "Allocator":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("schema_version") != 1:
            raise ValueError("unsupported memory-map schema")
        rom_size = int(raw["rom_size"])
        regions: dict[str, Region] = {}
        ordered: list[Region] = []
        for item in raw["regions"]:
            region = Region(
                id=str(item["id"]),
                start=parse_address(item["start"]),
                end=parse_address(item["end"]),
            )
            if region.id in regions:
                raise ValueError(f"duplicate memory region: {region.id}")
            if not 0 <= region.start < region.end <= rom_size:
                raise ValueError(f"invalid memory region: {region.id}")
            for previous in ordered:
                if region.start < previous.end and previous.start < region.end:
                    raise ValueError(f"overlapping memory regions: {previous.id} and {region.id}")
            regions[region.id] = region
            ordered.append(region)
        return cls(regions=regions)

    def reserve(self, region_id: str, size: int, owner: str, alignment: int = 1) -> Allocation:
        if size <= 0:
            raise ValueError(f"allocation size must be positive for {owner}")
        if alignment <= 0 or alignment & (alignment - 1):
            raise ValueError(f"alignment must be a power of two for {owner}")
        region = self.regions[region_id]
        cursor = self._cursors.get(region_id, region.start)
        start = (cursor + alignment - 1) & ~(alignment - 1)
        end = start + size
        if end > region.end:
            raise ValueError(
                f"region {region_id} overflow for {owner}: need {size} bytes at {start:#x}"
            )
        result = Allocation(owner=owner, region=region_id, start=start, end=end)
        self.allocations.append(result)
        self._cursors[region_id] = end
        return result

    def next_address(self, region_id: str) -> int:
        """Return the next unallocated address in a declared region."""
        region = self.regions[region_id]
        return self._cursors.get(region_id, region.start)

    def report(self) -> list[dict[str, int | str]]:
        return [
            {
                "owner": item.owner,
                "region": item.region,
                "start": f"0x{item.start:06X}",
                "end": f"0x{item.end:06X}",
                "bytes": item.end - item.start,
            }
            for item in self.allocations
        ]
