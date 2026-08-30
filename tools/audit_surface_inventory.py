#!/usr/bin/env python3
"""Audit every declared text surface against explicit verification status."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "data" / "config" / "text-surfaces.json"
STATUS = ROOT / "data" / "config" / "surface-status.json"
REPORT = ROOT / "build" / "reports" / "surface-inventory.json"
ALLOWED = {
    "build_verified", "runtime_partial", "runtime_verified",
    "pending_runtime", "exception", "unused_verified", "unknown",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true",
                        help="fail unless every surface is runtime-verified or an exception")
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args()
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    status_doc = json.loads(STATUS.read_text(encoding="utf-8"))
    surfaces = {item["id"]: item for item in inventory["surfaces"]}
    statuses = status_doc["statuses"]
    missing = sorted(set(surfaces) - set(statuses))
    extra = sorted(set(statuses) - set(surfaces))
    invalid = sorted(
        surface for surface, item in statuses.items()
        if item.get("state") not in ALLOWED or not str(item.get("evidence", "")).strip()
    )
    if missing or extra or invalid:
        raise SystemExit(
            f"surface status contract failed: missing={missing} extra={extra} invalid={invalid}"
        )
    counts = Counter(item["state"] for item in statuses.values())
    blockers = sorted(
        surface for surface, item in statuses.items()
        if item["state"] not in {"runtime_verified", "exception", "unused_verified"}
    )
    unknown = sorted(
        surface for surface, item in statuses.items() if item["state"] == "unknown"
    )
    report = {
        "surfaces": len(surfaces),
        "counts": dict(sorted(counts.items())),
        "release_ready": not blockers,
        "blockers": blockers,
        "unknown": unknown,
        "items": [
            {"id": surface, "source": surfaces[surface]["source"], **statuses[surface]}
            for surface in surfaces
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(surfaces)} surfaces: " + ", ".join(
        f"{name}={count}" for name, count in sorted(counts.items())))
    print(f"release blockers={len(blockers)} unknown={len(unknown)}")
    if args.release and blockers:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
