#!/usr/bin/env python3
"""Minimal 65816 disassembler for locating SRW4's text renderer.

Only what P4 needs: HiROM address translation, the full opcode table, and
explicit M/X width tracking (REP/SEP are followed; anything else leaves the
widths where the caller set them).  It is a reading aid, not an assembler.

    python3 tools/disasm65816.py C2:817A --count 60
    python3 tools/disasm65816.py --pc 0x02817A --count 60 --m 16 --x 16
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROM = Path(__file__).resolve().parent.parent / "rom" / (
    "Dai-4-ji Super Robot Taisen (Japan) (Rev 1).sfc"
)

# addressing modes: (name, operand length or None for M/X dependent)
IMP, IMM_M, IMM_X, IMM8, DP, DPX, DPY, IDP, IDPX, IDPY, IDPL, IDPLY = range(12)
ABS, ABSX, ABSY, ABSL, ABSLX, IND, INDX, IAL, REL, REL16, SR, SRY, BLK = range(12, 25)

MODE_LEN = {
    IMP: 0, IMM8: 1, DP: 1, DPX: 1, DPY: 1, IDP: 1, IDPX: 1, IDPY: 1,
    IDPL: 1, IDPLY: 1, ABS: 2, ABSX: 2, ABSY: 2, ABSL: 3, ABSLX: 3,
    IND: 2, INDX: 2, IAL: 2, REL: 1, REL16: 2, SR: 1, SRY: 1, BLK: 2,
}

FORMAT = {
    IMP: "", IMM8: "#${:02X}", DP: "${:02X}", DPX: "${:02X},X", DPY: "${:02X},Y",
    IDP: "(${:02X})", IDPX: "(${:02X},X)", IDPY: "(${:02X}),Y",
    IDPL: "[${:02X}]", IDPLY: "[${:02X}],Y",
    ABS: "${:04X}", ABSX: "${:04X},X", ABSY: "${:04X},Y",
    ABSL: "${:06X}", ABSLX: "${:06X},X",
    IND: "(${:04X})", INDX: "(${:04X},X)", IAL: "[${:04X}]",
    SR: "${:02X},S", SRY: "(${:02X},S),Y",
}

OPS: dict[int, tuple[str, int]] = {}


def _fill(entries: str) -> None:
    for line in entries.strip().splitlines():
        code, name, mode = line.split()
        OPS[int(code, 16)] = (name, globals()[mode])


_fill(
    """
00 BRK IMM8
01 ORA IDPX
02 COP IMM8
03 ORA SR
04 TSB DP
05 ORA DP
06 ASL DP
07 ORA IDPL
08 PHP IMP
09 ORA IMM_M
0A ASL IMP
0B PHD IMP
0C TSB ABS
0D ORA ABS
0E ASL ABS
0F ORA ABSL
10 BPL REL
11 ORA IDPY
12 ORA IDP
13 ORA SRY
14 TRB DP
15 ORA DPX
16 ASL DPX
17 ORA IDPLY
18 CLC IMP
19 ORA ABSY
1A INC IMP
1B TCS IMP
1C TRB ABS
1D ORA ABSX
1E ASL ABSX
1F ORA ABSLX
20 JSR ABS
21 AND IDPX
22 JSL ABSL
23 AND SR
24 BIT DP
25 AND DP
26 ROL DP
27 AND IDPL
28 PLP IMP
29 AND IMM_M
2A ROL IMP
2B PLD IMP
2C BIT ABS
2D AND ABS
2E ROL ABS
2F AND ABSL
30 BMI REL
31 AND IDPY
32 AND IDP
33 AND SRY
34 BIT DPX
35 AND DPX
36 ROL DPX
37 AND IDPLY
38 SEC IMP
39 AND ABSY
3A DEC IMP
3B TSC IMP
3C BIT ABSX
3D AND ABSX
3E ROL ABSX
3F AND ABSLX
40 RTI IMP
41 EOR IDPX
42 WDM IMM8
43 EOR SR
44 MVP BLK
45 EOR DP
46 LSR DP
47 EOR IDPL
48 PHA IMP
49 EOR IMM_M
4A LSR IMP
4B PHK IMP
4C JMP ABS
4D EOR ABS
4E LSR ABS
4F EOR ABSL
50 BVC REL
51 EOR IDPY
52 EOR IDP
53 EOR SRY
54 MVN BLK
55 EOR DPX
56 LSR DPX
57 EOR IDPLY
58 CLI IMP
59 EOR ABSY
5A PHY IMP
5B TCD IMP
5C JML ABSL
5D EOR ABSX
5E LSR ABSX
5F EOR ABSLX
60 RTS IMP
61 ADC IDPX
62 PER REL16
63 ADC SR
64 STZ DP
65 ADC DP
66 ROR DP
67 ADC IDPL
68 PLA IMP
69 ADC IMM_M
6A ROR IMP
6B RTL IMP
6C JMP IND
6D ADC ABS
6E ROR ABS
6F ADC ABSL
70 BVS REL
71 ADC IDPY
72 ADC IDP
73 ADC SRY
74 STZ DPX
75 ADC DPX
76 ROR DPX
77 ADC IDPLY
78 SEI IMP
79 ADC ABSY
7A PLY IMP
7B TDC IMP
7C JMP INDX
7D ADC ABSX
7E ROR ABSX
7F ADC ABSLX
80 BRA REL
81 STA IDPX
82 BRL REL16
83 STA SR
84 STY DP
85 STA DP
86 STX DP
87 STA IDPL
88 DEY IMP
89 BIT IMM_M
8A TXA IMP
8B PHB IMP
8C STY ABS
8D STA ABS
8E STX ABS
8F STA ABSL
90 BCC REL
91 STA IDPY
92 STA IDP
93 STA SRY
94 STY DPX
95 STA DPX
96 STX DPY
97 STA IDPLY
98 TYA IMP
99 STA ABSY
9A TXS IMP
9B TXY IMP
9C STZ ABS
9D STA ABSX
9E STZ ABSX
9F STA ABSLX
A0 LDY IMM_X
A1 LDA IDPX
A2 LDX IMM_X
A3 LDA SR
A4 LDY DP
A5 LDA DP
A6 LDX DP
A7 LDA IDPL
A8 TAY IMP
A9 LDA IMM_M
AA TAX IMP
AB PLB IMP
AC LDY ABS
AD LDA ABS
AE LDX ABS
AF LDA ABSL
B0 BCS REL
B1 LDA IDPY
B2 LDA IDP
B3 LDA SRY
B4 LDY DPX
B5 LDA DPX
B6 LDX DPY
B7 LDA IDPLY
B8 CLV IMP
B9 LDA ABSY
BA TSX IMP
BB TYX IMP
BC LDY ABSX
BD LDA ABSX
BE LDX ABSY
BF LDA ABSLX
C0 CPY IMM_X
C1 CMP IDPX
C2 REP IMM8
C3 CMP SR
C4 CPY DP
C5 CMP DP
C6 DEC DP
C7 CMP IDPL
C8 INY IMP
C9 CMP IMM_M
CA DEX IMP
CB WAI IMP
CC CPY ABS
CD CMP ABS
CE DEC ABS
CF CMP ABSL
D0 BNE REL
D1 CMP IDPY
D2 CMP IDP
D3 CMP SRY
D4 PEI DP
D5 CMP DPX
D6 DEC DPX
D7 CMP IDPLY
D8 CLD IMP
D9 CMP ABSY
DA PHX IMP
DB STP IMP
DC JML IAL
DD CMP ABSX
DE DEC ABSX
DF CMP ABSLX
E0 CPX IMM_X
E1 SBC IDPX
E2 SEP IMM8
E3 SBC SR
E4 CPX DP
E5 SBC DP
E6 INC DP
E7 SBC IDPL
E8 INX IMP
E9 SBC IMM_M
EA NOP IMP
EB XBA IMP
EC CPX ABS
ED SBC ABS
EE INC ABS
EF SBC ABSL
F0 BEQ REL
F1 SBC IDPY
F2 SBC IDP
F3 SBC SRY
F4 PEA ABS
F5 SBC DPX
F6 INC DPX
F7 SBC IDPLY
F8 SED IMP
F9 SBC ABSY
FA PLX IMP
FB XCE IMP
FC JSR INDX
FD SBC ABSX
FE INC ABSX
FF SBC ABSLX
"""
)


def to_pc(bank: int, addr: int) -> int:
    """HiROM CPU address -> file offset."""
    return ((bank & 0x3F) << 16) | addr


def to_cpu(pc: int) -> tuple[int, int]:
    return 0xC0 + (pc >> 16), pc & 0xFFFF


def disassemble(rom: bytes, pc: int, count: int, m16: bool, x16: bool):
    lines = []
    for _ in range(count):
        if pc >= len(rom):
            break
        opcode = rom[pc]
        name, mode = OPS.get(opcode, ("???", IMP))
        if mode == IMM_M:
            size = 2 if m16 else 1
        elif mode == IMM_X:
            size = 2 if x16 else 1
        else:
            size = MODE_LEN[mode]

        raw = rom[pc : pc + 1 + size]
        operand = int.from_bytes(raw[1:], "little") if size else 0
        bank, addr = to_cpu(pc)

        if mode in (IMM_M, IMM_X):
            text = f"#${operand:0{size * 2}X}"
        elif mode == REL:
            target = (addr + 2 + ((operand ^ 0x80) - 0x80)) & 0xFFFF
            text = f"${target:04X}"
        elif mode == REL16:
            target = (addr + 3 + ((operand ^ 0x8000) - 0x8000)) & 0xFFFF
            text = f"${target:04X}"
        elif mode == BLK:
            text = f"${raw[1]:02X},${raw[2]:02X}"
        else:
            text = FORMAT[mode].format(operand) if MODE_LEN.get(mode) else ""

        lines.append(
            f"${bank:02X}:{addr:04X}  {raw.hex(' '):<12}  {name} {text}".rstrip()
        )

        if opcode == 0xC2:  # REP
            if operand & 0x20:
                m16 = True
            if operand & 0x10:
                x16 = True
        elif opcode == 0xE2:  # SEP
            if operand & 0x20:
                m16 = False
            if operand & 0x10:
                x16 = False

        pc += 1 + size
        if name in ("RTS", "RTL", "RTI"):
            lines.append("")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("address", nargs="?", help="CPU address as BB:AAAA")
    parser.add_argument("--pc", type=lambda v: int(v, 0), help="file offset instead")
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--m", type=int, choices=(8, 16), default=8)
    parser.add_argument("--x", type=int, choices=(8, 16), default=8)
    parser.add_argument("--rom", type=Path, default=ROM)
    args = parser.parse_args()

    rom = args.rom.read_bytes()
    if args.pc is not None:
        pc = args.pc
    elif args.address:
        bank, _, addr = args.address.partition(":")
        pc = to_pc(int(bank, 16), int(addr, 16))
    else:
        parser.error("give BB:AAAA or --pc")

    for line in disassemble(rom, pc, args.count, args.m == 16, args.x == 16):
        print(line)


if __name__ == "__main__":
    main()
