"""Deterministic full-story repacker for the English ROM dialogue path."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .en_dialogue_font import BATTLE_QUOTE_PADDING
from .rom import Rom, RomError


MASTER_TABLE_PC = 0x280000
STORY_BANKS = (0xEB, *range(0xF1, 0xFD))
ENGINE_OPERANDS = {0xF0: 1, 0xF1: 1, 0xF2: 1, 0xF3: 1, 0xF4: 1,
                   0xF5: 1, 0xFB: 2, 0xFC: 1, 0xFD: 1, 0xFE: 2}
EN_QUOTE_HEADER = b"\xFC\x01\xAB\x43"


@dataclass(frozen=True)
class StoryBuildReport:
    blocks: int
    records: int
    bytes: int
    relocated_fields: int
    banks: tuple[int, ...]


def _shape(lead: int, operands: list[int]) -> str | None:
    if (lead, operands) == (0xFC, [0x08]):
        return "branch"
    if lead == 0xFB and len(operands) == 2 and operands[1] == 0x0C:
        return "address"
    if (lead, operands) == (0xFC, [0x07]):
        return "address"
    if (lead, operands) == (0xF5, [0x03]):
        return "operand"
    return None


def fields(data: bytes, *, where: str) -> tuple[int, ...]:
    """Return offsets of all 16-bit intra-block operands in a text stream."""
    result: list[int] = []
    index = 0
    while index < len(data):
        lead = data[index]
        if lead in (0xC0, 0xC1, 0xC2):
            if index + 1 >= len(data):
                raise RomError(f"{where}: private page lead has no slot")
            index += 2
            continue
        if lead < 0xF0:
            index += 1
            continue
        operands = ENGINE_OPERANDS.get(lead, 0)
        if index + 1 + operands > len(data):
            raise RomError(f"{where}: control ${lead:02X} is truncated")
        values = list(data[index + 1:index + 1 + operands])
        after = index + 1 + operands
        shape = _shape(lead, values)
        if shape == "branch":
            if after + 16 > len(data):
                raise RomError(f"{where}: $FC:08 branch table is truncated")
            result.extend(after + 2 * item for item in range(8))
            index = after + 16
        elif shape == "address":
            if after + 2 > len(data):
                raise RomError(f"{where}: ${lead:02X} address is truncated")
            result.append(after)
            index = after + 2
        elif shape == "operand":
            if after >= len(data):
                raise RomError(f"{where}: ${lead:02X} trailing operand is missing")
            index = after + 1
        else:
            index = after
    return tuple(result)


def quote_fields(data: bytes) -> tuple[int, ...]:
    """Locate table and direct pointer words in JP/EN battle-quote records.

    The English engine inserted ``$AB $43`` between the shared ``$FC $01``
    lead and the quote selector.  Records either use ``$FA count + pointers``
    or a direct ``$FC $07 pointer``.  Both forms must move with the translated
    streams; leaving a direct pointer unchanged can land in the middle of an
    unrelated record after repacking.
    """
    result: list[int] = []
    index = 0
    while index + 3 < len(data):
        if data[index:index + 4] == b"\xFC\x01\xAB\x43":
            command_at = index + 4
        elif data[index:index + 2] == b"\xFC\x01":
            command_at = index + 2
        else:
            index += 1
            continue
        if command_at >= len(data):
            raise RomError("truncated battle quote dispatch table")
        if data[command_at] == 0xFA:
            count_at = command_at + 1
            if count_at >= len(data):
                raise RomError("truncated battle quote dispatch table")
            start = count_at + 1
            end = start + data[count_at] * 2
        elif data[command_at:command_at + 2] == b"\xFC\x07":
            start = command_at + 2
            end = start + 2
        else:
            index = command_at + 1
            continue
        if end > len(data):
            raise RomError("truncated battle quote dispatch table")
        result.extend(range(start, end, 2))
        index = end
    return tuple(result)


def replace_en_quote_separators(data: bytearray) -> int:
    """Replace the EN renderer's raw separator after a battle pilot name.

    ``$AB $43`` supplies colon and space for English quote bodies, but Thai
    quote bodies already begin with their own separator. Use the dedicated
    zero-advance primary slot; replacement stays in-place so every dispatch
    offset remains unchanged.
    """
    count = 0
    cursor = 0
    while (at := data.find(EN_QUOTE_HEADER, cursor)) >= 0:
        data[at + 2:at + 4] = BATTLE_QUOTE_PADDING
        count += 1
        cursor = at + 4
    return count


def _cpu_to_pc(bank: int, address: int) -> int:
    return (bank & 0x3F) << 16 | address


def _slots(document: Mapping[str, object]) -> list[dict[str, object]]:
    return [item for item in document["summary"]["blocks"] if item.get("kind") != "unused"]


def _dispatch_records(data: bytes, header: bytes) -> list[list[tuple[int, int]]]:
    """Return every quote-pointer record following one dispatch header.

    Quote selectors have two shapes: ``$FA count + pointer table`` and the
    single ``$FC $07 pointer`` form.  Both must participate in EN/JP record
    alignment; otherwise direct weapon quotes silently relocate to the empty
    terminator.
    """
    records: list[list[tuple[int, int]]] = []
    cursor = 0
    while (at := data.find(header, cursor)) >= 0:
        command_at = at + len(header)
        if command_at >= len(data):
            raise RomError("truncated battle quote dispatch record")
        if data[command_at] == 0xFA:
            count_at = command_at + 1
            if count_at >= len(data):
                raise RomError("truncated battle quote dispatch record")
            first = count_at + 1
            end = first + data[count_at] * 2
        elif data[command_at:command_at + 2] == b"\xFC\x07":
            first = command_at + 2
            end = first + 2
        else:
            cursor = command_at + 1
            continue
        if end > len(data):
            raise RomError("truncated battle quote dispatch record")
        records.append([
            (pointer_at, data[pointer_at] | data[pointer_at + 1] << 8)
            for pointer_at in range(first, end, 2)
        ])
        cursor = end
    return records


def _en_record_source(clean: bytes, slot: int, table_bytes: int) -> tuple[int, int, bytes, bytes]:
    """Read an EN battle table and its variable-length dispatch from its master slot."""
    master = MASTER_TABLE_PC + slot * 3
    start = clean[master] | clean[master + 1] << 8
    bank = clean[master + 2]
    source_pc = _cpu_to_pc(bank, start)
    table = clean[source_pc:source_pc + table_bytes]
    if len(table) != table_bytes:
        raise RomError(f"battle block {slot}: truncated EN pointer table")
    ends = []
    for at in range(0, table_bytes, 2):
        target = table[at] | table[at + 1] << 8
        record_pc = _cpu_to_pc(bank, target)
        if clean[record_pc:record_pc + 5] != b"\xFC\x01\xAB\x43\xFA":
            continue
        end = target + 6 + clean[record_pc + 5] * 2
        ends.append(end)
    dispatch_start = start + table_bytes
    if not ends or min(target for target in (table[at] | table[at + 1] << 8
                                              for at in range(0, table_bytes, 2))
                       if clean[_cpu_to_pc(bank, target):_cpu_to_pc(bank, target) + 5]
                       == b"\xFC\x01\xAB\x43\xFA") != dispatch_start:
        raise RomError(f"battle block {slot}: cannot derive EN dispatch extent")
    dispatch_end = max(ends)
    return start, bank, table, clean[_cpu_to_pc(bank, dispatch_start):_cpu_to_pc(bank, dispatch_end)]


def install_full_story(rom: Rom, clean: bytes, document: Mapping[str, object],
                       messages: Mapping[str, str],
                       compile_text: Callable[[str], bytes]) -> StoryBuildReport:
    """Pack all active EN story blocks and rebase their owned pointers."""
    blocks = {int(item["slot"]): item for item in _slots(document)}
    rows_by_block = {
        slot: sorted((row for row in document["messages"] if int(row["block"]) == slot),
                     key=lambda row: int(row["offset"], 0))
        for slot in blocks
    }
    spans = [[bank, 1, 0x10000] for bank in STORY_BANKS]
    order = [49, 50, 51, *range(43), 48]
    placed: list[tuple[int, int, int, bytes, int, int]] = []
    relocated = 0
    record_sources = {
        slot: _en_record_source(clean, slot, int(block["pointers"]) * 2)
        for slot, block in blocks.items() if block.get("kind") == "record"
    }
    jp_reference = (Path(__file__).resolve().parents[2] / "rom" /
                    "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc").read_bytes()
    for slot in order:
        block = blocks[slot]
        rows = rows_by_block[slot]
        table_bytes = int(block["pointers"]) * 2
        record_source = record_sources.get(slot)
        dispatch_bytes = len(record_source[3]) if record_source else 0
        streams = {str(row["id"]): bytearray(compile_text(messages[str(row["id"])])) for row in rows}
        if any(not stream or stream[-1] not in (0xF7, 0xFF) for stream in streams.values()):
            raise RomError(f"story block {slot}: stream has no terminator")
        size = table_bytes + dispatch_bytes + sum(len(streams[str(row["id"])]) for row in rows) + 1
        span = next((item for item in spans if item[2] - item[1] >= size), None)
        if span is None:
            raise RomError(f"story block {slot} needs {size} bytes; no EN span fits it")
        bank, start, _ = span
        span[1] += size
        cursor = start + table_bytes + dispatch_bytes
        starts: dict[int, int] = {}
        source_rows = {int(row["offset"], 0): row for row in rows}
        original = {str(row["id"]): bytes(stream) for row, stream in
                    ((row, streams[str(row["id"])]) for row in rows)}
        for row in rows:
            starts[int(row["offset"], 0)] = cursor
            cursor += len(streams[str(row["id"])] )
        empty = cursor

        def resolve(row: Mapping[str, object], target: int) -> int:
            direct = starts.get(target)
            if direct is not None:
                return direct
            # Block 1's five-way objective selects a translated tail.  The
            # anchors are explicit controls retained by the translator.
            if str(row["id"]) == "01_0811":
                anchors = {0x081B: 10, 0x0825: 20, 0x082F: 30, 0x0839: 40,
                           0x0843: 81, 0x0844: 82}
                if target in anchors:
                    return starts[int(row["offset"], 0)] + anchors[target]
            for old, owner in source_rows.items():
                delta = target - old
                if 0 <= delta < int(owner["size"]):
                    stock = bytes.fromhex(str(owner["source_hex"]))
                    translated = original[str(owner["id"])]
                    if stock[:delta] == translated[:delta]:
                        return starts[old] + delta
                    common = 0
                    while common < min(len(stock), len(translated)) and stock[common] == translated[common]:
                        common += 1
                    if (delta == common and common < len(stock) and stock[common] < 0xC0
                            and translated[common] in (0xC0, 0xC1, 0xC2)):
                        return starts[old] + common
                    raise RomError(f"{row['id']}: target {target:#06x} is inside translated {owner['id']}")
            if target == int(block["extent"], 0):
                return empty
            raise RomError(f"{row['id']}: target {target:#06x} has no record owner")

        for row in rows:
            stream = streams[str(row["id"])]
            for at in fields(bytes(stream), where=str(row["id"])):
                target = stream[at] | stream[at + 1] << 8
                stream[at:at + 2] = resolve(row, target).to_bytes(2, "little")
                relocated += 1
        dispatch = bytearray()
        if dispatch_bytes:
            source_start, source_bank, source_table, source_dispatch = record_source
            dispatch = bytearray(source_dispatch)
            source_by_target: dict[int, int] = {}
            for row in rows:
                source_offset = int(row["offset"], 0)
                for index in row["table_slots"]:
                    at = int(index) * 2
                    target = source_table[at] | source_table[at + 1] << 8
                    source_by_target[target] = source_offset

            jp_pc = int(str(block["pc"]), 0)
            jp_dispatch = jp_reference[jp_pc + table_bytes:
                                       jp_pc + table_bytes + int(block["record_bytes"])]
            jp_start = (jp_pc & 0xFFFF) + table_bytes
            by_jp_field = {
                int(reference, 0) - jp_start: int(row["offset"], 0)
                for row in rows for reference in row.get("record_refs", ())
            }
            en_records = _dispatch_records(bytes(dispatch), EN_QUOTE_HEADER)
            jp_records = _dispatch_records(jp_dispatch, b"\xFC\x01")
            if len(en_records) > len(jp_records):
                raise RomError(f"battle block {slot}: EN dispatch record count changed")
            for en_record, jp_record in zip(en_records, jp_records):
                if len(en_record) != len(jp_record):
                    raise RomError(f"battle block {slot}: EN/JP dispatch shape changed")
                for (jp_at, jp_target), (_, en_target) in zip(jp_record, en_record):
                    source_offset = starts.get(jp_target)
                    if source_offset is None:
                        source_offset = by_jp_field.get(jp_at)
                        source_offset = starts.get(source_offset) if source_offset is not None else None
                    if source_offset is not None:
                        source_by_target[en_target] = next(
                            offset for offset, address in starts.items() if address == source_offset
                        )
            for at in quote_fields(bytes(dispatch)):
                target = dispatch[at] | dispatch[at + 1] << 8
                source_offset = source_by_target.get(target)
                if source_offset is None or source_offset not in starts:
                    raise RomError(
                        f"battle block {slot}: quote target "
                        f"${source_bank:02X}:{target:04X} has no translated record"
                    )
                address = starts[source_offset]
                dispatch[at:at + 2] = address.to_bytes(2, "little")
                relocated += 1
            expected_separators = dispatch.count(EN_QUOTE_HEADER)
            replaced = replace_en_quote_separators(dispatch)
            if not replaced or replaced != expected_separators:
                raise RomError(
                    f"battle block {slot}: replaced {replaced} of "
                    f"{expected_separators} EN quote separators"
                )
        table = bytearray(table_bytes)
        if dispatch_bytes:
            for index in range(int(block["pointers"])):
                at = index * 2
                target = source_table[at] | source_table[at + 1] << 8
                if source_start + table_bytes <= target < source_start + table_bytes + dispatch_bytes:
                    moved = start + table_bytes + target - (source_start + table_bytes)
                else:
                    moved = starts.get(source_by_target.get(target, -1), empty)
                table[at:at + 2] = moved.to_bytes(2, "little")
        else:
            for row in rows:
                for index in row["table_slots"]:
                    at = int(index) * 2
                    table[at:at + 2] = starts[int(row["offset"], 0)].to_bytes(2, "little")
        # The engine may reach an unreferenced table slot through a dynamic
        # dispatch.  Preserve the EN convention: it points at the block's
        # single empty terminator, rather than becoming a dangerous $0000.
        for index in range(int(block["pointers"])):
            at = index * 2
            if table[at:at + 2] == b"\x00\x00":
                table[at:at + 2] = empty.to_bytes(2, "little")
            address = table[at] | table[at + 1] << 8
            if not start <= address <= empty:
                raise RomError(f"story block {slot}, pointer {index}: relocated address is out of range")
        image = bytes(table) + bytes(dispatch) + b"".join(streams[str(row["id"])] for row in rows) + b"\xFF"
        if len(image) != size:
            raise RomError(f"story block {slot}: planned {size}, built {len(image)}")
        placed.append((slot, bank, start, image, len(rows), relocated))

    for slot, bank, start, image, _, _ in placed:
        rom.write_at(_cpu_to_pc(bank, start), image)
        rom.write_at(MASTER_TABLE_PC + slot * 3, bytes((start & 0xFF, start >> 8, bank)))
    return StoryBuildReport(
        blocks=len(placed), records=sum(item[4] for item in placed),
        bytes=sum(len(item[3]) for item in placed), relocated_fields=relocated,
        banks=tuple(sorted({item[1] for item in placed})),
    )
