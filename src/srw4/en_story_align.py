"""Align Thai/JP story identities to the locked English pointer graph.

This is intentionally structural.  It never uses translated prose, byte
offsets, or an inferred EN record boundary to decide a target.  A source
message with a direct JP pointer is matched to the EN pointer at the same
``(master slot, pointer index)``.  Alias topology then grades that decision.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Iterable

from .rom import RomError
from .script import cpu_to_pc, read_master_table


def _document_hash(document: object) -> str:
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _pointer_aliases(rom: bytes, blocks: Iterable[dict]) -> dict[tuple[int, int], tuple[int, ...]]:
    """Return the within-block alias group for every pointer-table row."""
    master = read_master_table(rom)
    result: dict[tuple[int, int], tuple[int, ...]] = {}
    for block in blocks:
        if block.get("kind") == "unused":
            continue
        slot = int(block["slot"])
        pointers = int(block["pointers"])
        bank, start = master[slot]
        if (bank, start) == (0, 0):
            raise RomError(f"story slot {slot} is unexpectedly null")
        base = cpu_to_pc(bank, start)
        values = [rom[base + index * 2] | rom[base + index * 2 + 1] << 8 for index in range(pointers)]
        by_value: dict[int, list[int]] = defaultdict(list)
        for index, value in enumerate(values):
            by_value[value].append(index)
        for index, value in enumerate(values):
            result[(slot, index)] = tuple(by_value[value])
    return result


def _source_rows(messages: Iterable[dict]) -> dict[tuple[int, int], dict]:
    """Index each direct source pointer row, rejecting ambiguous ownership."""
    rows: dict[tuple[int, int], dict] = {}
    for message in messages:
        block = int(message["block"])
        for pointer_index in message.get("table_slots", []):
            key = (block, int(pointer_index))
            if key in rows:
                raise RomError(f"source pointer row {block}:{pointer_index} belongs to two messages")
            rows[key] = message
    return rows


def _target(record: dict, rows: list[tuple[int, int]]) -> dict[str, object]:
    return {
        "record": f"{int(record['slot']):02d}_{str(record['address']).removeprefix('$')}",
        "bank": record["bank"],
        "address": record["address"],
        "pointer_rows": [f"{slot:02d}:{index:03d}" for slot, index in rows],
    }


def _dispatch_records(data: bytes, prefix: bytes) -> list[tuple[int, list[tuple[int, int]]]]:
    """Find fixed dispatch records, retaining each pointer field position."""
    records = []
    cursor = 0
    while True:
        start = data.find(prefix, cursor)
        if start < 0:
            return records
        count_at = start + len(prefix)
        if count_at >= len(data):
            return records
        count = data[count_at]
        first = count_at + 1
        if first + count * 2 > len(data):
            return records
        records.append(
            (
                start,
                [
                    (at, data[at] | data[at + 1] << 8)
                    for at in range(first, first + count * 2, 2)
                ],
            )
        )
        cursor = first + count * 2


def _dispatch_targets(
    jp_rom: bytes,
    en_rom: bytes,
    jp_source: dict,
    en_source: dict,
) -> tuple[dict[str, list[dict[str, object]]], dict[str, int]]:
    """Resolve JP ``record_refs`` through ordinally identical EN dispatch data."""
    blocks = {int(block["slot"]): block for block in jp_source["summary"]["blocks"]}
    messages_by_slot: dict[int, list[dict]] = defaultdict(list)
    for message in jp_source["messages"]:
        messages_by_slot[int(message["block"])].append(message)
    jp_master = read_master_table(jp_rom)
    en_master = read_master_table(en_rom)
    en_records = en_source["records"]
    en_blocks = {int(block["slot"]): block for block in en_source["blocks"]}
    target_owner: dict[str, str] = {}
    result: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    report = {"blocks": 0, "records": 0, "pointer_fields": 0, "source_messages": 0}

    for slot in range(20, 27):
        block = blocks[slot]
        pointers = int(block["pointers"])
        jp_bank, jp_start = jp_master[slot]
        en_bank, en_start = en_master[slot]
        jp_pc = cpu_to_pc(jp_bank, jp_start)
        en_pc = cpu_to_pc(en_bank, en_start)
        jp_dispatch_start = jp_start + pointers * 2
        jp_data = jp_rom[jp_pc + pointers * 2 : jp_pc + pointers * 2 + int(block["record_bytes"])]
        # The EN fixed records are longer than JP.  Their own prefix and exact
        # ordinal pointer shape, not a JP byte length, establish the EN range.
        en_data = en_rom[en_pc + pointers * 2 : en_pc + 0x10000 - en_start]
        jp_dispatch = _dispatch_records(jp_data, b"\xFC\x01\xFA")
        en_all = _dispatch_records(en_data, b"\xFC\x01\xAB\x43\xFA")
        en_dispatch = en_all[: len(jp_dispatch)]
        if len(en_dispatch) != len(jp_dispatch):
            raise RomError(f"dispatch slot {slot}: EN record count is shorter than JP")

        by_offset = {int(message["offset"], 16): message for message in messages_by_slot[slot]}
        by_position: dict[int, dict] = {}
        for message in messages_by_slot[slot]:
            for encoded_ref in message.get("record_refs", []):
                relative = int(encoded_ref, 16) - jp_dispatch_start
                if not 0 <= relative <= len(jp_data) - 2:
                    raise RomError(f"dispatch slot {slot}: record ref {encoded_ref} escapes JP dispatch")
                existing = by_position.setdefault(relative, message)
                if existing["id"] != message["id"]:
                    raise RomError(f"dispatch slot {slot}: JP record ref {encoded_ref} is ambiguous")

        for record_index, ((_, jp_fields), (_, en_fields)) in enumerate(zip(jp_dispatch, en_dispatch)):
            if len(jp_fields) != len(en_fields):
                raise RomError(f"dispatch slot {slot}, record {record_index}: JP/EN pointer shapes differ")
            for entry_index, ((jp_at, jp_target), (_, en_target)) in enumerate(zip(jp_fields, en_fields)):
                message = by_offset.get(jp_target) or by_position.get(jp_at)
                if message is None:
                    continue
                identity = f"{slot:02d}_{en_target:04X}"
                record = en_records.get(identity)
                if record is None:
                    en_block = en_blocks[slot]
                    interval_end = int(str(en_block["interval_end"]).removeprefix("$"), 16)
                    if not en_start <= en_target < interval_end:
                        raise RomError(
                            f"dispatch slot {slot}: EN target {identity} escapes its block interval"
                        )
                    record = {
                        "slot": slot,
                        "bank": f"${en_bank:02X}",
                        "address": f"${en_target:04X}",
                    }
                source_id = str(message["id"])
                existing_owner = target_owner.setdefault(identity, source_id)
                if existing_owner != source_id:
                    raise RomError(f"dispatch target {identity} has conflicting JP source identities")
                target = result[source_id].setdefault(
                    identity,
                    {
                        **_target(record, []),
                        "target_kind": "pointer-reachable" if identity in en_records else "dispatch-only",
                        "dispatch_references": [],
                    },
                )
                target["dispatch_references"].append(
                    {"slot": slot, "record_index": record_index, "entry_index": entry_index}
                )
                report["pointer_fields"] += 1
        report["blocks"] += 1
        report["records"] += len(jp_dispatch)

    report["source_messages"] = len(result)
    return {source_id: list(targets.values()) for source_id, targets in result.items()}, report


def align_story(
    jp_rom: bytes,
    en_rom: bytes,
    jp_source: dict,
    en_source: dict,
) -> dict[str, object]:
    """Create a conservative JP/Thai-to-EN mapping manifest.

    ``A`` means every direct pointer row retains its JP alias group.  ``B``
    preserves pointer identity but observes a changed EN alias group.  A split
    EN target or a source item with no direct pointer remains unresolved.
    """
    summary_blocks = jp_source["summary"]["blocks"]
    messages = jp_source["messages"]
    jp_aliases = _pointer_aliases(jp_rom, summary_blocks)
    en_aliases = _pointer_aliases(en_rom, summary_blocks)
    if set(jp_aliases) != set(en_aliases):
        raise RomError("JP and EN story pointer-row domains differ")

    source_by_row = _source_rows(messages)
    en_occurrences = {
        (int(row["slot"]), int(row["pointer_index"])): row
        for row in en_source["occurrences"]
    }
    if set(en_occurrences) != set(en_aliases):
        raise RomError("EN source occurrence rows do not match EN pointer topology")
    records = en_source["records"]
    dispatch_targets, dispatch_report = _dispatch_targets(jp_rom, en_rom, jp_source, en_source)

    topology_differences = [
        {
            "row": f"{slot:02d}:{index:03d}",
            "jp_alias_rows": [f"{slot:02d}:{item:03d}" for item in jp_aliases[(slot, index)]],
            "en_alias_rows": [f"{slot:02d}:{item:03d}" for item in en_aliases[(slot, index)]],
        }
        for slot, index in sorted(jp_aliases)
        if jp_aliases[(slot, index)] != en_aliases[(slot, index)]
    ]

    mappings: list[dict[str, object]] = []
    classification = Counter()
    reasons = Counter()
    for message in messages:
        source_id = str(message["id"])
        block = int(message["block"])
        pointer_rows = [(block, int(index)) for index in message.get("table_slots", [])]
        base = {
            "source_id": source_id,
            "source_block": block,
            "source_pointer_rows": [f"{slot:02d}:{index:03d}" for slot, index in pointer_rows],
            "source_record_refs": list(message.get("record_refs", [])),
        }
        if not pointer_rows:
            targets = dispatch_targets.get(source_id, [])
            if targets:
                mappings.append(
                    {
                        **base,
                        "confidence": "B",
                        "reason": "JP/EN fixed dispatch record ordinal and pointer shape match",
                        "targets": targets,
                    }
                )
                classification["B"] += 1
                reasons["dispatch_shape_match"] += 1
                continue
            reason = "no direct pointer row or proven fixed-dispatch target; requires control-flow audit"
            mappings.append({**base, "confidence": "UNRESOLVED", "reason": reason})
            classification["UNRESOLVED"] += 1
            reasons["no_direct_pointer_or_dispatch_target"] += 1
            continue

        record_ids = {en_occurrences[row]["record"] for row in pointer_rows}
        if None in record_ids:
            raise RomError(f"source {source_id} maps to an EN null pointer")
        if len(record_ids) != 1:
            candidates: dict[str, list[tuple[int, int]]] = defaultdict(list)
            for row in pointer_rows:
                candidates[str(en_occurrences[row]["record"])].append(row)
            mappings.append(
                {
                    **base,
                    "confidence": "B",
                    "reason": "same JP pointer identity splits across EN records; apply the same Thai source to each target",
                    "targets": [_target(records[item], rows) for item, rows in sorted(candidates.items())],
                }
            )
            classification["B"] += 1
            reasons["split_target"] += 1
            continue

        record_id = str(record_ids.pop())
        aliases_match = all(jp_aliases[row] == en_aliases[row] for row in pointer_rows)
        confidence = "A" if aliases_match else "B"
        reason = (
            "same pointer identity and alias topology"
            if aliases_match
            else "same pointer identity; EN alias topology differs (manual block 48 audit required)"
        )
        mappings.append({**base, "confidence": confidence, "reason": reason, "target": _target(records[record_id], pointer_rows)})
        classification[confidence] += 1
        reasons["direct_alias_match" if aliases_match else "alias_topology_changed"] += 1

    if len(mappings) != len(messages):
        raise RomError("mapping does not cover every source message")

    changed_by_slot = Counter(int(item["row"].split(":")[0]) for item in topology_differences)
    return {
        "schema": "srw4.jp-en-story-map.v1",
        "authority": "JP/Thai source identity plus JP/EN pointer and alias topology; no prose matching.",
        "inputs": {
            "jp_source_sha256": _document_hash(jp_source),
            "en_source_sha256": _document_hash(en_source),
        },
        "summary": {
            "source_messages": len(messages),
            "direct_pointer_messages": sum(1 for item in mappings if item["source_pointer_rows"]),
            "confidence": dict(sorted(classification.items())),
            "unresolved_reasons": dict(sorted(reasons.items())),
            "pointer_rows": len(jp_aliases),
            "alias_topology_match_rows": len(jp_aliases) - len(topology_differences),
            "alias_topology_different_rows": len(topology_differences),
            "alias_topology_differences_by_slot": {str(slot): count for slot, count in sorted(changed_by_slot.items())},
            "fixed_dispatch": dispatch_report,
        },
        "topology_differences": topology_differences,
        "mappings": mappings,
    }
