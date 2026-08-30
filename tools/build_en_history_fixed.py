#!/usr/bin/env python3
"""Run the historical EN+Thai builder with repaired battle record mapping."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("history", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.report = args.report.resolve()
    sys.path.insert(0, str(args.history / "src"))
    sys.path.insert(0, str(args.history / "tools"))

    from srw4.repack import quote_tables
    from srw4.rom import RomError, cpu_to_pc
    import srw4.enstorybattle as battle
    import srw4.enstorytext as storytext
    import build_en_th_priority as builder
    jp_rom = (args.history / "rom" / "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc").read_bytes()

    def en_dispatch_size(base: bytes, block: dict) -> int:
        """Measure the EN-only dispatch records referenced by a block table."""
        master = 0x280000 + block["slot"] * 3
        start = base[master] | base[master + 1] << 8
        bank = base[master + 2]
        table_bytes = block["pointers"] * 2
        table_pc = cpu_to_pc(bank, start)
        table = base[table_pc:table_pc + table_bytes]
        records = []
        for at in range(0, table_bytes, 2):
            target = table[at] | table[at + 1] << 8
            target_pc = cpu_to_pc(bank, target)
            if base[target_pc:target_pc + 5] != b"\xFC\x01\xAB\x43\xFA":
                continue
            end = target + 6 + base[target_pc + 5] * 2
            records.append((target, end))
        expected_start = start + table_bytes
        if not records or min(target for target, _ in records) != expected_start:
            raise RomError(f"battle block {block['slot']}: cannot derive EN dispatch extent")
        return max(end for _, end in records) - expected_start

    # The old size planner counted JP dispatch bytes.  EN records contain an
    # extra two-byte opcode, so reserve their measured size before allocation.
    original_measure = storytext.measure

    def measure_with_en_dispatch(source, translations, compiler):
        report = original_measure(source, translations, compiler)
        document = json.loads(source.read_text())
        blocks = {row["slot"]: row for row in document["summary"]["blocks"]}
        adjusted = []
        for need in report.blocks:
            block = blocks[need.slot]
            if block.get("kind") == "record":
                delta = en_dispatch_size(builder.build_en_base(
                    builder.CLEAN.read_bytes(), builder.IPS.read_bytes(),
                    builder.EnBaseContract.load(builder.CONFIG),
                )[0], block) - block["record_bytes"]
                need = replace(need, bytes=need.bytes + delta)
            adjusted.append(need)
        return replace(report, blocks=tuple(adjusted))

    storytext.measure = measure_with_en_dispatch

    @dataclass(frozen=True)
    class Report:
        slot: int
        records: int
        bytes: int
        dispatch_targets: int

    def install(rom, compiler, source, translations, expected_base, *,
                slot, bank, table_address, end_address):
        def dispatch_records(data: bytes, *, english: bool):
            prefix = b"\xFC\x01\xAB\x43\xFA" if english else b"\xFC\x01\xFA"
            found = []
            cursor = 0
            while True:
                at = data.find(prefix, cursor)
                if at < 0:
                    return found
                count_at = at + len(prefix)
                count = data[count_at]
                first = count_at + 1
                if first + count * 2 > len(data):
                    return found
                pointers = []
                for index in range(count):
                    pointer_at = first + index * 2
                    pointers.append((pointer_at, data[pointer_at] | data[pointer_at + 1] << 8))
                found.append(pointers)
                cursor = first + count * 2

        document = json.loads(source.read_text())
        block = next(row for row in document["summary"]["blocks"] if row["slot"] == slot)
        text = json.loads(translations.read_text())["messages"]
        rows = sorted(
            (row for row in document["messages"] if row["block"] == slot),
            key=lambda row: int(row["offset"], 16),
        )
        table_bytes = block["pointers"] * 2
        master = 0x280000 + slot * 3
        source_start = expected_base[master] | expected_base[master + 1] << 8
        source_bank = expected_base[master + 2]
        source_pc = cpu_to_pc(source_bank, source_start)
        source_table = expected_base[source_pc:source_pc + table_bytes]
        dispatch_bytes = en_dispatch_size(expected_base, block)
        dispatch = bytearray(expected_base[
            source_pc + table_bytes:source_pc + table_bytes + dispatch_bytes
        ])

        cursor = table_address + table_bytes + len(dispatch)
        starts, streams = {}, {}
        for row in rows:
            stream = compiler.compile(text[row["id"]], where=row["id"]).encode_ff_stream()
            if cursor + len(stream) > end_address:
                raise RomError(f"battle block {slot} crosses its planned bank range")
            starts[int(row["offset"], 16)] = cursor
            streams[row["id"]] = stream
            cursor += len(stream)
        empty = cursor
        cursor += 1
        if cursor > end_address:
            raise RomError(f"battle block {slot} has no room for its terminator")

        source_by_target = {}
        for row in rows:
            source_offset = int(row["offset"], 16)
            for index in row["table_slots"]:
                at = index * 2
                target = source_table[at] | source_table[at + 1] << 8
                previous = source_by_target.setdefault(target, source_offset)
                if previous != source_offset:
                    raise RomError(f"battle block {slot}: conflicting table target {target:#06x}")

        jp_pc = int(block["pc"], 16)
        jp_dispatch = jp_rom[
            jp_pc + table_bytes:jp_pc + table_bytes + block["record_bytes"]
        ]
        jp_dispatch_start = (jp_pc & 0xFFFF) + table_bytes
        source_by_jp_position = {}
        row_by_source_offset = {int(row["offset"], 16): int(row["offset"], 16) for row in rows}
        for row in rows:
            source_offset = int(row["offset"], 16)
            for encoded_ref in row.get("record_refs", ()):
                relative = int(encoded_ref, 16) - jp_dispatch_start
                if not 0 <= relative <= len(jp_dispatch) - 2:
                    raise RomError(f"battle block {slot}: record ref {encoded_ref} escapes dispatch")
                source_by_jp_position[relative] = source_offset

        jp_records = dispatch_records(jp_dispatch, english=False)
        en_records = dispatch_records(dispatch, english=True)
        if len(en_records) > len(jp_records):
            raise RomError(f"battle block {slot}: EN has more dispatch records than JP")
        for record_index, en_record in enumerate(en_records):
            jp_record = jp_records[record_index]
            if len(jp_record) != len(en_record):
                raise RomError(
                    f"battle block {slot}: dispatch record {record_index} shape differs"
                )
            for (jp_at, jp_target), (_, en_target) in zip(jp_record, en_record):
                # The pointer value is the authoritative JP message address.
                # ``record_refs`` is useful audit metadata but is incomplete
                # for live EN routes such as slot 23's Freezing Beam quote.
                source_offset = row_by_source_offset.get(jp_target)
                if source_offset is None:
                    source_offset = source_by_jp_position.get(jp_at)
                if source_offset is None:
                    continue
                previous = source_by_target.setdefault(en_target, source_offset)
                if previous != source_offset:
                    raise RomError(f"battle block {slot}: conflicting EN target {en_target:#06x}")

        en_quotes = [pointer for record in en_records for pointer in record]

        rewritten = 0
        for at, target in en_quotes:
            source_offset = source_by_target.get(target)
            address = empty if source_offset is None else starts[source_offset]
            dispatch[at:at + 2] = address.to_bytes(2, "little")
            rewritten += 1

        # A record block's leading table is not an ordinary message-pointer
        # table.  Most entries select a dispatch record, which then selects a
        # quote.  Preserve that level of indirection while relocating both
        # layers; treating every entry as a message produced an empty dialogue
        # box for blocks whose extractor rows have no ``table_slots``.
        source_dispatch_start = source_start + table_bytes
        source_dispatch_end = source_dispatch_start + len(dispatch)
        moved_dispatch_start = table_address + table_bytes
        table = bytearray(table_bytes)
        for index in range(block["pointers"]):
            at = index * 2
            target = source_table[at] | source_table[at + 1] << 8
            if source_dispatch_start <= target < source_dispatch_end:
                moved = moved_dispatch_start + target - source_dispatch_start
            elif target in source_by_target:
                moved = starts[source_by_target[target]]
            elif target == 0:
                moved = empty
            else:
                raise RomError(
                    f"battle block {slot}: table target {target:#06x} is neither dispatch nor quote"
                )
            table[at:at + 2] = moved.to_bytes(2, "little")

        image = bytes(table + dispatch + b"".join(streams[row["id"]] for row in rows) + b"\xFF")
        rom.write_at(cpu_to_pc(bank, table_address), image)
        rom.write_at(master, bytes((table_address & 0xFF, table_address >> 8, bank)))
        return Report(slot, len(rows), len(image), rewritten)

    battle.install_battle_slot = install
    storytext.install_battle_slot = install
    return builder.main([
        "--full-story", "--output", str(args.output), "--report", str(args.report)
    ])


if __name__ == "__main__":
    raise SystemExit(main())
