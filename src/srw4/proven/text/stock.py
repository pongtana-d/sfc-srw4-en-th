"""Policy and codec for runs rendered with the original fixed-width font."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
import json
from typing import Callable, Iterable


STOCK_REUSED_GLYPHS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZbkmxⅡν%")

_STOCK_NONSPACE = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "bkmx"
    "0123456789"
    "Ⅱν♥%/+~?!.,:()-"
)
_PRIMARY = STOCK_REUSED_GLYPHS | frozenset("♥")
_RUN_RE = re.compile(
    rf"[{re.escape(_STOCK_NONSPACE)}]+(?: +[{re.escape(_STOCK_NONSPACE)}]+)*"
)


def mixed_segments(text: str) -> list[tuple[bool, str]]:
    """Split visible text into ``(uses_stock_font, text)`` runs."""
    result: list[tuple[bool, str]] = []
    cursor = 0
    for match in _RUN_RE.finditer(text):
        run = match.group(0)
        if not any(char in _PRIMARY for char in run):
            continue
        if match.start() > cursor:
            result.append((False, text[cursor:match.start()]))
        result.append((True, run))
        cursor = match.end()
    if cursor < len(text):
        result.append((False, text[cursor:]))
    if not result:
        return [(False, text)] if text else []
    return [(stock, part) for stock, part in result if part]


def _direct_reverse() -> dict[str, int]:
    """Return the stock 8x16 direct-page mapping needed by Latin runs."""
    table: dict[int, str] = {0x00: "　"}
    for index, char in enumerate("ⅡⅢαΞνｒｍｋｂｘｔⅤ♥％／＋ー－～？！"):
        table[0x01 + index] = char
    for index, char in enumerate("ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"):
        table[0x16 + index] = char
    for index, char in enumerate("０１２３４５６７８９、・（）「」"):
        table[0x30 + index] = char
    for index, char in enumerate("ヴヶ々＝。：．±『』○×"):
        table[0xE0 + index] = char
    reverse = {char: code for code, char in table.items()}
    reverse.setdefault("－", 0x11)
    return reverse


DIRECT_REVERSE = _direct_reverse()
STOCK_OPERAND_HIGH = 0xFE
STATIC_RUNS = ("EN",)
LOCKED_RUNS = Path(__file__).resolve().parents[4] / "data" / "proven" / "stock-runs.json"


def stock_char_code(char: str) -> int:
    aliases = {
        "(": "（", ")": "）", ".": "．", ",": "、", ":": "：",
        "%": "％", "/": "／", "+": "＋", "-": "－", "~": "～",
        "?": "？", "!": "！",
    }
    if "A" <= char <= "Z" or "0" <= char <= "9" or char in "bkmx":
        char = chr(ord(char) + 0xFEE0)
    elif char == " ":
        char = "　"
    else:
        char = aliases.get(char, char)
    try:
        return DIRECT_REVERSE[char]
    except KeyError as error:
        raise ValueError(f"{char!r} has no glyph in the stock SRW4 font") from error


def encode_stock(run: str) -> bytes:
    return bytes(stock_char_code(char) for char in run)


def _translation_strings(translations: Path) -> Iterable[str]:
    def visit(value, field: str | None = None) -> Iterable[str]:
        if isinstance(value, dict):
            for key, child in value.items():
                yield from visit(child, str(key))
        elif isinstance(value, list):
            for child in value:
                yield from visit(child, field)
        elif isinstance(value, str) and field in {"translation", "target"}:
            yield value

    for path in sorted(translations.glob("*.json")):
        yield from visit(json.loads(path.read_text(encoding="utf-8")))


def discover_runs(translations: Path) -> list[str]:
    runs = set(STATIC_RUNS)
    runs.update(STOCK_REUSED_GLYPHS)
    runs.update(_STOCK_NONSPACE)
    runs.update(("♥", " "))
    token_re = re.compile(r"<[^>]*>")
    for text in _translation_strings(translations):
        for visible in token_re.split(text):
            runs.update(part for stock, part in mixed_segments(visible) if stock)
    ordered = sorted(runs)
    if len(ordered) > 256:
        raise ValueError(f"stock-run catalogue has {len(ordered)} entries; maximum is 256")
    return ordered


@dataclass(frozen=True)
class StockCatalog:
    runs: tuple[str, ...]

    @classmethod
    def discover(cls, translations: Path) -> "StockCatalog":
        return cls(tuple(discover_runs(translations)))

    @classmethod
    def load(cls, path: Path) -> "StockCatalog":
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("schema_version") != 1:
            raise ValueError("unsupported stock-run manifest schema")
        runs = tuple(str(run) for run in document["runs"])
        if runs != tuple(sorted(set(runs))):
            raise ValueError("stock-run manifest must be unique and sorted")
        if len(runs) > 256:
            raise ValueError("stock-run manifest exceeds 256 entries")
        return cls(runs)

    @classmethod
    def locked(cls) -> "StockCatalog":
        """Load the runtime-proven explicit catalogue used by production builds."""
        return cls.load(LOCKED_RUNS)

    @property
    def ids(self) -> dict[str, int]:
        return {run: index for index, run in enumerate(self.runs)}

    def control(self, run: str) -> bytes:
        ids = self.ids
        index = ids.get(run)
        if index is not None:
            return bytes((0xFB, index, STOCK_OPERAND_HIGH))
        payload = bytearray()
        for char in run:
            try:
                index = ids[char]
            except KeyError as error:
                raise ValueError(f"stock run {run!r} is absent from the catalogue") from error
            payload.extend((0xFB, index, STOCK_OPERAND_HIGH))
        return bytes(payload)

    def assets(
        self,
        string_pool_pc: int,
        *,
        encoder: Callable[[str], bytes] = encode_stock,
    ) -> tuple[bytes, bytes, list[dict[str, object]]]:
        """Build a 256-entry 24-bit table plus terminated stock strings."""
        table = bytearray(b"\xFF" * (256 * 3))
        pool = bytearray()
        report = []
        for index, run in enumerate(self.runs):
            pc = string_pool_pc + len(pool)
            cpu = ((0xC0 + (pc >> 16)) << 16) | (pc & 0xFFFF)
            encoded = encoder(run) + b"\xFF"
            table[index * 3:index * 3 + 3] = cpu.to_bytes(3, "little")
            pool.extend(encoded)
            report.append({"id": index, "text": run, "cpu": f"0x{cpu:06X}"})
        return bytes(table), bytes(pool), report


def encode_mixed(
    text: str,
    thai_encoder: Callable[[str], bytes],
    catalog: StockCatalog,
) -> tuple[bytes, int]:
    """Encode visible mixed text and return payload plus stock-font pixels."""
    payload = bytearray()
    stock_pixels = 0
    for stock, part in mixed_segments(text):
        if stock:
            payload.extend(catalog.control(part))
            stock_pixels += len(part) * 8
        else:
            payload.extend(thai_encoder(part))
    return bytes(payload), stock_pixels


def thai_first_segments(
    text: str, thai_chars: frozenset[str]
) -> list[tuple[bool, str]]:
    """Split text so only glyphs the Thai page lacks fall back to stock.

    `mixed_segments` grows a stock run across the digits and spaces that touch
    a reused glyph, which is what the pointer catalogues want. On a help line
    it makes the same number appear in two shapes: `100% 1` renders in the
    fixed-width font while the `1/3` two records away renders in the Thai one.
    Here a character is stock only when the Thai page has no glyph for it.
    """
    result: list[tuple[bool, str]] = []
    for part in re.split(r"(<[^>]*>)", text):
        if not part:
            continue
        if part.startswith("<"):
            result.append((False, part))
            continue
        for char in part:
            stock = char not in thai_chars
            if result and result[-1][0] == stock:
                result[-1] = (stock, result[-1][1] + char)
            else:
                result.append((stock, char))
    return result
