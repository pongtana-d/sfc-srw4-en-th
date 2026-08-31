"""Deterministic full-story repacker for the English ROM dialogue path."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .en_dialogue_font import BATTLE_QUOTE_PADDING, BATTLE_QUOTE_SEPARATOR
from .rom import Rom, RomError


MASTER_TABLE_PC = 0x280000
STORY_BANKS = (0xEB, *range(0xF1, 0xFD))
ENGINE_OPERANDS = {0xF0: 1, 0xF1: 1, 0xF2: 1, 0xF3: 1, 0xF4: 1,
                   0xF5: 1, 0xFB: 2, 0xFC: 1, 0xFD: 1, 0xFE: 2}
EN_QUOTE_HEADER = b"\xFC\x01\xAB\x43"
EN_PERSONALITY_HEADER = EN_QUOTE_HEADER + b"\xFC\x08"
PERSONALITY_SELECTOR_COUNT = 8


@dataclass(frozen=True)
class StoryBuildReport:
    blocks: int
    records: int
    bytes: int
    relocated_fields: int
    banks: tuple[int, ...]
    ordinary_thai_routes: dict[int, tuple[tuple[int, int], ...]]
    ordinary_profile_page2_routes: dict[int, tuple[tuple[int, int], ...]]
    ordinary_alternate_routes: dict[int, tuple[tuple[int, int], ...]]


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
    """Normalize the EN separator after a battle pilot name.

    Fixed quote tables (``FA``/``FC:07``) are relocated to the beginning of a
    Thai record, which already contains ``: ``.  Replace their stock separator
    with the zero-advance pad.  Personality branches (``FC:08``) retain an
    interior target after the source record's separator, so their header gets
    the private-page ``: `` pair instead.  Both forms remain four bytes,
    preserving every dispatch offset and every dynamic name length.
    """
    count = 0
    cursor = 0
    while (at := data.find(EN_QUOTE_HEADER, cursor)) >= 0:
        command_at = at + len(EN_QUOTE_HEADER)
        replacement = (
            BATTLE_QUOTE_SEPARATOR
            if data[command_at:command_at + 2] == b"\xFC\x08"
            else BATTLE_QUOTE_PADDING
        )
        data[at + 2:at + 4] = replacement
        count += 1
        cursor = at + 4
    return count


def _personality_records(data: bytes, header: bytes) -> list[list[tuple[int, int]]]:
    """Return the eight selector pointers following each personality header."""
    records: list[list[tuple[int, int]]] = []
    cursor = 0
    while (at := data.find(header, cursor)) >= 0:
        first = at + len(header)
        end = first + PERSONALITY_SELECTOR_COUNT * 2
        if end > len(data):
            raise RomError("truncated personality branch table")
        records.append([
            (pointer_at, data[pointer_at] | data[pointer_at + 1] << 8)
            for pointer_at in range(first, end, 2)
        ])
        cursor = end
    return records


def _fa_selector_fields(data: bytes, selector_at: int) -> list[tuple[int, int]]:
    """Return pointer fields from one bare ``FA count`` selector record."""
    if not 0 <= selector_at < len(data) - 1 or data[selector_at] != 0xFA:
        raise RomError(f"personality selector at {selector_at:#06x} is not FA")
    first = selector_at + 2
    end = first + data[selector_at + 1] * 2
    if end > len(data):
        raise RomError("truncated personality FA selector")
    return [
        (pointer_at, data[pointer_at] | data[pointer_at + 1] << 8)
        for pointer_at in range(first, end, 2)
    ]


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
                       compile_text: Callable[[str, str, range], bytes],
                       ordinary_records: Mapping[
                           str, tuple[bytes, tuple[int, ...]]
                       ] | None = None) -> StoryBuildReport:
    """Pack all active EN story blocks and rebase their owned pointers."""
    blocks = {int(item["slot"]): item for item in _slots(document)}
    rows_by_block = {
        slot: sorted((row for row in document["messages"] if int(row["block"]) == slot),
                     key=lambda row: int(row["offset"], 0))
        for slot in blocks
    }
    branch_ranges = {
        slot: range(
            min(int(row["offset"], 0) for row in rows),
            int(blocks[slot]["extent"], 0) + 1,
        )
        for slot, rows in rows_by_block.items()
        if rows
    }
    spans = [[bank, 1, 0x10000] for bank in STORY_BANKS]
    order = [49, 50, 51, *range(43), 48]
    placed: list[tuple[int, int, int, bytes, int, int]] = []
    relocated = 0
    ordinary_records = ordinary_records or {}
    ordinary_routes: dict[int, list[tuple[int, int]]] = {}
    ordinary_profile_page2_routes: dict[int, list[tuple[int, int]]] = {}
    ordinary_alternate_routes: dict[int, list[tuple[int, int]]] = {}
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
        streams: dict[str, bytearray] = {}
        for row in rows:
            message_id = str(row["id"])
            routed = ordinary_records.get(message_id)
            payload = (
                routed[0]
                if routed is not None
                else compile_text(messages[message_id], message_id, branch_ranges[slot])
            )
            streams[message_id] = bytearray(payload)
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

        for row in rows:
            routed = ordinary_records.get(str(row["id"]))
            if routed is None:
                continue
            payload, route_mask = routed
            if len(payload) != len(route_mask):
                raise RomError(f"{row['id']}: ordinary route mask length changed")
            record_start = starts[int(row["offset"], 0)]
            # Route controls with the primary page: the parser checks engine
            # controls before tagging a glyph, so F6/F7/FF remain stock-owned.
            # Visible bytes use page 1, the shared supplement, or page 2.
            targets = {
                1: ordinary_routes,
                2: ordinary_profile_page2_routes,
                3: ordinary_alternate_routes,
            }
            index = 0
            while index < len(route_mask):
                kind = route_mask[index] if route_mask[index] in targets else 1
                first = index
                while index < len(route_mask):
                    current = (
                        route_mask[index] if route_mask[index] in targets else 1
                    )
                    if current != kind:
                        break
                    index += 1
                target = targets[kind]
                target.setdefault(bank, []).append(
                    (record_start + first + 1, record_start + index + 1)
                )

        def resolve(row: Mapping[str, object], target: int) -> int:
            direct = starts.get(target)
            if direct is not None:
                return direct
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
            source_dispatch_start = source_start + table_bytes
            moved_dispatch_start = start + table_bytes
            en_personality = _personality_records(
                bytes(dispatch), EN_PERSONALITY_HEADER
            )
            jp_personality = _personality_records(
                jp_dispatch, b"\xFC\x01\xFC\x08"
            )
            if len(en_personality) != len(jp_personality):
                raise RomError(
                    f"battle block {slot}: EN/JP personality record count changed"
                )
            for en_record, jp_record in zip(en_personality, jp_personality):
                if len(en_record) != len(jp_record):
                    raise RomError(
                        f"battle block {slot}: EN/JP personality shape changed"
                    )
                for (_, jp_selector), (en_branch_at, en_selector) in zip(
                    jp_record, en_record
                ):
                    jp_fields = _fa_selector_fields(
                        jp_dispatch, jp_selector - jp_start
                    )
                    en_fields = _fa_selector_fields(
                        bytes(dispatch), en_selector - source_dispatch_start
                    )
                    if len(en_fields) != len(jp_fields):
                        raise RomError(
                            f"battle block {slot}: EN/JP personality selector shape changed"
                        )
                    for (jp_at, _), (en_at, _) in zip(jp_fields, en_fields):
                        source_offset = by_jp_field.get(jp_at)
                        if source_offset is None or source_offset not in starts:
                            raise RomError(
                                f"battle block {slot}: personality field "
                                f"{jp_at + jp_start:#06x} has no translated record"
                            )
                        address = starts[source_offset]
                        message_id = str(source_rows[source_offset]["id"])
                        if original[message_id].startswith(BATTLE_QUOTE_SEPARATOR):
                            address += len(BATTLE_QUOTE_SEPARATOR)
                        dispatch[en_at:en_at + 2] = address.to_bytes(2, "little")
                        relocated += 1
                    moved_selector = (
                        moved_dispatch_start + en_selector - source_dispatch_start
                    )
                    dispatch[en_branch_at:en_branch_at + 2] = moved_selector.to_bytes(
                        2, "little"
                    )
                    relocated += 1
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
        ordinary_thai_routes={
            bank: tuple(_merge_ranges(spans)) for bank, spans in ordinary_routes.items()
        },
        ordinary_profile_page2_routes={
            bank: tuple(_merge_ranges(spans))
            for bank, spans in ordinary_profile_page2_routes.items()
        },
        ordinary_alternate_routes={
            bank: tuple(_merge_ranges(spans))
            for bank, spans in ordinary_alternate_routes.items()
        },
    )


def _merge_ranges(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge adjacent source-router ranges without widening their ownership."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
