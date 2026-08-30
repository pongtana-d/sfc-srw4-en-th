"""Deterministic dictionary codec for EN-ROM Thai dialogue streams.

The byte stream is decompressed to WRAM before the normal EN dialogue parser
runs, so control bytes and FF-page glyph leads remain unchanged. `$FA` is not
used by the authored dialogue-control corpus and therefore marks a dictionary
reference followed by its one-byte entry id.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


ESCAPE = 0xFA
MAX_ENTRIES = 128
MIN_PHRASE = 3
MAX_PHRASE = 12


@dataclass(frozen=True)
class DictionaryCodec:
    entries: tuple[bytes, ...]

    def encode(self, stream: bytes) -> bytes:
        if ESCAPE in stream:
            raise ValueError("raw dialogue stream uses reserved dictionary escape $FA")
        by_length = tuple(sorted(enumerate(self.entries), key=lambda item: -len(item[1])))
        output = bytearray()
        cursor = 0
        while cursor < len(stream):
            match = next(
                ((index, phrase) for index, phrase in by_length if stream.startswith(phrase, cursor)),
                None,
            )
            if match is None:
                output.append(stream[cursor])
                cursor += 1
            else:
                index, phrase = match
                output.extend((ESCAPE, index))
                cursor += len(phrase)
        return bytes(output)

    def decode(self, encoded: bytes) -> bytes:
        output = bytearray()
        cursor = 0
        while cursor < len(encoded):
            byte = encoded[cursor]
            if byte != ESCAPE:
                output.append(byte)
                cursor += 1
                continue
            if cursor + 1 >= len(encoded):
                raise ValueError("truncated dictionary reference")
            index = encoded[cursor + 1]
            if index >= len(self.entries):
                raise ValueError(f"dictionary reference {index} is out of range")
            output.extend(self.entries[index])
            cursor += 2
        return bytes(output)

    @property
    def payload_bytes(self) -> int:
        return sum(len(entry) for entry in self.entries)


def build(streams: list[bytes], entries: int = MAX_ENTRIES) -> DictionaryCodec:
    """Choose the highest-value non-overlapping phrases reproducibly."""
    if not 1 <= entries <= 256:
        raise ValueError("dictionary entry count must fit in one byte")
    if any(ESCAPE in stream for stream in streams):
        raise ValueError("raw dialogue stream uses reserved dictionary escape $FA")
    counts: Counter[bytes] = Counter()
    for stream in streams:
        for length in range(MIN_PHRASE, MAX_PHRASE + 1):
            counts.update(stream[index:index + length] for index in range(len(stream) - length + 1))
    ranked = sorted(
        counts.items(), key=lambda item: (-(len(item[0]) - 2) * item[1], -len(item[0]), item[0])
    )
    chosen: list[bytes] = []
    for phrase, count in ranked:
        if count < 2 or (len(phrase) - 2) * count <= 0:
            break
        if any(phrase in prior or prior in phrase for prior in chosen):
            continue
        chosen.append(phrase)
        if len(chosen) == entries:
            break
    return DictionaryCodec(tuple(chosen))
