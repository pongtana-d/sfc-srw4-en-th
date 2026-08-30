"""Deterministic Core repacker for all story and battle-quote blocks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .allocation import Allocator
from .text.encoding import encode
from .text.stock import StockCatalog, encode_mixed


@dataclass(frozen=True)
class Write:
    pc: int
    payload: bytes
    owner: str
    expected_ff: bool


MASTER_TABLE = 0x280000
MASTER_COUNT = 52
BANK_SIZE = 0x10000
STORY_END = 0x3A0000
TERMINATORS = frozenset((0xF7, 0xFF))
PERSONALITY_BRANCH = bytes((0xFC, 0x08))
PERSONALITIES = 8
TOKEN = re.compile(r"<(END)?([0-9A-Fa-f]{2})(?::([0-9A-Fa-f]+))?>")


def _encode_message(text: str, layout: dict[str, object], stock: StockCatalog) -> bytes:
    payload = bytearray()
    cursor = 0
    run: list[str] = []

    def flush() -> None:
        if not run:
            return

        def thai(part: str) -> bytes:
            return encode(
                part, layout["codes"], layout.get("shorthand"), layout.get("phrases")
            )

        encoded, _ = encode_mixed("".join(run), thai, stock)
        payload.extend(encoded)
        run.clear()

    while cursor < len(text):
        char = text[cursor]
        if char == "<":
            match = TOKEN.match(text, cursor)
            if match is None:
                raise ValueError(f"malformed story token at {cursor} in {text!r}")
            flush()
            payload.append(int(match.group(2), 16))
            if match.group(3):
                payload.extend(bytes.fromhex(match.group(3)))
            cursor = match.end()
            continue
        if char == "\n":
            flush()
            payload.append(0xF6)
            cursor += 1
            continue
        run.append(char)
        cursor += 1
    flush()
    if not payload or payload[-1] not in TERMINATORS:
        raise ValueError("translated story message must retain its terminator")
    return bytes(payload)


def _record_references(
    data: bytes, start: int, end: int
) -> list[tuple[int, int, str]]:
    """Parse real pointer operands from a battle-quote command stream."""
    references: list[tuple[int, int, str]] = []
    cursor = start
    while cursor < end:
        if data[cursor:cursor + 2] == b"\xFC\x01":
            cursor += 2
            continue
        if data[cursor] == 0xFA:
            count, kind = data[cursor + 1], "message"
        elif data[cursor:cursor + 2] == b"\xFC\x07":
            count, kind = 1, "message"
        elif data[cursor:cursor + 2] == b"\xFC\x08":
            count, kind = 8, "record"
        else:
            raise ValueError(
                f"unknown battle-record opcode at {cursor:#x}: "
                f"{data[cursor:cursor + 8].hex(' ')}"
            )
        operand = cursor + 2
        next_cursor = operand + count * 2
        if next_cursor > end:
            raise ValueError(f"truncated battle record at {cursor:#x}")
        for index in range(count):
            position = operand + index * 2
            target = int.from_bytes(data[position:position + 2], "little")
            references.append((position, target, kind))
        cursor = next_cursor
    return references


def _remap_personality_tables(
    image: bytearray,
    messages: list[tuple[int, int, int, int]],
    offsets: dict[int, int],
) -> int:
    moved = 0
    for old, new, old_size, new_size in messages:
        cursor = image.find(PERSONALITY_BRANCH, new, new + new_size)
        while cursor >= 0:
            table = cursor + len(PERSONALITY_BRANCH)
            if table + 2 * PERSONALITIES > new + new_size - 1:
                cursor = image.find(PERSONALITY_BRANCH, cursor + 1, new + new_size)
                continue
            for index in range(PERSONALITIES):
                at = table + 2 * index
                word = int.from_bytes(image[at:at + 2], "little")
                if word in offsets:
                    target = offsets[word]
                elif old <= word < old + old_size:
                    target = new + (word - old)
                else:
                    continue
                image[at:at + 2] = target.to_bytes(2, "little")
                moved += 1
            cursor = image.find(PERSONALITY_BRANCH, cursor + 1, new + new_size)
    return moved


def _source_blocks(source: dict[str, object]) -> list[dict[str, object]]:
    grouped: dict[int, list[dict[str, object]]] = {}
    for message in source["messages"]:
        grouped.setdefault(int(message["block"]), []).append(message)
    blocks: list[dict[str, object]] = []
    for summary in source["summary"]["blocks"]:
        if summary["kind"] == "unused":
            continue
        slot = int(summary["slot"])
        messages = sorted(grouped.get(slot, []), key=lambda item: int(item["pc"], 16))
        # The current extraction deliberately removed 18 false-positive text
        # records from slots 1 and 32; their physical block summaries still
        # describe the original scan.  Never allow more records than that
        # physical ceiling, but let the audited source row set be authoritative.
        if not messages or len(messages) > int(summary["messages"]):
            raise ValueError(f"story block {slot} message inventory is invalid")
        pc = int(str(summary["pc"]), 16)
        base = pc & ~0xFFFF
        address = pc & 0xFFFF
        message_start = int(str(messages[0]["offset"]), 16)
        blocks.append({
            **summary, "base": base, "address": address,
            "extent_word": int(str(summary["extent"]), 16),
            "message_start": message_start, "messages_data": messages,
        })
    if len(blocks) != 47 or sum(len(block["messages_data"]) for block in blocks) != len(source["messages"]):
        raise ValueError("story source inventory lost or duplicated messages")
    return blocks


def build_story_data(
    root: Path,
    clean: bytes,
    *,
    source_path: Path | None = None,
    translation_path: Path | None = None,
    layout_path: Path | None = None,
    translation_dir: Path | None = None,
    allocation_path: Path | None = None,
) -> tuple[list[Write], dict[str, object]]:
    source_path = source_path or root / "translations/script.source.json"
    translation_path = translation_path or root / "translations/script.th.json"
    layout_path = layout_path or root / "font/encoding.json"
    translation_dir = translation_dir or root / "translations"
    allocation_path = allocation_path or root / "config/memory-map.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    translated_data = json.loads(
        translation_path.read_text(encoding="utf-8")
    )["messages"]
    blocks = _source_blocks(source)
    source_ids = {str(item["id"]) for item in source["messages"]}
    if set(translated_data) != source_ids:
        missing = source_ids - set(translated_data)
        extra = set(translated_data) - source_ids
        raise ValueError(f"story translation coverage mismatch: missing={len(missing)} extra={len(extra)}")

    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    stock = StockCatalog.locked()
    allocator = Allocator.from_file(allocation_path)
    writes: list[Write] = []
    placements: list[dict[str, object]] = []
    routes: dict[int, list[tuple[int, int]]] = {}
    translated = 0
    personality_words = 0
    record_words = 0
    ignored_overlapping_record_refs = 0

    for block in blocks:
        slot = int(block["slot"])
        old_base = int(block["base"])
        old_address = int(block["address"])
        message_start = int(block["message_start"])
        pointer_count = int(block["pointers"])
        prefix_end = old_base + message_start
        prefix = clean[old_base + old_address:prefix_end]
        if len(prefix) < pointer_count * 2:
            raise ValueError(f"story block {slot} pointer table exceeds its prefix")
        image = bytearray(prefix)
        offsets: dict[int, int] = {}
        message_moves: list[tuple[int, int, int, int]] = []
        message_index: dict[int, int] = {}

        for index, entry in enumerate(block["messages_data"]):
            old_pc = int(str(entry["pc"]), 16)
            old_offset = int(str(entry["offset"]), 16)
            expected = bytes.fromhex(str(entry["source_hex"]))
            if len(expected) != int(entry["size"]) or clean[old_pc:old_pc + len(expected)] != expected:
                raise ValueError(f"story source mismatch for {entry['id']}")
            payload = _encode_message(str(translated_data[str(entry["id"])]), layout, stock)
            new_offset = len(image)
            offsets[old_offset] = new_offset
            message_index[old_offset] = index
            message_moves.append((old_offset, new_offset, len(expected), len(payload)))
            image.extend(payload)
            translated += 1

        personality_words += _remap_personality_tables(image, message_moves, offsets)

        # Validate and relocate every table slot declared by the extracted source.
        relocated_slots: set[int] = set()
        for entry in block["messages_data"]:
            old_offset = int(str(entry["offset"]), 16)
            for table_slot in entry["table_slots"]:
                table_slot = int(table_slot)
                at = table_slot * 2
                if int.from_bytes(prefix[at:at + 2], "little") != old_offset:
                    raise ValueError(f"story table slot mismatch for {entry['id']}:{table_slot}")
                image[at:at + 2] = offsets[old_offset].to_bytes(2, "little")
                relocated_slots.add(table_slot)

        # Some table entries select command-prefix bytes rather than messages.
        # Preserve their offset inside the block when the block itself moves.
        for table_slot in range(pointer_count):
            if table_slot in relocated_slots:
                continue
            at = table_slot * 2
            target = int.from_bytes(prefix[at:at + 2], "little")
            if old_address <= target < message_start:
                image[at:at + 2] = (target - old_address).to_bytes(2, "little")
                relocated_slots.add(table_slot)

        # Battle blocks contain typed bytecode. Relocate only parsed operands.
        if block["kind"] == "record":
            record_start = pointer_count * 2
            record_end = message_start - old_address
            refs = _record_references(prefix, record_start, record_end)
            declared_record_positions = {
                int(str(position), 16) - old_address
                for entry in block["messages_data"] for position in entry["record_refs"]
            }
            parsed_message_positions = {position for position, _, kind in refs if kind == "message"}
            # The old extraction also recorded a handful of overlapping
            # 16-bit matches that straddle an opcode and a real operand. The
            # typed bytecode parser is authoritative, but every real operand
            # must still exist in the extracted provenance.
            if not parsed_message_positions <= declared_record_positions:
                raise ValueError(f"story block {slot} is missing extracted record refs")
            ignored_overlapping_record_refs += len(
                declared_record_positions - parsed_message_positions
            )
            for position, target, kind in refs:
                if kind == "message":
                    if target not in offsets:
                        raise ValueError(f"story block {slot} record targets unknown message {target:#x}")
                    moved = offsets[target]
                else:
                    if not old_address + record_start <= target < message_start:
                        raise ValueError(f"story block {slot} record branch leaves record area")
                    moved = target - old_address
                image[position:position + 2] = moved.to_bytes(2, "little")
                record_words += 1

        size = len(image)
        if size > BANK_SIZE:
            raise ValueError(f"story block {slot} is larger than one bank")
        cursor = allocator.next_address("story")
        if (cursor & 0xFFFF) + size > BANK_SIZE:
            padding = BANK_SIZE - (cursor & 0xFFFF)
            allocator.reserve("story", padding, f"story-bank-padding-{slot:02d}")
        allocation = allocator.reserve("story", size, f"story-block-{slot:02d}")
        if allocation.end > STORY_END:
            raise ValueError("translated story exceeds the declared story region")
        block_base = allocation.start & 0xFFFF

        # All internal words are block-relative so far; add the placed bank offset.
        for table_slot in relocated_slots:
            at = table_slot * 2
            value = int.from_bytes(image[at:at + 2], "little") + block_base
            image[at:at + 2] = value.to_bytes(2, "little")
        if block["kind"] == "record":
            record_start = pointer_count * 2
            record_end = message_start - old_address
            for position, _, _ in _record_references(prefix, record_start, record_end):
                value = int.from_bytes(image[position:position + 2], "little") + block_base
                image[position:position + 2] = value.to_bytes(2, "little")
        # Personality-table words were also remapped to block-relative targets.
        for old, new, _old_size, new_size in message_moves:
            cursor = image.find(PERSONALITY_BRANCH, new, new + new_size)
            while cursor >= 0:
                table = cursor + len(PERSONALITY_BRANCH)
                if table + 2 * PERSONALITIES <= new + new_size - 1:
                    for index in range(PERSONALITIES):
                        at = table + 2 * index
                        value = int.from_bytes(image[at:at + 2], "little")
                        if value in offsets.values() or new <= value < new + new_size:
                            image[at:at + 2] = (value + block_base).to_bytes(2, "little")
                cursor = image.find(PERSONALITY_BRANCH, cursor + 1, new + new_size)

        writes.append(Write(allocation.start, bytes(image), allocation.owner, True))
        new_bank = 0xC0 + (allocation.start >> 16)
        entry_pc = MASTER_TABLE + slot * 3
        expected_entry = clean[entry_pc:entry_pc + 3]
        old_bank = 0xC0 + (old_base >> 16)
        expected_master = old_address.to_bytes(2, "little") + bytes((old_bank,))
        if expected_entry != expected_master:
            raise ValueError(f"story master pointer source mismatch for block {slot}")
        replacement = (allocation.start & 0xFFFF).to_bytes(2, "little") + bytes((new_bank,))
        writes.append(Write(entry_pc, replacement, f"story-master-pointer-{slot:02d}", False))
        new_message_start = allocation.start + (message_start - old_address)
        routes.setdefault(new_bank, []).append(
            (((new_message_start & 0xFFFF) + 1), ((allocation.end & 0xFFFF) + 1))
        )
        placements.append({
            "slot": slot, "kind": block["kind"],
            "old_pc": f"0x{old_base + old_address:06X}",
            "new_pc": f"0x{allocation.start:06X}",
            "cpu": f"${new_bank:02X}:{allocation.start & 0xFFFF:04X}",
            "size": size, "messages": len(block["messages_data"]),
            "master_source": expected_entry.hex(" ").upper(),
        })

    story_allocations = [
        item for item in allocator.report()
        if str(item["owner"]).startswith("story-")
    ]
    used_end = max(
        write.pc + len(write.payload) for write in writes if write.expected_ff
    )
    return writes, {
        "translated": translated,
        "blocks": placements,
        "area_end": f"0x{used_end:06X}",
        "used_end": f"0x{used_end:06X}",
        "personality_words": personality_words,
        "record_words": record_words,
        "ignored_overlapping_record_refs": ignored_overlapping_record_refs,
        "allocations": story_allocations,
        "source_routes": {
            f"0x{bank:02X}": [[start, end] for start, end in bank_routes]
            for bank, bank_routes in sorted(routes.items())
        },
    }
