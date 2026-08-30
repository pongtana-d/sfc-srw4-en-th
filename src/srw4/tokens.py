"""The locked token map (`data/font/renewal-clusters.json`).

Direct ids are a released contract: a translation edit may append to
`extended`, but never renumber `direct` without bumping `encoding_version`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .contract import (
    DIRECT_MAX,
    DIRECT_SLOTS,
    ENCODING_VERSION,
    ENGINE_CODE_BASE,
    EXTENDED_LEAD,
    EXTENDED_PAGE_SIZE,
    EXTENDED_PAGES,
)
from .rom import RomError


class EncodingError(RomError):
    """A stream could not be built or decoded under the locked rules."""


@dataclass(frozen=True)
class TokenMap:
    encoding_version: int
    direct: tuple[str, ...]
    extended: tuple[str, ...]
    direct_slots: int
    extended_pages: int

    @classmethod
    def load(cls, path: Path) -> "TokenMap":
        doc = json.loads(path.read_text())
        direct = tuple(doc["direct"])
        extended = tuple(doc["extended"])
        slots = doc["direct_slots"]
        if len(direct) != slots:
            raise EncodingError(
                f"manifest declares {slots} direct slots but lists {len(direct)}"
            )
        if slots != DIRECT_SLOTS:
            raise EncodingError(f"direct block must be {DIRECT_SLOTS} slots, got {slots}")
        if doc["encoding_version"] != ENCODING_VERSION:
            raise EncodingError("manifest encoding version disagrees with text contract")
        if doc["extended_pages"] != EXTENDED_PAGES:
            raise EncodingError("manifest extended pages disagree with text contract")
        capacity = EXTENDED_PAGES * EXTENDED_PAGE_SIZE
        if len(extended) > capacity:
            raise EncodingError(
                f"{len(extended)} extended tokens exceed the {capacity}-slot block"
            )
        seen = set()
        for token in direct + extended:
            if token in seen:
                raise EncodingError(f"token listed twice in the manifest: {token}")
            seen.add(token)
            if ":" not in token or token.split(":", 1)[0] not in {"cluster", "char", "icon"}:
                raise EncodingError(f"malformed token in the manifest: {token!r}")
        return cls(doc["encoding_version"], direct, extended, slots, EXTENDED_PAGES)

    @property
    def tokens(self) -> tuple[str, ...]:
        return self.direct + self.extended

    def index(self, token: str) -> int:
        """Position in the flat token space; direct block first."""
        try:
            return self.direct.index(token)
        except ValueError:
            pass
        try:
            return len(self.direct) + self.extended.index(token)
        except ValueError:
            raise EncodingError(f"token not in the manifest: {token!r}") from None

    def __contains__(self, token: str) -> bool:
        return token in self.direct or token in self.extended

    def encode_glyph(self, token: str) -> bytes:
        """One byte for a direct token, lead + index for an extended one."""
        idx = self.index(token)
        if idx <= DIRECT_MAX:
            return bytes([idx])
        idx -= len(self.direct)
        page, offset = divmod(idx, EXTENDED_PAGE_SIZE)
        if page >= self.extended_pages:
            raise EncodingError(f"token {token!r} falls outside the extended block")
        return bytes([EXTENDED_LEAD + page, offset])

    def engine_code(self, token: str) -> int:
        """The sixteen-bit code the story engine will hand the rasteriser."""
        index = self.index(token)
        if index <= DIRECT_MAX:
            return index
        return ENGINE_CODE_BASE + index - len(self.direct)

    def from_engine_code(self, code: int) -> str:
        """The inverse: what the adapter has to do at runtime, in Python."""
        if code <= DIRECT_MAX:
            return self.token_at(code)
        return self.token_at(len(self.direct) + code - ENGINE_CODE_BASE)

    def token_at(self, index: int) -> str:
        tokens = self.tokens
        if index >= len(tokens):
            raise EncodingError(f"glyph id {index} is past the end of the token map")
        return tokens[index]
