"""Rewriting the story script into the expanded banks, in Thai.

Three kinds of pointer name a message and all three have to be rewritten: the
master table, the sixteen-bit table at the head of each block, and the address
fields the records carry inside themselves.

Those inside fields are the awkward ones. Most name the start of another
message, which is easy -- we know where every message went. A few name a byte
in the middle of a record, and where that byte lands depends on how the record
was re-encoded. Rather than guess, a record whose field points into the middle
of something is left in the game's own bytes: then every offset inside it keeps
its distance from the record's start, and the arithmetic is exact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .rom import RomError
from .script import (
    ENTRY_BYTES,
    MASTER_TABLE_PC,
    Block,
    PackedRecord,
    cpu_to_pc,
    load_blocks,
    pack,
    read_pointers,
)
from .stream import encode
from .text import Tokenizer
from .tokens import EncodingError, TokenMap


@dataclass
class Repacked:
    blocks: list
    offsets: dict[str, int]
    report: dict


def containing(messages: list[dict]) -> dict[int, dict[int, tuple[str, int]]]:
    """block -> offset -> (message id, distance into it), for every byte."""
    spans: dict[int, list[tuple[int, int, str]]] = {}
    for message in messages:
        start = int(message["offset"], 16)
        spans.setdefault(message["block"], []).append(
            (start, start + message["size"], message["id"])
        )
    return spans


def owner_of(spans: list[tuple[int, int, str]], target: int) -> tuple[str, int] | None:
    for start, end, mid in spans:
        if start <= target < end:
            return mid, target - start
    return None


def compile_records(
    messages: list[dict],
    translations: dict[str, str],
    tokenizer: Tokenizer,
    token_map: TokenMap,
    branch_ranges: dict[int, range],
    keep_stock: set[str],
) -> tuple[dict[str, PackedRecord], list[dict]]:
    """One record per message, plus the notes on anything left in Japanese."""
    records: dict[str, PackedRecord] = {}
    notes: list[dict] = []
    starts = {int(message["offset"], 16) for message in messages}

    for message in messages:
        mid = message["id"]
        stock = bytes.fromhex(message["source_hex"])
        text = translations.get(mid)
        reason = None

        if mid in keep_stock:
            reason = "an address names a byte inside it"
        elif text is None:
            reason = "no translation"
        else:
            try:
                result = tokenizer.tokenize(
                    text,
                    where=mid,
                    branch_range=branch_ranges.get(message["block"], range(0)),
                )
            except EncodingError as exc:
                reason = f"will not tokenize: {exc}"
            else:
                if result.issues:
                    reason = "; ".join(result.issues)
                else:
                    record = encode(result.pieces, token_map)
                    # A field that names the middle of a record cannot be
                    # followed once the record is re-encoded.
                    if any(r.stock_target not in starts for r in record.relocations):
                        reason = "an address field points into the middle of a record"
                    else:
                        records[mid] = PackedRecord(
                            record.data,
                            passthrough=False,
                            fields=tuple((r.offset, r.stock_target) for r in record.relocations),
                        )

        if mid not in records:
            records[mid] = PackedRecord(stock, passthrough=True)
            notes.append({"id": mid, "reason": reason, "bytes": len(stock)})

    return records, notes


def stock_fields(
    rom: bytes, message: dict, block: Block
) -> tuple[tuple[int, int], ...]:
    """Address fields inside a record we are copying through unchanged."""
    from .text import ENGINE_OPERANDS, follows

    data = bytes.fromhex(message["source_hex"])
    found: list[tuple[int, int]] = []
    index = 0
    while index < len(data):
        byte = data[index]
        if byte < 0xEC:
            index += 1
            continue
        operands = ENGINE_OPERANDS.get(byte, 0)
        carries = follows(byte, list(data[index + 1 : index + 1 + operands]))
        at = index + 1 + operands
        if carries == "branch":
            for entry in range(8):
                slot = at + entry * 2
                if slot + 1 >= len(data):
                    break
                found.append((slot, data[slot] | data[slot + 1] << 8))
            index = at + 16
            continue
        if carries == "address":
            if at + 1 < len(data):
                found.append((at, data[at] | data[at + 1] << 8))
            index = at + 2
            continue
        index = at + (1 if carries == "operand" else 0)
    return tuple(found)


QUOTE_LEAD = (0xFC, 0x01)      # what stands in front of every `$FA` table
QUOTE_TABLE = 0xFA             # `$FA n` then n sixteen-bit intra-block targets


def quote_tables(data: bytes) -> list[tuple[int, int]]:
    """Every target inside a block's dispatch area, as (offset, address).

    An entry is `$FC:01 $FA n` followed by n sixteen-bit addresses. The engine
    picks one at random at $C1:9369 -- that is how a pilot has several things
    to shout for the same attack. The addresses are intra-block, so they move
    when the block does, and nothing else in the pipeline sees them: the area
    is not made of messages and is never translated.
    """
    found: list[tuple[int, int]] = []
    index = 0
    while index + 3 < len(data):
        if (data[index], data[index + 1]) != QUOTE_LEAD or data[index + 2] != QUOTE_TABLE:
            index += 1
            continue
        count = data[index + 3]
        for entry in range(count):
            at = index + 4 + entry * 2
            if at + 1 >= len(data):
                break
            found.append((at, data[at] | data[at + 1] << 8))
        index += 4 + count * 2
    return found


def by_slot_lookup(blocks: list[Block], slot: int) -> Block:
    for block in blocks:
        if block.slot == slot:
            return block
    raise RomError(f"no block with slot {slot}")


def claim(spans, block: Block, target: int, keep_stock: set[str], sentinels: list[dict]) -> None:
    """Note what a stock address names, and what that costs us."""
    if block.dispatch_start <= target < block.dispatch_end:
        return                                  # the dispatch area moves whole
    rows = spans.get(block.slot, [])
    if any(target == start for start, _, _ in rows):
        return                                  # it names a message: nothing to do
    found = owner_of(rows, target)
    if found is None:
        sentinels.append({"block": block.slot, "target": f"{target:#06x}"})
        return                                  # past the last record: an empty slot
    keep_stock.add(found[0])


def repack(
    rom,
    source: bytes,
    summary: list[dict],
    messages: list[dict],
    translations: dict[str, str],
    tokenizer: Tokenizer,
    token_map: TokenMap,
    first_bank: int,
    last_bank: int,
) -> Repacked:
    blocks = load_blocks(source, summary)
    branch_ranges: dict[int, range] = {}
    for entry in summary:
        if entry.get("kind") == "unused":
            continue
        starts = [
            int(m["offset"], 16) for m in messages if m["block"] == entry["slot"]
        ]
        if starts:
            branch_ranges[entry["slot"]] = range(min(starts), int(entry["extent"], 16) + 1)

    # Before anything is laid out, find every address the game already holds
    # and see which of them name a byte inside a record rather than its start.
    # Those records have to keep the game's own bytes, so that the distance
    # from the record's start still means what it meant.
    spans = containing(messages)
    keep_stock: set[str] = set()
    sentinels: list[dict] = []
    for block in blocks:
        for pointer in read_pointers(source, block):
            if pointer == 0:
                continue
            claim(spans, block, pointer, keep_stock, sentinels)
    for message in messages:
        for _, target in stock_fields(source, message, None):
            claim(spans, by_slot_lookup(blocks, message["block"]), target, keep_stock, sentinels)

    records, notes = compile_records(
        messages, translations, tokenizer, token_map, branch_ranges, keep_stock
    )
    placed, offsets = pack(blocks, messages, records, first_bank, last_bank)
    by_slot = {block.slot: block for block in blocks}
    by_id = {message["id"]: message for message in messages}

    # Records that were copied through keep the game's own address fields, so
    # those have to be found in the stock bytes and rewritten too.
    for message in messages:
        mid = message["id"]
        if records[mid].passthrough:
            records[mid] = PackedRecord(
                records[mid].data,
                passthrough=True,
                fields=stock_fields(source, message, by_slot[message["block"]]),
            )

    old_to_new: dict[tuple[int, int], int] = {}
    for message in messages:
        old_to_new[(message["block"], int(message["offset"], 16))] = offsets[message["id"]]

    def resolve(slot: int, target: int, block_end: int, start: int | None = None) -> int | None:
        """Where a stock address points to now."""
        new = old_to_new.get((slot, target))
        if new is not None:
            return new
        block = by_slot[slot]
        if block.dispatch_start <= target < block.dispatch_end and start is not None:
            # The dispatch area is copied byte for byte and keeps its place
            # right behind the table, so every address inside it moves by the
            # same amount the block did.
            return target - block.start + start
        found = owner_of(spans.get(slot, []), target)
        if found is None:
            return block_end                    # an empty slot points past the text
        mid, delta = found
        return offsets[mid] + delta

    rewritten = 0
    stranded: list[dict] = []

    dispatch_rewritten = 0

    for entry in placed:
        block = by_slot[entry.slot]
        image = bytearray(entry.size)

        # The dispatch area first: its bytes are the game's own and travel
        # unchanged, but the addresses inside them name records that moved.
        if block.dispatch:
            stock = source[cpu_to_pc(block.bank, block.dispatch_start) :][: block.dispatch]
            image[block.table_bytes : block.head_bytes] = stock
            for at, target in quote_tables(stock):
                new = resolve(entry.slot, target, entry.start + entry.size, entry.start)
                if new is None:
                    stranded.append(
                        {"block": entry.slot, "target": f"{target:#06x}",
                         "why": "a quote table names nothing"}
                    )
                    continue
                image[block.table_bytes + at] = new & 0xFF
                image[block.table_bytes + at + 1] = new >> 8
                dispatch_rewritten += 1

        # The block's own table: every slot that named a message now names
        # wherever that message went. A slot pointing one past the end of the
        # block keeps meaning that.
        old_pointers = read_pointers(source, block)
        for index, pointer in enumerate(old_pointers):
            if pointer == 0:
                continue
            new = resolve(entry.slot, pointer, entry.start + entry.size, entry.start)
            if new is None:
                stranded.append(
                    {"block": entry.slot, "slot": index, "pointer": f"{pointer:#06x}"}
                )
                new = entry.start + entry.size
            image[index * 2] = new & 0xFF
            image[index * 2 + 1] = new >> 8

        for mid, at in entry.records.items():
            record = records[mid]
            local = at - entry.start
            image[local : local + len(record.data)] = record.data

            for offset, target in record.fields:
                new = resolve(entry.slot, target, entry.start + entry.size, entry.start)
                if new is None:
                    stranded.append(
                        {"id": mid, "target": f"{target:#06x}", "why": "nothing there"}
                    )
                    continue
                image[local + offset] = new & 0xFF
                image[local + offset + 1] = new >> 8
                rewritten += 1

        rom.write_at(cpu_to_pc(entry.bank, entry.start), bytes(image))

        at = MASTER_TABLE_PC + entry.slot * ENTRY_BYTES
        rom.write_at(at, bytes([entry.start & 0xFF, entry.start >> 8, entry.bank]))

    layout = {
        mid: {"bank": entry.bank, "offset": at, "bytes": len(records[mid].data),
              "thai": not records[mid].passthrough}
        for entry in placed
        for mid, at in entry.records.items()
    }
    banks = sorted({entry.bank for entry in placed})
    report = {
        "mode": "packed",
        "blocks": len(placed),
        "banks": [f"${bank:02X}" for bank in banks],
        "bytes": sum(entry.size for entry in placed),
        "records_in_thai": sum(1 for record in records.values() if not record.passthrough),
        "records_copied_through": len(notes),
        "address_fields_rewritten": rewritten,
        "stranded_pointers": stranded,
        "empty_slots": len(sentinels),
        "quote_table_targets_rewritten": dispatch_rewritten,
        "copied_through": notes[:60],
    }
    report["layout"] = layout
    return Repacked(placed, offsets, report)
