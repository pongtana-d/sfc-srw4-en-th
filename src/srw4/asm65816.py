"""A small 65816 assembler.

The project builds everything from source with no outside tools, and the
blitter is no exception: an assembler we own is one less thing that has to be
installed for a build to reproduce, and it can refuse anything ambiguous rather
than guessing. It covers the addressing modes this project uses and raises on
anything it does not know, which is the behaviour we want -- a silent wrong
encoding in a blitter is very expensive to find later.

Register width matters on the 65816: `LDA #$00` is one byte of operand when the
accumulator is 8-bit and two when it is 16-bit. The assembler will not guess.
`.a8`/`.a16`/`.i8`/`.i16` declare the width, and an immediate assembled while
the width is unknown is an error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Addressing modes, named the way the 65816 manual names them.
IMP = "imp"        # implied
ACC = "acc"        # A
IMM = "imm"        # #$nn or #$nnnn, width from the register flags
DP = "dp"          # $nn
DPX = "dpx"        # $nn,x
DPY = "dpy"        # $nn,y
IDP = "idp"        # ($nn)
IDX = "idx"        # ($nn,x)
IDY = "idy"        # ($nn),y
ILDP = "ildp"      # [$nn]
ILDY = "ildy"      # [$nn],y
ABS = "abs"        # $nnnn
ABSX = "absx"      # $nnnn,x
ABSY = "absy"      # $nnnn,y
IABS = "iabs"      # ($nnnn)
IABSX = "iabsx"    # ($nnnn,x)
IAL = "ial"        # [$nnnn]
LONG = "long"      # $nnnnnn
LONGX = "longx"    # $nnnnnn,x
SR = "sr"          # $nn,s
SRY = "sry"        # ($nn,s),y
REL = "rel"        # branch, one byte
RELL = "rell"      # BRL/PER, two bytes
BLK = "blk"        # MVN/MVP

OPERAND_SIZE = {
    IMP: 0, ACC: 0,
    DP: 1, DPX: 1, DPY: 1, IDP: 1, IDX: 1, IDY: 1, ILDP: 1, ILDY: 1, SR: 1, SRY: 1,
    ABS: 2, ABSX: 2, ABSY: 2, IABS: 2, IABSX: 2, IAL: 2,
    LONG: 3, LONGX: 3,
    REL: 1, RELL: 2, BLK: 2,
}

# mnemonic -> {mode: opcode}
OPCODES: dict[str, dict[str, int]] = {
    "adc": {IMM: 0x69, DP: 0x65, DPX: 0x75, ABS: 0x6D, ABSX: 0x7D, ABSY: 0x79,
            LONG: 0x6F, LONGX: 0x7F, IDP: 0x72, IDX: 0x61, IDY: 0x71,
            ILDP: 0x67, ILDY: 0x77, SR: 0x63, SRY: 0x73},
    "and": {IMM: 0x29, DP: 0x25, DPX: 0x35, ABS: 0x2D, ABSX: 0x3D, ABSY: 0x39,
            LONG: 0x2F, LONGX: 0x3F, IDP: 0x32, IDX: 0x21, IDY: 0x31,
            ILDP: 0x27, ILDY: 0x37, SR: 0x23, SRY: 0x33},
    "asl": {ACC: 0x0A, DP: 0x06, DPX: 0x16, ABS: 0x0E, ABSX: 0x1E},
    "bcc": {REL: 0x90}, "bcs": {REL: 0xB0}, "beq": {REL: 0xF0}, "bmi": {REL: 0x30},
    "bne": {REL: 0xD0}, "bpl": {REL: 0x10}, "bra": {REL: 0x80}, "bvc": {REL: 0x50},
    "bvs": {REL: 0x70}, "brl": {RELL: 0x82},
    "bit": {IMM: 0x89, DP: 0x24, DPX: 0x34, ABS: 0x2C, ABSX: 0x3C},
    "clc": {IMP: 0x18}, "cld": {IMP: 0xD8}, "cli": {IMP: 0x58}, "clv": {IMP: 0xB8},
    "cmp": {IMM: 0xC9, DP: 0xC5, DPX: 0xD5, ABS: 0xCD, ABSX: 0xDD, ABSY: 0xD9,
            LONG: 0xCF, LONGX: 0xDF, IDP: 0xD2, IDX: 0xC1, IDY: 0xD1,
            ILDP: 0xC7, ILDY: 0xD7, SR: 0xC3, SRY: 0xD3},
    "cpx": {IMM: 0xE0, DP: 0xE4, ABS: 0xEC},
    "cpy": {IMM: 0xC0, DP: 0xC4, ABS: 0xCC},
    "dec": {ACC: 0x3A, DP: 0xC6, DPX: 0xD6, ABS: 0xCE, ABSX: 0xDE},
    "dex": {IMP: 0xCA}, "dey": {IMP: 0x88},
    "eor": {IMM: 0x49, DP: 0x45, DPX: 0x55, ABS: 0x4D, ABSX: 0x5D, ABSY: 0x59,
            LONG: 0x4F, LONGX: 0x5F, IDP: 0x52, IDX: 0x41, IDY: 0x51,
            ILDP: 0x47, ILDY: 0x57, SR: 0x43, SRY: 0x53},
    "inc": {ACC: 0x1A, DP: 0xE6, DPX: 0xF6, ABS: 0xEE, ABSX: 0xFE},
    "inx": {IMP: 0xE8}, "iny": {IMP: 0xC8},
    "jmp": {ABS: 0x4C, IABS: 0x6C, IABSX: 0x7C, LONG: 0x5C, IAL: 0xDC},
    "jml": {LONG: 0x5C, IAL: 0xDC},
    "jsr": {ABS: 0x20, IABSX: 0xFC},
    "jsl": {LONG: 0x22},
    "lda": {IMM: 0xA9, DP: 0xA5, DPX: 0xB5, ABS: 0xAD, ABSX: 0xBD, ABSY: 0xB9,
            LONG: 0xAF, LONGX: 0xBF, IDP: 0xB2, IDX: 0xA1, IDY: 0xB1,
            ILDP: 0xA7, ILDY: 0xB7, SR: 0xA3, SRY: 0xB3},
    "ldx": {IMM: 0xA2, DP: 0xA6, DPY: 0xB6, ABS: 0xAE, ABSY: 0xBE},
    "ldy": {IMM: 0xA0, DP: 0xA4, DPX: 0xB4, ABS: 0xAC, ABSX: 0xBC},
    "lsr": {ACC: 0x4A, DP: 0x46, DPX: 0x56, ABS: 0x4E, ABSX: 0x5E},
    "mvn": {BLK: 0x54}, "mvp": {BLK: 0x44},
    "nop": {IMP: 0xEA},
    "ora": {IMM: 0x09, DP: 0x05, DPX: 0x15, ABS: 0x0D, ABSX: 0x1D, ABSY: 0x19,
            LONG: 0x0F, LONGX: 0x1F, IDP: 0x12, IDX: 0x01, IDY: 0x11,
            ILDP: 0x07, ILDY: 0x17, SR: 0x03, SRY: 0x13},
    "pea": {ABS: 0xF4}, "pei": {DP: 0xD4}, "per": {RELL: 0x62},
    "pha": {IMP: 0x48}, "phb": {IMP: 0x8B}, "phd": {IMP: 0x0B}, "phk": {IMP: 0x4B},
    "php": {IMP: 0x08}, "phx": {IMP: 0xDA}, "phy": {IMP: 0x5A},
    "pla": {IMP: 0x68}, "plb": {IMP: 0xAB}, "pld": {IMP: 0x2B}, "plp": {IMP: 0x28},
    "plx": {IMP: 0xFA}, "ply": {IMP: 0x7A},
    "rep": {IMM: 0xC2}, "sep": {IMM: 0xE2},
    "rol": {ACC: 0x2A, DP: 0x26, DPX: 0x36, ABS: 0x2E, ABSX: 0x3E},
    "ror": {ACC: 0x6A, DP: 0x66, DPX: 0x76, ABS: 0x6E, ABSX: 0x7E},
    "rti": {IMP: 0x40}, "rtl": {IMP: 0x6B}, "rts": {IMP: 0x60},
    "sbc": {IMM: 0xE9, DP: 0xE5, DPX: 0xF5, ABS: 0xED, ABSX: 0xFD, ABSY: 0xF9,
            LONG: 0xEF, LONGX: 0xFF, IDP: 0xF2, IDX: 0xE1, IDY: 0xF1,
            ILDP: 0xE7, ILDY: 0xF7, SR: 0xE3, SRY: 0xF3},
    "sec": {IMP: 0x38}, "sed": {IMP: 0xF8}, "sei": {IMP: 0x78},
    "sta": {DP: 0x85, DPX: 0x95, ABS: 0x8D, ABSX: 0x9D, ABSY: 0x99,
            LONG: 0x8F, LONGX: 0x9F, IDP: 0x92, IDX: 0x81, IDY: 0x91,
            ILDP: 0x87, ILDY: 0x97, SR: 0x83, SRY: 0x93},
    "stp": {IMP: 0xDB},
    "stx": {DP: 0x86, DPY: 0x96, ABS: 0x8E},
    "sty": {DP: 0x84, DPX: 0x94, ABS: 0x8C},
    "stz": {DP: 0x64, DPX: 0x74, ABS: 0x9C, ABSX: 0x9E},
    "trb": {DP: 0x14, ABS: 0x1C},
    "tsb": {DP: 0x04, ABS: 0x0C},
    "tax": {IMP: 0xAA}, "tay": {IMP: 0xA8}, "tcd": {IMP: 0x5B}, "tcs": {IMP: 0x1B},
    "tdc": {IMP: 0x7B}, "tsc": {IMP: 0x3B}, "tsx": {IMP: 0xBA}, "txa": {IMP: 0x8A},
    "txs": {IMP: 0x9A}, "txy": {IMP: 0x9B}, "tya": {IMP: 0x98}, "tyx": {IMP: 0xBB},
    "wai": {IMP: 0xCB}, "wdm": {IMM: 0x42}, "xba": {IMP: 0xEB}, "xce": {IMP: 0xFB},
}

BRANCHES = {name for name, modes in OPCODES.items() if REL in modes}


class AsmError(Exception):
    """The source could not be assembled. Never a guess, always a stop."""


@dataclass
class Line:
    number: int
    text: str

    def fail(self, message: str) -> AsmError:
        return AsmError(f"line {self.number}: {message}\n    {self.text.strip()}")


@dataclass
class Assembled:
    code: bytes
    origin: int
    labels: dict[str, int]
    listing: list[tuple[int, bytes, str]] = field(default_factory=list)

    def label(self, name: str) -> int:
        try:
            return self.labels[name]
        except KeyError:
            raise AsmError(f"no such label: {name}") from None


COMMENT = re.compile(r";.*$")
LABEL_DEF = re.compile(r"^([A-Za-z_.][\w.]*):$")


class Assembler:
    """Two passes: measure every instruction, then emit with labels resolved."""

    def __init__(self, origin: int = 0x000000, constants: dict[str, int] | None = None):
        self.origin = origin
        # Addresses the caller fixes from outside -- the atlas base, the WRAM
        # context block -- so the same source assembles for the fixture ROM and
        # for the real one without editing it.
        self.constants = dict(constants or {})
        self.a16 = None      # None means "not declared yet"
        self.i16 = None

    # --- expressions ------------------------------------------------------

    def value(self, text: str, labels: dict[str, int], line: Line) -> int:
        text = text.strip()
        if not text:
            raise line.fail("empty expression")
        for operator in ("+", "-"):
            # Only split on a top-level operator, and only after the first
            # character so that "-1" still parses as a number.
            depth = 0
            for index in range(len(text) - 1, 0, -1):
                char = text[index]
                if char in ")]":
                    depth += 1
                elif char in "([":
                    depth -= 1
                elif char == operator and depth == 0:
                    left = self.value(text[:index], labels, line)
                    right = self.value(text[index + 1 :], labels, line)
                    return left + right if operator == "+" else left - right
        if text.startswith("<"):
            return self.value(text[1:], labels, line) & 0xFF
        if text.startswith(">"):
            return (self.value(text[1:], labels, line) >> 8) & 0xFF
        if text.startswith("^"):
            return (self.value(text[1:], labels, line) >> 16) & 0xFF
        try:
            if text.startswith("$"):
                return int(text[1:], 16)
            if text.startswith("%"):
                return int(text[1:], 2)
        except ValueError:
            raise line.fail(f"cannot read the number {text!r}") from None
        if text.lstrip("-").isdigit():
            return int(text)
        if text in labels:
            return labels[text]
        raise line.fail(f"unknown symbol {text!r}")

    # --- operand parsing --------------------------------------------------

    def parse_operand(self, operand: str, mnemonic: str, line: Line) -> tuple[str, str, int | None]:
        """Return (mode, expression, forced size) for one operand."""
        operand = operand.strip()
        if not operand or operand.lower() == "a":
            return (ACC if ACC in OPCODES[mnemonic] else IMP), "", None

        if operand.startswith("#"):
            return IMM, operand[1:], None

        forced = None
        body = operand
        # An explicit width, because "$12" could be direct page or absolute.
        if body[:2] in (".b", ".w", ".l") and (len(body) == 2 or body[2] in " \t"):
            pass
        match = re.match(r"^(\.[bwl])\s+(.*)$", body)
        if match:
            forced = {".b": 1, ".w": 2, ".l": 3}[match.group(1)]
            body = match.group(2).strip()

        if body.startswith("[") :
            inner, _, rest = body[1:].partition("]")
            rest = rest.strip().lower()
            if rest == ",y":
                return ILDY, inner, forced
            if rest == "":
                return (IAL if mnemonic == "jmp" else ILDP), inner, forced
            raise line.fail(f"cannot parse operand {operand!r}")

        if body.startswith("("):
            inner, _, rest = body[1:].rpartition(")")
            rest = rest.strip().lower()
            lowered = inner.strip().lower()
            if lowered.endswith(",s") and rest == ",y":
                return SRY, inner.strip()[:-2], forced
            if lowered.endswith(",x"):
                expression = inner.strip()[:-2]
                return (IABSX if mnemonic in ("jmp", "jsr") else IDX), expression, forced
            if rest == ",y":
                return IDY, inner, forced
            if rest == "":
                return (IABS if mnemonic == "jmp" else IDP), inner, forced
            raise line.fail(f"cannot parse operand {operand!r}")

        lowered = body.lower()
        if lowered.endswith(",x"):
            return ("indexed_x", body[:-2], forced)
        if lowered.endswith(",y"):
            return ("indexed_y", body[:-2], forced)
        if lowered.endswith(",s"):
            return SR, body[:-2], forced
        return ("direct", body, forced)

    def resolve_mode(
        self, mnemonic: str, mode: str, expression: str, forced: int | None,
        labels: dict[str, int], line: Line,
    ) -> tuple[str, int]:
        """Turn a shape like "indexed_x" into the real mode, given the value."""
        table = OPCODES[mnemonic]
        if BLK in table:
            return BLK, 0
        if mode in (IMM, ACC, IMP, IDP, IDX, IDY, ILDP, ILDY, IABS, IABSX, IAL, SR, SRY):
            return mode, 0
        if mnemonic in BRANCHES:
            return REL, 0
        if RELL in table and mode == "direct":
            return RELL, 0

        try:
            value = self.value(expression, labels, line)
            size = forced or (1 if value <= 0xFF else (2 if value <= 0xFFFF else 3))
        except AsmError:
            # A label defined further down. Assume the widest mode this
            # instruction has, so later passes can only make it shorter and the
            # sizing settles instead of oscillating.
            value = 0
            size = forced or 1
            if not forced:
                widest = {"direct": (LONG, ABS, DP), "indexed_x": (LONGX, ABSX, DPX),
                          "indexed_y": (ABSY, DPY)}[mode]
                for candidate in widest:
                    if candidate in table:
                        size = OPERAND_SIZE[candidate]
                        break
        candidates = {
            "direct": {1: DP, 2: ABS, 3: LONG},
            "indexed_x": {1: DPX, 2: ABSX, 3: LONGX},
            "indexed_y": {1: DPY, 2: ABSY, 3: None},
        }[mode]

        # A label inside this block is a full 24-bit address, but an
        # instruction with no long form -- JSR, most of them -- wants the
        # 16-bit part. Drop the bank when it is the bank we are assembling into.
        long_form = candidates.get(3)
        if (
            size == 3
            and (long_form is None or long_form not in table)
            and value >> 16 == self.origin >> 16
        ):
            value &= 0xFFFF
            size = forced or (1 if value <= 0xFF else 2)

        while size <= 3:
            chosen = candidates.get(size)
            if chosen and chosen in table:
                return chosen, value
            size += 1
        raise line.fail(f"{mnemonic.upper()} has no {mode} addressing mode")

    # --- passes -----------------------------------------------------------

    def assemble(self, source: str) -> Assembled:
        lines = [Line(number, text) for number, text in enumerate(source.splitlines(), 1)]
        labels: dict[str, int] = dict(self.constants)

        # Sizing passes: an instruction that refers to a label defined later
        # starts out at its widest, and may shrink once the label is known.
        # Repeat until the label table stops moving.
        for _ in range(8):
            self.a16 = self.i16 = None
            fresh: dict[str, int] = dict(self.constants)
            self._walk(lines, fresh, emit=False, known=labels)
            if fresh == labels:
                break
            labels = fresh
        else:
            raise AsmError("instruction sizes never settled; check for a label cycle")

        self.a16 = self.i16 = None
        code, listing = self._walk(lines, labels, emit=True)
        return Assembled(bytes(code), self.origin, labels, listing)

    def _walk(self, lines: list[Line], labels: dict[str, int], emit: bool, known=None):
        out = bytearray()
        listing: list[tuple[int, bytes, str]] = []
        address = self.origin

        for line in lines:
            text = COMMENT.sub("", line.text).strip()
            if not text:
                continue

            label = LABEL_DEF.match(text)
            if label:
                name = label.group(1)
                if not emit:
                    if name in self.constants:
                        raise line.fail(f"{name} is already a constant from the build")
                    if name in labels:
                        raise line.fail(f"label {name} defined twice")
                    labels[name] = address
                continue

            if text.lower().startswith(".org"):
                address = self.value(text.split(None, 1)[1], known or labels, line)
                if not out:
                    self.origin = address
                continue

            head, _, rest = text.partition(" ")
            head = head.lower()
            rest = rest.strip()

            width_suffix = None
            if "." in head and not head.startswith("."):
                head, _, suffix = head.partition(".")
                width_suffix = {"b": 1, "w": 2, "l": 3}.get(suffix)
                if width_suffix is None:
                    raise line.fail(f"unknown width suffix .{suffix}")

            if head.startswith("."):
                chunk = self._directive(head, rest, known or labels, line, address, emit)
                out += chunk
                address += len(chunk)
                if emit and chunk:
                    listing.append((address - len(chunk), bytes(chunk), text))
                continue

            if head not in OPCODES:
                raise line.fail(f"unknown instruction {head!r}")

            chunk = self._instruction(
                head, rest, known or labels, line, address, emit, width_suffix
            )
            out += chunk
            if emit:
                listing.append((address, bytes(chunk), text))
            address += len(chunk)

        return (out, listing) if emit else (out, listing)

    def _directive(self, head, rest, labels, line, address, emit) -> bytes:
        if head in (".a8", ".a16"):
            self.a16 = head == ".a16"
            return b""
        if head in (".i8", ".i16"):
            self.i16 = head == ".i16"
            return b""
        if head in (".db", ".byte", ".dw", ".word", ".dl", ".long"):
            width = {".db": 1, ".byte": 1, ".dw": 2, ".word": 2, ".dl": 3, ".long": 3}[head]
            out = bytearray()
            for part in rest.split(","):
                value = self.value(part, labels, line) if emit else 0
                out += value.to_bytes(width, "little")
            return bytes(out)
        if head in (".res", ".fill"):
            count, _, filler = rest.partition(",")
            value = self.value(filler, labels, line) if filler.strip() else 0
            return bytes([value & 0xFF]) * self.value(count, labels, line)
        raise line.fail(f"unknown directive {head!r}")

    def _instruction(self, mnemonic, operand, labels, line, address, emit, width=None) -> bytes:
        shape, expression, forced = self.parse_operand(operand, mnemonic, line)
        forced = forced or width
        encoded = self._encode(mnemonic, shape, expression, forced, labels, line, address, emit)
        self._track_widths(mnemonic, shape, expression, labels, line)
        return encoded

    def _track_widths(self, mnemonic, shape, expression, labels, line) -> None:
        """Follow SEP/REP so the source does not have to repeat itself.

        This reads the source top to bottom and cannot follow a branch, so a
        routine entered with a different width still needs .a8/.a16 to say so.
        """
        if mnemonic not in ("sep", "rep") or shape != IMM:
            return
        try:
            bits = self.value(expression, labels, line)
        except AsmError:
            return
        wide = mnemonic == "rep"
        if bits & 0x20:
            self.a16 = wide
        if bits & 0x10:
            self.i16 = wide

    def _encode(self, mnemonic, shape, expression, forced, labels, line, address, emit) -> bytes:
        mode, _ = self.resolve_mode(mnemonic, shape, expression, forced, labels, line)
        table = OPCODES[mnemonic]
        if mode not in table:
            raise line.fail(f"{mnemonic.upper()} has no {mode} addressing mode")
        opcode = table[mode]

        if mode in (IMP, ACC):
            return bytes([opcode])

        if mode == IMM:
            width = self._immediate_width(mnemonic, line)
            value = self.value(expression, labels, line) if emit else 0
            return bytes([opcode]) + (value & ((1 << (8 * width)) - 1)).to_bytes(width, "little")

        if mode == BLK:
            source_bank, _, destination = expression.partition(",")
            if not destination:
                raise line.fail("MVN/MVP need two banks")
            return bytes(
                [opcode, self.value(destination, labels, line) & 0xFF,
                 self.value(source_bank, labels, line) & 0xFF]
            )

        if mode in (REL, RELL):
            size = OPERAND_SIZE[mode]
            if not emit:
                return bytes(1 + size)
            target = self.value(expression, labels, line)
            offset = target - (address + 1 + size)
            limit = 0x80 if mode == REL else 0x8000
            if not -limit <= offset < limit:
                raise line.fail(f"branch out of range by {offset} bytes")
            return bytes([opcode]) + (offset & (limit * 2 - 1)).to_bytes(size, "little")

        size = OPERAND_SIZE[mode]
        value = self.value(expression, labels, line) if emit else 0
        limit = 1 << (8 * size)
        if emit and value >= limit and value >> 16 == self.origin >> 16 and size == 2:
            # Same-bank label reached by an instruction with no long form.
            value &= 0xFFFF
        if emit and value >= limit:
            raise line.fail(f"value {value:#x} does not fit in {size} byte(s)")
        return bytes([opcode]) + value.to_bytes(size, "little")

    def _immediate_width(self, mnemonic: str, line: Line) -> int:
        if mnemonic in ("rep", "sep", "wdm"):
            return 1
        if mnemonic in ("ldx", "ldy", "cpx", "cpy"):
            flag = self.i16
            which = "index registers"
        else:
            flag = self.a16
            which = "the accumulator"
        if flag is None:
            raise line.fail(
                f"the width of {which} is not declared here; add .a8/.a16 or .i8/.i16"
            )
        return 2 if flag else 1


def assemble(
    source: str, origin: int = 0x000000, constants: dict[str, int] | None = None
) -> Assembled:
    return Assembler(origin, constants).assemble(source)
