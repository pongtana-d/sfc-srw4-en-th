"""The story script: where its blocks live, and how to move them.

The game finds a block through a table of 52 twenty-four-bit pointers at
`$E8:0000`. Each block begins with its own table of sixteen-bit pointers, one
per message, and those are absolute inside the block's bank -- which is why a
block cannot simply be pushed anywhere: it has to land whole, in one bank, and
every pointer that names it has to be rewritten.

Three kinds of pointer name a message, and all three have to move together:

  the master table   $E8:0000, 24-bit, one per block
  the block's table  at the head of each block, 16-bit, one per message
  `$FC:08` branches  inside a record, 16-bit, one per protagonist
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .rom import RomError

MASTER_TABLE_PC = 0x280000
MASTER_SLOTS = 52
ENTRY_BYTES = 3
BANK_SIZE = 0x10000


def cpu_to_pc(bank: int, address: int) -> int:
    return ((bank & 0x3F) << 16) | address


def pc_to_cpu(pc: int) -> tuple[int, int]:
    return 0xC0 + (pc >> 16), pc & 0xFFFF


@dataclass(frozen=True)
class Block:
    slot: int
    bank: int          # CPU bank, $C0-$FF
    start: int         # offset of the block inside that bank
    end: int           # one past its last byte, still inside the bank
    pointers: int      # how many entries its own table has
    dispatch: int = 0  # bytes of fixed records between the table and the text


    @property
    def pc(self) -> int:
        return cpu_to_pc(self.bank, self.start)

    @property
    def size(self) -> int:
        return self.end - self.start

    @property
    def table_bytes(self) -> int:
        return self.pointers * 2

    @property
    def head_bytes(self) -> int:
        """Everything before the first message: the table and the dispatch area.

        Seven blocks ($EA-$EC, slots 20-26) carry a block of fixed records
        between the two -- 1,271 `$FC:01 $FA n` battle-quote tables. They are
        not messages, they are never translated, and they hold intra-block
        addresses, so they travel with the block byte for byte.
        """
        return self.table_bytes + self.dispatch

    @property
    def dispatch_start(self) -> int:
        return self.start + self.table_bytes

    @property
    def dispatch_end(self) -> int:
        return self.dispatch_start + self.dispatch


def read_master_table(rom: bytes) -> list[tuple[int, int]]:
    """The 52 entries as (bank, address). Unused slots read as $00:0000."""
    out = []
    for slot in range(MASTER_SLOTS):
        at = MASTER_TABLE_PC + slot * ENTRY_BYTES
        address = rom[at] | rom[at + 1] << 8
        out.append((rom[at + 2], address))
    return out


def load_blocks(rom: bytes, summary: list[dict]) -> list[Block]:
    """Blocks from the extraction summary, checked against the master table."""
    table = read_master_table(rom)
    blocks = []
    for entry in summary:
        if entry.get("kind") == "unused":
            continue
        slot = entry["slot"]
        pc = int(entry["pc"], 16)
        bank, address = pc_to_cpu(pc)
        if table[slot] != (bank, address):
            recorded = f"${table[slot][0]:02X}:{table[slot][1]:04X}"
            raise RomError(
                f"block {slot}: the master table says {recorded}, "
                f"the summary says ${bank:02X}:{address:04X}"
            )
        blocks.append(
            Block(
                slot,
                bank,
                address,
                int(entry["extent"], 16),
                entry["pointers"],
                entry.get("record_bytes", 0),
            )
        )
    return blocks


def read_pointers(rom: bytes, block: Block) -> list[int]:
    base = block.pc
    return [rom[base + i * 2] | rom[base + i * 2 + 1] << 8 for i in range(block.pointers)]


@dataclass(frozen=True)
class Move:
    """One block's journey: same bytes, new bank, every pointer rewritten."""

    block: Block
    to_bank: int
    to_start: int

    @property
    def to_pc(self) -> int:
        return cpu_to_pc(self.to_bank, self.to_start)

    @property
    def shift(self) -> int:
        return self.to_start - self.block.start

    def rebase(self, pointer: int) -> int | None:
        """A pointer inside the old block, as it must read in the new one.

        The end of a block is a legal target: the project quotes ranges one
        byte past the text, and empty table slots use that address. A pointer
        outside the block is not ours to move, so it comes back as None and the
        caller decides whether that is survivable.
        """
        if not self.block.start <= pointer <= self.block.end:
            return None
        moved = pointer + self.shift
        if not 0 <= moved < BANK_SIZE:
            raise RomError(f"block {self.block.slot}: moving pointer {pointer:#06x} leaves the bank")
        return moved


def plan_mirror(blocks: list[Block], first_bank: int) -> list[Move]:
    """Copy each script bank to a new one, keeping every offset where it is.

    Nothing inside a block changes, so the only rewrite is the bank byte in the
    master table. That makes it the honest way to prove the mechanism works
    before any text changes: the screen must come out identical.
    """
    banks = sorted({block.bank for block in blocks})
    mapping = {bank: first_bank + index for index, bank in enumerate(banks)}
    highest = max(mapping.values())
    if highest > 0xFF:
        raise RomError(f"the script needs {len(banks)} banks; {first_bank:#04x} is too high a start")
    return [Move(block, mapping[block.bank], block.start) for block in blocks]


def mirror_banks(rom, moves: list[Move], source: bytes) -> dict:
    """Copy whole banks, then point the master table at the copies.

    Copying only the blocks is not enough. The bytes between and after them
    belong to the game too, and a record that runs on past its terminator would
    then read fill instead of whatever used to sit there. A mirror has to be a
    mirror: the entire bank, byte for byte.
    """
    banks: dict[int, int] = {}
    for move in moves:
        if move.shift:
            raise RomError("mirroring cannot shift a block inside its bank")
        banks.setdefault(move.block.bank, move.to_bank)

    for source_bank, destination in banks.items():
        start = cpu_to_pc(source_bank, 0)
        rom.write_at(cpu_to_pc(destination, 0), source[start : start + BANK_SIZE])

    for move in moves:
        at = MASTER_TABLE_PC + move.block.slot * ENTRY_BYTES
        rom.write_at(
            at, bytes([move.to_start & 0xFF, move.to_start >> 8, move.to_bank])
        )

    return {
        "blocks": [
            {
                "slot": move.block.slot,
                "from": f"${move.block.bank:02X}:{move.block.start:04X}",
                "to": f"${move.to_bank:02X}:{move.to_start:04X}",
                "bytes": move.block.size,
                "pointers": move.block.pointers,
                "branch_fields": 0,
                "pointers_outside_the_block": 0,
            }
            for move in moves
        ],
        "moved_bytes": len(banks) * BANK_SIZE,
        "whole_banks": {f"${a:02X}": f"${b:02X}" for a, b in sorted(banks.items())},
    }


def apply(rom, moves: list[Move], source: bytes, relocations: dict[int, list[dict]] | None = None) -> dict:
    """Copy the blocks, rewrite their pointers, and repoint the master table."""
    report = []
    for move in moves:
        block = move.block
        # A block may run to the very end of its bank, where `end` is 0x10000;
        # that address cannot be OR-ed into a bank, so measure from the start.
        payload = bytearray(source[block.pc : block.pc + block.size])

        # The block's own table first: every message it names has moved by the
        # same amount as the block did.
        stranded = []
        for index in range(block.pointers):
            at = index * 2
            pointer = payload[at] | payload[at + 1] << 8
            if pointer == 0:
                continue
            moved = move.rebase(pointer)
            if moved is None:
                stranded.append(f"slot {index} -> {pointer:#06x}")
                continue
            payload[at] = moved & 0xFF
            payload[at + 1] = moved >> 8

        # Then any `$FC:08` branch table inside a record.
        rewritten = 0
        for entry in (relocations or {}).get(block.slot, []):
            at = entry["offset"] - block.start
            pointer = payload[at] | payload[at + 1] << 8
            moved = move.rebase(pointer)
            if moved is None:
                stranded.append(f"branch at {entry['offset']:#06x} -> {pointer:#06x}")
                continue
            payload[at] = moved & 0xFF
            payload[at + 1] = moved >> 8
            rewritten += 1

        if stranded and move.shift:
            raise RomError(
                f"block {block.slot} moves by {move.shift:#x} but "
                f"{len(stranded)} pointer(s) leave it: {', '.join(stranded[:4])}"
            )

        rom.write_at(move.to_pc, bytes(payload))

        at = MASTER_TABLE_PC + block.slot * ENTRY_BYTES
        rom.write_at(at, bytes([move.to_start & 0xFF, move.to_start >> 8, move.to_bank]))

        report.append(
            {
                "slot": block.slot,
                "from": f"${block.bank:02X}:{block.start:04X}",
                "to": f"${move.to_bank:02X}:{move.to_start:04X}",
                "bytes": block.size,
                "pointers": block.pointers,
                "branch_fields": rewritten,
                "pointers_outside_the_block": len(stranded),
            }
        )
    return {"blocks": report, "moved_bytes": sum(entry["bytes"] for entry in report)}


@dataclass
class PackedBlock:
    slot: int
    bank: int
    start: int
    size: int
    records: dict[str, int]      # message id -> new offset inside the bank
    passthrough: list[str]


def pack(
    blocks: list[Block],
    messages: list[dict],
    records: dict[str, "PackedRecord"],
    first_bank: int,
    last_bank: int,
) -> tuple[list[PackedBlock], dict[str, int]]:
    """Lay the rewritten records out in the expanded banks, one block at a time.

    A block has to land whole and inside one bank, because the pointers at its
    head are sixteen bits and name an address in that bank. Blocks are placed in
    order and a block that will not fit in what is left of a bank starts the
    next one.
    """
    by_block: dict[int, list[dict]] = {}
    for message in messages:
        by_block.setdefault(message["block"], []).append(message)

    packed: list[PackedBlock] = []
    offsets: dict[str, int] = {}
    bank = first_bank
    cursor = 0

    for block in sorted(blocks, key=lambda entry: entry.slot):
        head = block.head_bytes
        body = sum(len(records[m["id"]].data) for m in by_block.get(block.slot, []))
        size = head + body
        if size > BANK_SIZE:
            raise RomError(
                f"block {block.slot} needs {size} bytes and cannot fit in one bank"
            )
        if cursor + size > BANK_SIZE:
            bank += 1
            cursor = 0
        if bank > last_bank:
            raise RomError(
                f"the script needs more than banks ${first_bank:02X}-${last_bank:02X}"
            )

        start = cursor
        at = start + head
        placed: dict[str, int] = {}
        for message in by_block.get(block.slot, []):
            placed[message["id"]] = at
            offsets[message["id"]] = at
            at += len(records[message["id"]].data)

        packed.append(
            PackedBlock(
                slot=block.slot,
                bank=bank,
                start=start,
                size=size,
                records=placed,
                passthrough=[
                    m["id"] for m in by_block.get(block.slot, [])
                    if records[m["id"]].passthrough
                ],
            )
        )
        cursor = at

    return packed, offsets


@dataclass
class PackedRecord:
    """One message as it will sit in the ROM."""

    data: bytes
    passthrough: bool
    fields: tuple = ()           # (offset inside the record, stock target)


def load_summary(path: Path) -> list[dict]:
    return json.loads(path.read_text())["summary"]["blocks"]
