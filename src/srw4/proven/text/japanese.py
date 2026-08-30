"""Minimal decoder for verified SRW4 catalog strings.

The Core rewrite only needs Japanese decoding as a build-time assertion and
glossary lookup.  Runtime rendering never depends on this module.
"""

from __future__ import annotations

import json
from pathlib import Path


HIRAGANA = (
    "ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞ"
    "ただちぢっつづてでとどなにぬねのはばぱひびぴふぶぷへべぺほぼぽ"
    "まみむめもゃやゅゆょよらりるれろわをん"
)
KATAKANA = (
    "ァアィイゥウェエォオカガキギクグケゲコゴサザシジスズセゼソゾ"
    "タダチヂッツヅテデトドナニヌネノハバパヒビピフブプヘベペホボポ"
    "マミムメモャヤュユョヨラリルレロワヲン"
)


def direct_table() -> dict[int, str]:
    table: dict[int, str] = {0x00: "　"}
    for index, char in enumerate("ⅡⅢαΞνｒｍｋｂｘｔⅤ♥％／＋ー－～？！"):
        table[0x01 + index] = char
    for index, char in enumerate("ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"):
        table[0x16 + index] = char
    for index, char in enumerate("０１２３４５６７８９、・（）「」"):
        table[0x30 + index] = char
    for index, char in enumerate(HIRAGANA):
        table[0x40 + index] = char
    for index, char in enumerate(KATAKANA):
        table[0x90 + index] = char
    for index, char in enumerate("ヴヶ々＝。：．±『』○×"):
        table[0xE0 + index] = char
    return table


DIRECT = direct_table()


class CatalogDecoder:
    """Decode the direct/kanji/control subset used by catalog names."""

    def __init__(self, kanji_path: Path) -> None:
        raw = json.loads(kanji_path.read_text(encoding="utf-8"))
        self.kanji = {
            int(key, 16): str(value)
            for key, value in raw.items()
            if not key.startswith("_") and value
        }

    def decode(self, payload: bytes) -> str:
        out: list[str] = []
        cursor = 0
        while cursor < len(payload):
            value = payload[cursor]
            cursor += 1
            if 0xF0 <= value <= 0xF5:
                if cursor >= len(payload):
                    raise ValueError("truncated kanji code in catalog string")
                index = (value - 0xF0) * 0x100 + payload[cursor]
                cursor += 1
                if index not in self.kanji:
                    raise ValueError(f"unknown catalog kanji index {index:#06x}")
                out.append(self.kanji[index])
            elif value == 0xFB:
                if cursor + 2 > len(payload):
                    raise ValueError("truncated runtime-name control in catalog string")
                operand = payload[cursor:cursor + 2]
                cursor += 2
                out.append(f"<FB:{operand.hex().upper()}>")
            elif value == 0xFF:
                if cursor != len(payload):
                    raise ValueError("bytes follow catalog string terminator")
            elif value in DIRECT:
                out.append(DIRECT[value])
            else:
                raise ValueError(f"unsupported catalog byte {value:#04x}")
        return "".join(out)


def read_catalog_string(rom: bytes, bank_pc: int, pointer: int) -> bytes:
    """Read a terminated name while retaining multi-byte operands."""
    cursor = bank_pc + pointer
    payload = bytearray()
    for _ in range(64):
        value = rom[cursor]
        payload.append(value)
        cursor += 1
        if value == 0xFF:
            return bytes(payload)
        if 0xF0 <= value <= 0xF5:
            payload.append(rom[cursor])
            cursor += 1
        elif value == 0xFB:
            payload.extend(rom[cursor:cursor + 2])
            cursor += 2
    raise ValueError(f"unterminated catalog string at pointer {pointer:#06x}")
