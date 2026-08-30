"""Build-time Thai overlays for the five opening-crawl pages."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .allocation import Allocator
from .renderer65816 import Asm, pc_to_cpu
from .catalogs import Write
from .text.encoding import clusters, encode
from .text.renderer import Renderer
from .text.stock import encode_stock, mixed_segments


ORIGINAL_FONT = 0x2E8000
OVERLAY_TILE_BYTES = 0x2000
OVERLAY_MAP_BYTES = 0x1000
OVERLAY_TILE_BASE = 0x0100
INTRO_HOOK_SLOT = 0x400
INTRO_HOOK_PC = 0x018F32
INTRO_HOOK_SOURCE = bytes.fromhex("B7 1A 29 FF 00")

PAGES = (
    ("intro", "translations/intro.th.json", 0x0CEA8E, 0x0CEC42, 0xEC41),
    ("intro_page2", "translations/intro-page2.th.json", 0x0CEC49, 0x0CEE39, 0xEE38),
    ("intro_page3", "translations/intro-page3.th.json", 0x0CEE40, 0x0CEFBD, 0xEFBC),
    ("intro_page4", "translations/intro-page4.th.json", 0x0CEFC4, 0x0CF05C, 0xF05B),
    ("intro_page5", "translations/intro-page5.th.json", 0x0CF063, 0x0CF10C, 0xF10B),
)
CONTROL_RE = re.compile(r"<[^>]+>")


def _source(entry: dict[str, object], clean: bytes, start: int, end: int) -> bytes:
    if (int(str(entry["address"]), 0), int(str(entry["end"]), 0)) != (start, end):
        raise ValueError("intro translation address disagrees with the verified page")
    source = clean[start:end]
    if entry.get("source_sha256"):
        if hashlib.sha256(source).hexdigest() != str(entry["source_sha256"]):
            raise ValueError(f"intro source hash mismatch at {start:#x}")
    else:
        expected = bytes.fromhex(str(entry["source_hex"]))
        if source != expected:
            raise ValueError(f"intro source bytes mismatch at {start:#x}")
    return source


def _tile(rows: list[int]) -> bytes:
    return bytes(value for row in rows for value in (row, row)) + bytes(16)


def _build_page(
    root: Path, clean: bytes, entry: dict[str, object]
) -> tuple[bytes, bytes, dict[str, object]]:
    layout = json.loads((root / "font/encoding.json").read_text(encoding="utf-8"))
    model = json.loads((root / "font/thai.json").read_text(encoding="utf-8"))
    renderer = Renderer(model, layout)
    tile_bytes = bytearray(b"\xFF" * OVERLAY_TILE_BYTES)
    tile_by_cluster: dict[str, int] = {}
    lines = [
        CONTROL_RE.sub("", line)
        for line in str(entry["translation"]).splitlines()
        if line and not line.startswith("<END")
    ]
    if len(lines) > 16:
        raise ValueError("intro overlay has more than sixteen 8x16 lines")
    page = bytearray(OVERLAY_MAP_BYTES)
    for line_index, line in enumerate(lines):
        row = 8 + line_index * 3 if line_index < 8 else 32 + (line_index - 8) * 3
        column = 3
        for cluster in clusters(line):
            if cluster == " ":
                column += 1
                continue
            code = tile_by_cluster.get(cluster)
            if code is None:
                segments = mixed_segments(cluster)
                if len(segments) == 1 and segments[0] == (True, cluster):
                    stock_code = encode_stock(cluster)[0]
                    rows = list(clean[ORIGINAL_FONT + stock_code * 16:
                                      ORIGINAL_FONT + stock_code * 16 + 16])
                else:
                    encoded = encode(
                        cluster,
                        layout["codes"],
                        layout.get("shorthand"),
                        layout.get("phrases"),
                    )
                    rows = renderer.draw(encoded, 8)
                code = len(tile_by_cluster)
                if code >= OVERLAY_TILE_BYTES // 64:
                    raise ValueError("intro overlay needs more than 128 private glyphs")
                tile_by_cluster[cluster] = code
                at = code * 64
                tile_bytes[at:at + 32] = _tile(rows[:8])
                tile_bytes[at + 32:at + 64] = _tile(rows[8:16])
            if column >= 31:
                raise ValueError(f"intro line is too wide: {line!r}")
            tile_id = OVERLAY_TILE_BASE + code * 2
            offset = (row * 32 + column) * 2
            page[offset:offset + 2] = (0x2000 | tile_id).to_bytes(2, "little")
            page[offset + 64:offset + 66] = (0x2000 | tile_id + 1).to_bytes(
                2, "little"
            )
            column += 1
    return bytes(tile_bytes), bytes(page), {
        "translation": entry["translation"],
        "private_glyphs": len(tile_by_cluster),
        "overlay_lines": len(lines),
    }


def _emit_copy(asm: Asm, label: str, map_cpu: int, tiles_cpu: int) -> None:
    asm.label(label)
    asm.emit(0xA2, 0x00, 0x00)
    asm.label(f"map_{label}")
    asm.emit(0xBF, map_cpu & 0xFF, map_cpu >> 8 & 0xFF, map_cpu >> 16 & 0xFF)
    asm.emit(0x9F, 0x00, 0xA0, 0x7E, 0xE8, 0xE8, 0xE0, 0x00, 0x10)
    asm.branch(0xD0, f"map_{label}")
    asm.emit(0xA2, 0x00, 0x00)
    asm.label(f"tiles_{label}")
    asm.emit(0xBF, tiles_cpu & 0xFF, tiles_cpu >> 8 & 0xFF, tiles_cpu >> 16 & 0xFF)
    asm.emit(0x9F, 0x00, 0x80, 0x7F, 0xE8, 0xE8, 0xE0, 0x00, 0x20)
    asm.branch(0xD0, f"tiles_{label}")


def build_intro_hook(
    hook_pc: int, pages: list[tuple[int, int]]
) -> bytes:
    """Build the sole runtime hook that replaces each completed crawl page."""
    asm = Asm(hook_pc)
    asm.emit(0xDA, 0x5A, 0xA5, 0x1C, 0xC9, 0xCC, 0x00)
    asm.branch(0xF0, "crawl_bank")
    asm.brl("stock")
    asm.label("crawl_bank")
    asm.emit(0xA5, 0x1A)
    for index, (_, _, _, _, terminator) in enumerate(PAGES):
        asm.emit(0xC9, terminator & 0xFF, terminator >> 8)
        if index < 3:
            asm.branch(0xF0, f"page{index + 1}")
        else:
            asm.branch(0xD0, f"after_page{index + 1}")
            asm.brl(f"page{index + 1}")
            asm.label(f"after_page{index + 1}")
    asm.brl("stock")
    for index, (tiles_pc, map_pc) in enumerate(pages):
        _emit_copy(asm, f"page{index + 1}", pc_to_cpu(map_pc), pc_to_cpu(tiles_pc))
        if index + 1 < len(pages):
            asm.brl("stock")
    asm.label("stock")
    asm.emit(0x7A, 0xFA, 0xB7, 0x1A, 0x29, 0xFF, 0x00)
    asm.emit(0x5C, 0x37, 0x8F, 0x81)
    return asm.finish()


def build_intro_data(
    root: Path,
    clean: bytes,
    allocator: Allocator,
    *,
    translation_dir: Path | None = None,
) -> tuple[list[Write], dict[str, object], int]:
    """Allocate all five overlays and the final-copy hook."""
    hook = allocator.reserve("adapters", INTRO_HOOK_SLOT, "intro-final-hook", alignment=0x100)
    writes: list[Write] = []
    page_addresses: list[tuple[int, int]] = []
    reports: list[dict[str, object]] = []
    translation_dir = translation_dir or root / "translations"
    for key, relative, start, end, _ in PAGES:
        entry = json.loads(
            (translation_dir / Path(relative).name).read_text(encoding="utf-8")
        )
        source = _source(entry, clean, start, end)
        tiles, tilemap, report = _build_page(root, clean, entry)
        tile_alloc = allocator.reserve(
            "adapters", len(tiles), f"{key}-tiles", alignment=0x100
        )
        map_alloc = allocator.reserve(
            "adapters", len(tilemap), f"{key}-map", alignment=0x100
        )
        writes.extend((
            Write(tile_alloc.start, tiles, f"{key}-tiles", True),
            Write(map_alloc.start, tilemap, f"{key}-map", True),
        ))
        page_addresses.append((tile_alloc.start, map_alloc.start))
        reports.append({
            "key": key,
            "pc_start": f"0x{start:06X}",
            "pc_end": f"0x{end:06X}",
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "tiles_pc": f"0x{tile_alloc.start:06X}",
            "map_pc": f"0x{map_alloc.start:06X}",
            **report,
        })
    hook_payload = build_intro_hook(hook.start, page_addresses)
    if len(hook_payload) > INTRO_HOOK_SLOT:
        raise ValueError("intro final hook overflowed its declared slot")
    writes.append(Write(hook.start, hook_payload, "intro-final-hook", True))
    return writes, {
        "pages": reports,
        "hook_pc": f"0x{hook.start:06X}",
        "hook_bytes": len(hook_payload),
    }, hook.start
