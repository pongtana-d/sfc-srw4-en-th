"""Turning a translation string into pieces the encoder can lay down.

A translation line mixes three things: Thai text, engine control bytes written
as `<FC:05>`-style escapes, and inline icons written as `<AiL>`. This module
splits them apart without ever interpreting what a control byte means.

The one thing it does interpret is *how many operand bytes* a control lead
swallows, because that is what tells a bare `<09>` apart from the `09` that
sits inside `<FB:F1:0C>`. A bare low byte is not a control at all -- it is a
glyph of the game's own font that the translator kept -- and it must be folded
into one of our own glyph tokens, or the line would end up with two owners.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .tokens import EncodingError
from .contract import ENGINE_FLOOR, ENGINE_OPERANDS, NEWLINE_BYTE, RESERVED_FIRST

# Combining marks never start a cluster; they attach to the character before.
THAI_MARKS = frozenset("ัิีึืฺุู็่้๊๋์ํ๎")
THAI_RANGE = ("฀", "๿")

ESCAPE = re.compile(r"<([^<>]*)>")
HEX_ESCAPE = re.compile(r"^[0-9A-F]{2}(?::(?:[0-9A-F]{2})+)*$")
NAME_ESCAPE = re.compile(r"^NAME:\$([0-9A-Fa-f]{4})$")
END_ESCAPE = re.compile(r"^END([0-9A-F]{2})$")

ADAPTER_SPLIT = RESERVED_FIRST  # below this the adapter draws; next band is reserved
BRANCH_LEAD = (0xFC, 0x08)
# `$FB` normally inserts a runtime name and takes two operand bytes. When the
# second of them is $0C it takes two more: a sixteen-bit pointer into the same
# block. Those bytes are an address, never text, and they have to move when the
# block does.
POINTER_LEAD = 0xFB
POINTER_MARK = 0x0C
BRANCH_ENTRIES = 8  # one target per protagonist; short tables are reported, not guessed

# Some engines spell the same lead differently. The story script reads `$F8` as
# a lone control -- it stands in front of ordinary text 354 times -- while the
# catalog pool at $D2:8103 reads it as a two-byte "insert a value" command. One
# global table cannot be right for both, so each engine names its own.
ENGINES: dict[str, dict[int, int]] = {
    "story": {},
    "catalog": {0xF8: 1},
}


def follows(lead: int, operands: list[int]) -> str | None:
    """What a command carries *after* its declared operands.

    This is the one place that knows the shapes, because three walkers need
    the same answer: the tokenizer here, the reference renderer, and the
    repacker that has to rewrite the addresses. Getting it wrong is quiet --
    the bytes are simply read as text and drawn, or left behind when a block
    moves -- so the shapes are listed rather than inferred.

      "branch"   an eight-entry table of intra-block targets
      "address"  one sixteen-bit intra-block target
      "operand"  one more plain operand byte, not text
    """
    if lead == BRANCH_LEAD[0] and operands == [BRANCH_LEAD[1]]:
        return "branch"
    if lead == POINTER_LEAD and len(operands) == 2 and operands[1] == POINTER_MARK:
        return "address"
    # `$FC:07` closes the five-way condition chain in record 01_0811, and every
    # one of its targets lands inside that record, one byte past the text.
    if lead == 0xFC and operands == [0x07]:
        return "address"
    # `$FC:00:01` prefixes every line of the opening crawl, fifty times, always
    # the same three bytes. That is a command's shape, not a character.
    if lead == 0xFC and operands == [0x00]:
        return "operand"
    return None


@dataclass(frozen=True)
class Glyph:
    """One of our own glyphs: a Thai cluster, a character or an icon."""

    token: str


@dataclass(frozen=True)
class Engine:
    """Engine bytes that travel back to the stock engine untouched."""

    data: bytes


@dataclass(frozen=True)
class Pointer:
    """A sixteen-bit intra-block address carried inside a record."""

    target: int
    lead: int          # the engine byte that owns it, for the report


@dataclass(frozen=True)
class Branch:
    """The table of 16-bit intra-block targets that follows `$FC:08`.

    The targets are offsets into the block the message lives in, so they are
    only correct for the stock layout. Repacking has to rewrite them, which is
    why they are kept apart from ordinary engine bytes.

    A well-formed table has one target per protagonist. Targets are checked
    against the message offsets of the block, and anything that does not
    resolve is reported rather than quietly accepted, because a wrong table
    length would swallow the text that follows it.
    """

    targets: tuple[int, ...]


Piece = Glyph | Engine | Branch | Pointer


@dataclass(frozen=True)
class StockFolding:
    """A stock-font byte that had to be turned back into one of our glyphs.

    `after_command` says the byte sat immediately behind an engine command.
    That is where an operand we do not know about would show up, so those are
    told apart from bytes standing in the middle of text, which really are
    characters somebody forgot to translate.
    """

    byte: int
    token: str | None
    context: str
    after_command: bool = False


def load_stock_codes(path: Path) -> dict[int, str]:
    """code -> character, inverted from `renewal-stock.json`."""
    glyphs = json.loads(path.read_text())["glyphs"]
    codes: dict[int, str] = {}
    for char, entry in glyphs.items():
        code = entry["code"]
        if code in codes:
            raise EncodingError(
                f"stock code {code:#04x} claimed by both {codes[code]!r} and {char!r}"
            )
        codes[code] = char
    return codes


def segment(text: str) -> list[str]:
    """Split plain text into grapheme clusters (a base plus its marks)."""
    clusters: list[str] = []
    for ch in text:
        if ch in THAI_MARKS and clusters:
            clusters[-1] += ch
        else:
            clusters.append(ch)
    return clusters


def token_for(cluster: str) -> str:
    kind = "cluster" if THAI_RANGE[0] <= cluster[0] <= THAI_RANGE[1] else "char"
    return f"{kind}:{cluster}"


class Tokenizer:
    def __init__(
        self,
        icons: set[str],
        stock_codes: dict[int, str],
        *,
        engine: str = "story",
    ):
        self.icons = icons
        self.stock_codes = stock_codes
        if engine not in ENGINES:
            raise EncodingError(f"unknown engine {engine!r}")
        self.engine = engine
        self.operands = {**ENGINE_OPERANDS, **ENGINES[engine]}

    def tokenize(
        self,
        text: str,
        *,
        where: str = "",
        branch_range: range = range(0),
    ) -> "Tokenized":
        """Split a line into pieces, folding stray stock-font bytes into glyphs.

        `branch_range` is the span of offsets the block occupies. A `$FC:08`
        target outside it is reported: either the table is not eight entries
        long after all, or the record is damaged.
        """
        pieces: list[Piece] = []
        foldings: list[StockFolding] = []
        issues: list[str] = []
        state = _EngineState(branch_range=branch_range)

        for kind, value, context in self._scan(text, where):
            if kind == "text":
                if state.pending or state.branch is not None or state.pointer is not None:
                    issues.append(
                        f"text starts while {state.pending} operand bytes are owed"
                    )
                    state.pending = 0
                    state.close(pieces)
                for cluster in segment(value):
                    if cluster == "\n":
                        _append_engine(pieces, bytes([NEWLINE_BYTE]))
                    else:
                        pieces.append(Glyph(token_for(cluster)))
            elif kind == "icon":
                if state.pending or state.branch is not None or state.pointer is not None:
                    issues.append(f"icon <{value}> arrives while operand bytes are owed")
                    state.pending = 0
                    state.close(pieces)
                pieces.append(Glyph(f"icon:{value}"))
            else:  # bytes
                self._consume(value, state, pieces, foldings, context)

        state.close(pieces)
        if state.pointer is not None:
            issues.append("record ends in the middle of an address")
        if state.pending:
            issues.append(f"record ends with {state.pending} operand bytes missing")
        if state.short_table:
            issues.append("$FC:08 branch table is shorter than eight targets")
        if state.unresolved:
            issues.append(
                "branch targets outside the block: "
                + ", ".join(f"{t:#06x}" for t in state.unresolved)
            )
        return Tokenized(pieces, foldings, issues)

    def _scan(self, text: str, where: str):
        """Yield (kind, value, context) for text runs, icons and byte groups."""
        position = 0
        for match in ESCAPE.finditer(text):
            if match.start() > position:
                yield "text", text[position : match.start()], ""
            position = match.end()
            tag = match.group(1)
            context = text[max(0, match.start() - 20) : match.end() + 20]

            end = END_ESCAPE.match(tag)
            if end:
                yield "bytes", [int(end.group(1), 16)], context
                continue

            name = NAME_ESCAPE.match(tag)
            if name:
                pointer = int(name.group(1), 16)
                yield "bytes", [0xFB, pointer & 0xFF, pointer >> 8], context
                continue

            if HEX_ESCAPE.match(tag):
                values: list[int] = []
                for part in tag.split(":"):
                    values += [int(part[i : i + 2], 16) for i in range(0, len(part), 2)]
                yield "bytes", values, context
                continue

            if tag in self.icons:
                yield "icon", tag, context
                continue

            raise EncodingError(f"{where}: unknown escape <{tag}>")

        if position < len(text):
            yield "text", text[position:], ""

    def _consume(self, values, state, pieces, foldings, context) -> None:
        for byte in values:
            if state.branch is not None:
                state.feed_branch(byte, pieces)
                if state.branch is not None:
                    continue
                # The pair ended the table; fall through and re-read this byte.
                for spilled in state.take_spill():
                    self._plain(spilled, state, pieces, foldings, context)
                continue

            self._plain(byte, state, pieces, foldings, context)

    def _plain(self, byte, state, pieces, foldings, context) -> None:
        if state.pointer is not None:
            state.feed_pointer(byte, pieces)
            return

        if state.pending:
            _append_engine(pieces, bytes([byte]))
            state.pending -= 1
            state.operands.append(byte)
            if state.pending == 0:
                state.after_operands(pieces)
            return

        if byte >= ENGINE_FLOOR:
            _append_engine(pieces, bytes([byte]))
            state.lead = byte
            state.operands = []
            state.pending = self.operands.get(byte, 0)
            if state.pending == 0:
                state.lead = None
            return

        # A bare byte below the engine floor is a glyph of the stock font that
        # the translator kept. It has to become one of our glyphs, or the line
        # would be drawn by two owners at once.
        char = self.stock_codes.get(byte)
        token = token_for(char) if char is not None else None
        after_command = bool(pieces) and isinstance(pieces[-1], Engine)
        foldings.append(StockFolding(byte, token, context, after_command))
        if token is not None:
            pieces.append(Glyph(token))


@dataclass
class Tokenized:
    pieces: list[Piece]
    foldings: list[StockFolding]
    issues: list[str]


@dataclass
class _EngineState:
    branch_range: range = range(0)
    pending: int = 0
    lead: int | None = None
    operands: list[int] = field(default_factory=list)
    branch: list[int] | None = None
    pointer: list[int] | None = None
    pointer_lead: int = POINTER_LEAD
    targets: list[int] = field(default_factory=list)
    spill: list[int] = field(default_factory=list)
    unresolved: list[int] = field(default_factory=list)
    short_table: bool = False

    def after_operands(self, pieces: list[Piece]) -> None:
        """Decide whether this command carries anything after its operands."""
        lead, operands = self.lead, self.operands
        self.lead = None
        carries = follows(lead, operands)
        if carries == "branch":
            self.branch = []
        elif carries == "address":
            self.pointer = []
            self.pointer_lead = lead      # $FB and $FC both carry one
        elif carries == "operand":
            self.pending = 1        # lead is already cleared: no second helping

    def feed_pointer(self, byte: int, pieces: list[Piece]) -> None:
        """Collect the two bytes of an intra-block address."""
        assert self.pointer is not None
        self.pointer.append(byte)
        if len(self.pointer) < 2:
            return
        target = self.pointer[0] | self.pointer[1] << 8
        self.pointer = None
        if target not in self.branch_range:
            self.unresolved.append(target)
        pieces.append(Pointer(target, self.pointer_lead))

    def feed_branch(self, byte: int, pieces: list[Piece]) -> None:
        """Collect one byte of a branch table, closing it when it is full."""
        assert self.branch is not None
        self.branch.append(byte)
        if len(self.branch) < 2:
            return
        target = self.branch[0] | self.branch[1] << 8
        self.targets.append(target)
        if target not in self.branch_range:
            self.unresolved.append(target)
        self.branch = []
        if len(self.targets) == BRANCH_ENTRIES:
            self.close(pieces)

    def take_spill(self) -> list[int]:
        spilled, self.spill = self.spill, []
        return spilled

    def close(self, pieces: list[Piece]) -> None:
        """Emit the table collected so far, if any."""
        if self.branch:
            self.spill = list(self.branch) + self.spill
            self.short_table = True
        self.branch = None
        if self.targets:
            if len(self.targets) < BRANCH_ENTRIES:
                self.short_table = True
            pieces.append(Branch(tuple(self.targets)))
            self.targets = []


def _append_engine(pieces: list[Piece], data: bytes) -> None:
    if pieces and isinstance(pieces[-1], Engine):
        pieces[-1] = Engine(pieces[-1].data + data)
    else:
        pieces.append(Engine(data))
