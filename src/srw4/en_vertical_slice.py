"""EN dialogue fixture using whole-bank mirrors and FF Thai font pages."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .en_ff_router import install as install_router
from .proven.text.encoding import encode
from .proven.text.font import build_page


ROOT = Path(__file__).resolve().parents[2]
FONT = ROOT / "data" / "proven" / "font"
TRANSLATION = ROOT / "data" / "translations" / "script.th.json"
MASTER_TABLE_PC = 0x280000
BANK_SIZE = 0x10000
PAGE_PC = 0x3F4000                 # CPU $FF:4000
WIDTH_PC = 0x3F7000                # CPU $FF:7000


@dataclass(frozen=True)
class Fixture:
    name: str
    slot: int
    source_bank: int
    destination_bank: int
    record_address: int
    stream_address: int
    message_id: str


FIXTURES = (
    Fixture("map", 2, 0xF1, 0xEC, 0x246D, 0xCD4E, "02_17F1"),
    Fixture("battle", 20, 0xF7, 0xED, 0x4BF1, 0xDE79, "20_2DDA"),
)


def _ff_stream(text: str, layout: dict[str, object]) -> bytes:
    raw = encode(text, layout["codes"], layout["shorthand"], layout["phrases"])
    result = bytearray()
    for byte in raw:
        result.extend((0xC0, byte)) if byte < 0xEC else result.append(byte)
    return bytes(result) + b"\xFF"


def _place_fill(image: bytearray, pc: int, data: bytes, owner: str) -> None:
    if image[pc:pc + len(data)] != b"\xFF" * len(data):
        raise ValueError(f"{owner} overlaps non-fill bytes at {pc:#08x}")
    image[pc:pc + len(data)] = data


def _mirror_bank(image: bytearray, source_bank: int, destination_bank: int) -> None:
    source_pc = (source_bank & 0x3F) << 16
    destination_pc = (destination_bank & 0x3F) << 16
    _place_fill(image, destination_pc, bytes(image[source_pc:source_pc + BANK_SIZE]),
                f"story bank ${source_bank:02X} mirror")


def _redirect_within_mirror(image: bytearray, fixture: Fixture, stream: bytes) -> None:
    record_pc = ((fixture.destination_bank & 0x3F) << 16) + fixture.record_address
    stream_pc = ((fixture.destination_bank & 0x3F) << 16) + fixture.stream_address
    if image[stream_pc:stream_pc + len(stream)] != b"\xFF" * len(stream):
        raise ValueError(f"{fixture.name} stream region is not free in mirror bank")
    image[stream_pc:stream_pc + len(stream)] = stream
    # C2/EB reads this word only after setting CD to destination_bank.
    image[record_pc:record_pc + 5] = bytes((
        0xC2, 0xEB, fixture.stream_address & 0xFF,
        fixture.stream_address >> 8, fixture.destination_bank,
    ))
    master = MASTER_TABLE_PC + fixture.slot * 3
    image[master + 2] = fixture.destination_bank


def apply(image: bytes) -> tuple[bytes, dict[str, object]]:
    if len(image) != 0x400000:
        raise ValueError("EN dialogue fixture requires a 4 MiB ROM")
    layout = json.loads((FONT / "encoding.json").read_text(encoding="utf-8"))
    model = json.loads((FONT / "thai.json").read_text(encoding="utf-8"))
    messages = json.loads(TRANSLATION.read_text(encoding="utf-8"))["messages"]
    payload = bytearray(image)
    assets = build_page(model, layout)
    _place_fill(payload, PAGE_PC, assets["thai-page.bin"], "Thai page one")
    _place_fill(payload, WIDTH_PC, assets["thai-advance.bin"], "Thai page-one widths")

    report = []
    for fixture in FIXTURES:
        _mirror_bank(payload, fixture.source_bank, fixture.destination_bank)
        text = messages[fixture.message_id].replace("<ENDFF>", "").replace("<FB:1E80>", "")
        stream = _ff_stream(text, layout)
        _redirect_within_mirror(payload, fixture, stream)
        report.append({"name": fixture.name,
                       "from": f"${fixture.source_bank:02X}:{fixture.record_address:04X}",
                       "to": f"${fixture.destination_bank:02X}:{fixture.stream_address:04X}",
                       "stream_bytes": len(stream)})

    router = install_router(payload)
    return bytes(payload), {
        "scope": "EN map/event dialogue + battle quote router fixture",
        "mirrors": report,
        "router": {"pc": f"0x{router.origin:06X}", "bytes": router.bytes},
        "protocol": "C0 + glyph in mirrored private banks; C2 EB redirect",
    }
