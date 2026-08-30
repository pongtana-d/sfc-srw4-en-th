"""Allocation map for the expanded banks.

The map itself lives in `data/config/allocation-map.json`. This module loads
it, hands out space inside a named region, and refuses anything that would
overlap an earlier allocation. Every allocation is recorded so the build report
can say exactly what went where.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .rom import RomError


def _parse_int(value) -> int:
    return int(value, 0) if isinstance(value, str) else int(value)


@dataclass(frozen=True)
class Region:
    id: str
    banks: str
    start: int
    end: int
    purpose: str

    @property
    def size(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class Allocation:
    region: str
    owner: str
    start: int
    end: int

    @property
    def size(self) -> int:
        return self.end - self.start


@dataclass
class AllocationMap:
    regions: dict[str, Region]
    fill_byte: int
    allocations: list[Allocation] = field(default_factory=list)
    _cursors: dict[str, int] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "AllocationMap":
        doc = json.loads(path.read_text())
        regions: dict[str, Region] = {}
        ordered: list[Region] = []
        for entry in doc["regions"]:
            region = Region(
                id=entry["id"],
                banks=entry["banks"],
                start=_parse_int(entry["start"]),
                end=_parse_int(entry["end"]),
                purpose=entry["purpose"],
            )
            if region.end <= region.start:
                raise RomError(f"region {region.id} is empty or inverted")
            if region.id in regions:
                raise RomError(f"duplicate region id: {region.id}")
            regions[region.id] = region
            ordered.append(region)

        for earlier, later in zip(ordered, ordered[1:]):
            if later.start < earlier.end:
                raise RomError(
                    f"regions {earlier.id} and {later.id} overlap at {later.start:#08x}"
                )

        space = doc["expanded_space"]
        lo, hi = _parse_int(space["start"]), _parse_int(space["end"])
        for region in ordered:
            if region.start < lo or region.end > hi:
                raise RomError(f"region {region.id} escapes the expanded space")

        return cls(
            regions=regions,
            fill_byte=_parse_int(doc["fill_byte"]),
            _cursors={region.id: region.start for region in ordered},
        )

    def allocate(self, region_id: str, owner: str, size: int, align: int = 1) -> int:
        """Reserve `size` bytes in a region and return the PC offset."""
        region = self.regions.get(region_id)
        if region is None:
            raise RomError(f"unknown region: {region_id}")
        if size <= 0:
            raise RomError(f"{owner}: allocation size must be positive, got {size}")

        start = self._cursors[region_id]
        if align > 1:
            start = (start + align - 1) & ~(align - 1)
        end = start + size
        if end > region.end:
            raise RomError(
                f"region {region_id} is full: {owner} needs {size} bytes, "
                f"{region.end - start} left"
            )
        self._cursors[region_id] = end
        self.allocations.append(Allocation(region_id, owner, start, end))
        return start

    def used(self, region_id: str) -> int:
        return self._cursors[region_id] - self.regions[region_id].start

    def report(self) -> dict:
        return {
            "regions": [
                {
                    "id": r.id,
                    "banks": r.banks,
                    "start": f"{r.start:#08x}",
                    "end": f"{r.end:#08x}",
                    "bytes": r.size,
                    "used": self.used(r.id),
                    "free": r.size - self.used(r.id),
                    "purpose": r.purpose,
                }
                for r in self.regions.values()
            ],
            "allocations": [
                {
                    "region": a.region,
                    "owner": a.owner,
                    "start": f"{a.start:#08x}",
                    "end": f"{a.end:#08x}",
                    "bytes": a.size,
                }
                for a in self.allocations
            ],
        }
