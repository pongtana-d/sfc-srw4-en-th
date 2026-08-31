"""Compile translated EN dialogue text into private FF-page byte streams."""
from __future__ import annotations

import re
from collections.abc import Mapping

from .en_dialogue_font import SLOT
from .en_dialogue_codec import DictionaryCodec, build as build_dictionary
from .proven.text.encoding import encode


_TAG = re.compile(r"<[^>]+>")
# Corpus audit: largest current decoded record is 777 bytes (`48_17CE`).
# One 1 KiB WRAM buffer therefore has headroom without a magic allocation.
WRAM_BUFFER_BYTES = 0x400
# `renewal-memory-map.json` reserves $7E:FA36-$7E:FFA0 below the renderer
# state. This 1 KiB prefix is the decoder's record buffer.
WRAM_BUFFER_BASE = 0x7EFA36
WRAM_BUFFER_END = WRAM_BUFFER_BASE + WRAM_BUFFER_BYTES


def _control(tag: str) -> bytes:
    if tag == "<ENDFF>":
        return b"\xFF"
    if tag == "<ENDF7>":
        return b"\xF7"
    try:
        return bytes.fromhex(tag[1:-1].replace(":", ""))
    except ValueError as error:
        raise ValueError(f"invalid dialogue control {tag}") from error


def _plain(text: str, layout: Mapping[str, object]) -> bytes:
    codes = layout["codes"]
    shorthand = layout["shorthand"]
    phrases = layout["phrases"]
    output = bytearray()
    selected_page: int | None = None

    def emit(byte: int, page_lead: int = 0xC1) -> None:
        """Emit a glyph, selecting its private page for a fresh run."""
        nonlocal selected_page
        # C1 selects the Thai VWF page; C2 selects the supplemental Latin/icon
        # page. Direct bytes may follow only while that same page remains live.
        if selected_page != page_lead or byte >= 0xC0:
            output.extend((page_lead, byte))
            selected_page = page_lead
        else:
            output.append(byte)

    for line_index, line in enumerate(text.split("\n")):
        if line_index:
            output.append(0xF6)
            selected_page = None
        chunk: list[str] = []

        def flush() -> None:
            if not chunk:
                return
            for byte in encode("".join(chunk), codes, shorthand, phrases):
                # `$C0`-$EB overlap engine controls and must always be led.
                # The first byte of each render run also establishes the page.
                emit(byte)
            chunk.clear()

        for character in line:
            # Prefer the primary authored page whenever it owns the glyph.
            # SLOT also contains catalog-friendly copies of punctuation,
            # digits and spaces; choosing those first inserted a C2 page
            # switch in dialogue such as ``ชื่อ: ข้อความ`` and could leave
            # the battle/story renderer on the wrong page mid-run.
            slot = None if character in codes else SLOT.get(character)
            if slot is None:
                chunk.append(character)
                continue
            flush()
            emit(slot, 0xC2)
        flush()
    return bytes(output)


def compile_text(text: str, layout: Mapping[str, object]) -> bytes:
    """Compile one authored translation, retaining every explicit control."""
    output = bytearray()
    cursor = 0
    for match in _TAG.finditer(text):
        output.extend(_plain(text[cursor:match.start()], layout))
        output.extend(_control(match.group()))
        cursor = match.end()
    output.extend(_plain(text[cursor:], layout))
    if not output or output[-1] not in (0xF7, 0xFF):
        raise ValueError("dialogue stream has no authored terminator")
    return bytes(output)


def compile_ordinary_text(
    text: str, layout: Mapping[str, object]
) -> tuple[bytes, tuple[int, ...]]:
    """Compile a story record drawn by the ordinary/menu text engine.

    Block 48 (the Character Archives biographies) is stored in the story
    pointer graph, but the English ROM draws it through the ordinary callsite.
    That parser cannot consume the dialogue-only C1/C2 page leads.  Emit the
    same game-ready glyph ids without page leads and return a byte route mask:
    visible glyphs use the ordinary Thai renderer, while line/control bytes
    remain owned by the stock parser.
    """
    output = bytearray()
    routes: list[int] = []

    def visible(chunk: str) -> None:
        if not chunk:
            return
        for line_index, line in enumerate(chunk.split("\n")):
            if line_index:
                output.append(0xF6)
                routes.append(0)
            primary: list[str] = []

            def flush_primary() -> None:
                if not primary:
                    return
                encoded = encode(
                    "".join(primary),
                    layout["codes"],
                    layout["shorthand"],
                    layout["phrases"],
                )
                if any(byte >= 0xEC for byte in encoded):
                    raise ValueError("ordinary text glyph overlaps the engine control range")
                output.extend(encoded)
                routes.extend((1,) * len(encoded))
                primary.clear()

            for character in line:
                supplement = None if character in layout["codes"] else SLOT.get(character)
                if supplement is None:
                    primary.append(character)
                    continue
                flush_primary()
                output.append(supplement)
                routes.append(2)
            flush_primary()

    cursor = 0
    for match in _TAG.finditer(text):
        visible(text[cursor:match.start()])
        control = _control(match.group())
        output.extend(control)
        routes.extend((0,) * len(control))
        cursor = match.end()
    visible(text[cursor:])
    if not output or output[-1] not in (0xF7, 0xFF):
        raise ValueError("ordinary text stream has no authored terminator")
    return bytes(output), tuple(routes)


def compile_catalog(messages: Mapping[str, str], layout: Mapping[str, object]) -> tuple[dict[str, bytes], DictionaryCodec]:
    """Return independently decodable records and their shared dictionary."""
    streams = {message_id: compile_text(text, layout) for message_id, text in messages.items()}
    codec = build_dictionary(list(streams.values()))
    encoded = {message_id: codec.encode(stream) for message_id, stream in streams.items()}
    if any(codec.decode(encoded[key]) != stream for key, stream in streams.items()):
        raise ValueError("dictionary codec failed byte-for-byte verification")
    return encoded, codec


def max_decoded_size(messages: Mapping[str, str], layout: Mapping[str, object]) -> int:
    """Build-time guard for the single-record WRAM decoder buffer."""
    size = max(len(compile_text(text, layout)) for text in messages.values())
    if size > WRAM_BUFFER_BYTES:
        raise ValueError(f"decoded dialogue record {size} exceeds {WRAM_BUFFER_BYTES}-byte WRAM buffer")
    return size
