"""Encoding pieces into the pilot stream, and reading one back.

The pilot stream is the coexistence form: our glyphs live at `$00`-`$D3` and
the stock engine's control bytes ride along raw from `$EC` upwards, operands
included. The gap at `$D4`-`$EB` is what makes that safe -- nothing has to be
escaped, and the adapter can decide byte by byte who owns what.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .text import (
    ADAPTER_SPLIT,
    ENGINE_FLOOR,
    BRANCH_LEAD,
    POINTER_LEAD,
    POINTER_MARK,
    Pointer,
    ENGINE_OPERANDS,
    Branch,
    Engine,
    Glyph,
    Piece,
)
from .contract import TERMINATORS
from .tokens import DIRECT_MAX, EXTENDED_LEAD, EncodingError, TokenMap


@dataclass(frozen=True)
class Relocation:
    """A 16-bit intra-block target that repacking has to rewrite."""

    offset: int          # byte offset of the field inside this record
    stock_target: int    # the offset it pointed at in the stock layout
    lead: int            # byte offset of the command that owns the field
    kind: str = "branch" # "branch" for a $FC:08 table, "pointer" for $FB xx 0C


@dataclass
class Record:
    data: bytes
    relocations: tuple[Relocation, ...] = ()
    glyphs: int = 0
    engine_bytes: int = 0

    def __len__(self) -> int:
        return len(self.data)

    @property
    def branch_tables(self) -> dict[int, int]:
        """lead offset -> entry count, for records carrying a `$FC:08` table.

        Only the verifier needs this. The adapter in the ROM never does: it
        hands `$FC:08` back to the stock engine, which walks its own table.
        """
        tables: dict[int, int] = {}
        for relocation in self.relocations:
            if relocation.kind == "branch":
                tables[relocation.lead] = tables.get(relocation.lead, 0) + 1
        return tables


def encode(pieces: list[Piece], token_map: TokenMap) -> Record:
    out = bytearray()
    relocations: list[Relocation] = []
    glyphs = 0
    engine_bytes = 0

    for piece in pieces:
        if isinstance(piece, Glyph):
            out += token_map.encode_glyph(piece.token)
            glyphs += 1
        elif isinstance(piece, Engine):
            out += piece.data
            engine_bytes += len(piece.data)
        elif isinstance(piece, Pointer):
            relocations.append(Relocation(len(out), piece.target, len(out), "pointer"))
            out += bytes([piece.target & 0xFF, piece.target >> 8])
            engine_bytes += 2
        elif isinstance(piece, Branch):
            lead = len(out) - 2  # the `$FC:08` was already emitted as engine bytes
            for target in piece.targets:
                relocations.append(Relocation(len(out), target, lead, "branch"))
                out += bytes([target & 0xFF, target >> 8])
                engine_bytes += 2
        else:  # pragma: no cover - the union is closed
            raise EncodingError(f"unknown piece: {piece!r}")

    return Record(bytes(out), tuple(relocations), glyphs, engine_bytes)


@dataclass
class Decoded:
    tokens: list[str] = field(default_factory=list)
    engine: list[bytes] = field(default_factory=list)
    terminator: int | None = None


def decode(
    data: bytes,
    token_map: TokenMap,
    branch_tables: dict[int, int] | None = None,
) -> Decoded:
    """Walk a pilot stream exactly the way the adapter will.

    Raises rather than reading on, so a malformed record fails the build
    instead of tearing a screen at runtime.
    """
    result = Decoded()
    index = 0
    length = len(data)

    while index < length:
        byte = data[index]

        if byte <= DIRECT_MAX:
            result.tokens.append(token_map.token_at(byte))
            index += 1
            continue

        if byte < ENGINE_FLOOR:
            raise EncodingError(
                f"byte {byte:#04x} at {index} is in the reserved gap $D0-$EB"
            )

        if EXTENDED_LEAD <= byte < EXTENDED_LEAD + token_map.extended_pages:
            if index + 1 >= length:
                raise EncodingError(f"extended lead {byte:#04x} at {index} has no index byte")
            page = byte - EXTENDED_LEAD
            glyph_id = (DIRECT_MAX + 1) + page * 0x100 + data[index + 1]
            result.tokens.append(token_map.token_at(glyph_id))
            index += 2
            continue

        entries = (branch_tables or {}).get(index)
        if entries is not None:
            if (byte, data[index + 1] if index + 1 < length else None) != BRANCH_LEAD:
                raise EncodingError(f"a branch table was declared at {index}, but no $FC:08 is there")
            table_end = index + 2 + entries * 2
            if table_end > length:
                raise EncodingError(f"$FC:08 branch table at {index} runs past the record")
            result.engine.append(data[index:table_end])
            index = table_end
            continue

        operands = ENGINE_OPERANDS.get(byte, 0)
        # `$FB` carries an address after its operands when the second of them
        # is $0C. Those two bytes are not text and must not be read as glyphs.
        if (
            byte == POINTER_LEAD
            and index + 2 < length
            and data[index + 2] == POINTER_MARK
        ):
            operands += 2
        end = index + 1 + operands
        if end > length:
            raise EncodingError(
                f"engine lead {byte:#04x} at {index} wants {operands} operand bytes, "
                f"only {length - index - 1} left"
            )
        result.engine.append(data[index:end])
        if byte in TERMINATORS:
            result.terminator = byte
        index = end

    return result


def adapter_owner(byte: int, *, extended_pages: int) -> str:
    """Who draws this byte: us, the stock engine, or nobody.

    The two-byte glyph leads are the engine's own escape, so the engine reads
    them and hands us the code it works out. They are ours all the same.
    """
    if byte < ADAPTER_SPLIT:
        return "renewal"
    if byte < ENGINE_FLOOR:
        return "nobody"
    if EXTENDED_LEAD <= byte < EXTENDED_LEAD + extended_pages:
        return "renewal"
    return "engine"
