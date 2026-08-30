"""A 65816 disassembler, built by inverting the assembler's own tables.

Reading the game's code is unavoidable when hooking it, and a disassembler that
shares tables with the assembler cannot drift from it. Register width is
tracked through `rep`/`sep` so immediates come out the right length; where the
width is genuinely unknown the output says so instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass

from .asm65816 import (
    ABS, ABSX, ABSY, ACC, BLK, DP, DPX, DPY, IABS, IABSX, IAL, IDP, IDX, IDY,
    ILDP, ILDY, IMM, IMP, LONG, LONGX, OPCODES, OPERAND_SIZE, REL, RELL, SR, SRY,
)

# opcode -> (mnemonic, mode)
DECODE: dict[int, tuple[str, str]] = {}
for _name, _modes in OPCODES.items():
    for _mode, _opcode in _modes.items():
        DECODE[_opcode] = (_name, _mode)

FORMAT = {
    IMP: "", ACC: " a",
    DP: " ${:02X}", DPX: " ${:02X},x", DPY: " ${:02X},y",
    IDP: " (${:02X})", IDX: " (${:02X},x)", IDY: " (${:02X}),y",
    ILDP: " [${:02X}]", ILDY: " [${:02X}],y",
    SR: " ${:02X},s", SRY: " (${:02X},s),y",
    ABS: " ${:04X}", ABSX: " ${:04X},x", ABSY: " ${:04X},y",
    IABS: " (${:04X})", IABSX: " (${:04X},x)", IAL: " [${:04X}]",
    LONG: " ${:06X}", LONGX: " ${:06X},x",
}

# Instructions that end a straight run of code.
TERMINAL = {"rts", "rtl", "rti", "jmp", "brl", "stp"}


@dataclass
class Line:
    pc: int
    raw: bytes
    text: str

    def __str__(self) -> str:
        return f"{self.pc:06X}  {self.raw.hex(' '):<14} {self.text}"


def disassemble(
    rom: bytes,
    start: int,
    count: int = 40,
    *,
    accumulator_16: bool | None = None,
    index_16: bool | None = None,
    stop_at_return: bool = True,
) -> list[Line]:
    """Decode instructions from `start`, following rep/sep for widths."""
    lines: list[Line] = []
    pc = start
    a16, i16 = accumulator_16, index_16

    for _ in range(count):
        opcode = rom[pc]
        entry = DECODE.get(opcode)
        if entry is None:
            lines.append(Line(pc, rom[pc : pc + 1], f".byte ${opcode:02X}"))
            pc += 1
            continue

        name, mode = entry
        if mode == IMM:
            # rep/sep always take one byte, whatever the register widths are.
            wide = False if name in {"rep", "sep"} else (
                a16 if name not in {"ldx", "ldy", "cpx", "cpy"} else i16
            )
            if wide is None:
                size = 1
                suffix = "  ; width unknown"
            else:
                size = 2 if wide else 1
                suffix = ""
        else:
            size = OPERAND_SIZE[mode]
            suffix = ""

        operand = rom[pc + 1 : pc + 1 + size]
        raw = rom[pc : pc + 1 + size]
        value = int.from_bytes(operand, "little") if operand else 0

        if mode == IMM:
            text = f"{name} #${value:0{size * 2}X}{suffix}"
        elif mode in (REL, RELL):
            width = 1 if mode == REL else 2
            offset = value - (1 << (width * 8)) if value >= 1 << (width * 8 - 1) else value
            target = (pc + 1 + width + offset) & 0xFFFF | (pc & 0xFF0000)
            text = f"{name} ${target & 0xFFFF:04X}"
        elif mode == BLK:
            text = f"{name} ${operand[1]:02X},${operand[0]:02X}"
        else:
            text = name + FORMAT[mode].format(value)

        lines.append(Line(pc, raw, text))

        if name == "rep":
            if value & 0x20:
                a16 = True
            if value & 0x10:
                i16 = True
        elif name == "sep":
            if value & 0x20:
                a16 = False
            if value & 0x10:
                i16 = False

        pc += 1 + size
        if stop_at_return and name in TERMINAL:
            break

    return lines
