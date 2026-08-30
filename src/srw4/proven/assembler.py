"""Generic 65816 emitter, independent of any particular renderer.

RENEWAL.md §16.1 requires the generic `Asm` and `pc_to_cpu` to live here, with
their own tests, before `renderer65816.py` can be deleted at cleanup.  Nothing
in this module knows what is being assembled: no renderer state, no font, no
hook.  `renderer65816.py` imports it so both systems emit through one assembler
and a fix to a branch fixup cannot land in only one of them.
"""

from __future__ import annotations


def pc_to_cpu(pc: int) -> int:
    return ((0xC0 + (pc >> 16)) << 16) | (pc & 0xFFFF)


class Asm:
    """Byte emitter with 8-bit branch labels."""

    def __init__(self, origin: int) -> None:
        self.origin = origin
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []
        self.long_fixups: list[tuple[int, str]] = []
        self.absolute_fixups: list[tuple[int, str]] = []

    def emit(self, *values: int) -> None:
        self.code.extend(values)

    def label(self, name: str) -> None:
        self.labels[name] = len(self.code)

    def branch(self, opcode: int, name: str) -> None:
        self.emit(opcode, 0)
        self.fixups.append((len(self.code) - 1, name))

    def brl(self, name: str) -> None:
        self.emit(0x82, 0, 0)
        self.long_fixups.append((len(self.code) - 2, name))

    def jsr(self, name: str) -> None:
        """Call a label in the same bank; the operand is absolute, not relative.

        A routine long enough to want a helper twice is long enough that
        duplicating the helper is the worse of the two costs.
        """
        self.emit(0x20, 0, 0)
        self.absolute_fixups.append((len(self.code) - 2, name))

    # Direct-page opcode -> its 24-bit absolute-long form.  There is no long
    # INC, DEC or STZ, so those three are open-coded at their call sites.
    LONG_FORM = {0xA5: 0xAF, 0x85: 0x8F, 0xC5: 0xCF, 0x65: 0x6F,
                 0xE5: 0xEF, 0x25: 0x2F, 0x05: 0x0F, 0x45: 0x4F}

    def var(self, opcode: int, address: int) -> None:
        """Reach renderer-owned private WRAM with an absolute-long operand."""
        self.emit(self.LONG_FORM[opcode],
                  address & 0xFF, (address >> 8) & 0xFF, (address >> 16) & 0xFF)

    def var_to_x(self, address: int) -> None:
        """Load a word from private WRAM through 16-bit A, then transfer to X."""
        self.var(0xA5, address)
        self.emit(0xAA)

    def var_to_x_preserving_a(self, address: int) -> None:
        """Load X from private WRAM without destroying a live 16-bit A value."""
        self.emit(0x48)                         # PHA
        self.var_to_x(address)
        self.emit(0x68)                         # PLA

    def var_to_x_from_m8(self, address: int) -> None:
        """Load a private word into 16-bit X while preserving an 8-bit A."""
        self.emit(0xC2, 0x20)
        self.var_to_x_preserving_a(address)
        self.emit(0xE2, 0x20)

    def clear_var(self, address: int) -> None:
        """Store zero to private WRAM; 65816 has no STZ absolute-long."""
        self.emit(0xA9, 0x00, 0x00)
        self.var(0x85, address)

    def long_index(self, opcode: int, address: int) -> None:
        self.emit(opcode, address & 0xFF, (address >> 8) & 0xFF, (address >> 16) & 0xFF)

    def finish(self) -> bytes:
        for at, name in self.fixups:
            delta = self.labels[name] - (at + 1)
            if not -128 <= delta <= 127:
                raise ValueError(f"branch to {name} out of range ({delta})")
            self.code[at] = delta & 0xFF
        for at, name in self.long_fixups:
            delta = self.labels[name] - (at + 2)
            self.code[at : at + 2] = (delta & 0xFFFF).to_bytes(2, "little")
        for at, name in self.absolute_fixups:
            target = self.origin + self.labels[name]
            if target >> 16 != self.origin >> 16:
                raise ValueError(f"{name} is in another bank; JSR cannot reach it")
            self.code[at : at + 2] = (target & 0xFFFF).to_bytes(2, "little")
        return bytes(self.code)


# --------------------------------------------------------- opcode scanning

# Instruction lengths, keyed by opcode, for the subset the Renewal emitters
# produce.  Values are either a fixed byte count including the opcode, or the
# string "m" / "x" for an immediate whose width follows the register size.
#
# The table is deliberately partial and `scan_opcodes` raises on anything it
# does not know.  A permissive decoder would be worse than none here: the whole
# point is to find a forbidden opcode, and a decoder that quietly resynchronises
# on unknown bytes can walk into the middle of an operand and report one that
# was never there - or miss one that was.
LENGTHS: dict[int, int | str] = {
    0x00: 2,                                              # BRK
    0x08: 1, 0x0B: 1, 0x28: 1, 0x2B: 1, 0x48: 1, 0x68: 1,  # stack
    0x5A: 1, 0x7A: 1, 0xDA: 1, 0xFA: 1,                   # PHY PLY PHX PLX
    0x8B: 1, 0xAB: 1,                                     # PHB PLB
    0x18: 1, 0x38: 1, 0xEA: 1, 0x6B: 1, 0x60: 1, 0x40: 1,
    0x1A: 1, 0x3A: 1, 0x0A: 1, 0x4A: 1, 0x2A: 1, 0x6A: 1,
    0xAA: 1, 0xA8: 1, 0x8A: 1, 0x98: 1, 0xBA: 1, 0x9A: 1,
    0xE8: 1, 0xC8: 1, 0xCA: 1, 0x88: 1, 0xEB: 1, 0x5B: 1,
    0xC2: 2, 0xE2: 2,                                     # REP SEP
    0x09: "m", 0x29: "m", 0x49: "m", 0x69: "m", 0x89: "m",
    0xA9: "m", 0xC9: "m", 0xE9: "m",
    0xA0: "x", 0xA2: "x", 0xC0: "x", 0xE0: "x",
    0x05: 2, 0x25: 2, 0x45: 2, 0x65: 2, 0x85: 2, 0xA5: 2,
    0xC5: 2, 0xE5: 2, 0x06: 2, 0x26: 2, 0x46: 2, 0x66: 2,
    0xC6: 2, 0xE6: 2, 0x64: 2, 0x84: 2, 0x86: 2, 0xA4: 2, 0xA6: 2,
    0x24: 2, 0xB7: 2, 0x97: 2, 0xA7: 2, 0x87: 2,
    0x0D: 3, 0x2D: 3, 0x4D: 3, 0x6D: 3, 0x8D: 3, 0xAD: 3,
    0xCD: 3, 0xED: 3, 0x9C: 3, 0x8C: 3, 0x8E: 3, 0xAC: 3, 0xAE: 3,
    0xCE: 3, 0xEE: 3, 0x2C: 3, 0x9D: 3, 0xBD: 3, 0x1C: 3,
    0x99: 3, 0xB9: 3,                                     # STA LDA abs,Y
    0x19: 3, 0x9E: 3, 0x1D: 3,                            # ORA abs,Y/abs,X, STZ abs,X
    0x0F: 4, 0x2F: 4, 0x4F: 4, 0x6F: 4, 0x8F: 4, 0xAF: 4,
    0xCF: 4, 0xEF: 4, 0x1F: 4, 0x3F: 4, 0x5F: 4, 0x7F: 4,
    0x9F: 4, 0xBF: 4, 0xDF: 4, 0xFF: 4,
    0x20: 3,                                              # JSR abs
    0x22: 4, 0x5C: 4, 0xDC: 3, 0x7C: 3, 0xFC: 3,
    0x4C: 3, 0x82: 3, 0x54: 3, 0x44: 3,
    0x10: 2, 0x30: 2, 0x50: 2, 0x70: 2, 0x90: 2, 0xB0: 2, 0xD0: 2, 0xF0: 2,
    0x80: 2,
}


class DecodeError(ValueError):
    """Raised when a routine cannot be walked instruction by instruction."""


def scan_opcodes(code: bytes, accumulator_16: bool = True,
                 index_16: bool = True) -> list[tuple[int, int]]:
    """Walk a routine and return every `(offset, opcode)` in it.

    Checking for a forbidden opcode by searching the raw bytes finds operands
    too: `STA $00420B` contains $0B, which is PHD, and the catalog adapter was
    rejected for an instruction it never had.  Walking the stream is the only
    way to tell an opcode from a byte that looks like one.

    Immediate widths follow the register sizes, so REP and SEP are tracked as
    they go; the caller says what the sizes were on entry.
    """
    found: list[tuple[int, int]] = []
    at = 0
    while at < len(code):
        opcode = code[at]
        found.append((at, opcode))
        length = LENGTHS.get(opcode)
        if length is None:
            raise DecodeError(
                f"opcode ${opcode:02X} at {at} is not in the length table; "
                "add it deliberately rather than letting the scan guess")
        if length == "m":
            length = 3 if accumulator_16 else 2
        elif length == "x":
            length = 3 if index_16 else 2
        if opcode in (0xC2, 0xE2):
            bits = code[at + 1]
            wide = opcode == 0xC2
            if bits & 0x20:
                accumulator_16 = wide
            if bits & 0x10:
                index_16 = wide
        at += length
    return found
