"""Isolated 65816 caller used to prove the generated renderer in an emulator."""

from __future__ import annotations

from .renderer65816 import (
    Asm,
    BATTLE_STATE_BASE,
    ORDINARY_STATE_BASE,
    pc_to_cpu,
)
from .text import encoding


TILEMAP_SENTINEL = 0x201C


def build_driver(
    text: str,
    layout: dict,
    advance: bytes,
    driver_pc: int,
    string_pc: int,
    renderer_pc: int,
    *,
    battle: bool = False,
) -> tuple[bytes, bytes, int]:
    payload = encoding.encode(
        text,
        layout["codes"],
        layout.get("shorthand"),
        layout.get("phrases"),
    ) + b"\xFF"
    width = sum(advance[code] for code in payload[:-1])
    guard_column = max(1, (width + 7) // 8) * 2

    asm = Asm(driver_pc)
    asm.emit(0x78)                             # SEI
    asm.emit(0xC2, 0x30)                       # REP #$30
    asm.emit(0xA9, 0x00, 0x00, 0x5B)          # LDA #0 / TCD
    asm.emit(0xE2, 0x20)                       # SEP #$20
    asm.emit(0xA9, 0x00, 0x48, 0xAB)          # DB = $00
    asm.emit(0x8D, 0x00, 0x42)                 # disable NMI
    asm.emit(0xA9, 0x55, 0x85, 0xFD)          # colour plane 1
    asm.emit(0xA9, 0xAA, 0x85, 0xFE)          # colour planes 2/3
    asm.emit(0xC2, 0x20)                       # REP #$20
    asm.emit(0xA9, 0x00, 0x00)
    state_base = BATTLE_STATE_BASE if battle else ORDINARY_STATE_BASE
    asm.emit(0x8F, state_base & 0xFF, (state_base >> 8) & 0xFF, state_base >> 16)

    for value, dp in (
        (0x0000 if battle else 0x03FE, 0xD0),
        (0x0002, 0x18),
        (0x0000, 0x2E),
    ):
        asm.emit(0xA9, value & 0xFF, value >> 8, 0x85, dp)

    asm.emit(0xA9, TILEMAP_SENTINEL & 0xFF, TILEMAP_SENTINEL >> 8)
    for column in range(0, guard_column + 1, 2):
        for address in (0x7E8000 + column, 0x7E8040 + column):
            asm.emit(0x8F, address & 0xFF, (address >> 8) & 0xFF, address >> 16)
    asm.emit(0xA9, 0x00, 0x00, 0x8D, 0x18, 0x0E)
    asm.emit(0xA2, 0x00, 0x00)                 # string index

    asm.label("next")
    asm.emit(0xE2, 0x20)
    asm.long_index(0xBF, pc_to_cpu(string_pc))
    asm.emit(0xC9, 0xFF)
    asm.branch(0xF0, "done")
    asm.emit(0xC2, 0x20, 0x29, 0xFF, 0x00)
    asm.emit(0xDA)                             # PHX
    target = pc_to_cpu(renderer_pc)
    asm.emit(0x22, target & 0xFF, (target >> 8) & 0xFF, target >> 16)
    asm.emit(0xFA)                             # PLX
    if not battle:
        asm.emit(0xDA, 0xA6, 0x18, 0xA5, 0x00)
        asm.long_index(0x9F, 0x7E8000)
        asm.emit(0xE6, 0x18, 0xE6, 0x18, 0xFA)
    asm.emit(0xE8)
    asm.brl("next")

    asm.label("done")
    asm.branch(0x80, "done")
    return asm.finish(), payload, width
