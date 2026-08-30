"""Build-time overlay for the five opening-crawl pages.

The crawl is not fed through either ordinary text parser.  At each verified
page terminator the hook copies a prebuilt 32x64 tilemap and private 1bpp tile
data into the same WRAM resources the stock crawl uploads on VBlank.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .asm65816 import assemble
from .pipeline import Pipeline
from .rom import RomError
from .text import Glyph as TextGlyph

HOOK_AT = 0x018F32
HOOK_EXPECTED = bytes.fromhex("B7 1A 29 FF 00")
TILE_BYTES = 0x2000
MAP_BYTES = 0x1000
TILE_BASE = 0x0100
PAGES = (
    # Runtime crawl pages are copied into the current CC script workspace.
    # Page 1 terminator is traced from sstate1 at $CC:9485; the older static
    # source address ($CC:EC41) is not reached after the current relocation.
    ("intro", "intro.th.json", 0x0CEA8E, 0x0CEC42, 0x9485),
    ("intro_page2", "intro-page2.th.json", 0x0CEC49, 0x0CEE39, 0xEE38),
    ("intro_page3", "intro-page3.th.json", 0x0CEE40, 0x0CEFBD, 0xEFBC),
    ("intro_page4", "intro-page4.th.json", 0x0CEFC4, 0x0CF05C, 0xF05B),
    ("intro_page5", "intro-page5.th.json", 0x0CF063, 0x0CF10C, 0xF10B),
)
# The EN patch keeps the original JP crawl records as inactive reference data,
# but its live English crawl is in bank $FE.  Source ranges below still verify
# that the existing Thai translations correspond to the original five pages;
# the final field is the measured terminator of each active EN record.
EN_PAGES = (
    ("intro", "intro.th.json", 0x0CEA8E, 0x0CEC42, 0x6A60),
    ("intro_page2", "intro-page2.th.json", 0x0CEC49, 0x0CEE39, 0x6D50),
    ("intro_page3", "intro-page3.th.json", 0x0CEE40, 0x0CEFBD, 0x6FAC),
    ("intro_page4", "intro-page4.th.json", 0x0CEFC4, 0x0CF05C, 0x708B),
    ("intro_page5", "intro-page5.th.json", 0x0CF063, 0x0CF10C, 0x71D7),
)


@dataclass(frozen=True)
class IntroBuild:
    writes: tuple[tuple[int, bytes], ...]
    hook_pc: int
    hook_code: bytes
    report: dict


def _cpu(pc: int) -> int:
    return ((0xC0 + (pc >> 16)) << 16) | (pc & 0xFFFF)


def _tile(rows: tuple[int, ...]) -> bytes:
    if len(rows) != 16:
        raise RomError("intro glyph must be 8x16")
    return bytes(value for row in rows[:8] for value in (row, row)) + bytes(16) + \
        bytes(value for row in rows[8:] for value in (row, row)) + bytes(16)


def _visible_tokens(pipeline: Pipeline, line: str, where: str) -> list[str]:
    result = pipeline.tokenizer.tokenize(line, where=where)
    if result.issues:
        raise RomError(f"{where}: " + "; ".join(result.issues))
    return [piece.token for piece in result.pieces if isinstance(piece, TextGlyph)]


def _page(root: Path, clean: bytes, pipeline: Pipeline, item: tuple[str, str, int, int, int]):
    key, filename, start, end, _terminator = item
    entry = json.loads((root / "data" / "translations" / filename).read_text())
    if int(entry["address"], 0) != start or int(entry["end"], 0) != end:
        raise RomError(f"{key}: verified source range changed")
    source = clean[start:end]
    expected_hash = entry.get("source_sha256")
    if expected_hash is not None:
        if hashlib.sha256(source).hexdigest() != expected_hash:
            raise RomError(f"{key}: verified source hash changed")
    elif source != bytes.fromhex(entry["source_hex"]):
        raise RomError(f"{key}: verified source bytes changed")
    # Unreferenced glyph slots must be transparent.  Filling them with $FF
    # sets every 4bpp plane and produces a solid palette-15 block if the stock
    # crawl briefly touches a spare tile during a page transition.
    tiles = bytearray(TILE_BYTES)
    tile_for: dict[str, int] = {}
    tilemap = bytearray(MAP_BYTES)
    # A visible final line commonly carries ``<FE><ENDFF>`` at its tail.  Keep
    # that line while removing only its terminator controls.
    lines = []
    for authored in str(entry["translation"]).splitlines():
        line = authored
        for ending in ("<FE><ENDFF>", "<ENDFF>", "<ENDF7>"):
            line = line.removesuffix(ending)
        if line:
            lines.append(line)
    if len(lines) > 16:
        raise RomError(f"{key}: overlay has over sixteen lines")
    for line_no, line in enumerate(lines):
        row = 8 + line_no * 3 if line_no < 8 else 32 + (line_no - 8) * 3
        column = 3
        for token in _visible_tokens(pipeline, line, f"{key}:{line_no}"):
            if token == "char: ":
                column += 1
                continue
            code = tile_for.setdefault(token, len(tile_for))
            if code >= TILE_BYTES // 64:
                raise RomError(f"{key}: needs too many private glyphs")
            if code * 64 == len(tile_for) * 64 - 64:
                tiles[code * 64 : code * 64 + 64] = _tile(pipeline.atlas[token].rows)
            if column >= 31:
                raise RomError(f"{key}: line exceeds 28 cells")
            tile = TILE_BASE + code * 2
            offset = (row * 32 + column) * 2
            tilemap[offset : offset + 2] = (0x2000 | tile).to_bytes(2, "little")
            tilemap[offset + 64 : offset + 66] = (0x2000 | tile + 1).to_bytes(2, "little")
            column += 1
    return bytes(tiles), bytes(tilemap), {"key": key, "lines": len(lines), "glyphs": len(tile_for), "source_sha256": hashlib.sha256(source).hexdigest()}


def _hook(
    origin: int,
    pages: list[tuple[int, int]],
    page_specs: tuple[tuple[str, str, int, int, int], ...] = PAGES,
    source_bank: int = 0xCC,
) -> bytes:
    body = [".a16", ".i16", "intro_overlay:", "  phx", "  phy", "  lda.l $00001C", f"  cmp #${source_bank:04X}", "  beq crawl", "  brl stock", "crawl:", "  lda.l $00001A"]
    for index, item in enumerate(page_specs):
        body += [f"  cmp #${item[4]:04X}", f"  bne next{index + 1}", f"  brl page{index + 1}", f"next{index + 1}:"]
    body += ["  brl stock"]
    for index, (tiles, tilemap) in enumerate(pages):
        body += [f"page{index + 1}:", "  ldx #$0000", f"map{index + 1}:", f"  lda.l ${_cpu(tilemap):06X},x", "  sta.l $7EA000,x", "  inx", "  inx", "  cpx #$1000", f"  bne map{index + 1}", "  ldx #$0000", f"tiles{index + 1}:", f"  lda.l ${_cpu(tiles):06X},x", "  sta.l $7F8000,x", "  inx", "  inx", "  cpx #$2000", f"  bne tiles{index + 1}", "  brl stock"]
    body += ["stock:", "  ply", "  plx", "  lda [$1A],y", "  and #$00FF", "  jml $818F37"]
    return assemble("\n".join(body), _cpu(origin)).code


def build(
    root: Path,
    clean: bytes,
    pipeline: Pipeline,
    allocation,
    *,
    page_specs: tuple[tuple[str, str, int, int, int], ...] = PAGES,
    source_bank: int = 0xCC,
) -> IntroBuild:
    writes: list[tuple[int, bytes]] = []
    pages: list[tuple[int, int]] = []
    report_pages = []
    for item in page_specs:
        tiles, tilemap, report = _page(root, clean, pipeline, item)
        tiles_at = allocation.allocate("spare", f"{item[0]}.tiles", len(tiles), align=0x100)
        map_at = allocation.allocate("spare", f"{item[0]}.map", len(tilemap), align=0x100)
        writes += [(tiles_at, tiles), (map_at, tilemap)]
        pages.append((tiles_at, map_at)); report_pages.append(report)
    hook_at = allocation.allocate("hook_trampolines", "intro.overlay", 0x800, align=0x100)
    hook = _hook(hook_at, pages, page_specs, source_bank)
    if len(hook) > 0x800:
        raise RomError("intro overlay hook exceeds reservation")
    return IntroBuild(tuple(writes), hook_at, hook, {"pages": report_pages, "hook": f"${_cpu(hook_at):06X}", "hook_bytes": len(hook)})
