"""Install the existing Thai opening crawl on the pinned English-combo ROM."""

from __future__ import annotations

from pathlib import Path

from .intro import EN_PAGES, HOOK_AT, HOOK_EXPECTED, build
from .pipeline import Pipeline
from .proven.assembler import pc_to_cpu


# Bank $ED is erased in the pinned EN ROM and excluded from the EN story
# repacker. Bank $EC is already owned by the Spirit-name renderer and assets.
# One bank holds five 0x3000 overlay resources plus the 0x800 hook.
EN_INTRO_REGION_START = 0x2D0000
EN_INTRO_REGION_END = 0x2DF800
EN_CRAWL_BANK = 0xFE
EN_TERMINATOR_TAIL = bytes.fromhex("FF FE 00 FE 01 FF")


class _LinearAllocator:
    """Allocate the fixed EN intro bank sequentially with explicit bounds."""

    def __init__(self) -> None:
        self.cursor = EN_INTRO_REGION_START

    def allocate(self, _region: str, _owner: str, size: int, *, align: int = 1) -> int:
        start = (self.cursor + align - 1) & ~(align - 1)
        end = start + size
        if end > EN_INTRO_REGION_END:
            raise ValueError("EN intro assets exceed their reserved bank-$ED region")
        self.cursor = end
        return start


def _place_fill(image: bytearray, pc: int, payload: bytes, owner: str) -> None:
    if image[pc:pc + len(payload)] != b"\xFF" * len(payload):
        raise ValueError(f"{owner} overlaps occupied EN ROM bytes at {pc:#08x}")
    image[pc:pc + len(payload)] = payload


def install(image: bytearray, clean: bytes, root: Path) -> dict[str, object]:
    """Compile all five translated pages and hook the stock EN crawl redraw."""
    if image[HOOK_AT:HOOK_AT + len(HOOK_EXPECTED)] != HOOK_EXPECTED:
        raise ValueError("EN intro hook source changed or is already occupied")
    if clean[HOOK_AT:HOOK_AT + len(HOOK_EXPECTED)] != HOOK_EXPECTED:
        raise ValueError("pinned EN ROM no longer matches the intro hook contract")
    for key, _filename, _start, _end, terminator in EN_PAGES:
        pc = ((EN_CRAWL_BANK & 0x3F) << 16) | terminator
        if clean[pc:pc + len(EN_TERMINATOR_TAIL)] != EN_TERMINATOR_TAIL:
            raise ValueError(f"active EN intro terminator changed for {key}")

    pipeline = Pipeline.from_rom_bytes(root, clean)
    result = build(
        root,
        clean,
        pipeline,
        _LinearAllocator(),
        page_specs=EN_PAGES,
        source_bank=EN_CRAWL_BANK,
    )
    for index, (pc, payload) in enumerate(result.writes):
        _place_fill(image, pc, payload, f"EN intro resource {index + 1}")
    _place_fill(image, result.hook_pc, result.hook_code, "EN intro hook body")

    hook_cpu = pc_to_cpu(result.hook_pc)
    image[HOOK_AT:HOOK_AT + len(HOOK_EXPECTED)] = bytes((
        0x5C,
        hook_cpu & 0xFF,
        hook_cpu >> 8 & 0xFF,
        hook_cpu >> 16,
        0xEA,
    ))
    return {
        **result.report,
        "source": "data/translations/intro*.th.json",
        "base": "pinned English-combo ROM",
        "region": f"0x{EN_INTRO_REGION_START:06X}-0x{EN_INTRO_REGION_END:06X}",
    }
