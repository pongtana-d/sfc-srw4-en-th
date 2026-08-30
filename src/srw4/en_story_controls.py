"""Static English story-control dispatch evidence.

This module deliberately distinguishes a known inline operand from a handler
that may consume, redirect, or return through another stream.  It is a contract
for a future decoder, not a permissive decoder itself.
"""

from __future__ import annotations

from .rom import RomError

DISPATCH_TABLE_PC = 0x0199BC
DISPATCH_TABLE_CPU = "$C1:99BC"


def story_control_contract(rom: bytes) -> dict[str, object]:
    """Read the `$F5-$FF` indirect dispatch table from the EN base ROM."""
    if len(rom) <= DISPATCH_TABLE_PC + 0x20:
        raise RomError("ROM is too small for the English story dispatch table")
    dispatch = []
    for lead in range(0xF5, 0x100):
        index = (lead & 0x0F) * 2
        at = DISPATCH_TABLE_PC + index
        handler = rom[at] | rom[at + 1] << 8
        dispatch.append(
            {
                "lead": f"${lead:02X}",
                "handler": f"$C1:{handler:04X}",
                "inline_operand_policy": "handler-defined; do not consume speculatively",
            }
        )
    return {
        "schema": "srw4.en-story-control-contract.v1",
        "authority": "English-ROM disassembly: $C1:91F9-$C1:9244 and its indirect table.",
        "byte_classes": [
            {"range": "$00-$EB", "kind": "glyph"},
            {"range": "$EC-$EF", "kind": "artwork"},
            {"range": "$F0-$F4", "kind": "inline-control", "operand_bytes": 1},
            {"range": "$F5-$FF", "kind": "indirect-control", "dispatch_table": DISPATCH_TABLE_CPU},
        ],
        "dispatch": dispatch,
        "safety": [
            "F7 is an indirect control handler, not a terminator.",
            "FF is an indirect return handler; it is not a standalone record-boundary rule.",
            "A production decoder must leave handler-defined controls opaque until their full paths are proven.",
        ],
    }
