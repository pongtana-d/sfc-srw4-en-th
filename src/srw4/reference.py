"""Compare a translated reference ROM with the verified clean image.

The output deliberately separates facts (byte differences and known hooks)
from heuristics (possible long calls and 24-bit pointers).  A translated ROM
is useful evidence, but it is not source code and must not silently become a
build input.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from .rom import CLEAN_SIZE, EXPANDED_SIZE, compute_checksum

FILL_BYTE = 0xFF
HEADER_BASE = 0xFFC0


class ReferenceError(ValueError):
    """The two images cannot be compared safely."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex(data: bytes) -> str:
    return data.hex(" ").upper()


def _pc(pc: int) -> str:
    return f"0x{pc:06X}"


def _cpu(pc: int) -> str:
    return f"${0xC0 + (pc >> 16):02X}:{pc & 0xFFFF:04X}"


def contiguous_ranges(offsets: Iterable[int]) -> list[tuple[int, int]]:
    """Collapse sorted offsets into start-inclusive, end-exclusive ranges."""
    ranges: list[list[int]] = []
    for offset in offsets:
        if not ranges or offset != ranges[-1][1]:
            ranges.append([offset, offset + 1])
        else:
            ranges[-1][1] += 1
    return [(start, end) for start, end in ranges]


def _changed_count(clean: bytes, reference: bytes, start: int, end: int) -> int:
    end = min(end, len(clean), len(reference))
    if start >= end:
        return 0
    return sum(a != b for a, b in zip(clean[start:end], reference[start:end]))


def _decode_transfer(raw: bytes) -> dict | None:
    if len(raw) < 4 or raw[0] not in (0x22, 0x5C):
        return None
    target = raw[1] | raw[2] << 8 | raw[3] << 16
    return {
        "opcode": "JSL" if raw[0] == 0x22 else "JML",
        "target": f"${target >> 16:02X}:{target & 0xFFFF:04X}",
        "target_pc": _pc(((target >> 16) & 0x3F) << 16 | (target & 0xFFFF)),
    }


def _known_hooks(clean: bytes, reference: bytes, document: dict) -> list[dict]:
    results = []
    for hook in document.get("hooks", []):
        pc = int(hook["pc"], 16)
        expected = bytes.fromhex(hook["expected"])
        observed = reference[pc : pc + len(expected)]
        clean_observed = clean[pc : pc + len(expected)]
        if clean_observed != expected:
            raise ReferenceError(
                f"clean bytes at {hook['pc']} do not match hook {hook['id']}"
            )

        classification = "unchanged"
        if observed != expected:
            classification = "novel_replacement"
            for field in ("active_replacement", "legacy_replacement"):
                replacement = hook.get(field)
                if replacement and observed == bytes.fromhex(replacement):
                    classification = f"matches_{field}"
                    break

        item = {
            "id": hook["id"],
            "pc": hook["pc"],
            "cpu": hook["cpu"],
            "classification": classification,
            "expected": _hex(expected),
            "observed": _hex(observed),
        }
        transfer = _decode_transfer(observed)
        if transfer:
            item["control_transfer"] = transfer
        results.append(item)
    return results


def _long_transfer_candidates(clean: bytes, reference: bytes) -> list[dict]:
    """Find changed JSL/JML-looking sequences that target expanded banks.

    This is intentionally labelled a candidate scan: data can resemble 65816
    instructions.  A candidate becomes a hook only after disassembly or an
    emulator trace confirms that the CPU executes it.
    """
    results = []
    for pc in range(min(len(clean), len(reference)) - 3):
        raw = reference[pc : pc + 4]
        if raw[0] not in (0x22, 0x5C) or not 0xF0 <= raw[3] <= 0xFF:
            continue
        if clean[pc : pc + 4] == raw:
            continue
        target_pc = ((raw[3] & 0x3F) << 16) | raw[2] << 8 | raw[1]
        if target_pc >= len(reference):
            continue
        # Reject pointers into an untouched FF-only area.
        if set(reference[target_pc : target_pc + 8]) <= {FILL_BYTE}:
            continue
        results.append(
            {
                "pc": _pc(pc),
                "cpu": _cpu(pc),
                "bytes": _hex(raw),
                **(_decode_transfer(raw) or {}),
            }
        )
    return results


def _pointer_candidates(clean: bytes, reference: bytes, limit: int) -> dict:
    """Find changed little-endian 24-bit values that point into expansion.

    There is no reliable way to distinguish pointers from arbitrary data by
    bytes alone.  Keep the total and per-bank counts, but cap examples so the
    report stays reviewable.
    """
    total = 0
    by_bank: dict[str, int] = {}
    examples = []
    overlap = min(len(clean), len(reference))
    for bank_at in range(2, overlap):
        bank = reference[bank_at]
        if bank == clean[bank_at] or not 0xF0 <= bank <= 0xFF:
            continue
        target_pc = ((bank & 0x3F) << 16) | reference[bank_at - 1] << 8 | reference[bank_at - 2]
        if not CLEAN_SIZE <= target_pc < len(reference):
            continue
        if set(reference[target_pc : target_pc + 8]) <= {FILL_BYTE}:
            continue
        source_pc = bank_at - 2
        source_bank = f"${0xC0 + (source_pc >> 16):02X}"
        by_bank[source_bank] = by_bank.get(source_bank, 0) + 1
        total += 1
        if len(examples) < limit:
            examples.append(
                {
                    "source_pc": _pc(source_pc),
                    "source_cpu": _cpu(source_pc),
                    "bytes": _hex(reference[source_pc : source_pc + 3]),
                    "target_pc": _pc(target_pc),
                    "target_cpu": f"${bank:02X}:{target_pc & 0xFFFF:04X}",
                }
            )
    return {
        "method": "heuristic: changed LE24 value whose bank became $F0-$FF and whose target is non-FF",
        "total": total,
        "examples_limit": limit,
        "examples_truncated": total > limit,
        "by_source_bank": dict(sorted(by_bank.items())),
        "examples": examples,
    }


def _region_changes(clean: bytes, reference: bytes, rom_map: dict, script: dict) -> dict:
    pointer_tables = []
    for region in rom_map.get("pointer_tables", []):
        start, end = int(region["start"], 16), int(region["end"], 16)
        pointer_tables.append(
            {
                "id": region["id"],
                "start": region["start"],
                "end": region["end"],
                "changed_bytes": _changed_count(clean, reference, start, end),
            }
        )

    string_pools = []
    for region in rom_map.get("legacy_string_pools", []):
        start, end = int(region["start"], 16), int(region["end"], 16)
        string_pools.append(
            {
                "id": region["id"],
                "start": region["start"],
                "end": region["end"],
                "changed_bytes": _changed_count(clean, reference, start, end),
            }
        )

    blocks = []
    for block in script.get("summary", {}).get("blocks", []):
        if block.get("kind") == "unused":
            continue
        start = int(block["pc"], 16)
        end = (start & ~0xFFFF) + int(block["extent"], 16)
        changed = _changed_count(clean, reference, start, end)
        if changed:
            blocks.append(
                {
                    "slot": block["slot"],
                    "start": _pc(start),
                    "end": _pc(end),
                    "changed_bytes": changed,
                }
            )
    return {
        "pointer_tables": pointer_tables,
        "known_string_pools": string_pools,
        "story_blocks": {
            "changed_blocks": len(blocks),
            "changed_bytes": sum(block["changed_bytes"] for block in blocks),
            "blocks": blocks,
        },
    }


def _expansion_payload(reference: bytes) -> dict:
    banks = []
    total = 0
    for bank in range(0xF0, 0x100):
        start = (bank - 0xC0) << 16
        block = reference[start : start + 0x10000]
        occupied = [i for i, value in enumerate(block) if value != FILL_BYTE]
        count = len(occupied)
        total += count
        banks.append(
            {
                "bank": f"${bank:02X}",
                "non_ff_bytes": count,
                "first_non_ff": f"${occupied[0]:04X}" if occupied else None,
                "last_non_ff": f"${occupied[-1]:04X}" if occupied else None,
                "sha256": _sha256(block),
            }
        )
    return {
        "method": "non-FF occupancy estimate; FF may also be legitimate payload data",
        "bytes": len(reference) - CLEAN_SIZE,
        "non_ff_bytes": total,
        "non_ff_percent": round(total * 100 / max(1, len(reference) - CLEAN_SIZE), 2),
        "banks": banks,
    }


def analyze_reference(
    clean: bytes,
    reference: bytes,
    *,
    hooks: dict,
    rom_map: dict,
    script: dict,
    pointer_example_limit: int = 128,
) -> dict:
    """Return a deterministic, JSON-serialisable reference-ROM report."""
    if len(clean) != CLEAN_SIZE:
        raise ReferenceError(f"clean ROM must be {CLEAN_SIZE} bytes, got {len(clean)}")
    if len(reference) != EXPANDED_SIZE:
        raise ReferenceError(
            f"reference ROM must be {EXPANDED_SIZE} bytes, got {len(reference)}"
        )
    if pointer_example_limit < 0:
        raise ReferenceError("pointer example limit cannot be negative")

    changed = [pc for pc, pair in enumerate(zip(clean, reference)) if pair[0] != pair[1]]
    runs = contiguous_ranges(changed)
    changed_by_bank = []
    for start in range(0, len(clean), 0x10000):
        count = _changed_count(clean, reference, start, start + 0x10000)
        if count:
            changed_by_bank.append(
                {"bank": f"${0xC0 + (start >> 16):02X}", "changed_bytes": count}
            )

    stored_complement = int.from_bytes(reference[0xFFDC:0xFFDE], "little")
    stored_checksum = int.from_bytes(reference[0xFFDE:0xFFE0], "little")
    title = reference[HEADER_BASE : HEADER_BASE + 21].decode("ascii", "replace").rstrip()
    known_hooks = _known_hooks(clean, reference, hooks)
    return {
        "schema": "srw4-reference-rom-report/1",
        "warning": "Reference evidence only; never use this ROM as a build input.",
        "input": {
            "clean": {"bytes": len(clean), "sha256": _sha256(clean)},
            "reference": {
                "bytes": len(reference),
                "sha256": _sha256(reference),
                "title": title,
                "map_mode": f"0x{reference[0xFFD5]:02X}",
                "stored_checksum": f"0x{stored_checksum:04X}",
                "stored_complement": f"0x{stored_complement:04X}",
                "checksum_valid": compute_checksum(reference) == stored_checksum
                and stored_checksum ^ stored_complement == 0xFFFF,
            },
        },
        "stock_diff": {
            "changed_bytes": len(changed),
            "changed_runs": len(runs),
            "changed_by_bank": changed_by_bank,
            "largest_runs": [
                {"start": _pc(start), "end": _pc(end), "bytes": end - start}
                for start, end in sorted(runs, key=lambda item: (item[1] - item[0], -item[0]), reverse=True)[:32]
            ],
        },
        "hooks": {
            "known": known_hooks,
            "known_changed": sum(hook["classification"] != "unchanged" for hook in known_hooks),
            "long_transfer_candidates": _long_transfer_candidates(clean, reference),
        },
        "pointers": _pointer_candidates(clean, reference, pointer_example_limit),
        "script_and_catalog_regions": _region_changes(clean, reference, rom_map, script),
        "expansion_payload": _expansion_payload(reference),
    }
