"""Thai player-name keyboard, presets and runtime source contracts."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .text.encoding import encode


INPUT_TABLES = (0x03A082, 0x03A106)
INPUT_TABLE_SIZE = 132
INPUT_KEY_CAPACITY = 127
INPUT_ROW_LENGTHS = (22, 22, 19)
DISPLAY_ROW_LENGTHS = (22, 22, 22, 22, 22, 17)
# Keep the 63-cell navigation contract after retiring obsolete ฃ/ฅ/ฦ glyphs.
# Prefer marks that are useful in modern names; mai chattawa remains available
# through precomposed text but does not consume a keyboard cell.
MARK_KEYS = ("ั", "ิ", "ี", "ึ", "ื", "็", "่", "้", "๊", "์", "ุ", "ู")
COMMAND_ROW = bytes((0xF0, 0xF1, 0xF2, 0x00, 0xF3))

PRESET_POINTERS = 0x128347
PRESET_POINTER_COUNT = 27
PRESET_POOL = (0x1288ED, 0x12897D)
PRESET_COUNT = 25

NAVIGATION_TABLES = (
    (0x03A1CA, bytes((0, 22, 44, 127, 132, 132, 132, 132))),
    (0x03A1D2, bytes((22, 22, 19, 5, 0, 0, 0))),
    (0x03A1D9, bytes((41, 44, 47, 52, 57, 63, 128, 129, 130, 131, 132, 0xFF))),
    (0x03A1E5, bytes((22, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))),
    (0x03A1F1, bytes((0, 131, 127, 128, 129, 130, 0, 5, 10, 15, 21, 0))),
    (0x03A1FD, bytes((3, 8, 13, 19, 22, 63, 128, 129, 130, 131, 132, 0xFF))),
    (0x03A209, bytes((0, 0, 0, 0, 0, 0xEA, 0, 0, 0, 0, 0, 0))),
    (0x03A215, bytes((127, 128, 129, 130, 131, 0, 44, 49, 54, 59, 62, 0))),
)

HITBOX_TABLE = 0x03A222
HITBOX_RECORDS = (
    (0x02, 0x05, 1, 5), (0x09, 0x05, 1, 10),
    (0x10, 0x05, 1, 15), (0x17, 0x05, 1, 22),
    (0x02, 0x08, 1, 27), (0x09, 0x08, 1, 32),
    (0x10, 0x08, 1, 37), (0x17, 0x08, 1, 44),
    (0x02, 0x0B, 1, 49), (0x09, 0x0B, 1, 54),
    (0x10, 0x0B, 1, 59), (0x17, 0x0B, 1, 63),
    (0x00, 0x00, 0, 127),
    (0x02, 0x17, 4, 128), (0x09, 0x17, 2, 129),
    (0x0C, 0x17, 2, 130), (0x10, 0x17, 3, 131),
    (0x18, 0x17, 3, 132),
)
HITBOX_PAYLOAD = (
    b"".join(bytes(record) for record in HITBOX_RECORDS) + b"\xFF\xFF\xFF"
)

GRID_FIELDS = (
    (0, 0, 0x0CAB5D, 5), (1, 0, 0x0CAB65, 5),
    (2, 0, 0x0CAB6D, 5), (3, 0, 0x0CAB75, 5),
    (4, 0, 0x0CAB7D, 5), (5, 0, 0x0CAB85, 5),
    (0, 5, 0x0CAB8D, 5), (1, 5, 0x0CAB95, 5),
    (2, 5, 0x0CAB9D, 5), (3, 5, 0x0CABA5, 5),
    (4, 5, 0x0CABAD, 5), (5, 5, 0x0CABB5, 5),
    (0, 10, 0x0CABBD, 5), (1, 10, 0x0CABC5, 5),
    (2, 10, 0x0CABCD, 5), (3, 10, 0x0CABD5, 5),
    (4, 10, 0x0CABDD, 5),
    (0, 15, 0x0CAC52, 7), (1, 15, 0x0CAC5C, 7),
    (2, 15, 0x0CAC66, 7), (3, 15, 0x0CAC70, 7),
    (4, 15, 0x0CAC7A, 7), (5, 10, 0x0CAC84, 6),
)

LABEL_FIELDS = {
    "keyboard": (0x0CABE5, 0x0CABE9),
    "space": (0x0CAC44, 0x0CAC48),
    "finish": (0x0CAC4B, 0x0CAC4F),
    "name": (0x0CAC96, 0x0CAC9A),
    "nickname": (0x0CAC9D, 0x0CACA1),
}
CONFIRMATION_FIELDS = (
    (
        "confirmation",
        0x0CAE1C,
        0x0CAE25,
        bytes.fromhex("52 8B 66 43 43 66 58 4A 14"),
    ),
    (
        "nickname_confirmation",
        0x0CAE67,
        0x0CAE70,
        bytes.fromhex("52 8B 66 43 43 66 58 4A 14"),
    ),
)

# Parser pointers have already advanced past the current byte.
FIXED_SOURCE_RANGES = {0xCC: ((0xAB5E, 0xABE3), (0xAC53, 0xAC8B))}
LABEL_SOURCE_RANGES = {
    0xCC: (
        (0xABE6, 0xABEA),
        (0xAC45, 0xAC50),
        (0xAC97, 0xACA2),
        # F8 06 emits six live name bytes while leaving the outer script
        # pointer at these three already-advanced positions.
        (0xACC2, 0xACC3),
        (0xACC5, 0xACC6),
        (0xACCA, 0xACCB),
        (0xAE1D, 0xAE26),
        (0xAE68, 0xAE71),
    )
}
RUNTIME_SOURCE_RANGES = {
    0x00: ((0x1009, 0x1054), (0x1FA8, 0x1FCB), (0x1FD2, 0x1FF3)),
    0x7E: ((0xDFE5, 0xE000),),
}

MARK_PREVIEW_CODES = dict(
    zip(
        ("ั", "ิ", "ี", "ึ", "ื", "็", "่", "้", "๊", "๋", "์", "ุ", "ู"),
        (
            0xD6,
            0xD7,
            0xD8,
            0xD9,
            0xDF,
            0xE2,
            0xE3,
            0xE4,
            0xE5,
            0xE6,
            0xE7,
            0xE8,
            0xE9,
        ),
    )
)
MARK_PREVIEW_RANGES = ((0xD6, 0xDA), (0xDF, 0xE0), (0xE2, 0xEA))


@dataclass(frozen=True)
class NamingWrite:
    pc: int
    payload: bytes
    owner: str


def preview_glyphs(model: dict) -> dict[int, bytes]:
    """Build centered standalone artwork for otherwise zero-width marks."""
    result: dict[int, bytes] = {}
    for token, code in MARK_PREVIEW_CODES.items():
        spec = model["marks"][token]
        rows = [0] * 16
        below = token in ("ุ", "ู")
        width = int(spec["width"])
        x = max(0, (8 - width) // 2)
        sprite = [int(value) >> x for value in spec["sprite"]]
        start = 9 if below else max(2, 7 - len(sprite))
        for index, value in enumerate(sprite):
            rows[start + index] |= value
        result[code] = bytes(rows)
    return result


def page_with_previews(page: bytes, model: dict) -> bytes:
    result = bytearray(page)
    for code, glyph in preview_glyphs(model).items():
        result[code * 16:code * 16 + 16] = glyph
    return bytes(result)


def fixed_advance(proportional: bytes, model: dict) -> bytes:
    result = bytearray(0 if value == 0 else 8 for value in proportional)
    for code in preview_glyphs(model):
        result[code] = 8
    return bytes(result)


def _encoded(text: str, layout: dict) -> bytes:
    return encode(
        text,
        layout["codes"],
        layout.get("shorthand"),
        layout.get("phrases"),
    )


def build_naming_data(
    root: Path, clean: bytes, *, translation_dir: Path | None = None
) -> tuple[list[NamingWrite], dict]:
    """Return asserted writes for the Thai keyboard and default names."""
    layout = json.loads((root / "font" / "encoding.json").read_text(encoding="utf-8"))
    translations = translation_dir or root / "translations"
    text = json.loads((translations / "naming-screen.th.json").read_text(encoding="utf-8"))
    codes = layout["codes"]

    base_tokens = [
        token for token, code in sorted(codes.items(), key=lambda item: item[1])
        if 0x01 <= code <= codes["ไ"]
    ]
    key_tokens = base_tokens + list(MARK_KEYS)
    if len(key_tokens) != sum(INPUT_ROW_LENGTHS):
        raise ValueError(f"Thai naming keyboard needs 63 keys, generated {len(key_tokens)}")
    key_codes = bytes(codes[token] for token in key_tokens)
    input_payload = key_codes + b"\xFF" * (INPUT_KEY_CAPACITY - len(key_codes)) + COMMAND_ROW
    if len(input_payload) != INPUT_TABLE_SIZE:
        raise ValueError("Thai naming input table has the wrong size")

    display_tokens = key_tokens + [" "] * (sum(DISPLAY_ROW_LENGTHS) - len(key_tokens))
    display_codes = bytes(
        MARK_PREVIEW_CODES[token] if token in MARK_PREVIEW_CODES else codes[token]
        for token in display_tokens
    )
    display_rows: list[bytes] = []
    cursor = 0
    for length in DISPLAY_ROW_LENGTHS:
        display_rows.append(display_codes[cursor:cursor + length])
        cursor += length

    writes: list[NamingWrite] = []
    for table in INPUT_TABLES:
        writes.append(NamingWrite(table, input_payload, f"naming-input:{table:06X}"))
    for start, payload in NAVIGATION_TABLES:
        writes.append(NamingWrite(start, payload, f"naming-navigation:{start:06X}"))
    writes.append(NamingWrite(HITBOX_TABLE, HITBOX_PAYLOAD, "naming-hitboxes"))
    for row, first, start, length in GRID_FIELDS:
        writes.append(NamingWrite(
            start,
            display_rows[row][first:first + length],
            f"naming-grid:{start:06X}",
        ))

    label_report = []
    for key, (start, end) in LABEL_FIELDS.items():
        translation = str(text["labels"][key])
        payload = _encoded(translation, layout)
        size = end - start
        if len(payload) > size:
            raise ValueError(f"naming label {key} needs {len(payload)} bytes; field holds {size}")
        payload += bytes((codes[" "],)) * (size - len(payload))
        writes.append(NamingWrite(start, payload, f"naming-label:{key}"))
        label_report.append({
            "key": key,
            "translation": translation,
            "pc": f"0x{start:06X}",
            "bytes": len(payload),
        })

    translation = str(text["labels"]["confirmation"])
    for key, start, end, expected in CONFIRMATION_FIELDS:
        if clean[start:end] != expected:
            raise ValueError(f"naming {key} source mismatch")
        payload = _encoded(translation, layout)
        size = end - start
        if len(payload) > size:
            raise ValueError(
                f"naming {key} needs {len(payload)} bytes; field holds {size}"
            )
        encoded_size = len(payload)
        payload += bytes((codes["<Pad>"],)) * (size - len(payload))
        writes.append(NamingWrite(start, payload, f"naming-label:{key}"))
        label_report.append({
            "key": key,
            "translation": translation,
            "pc": f"0x{start:06X}",
            "bytes": len(payload),
            "encoded_bytes": encoded_size,
            "source_hex": expected.hex(" ").upper(),
        })

    presets = text["presets"]
    if len(presets) != PRESET_COUNT:
        raise ValueError(f"naming screen needs {PRESET_COUNT} preset names")
    original_pointers = [
        int.from_bytes(clean[PRESET_POINTERS + 2 * index:PRESET_POINTERS + 2 * index + 2], "little")
        for index in range(PRESET_POINTER_COUNT)
    ]
    payload = bytearray()
    relocated: dict[int, int] = {}
    preset_report = []
    source_pc = PRESET_POOL[0]
    for index, entry in enumerate(presets):
        source = bytes.fromhex(str(entry["source_hex"]))
        if clean[source_pc:source_pc + len(source)] != source:
            raise ValueError(f"naming preset source mismatch for {entry['source']!r}")
        translated = _encoded(str(entry["translation"]), layout)
        byte_limit = 9 if index < 4 else 6
        if len(translated) > byte_limit:
            raise ValueError(
                f"naming preset {entry['translation']!r} needs {len(translated)} bytes; "
                f"buffer holds {byte_limit}"
            )
        pointer = (PRESET_POOL[0] + len(payload)) & 0xFFFF
        relocated[source_pc & 0xFFFF] = pointer
        payload.extend(translated)
        payload.append(0xFF)
        preset_report.append({
            "source": entry["source"],
            "translation": entry["translation"],
            "pointer": f"0x{pointer:04X}",
            "bytes": len(translated),
            "byte_limit": byte_limit,
        })
        source_pc += len(source)
    if source_pc != PRESET_POOL[1]:
        raise ValueError("naming preset source records do not fill the verified pool")

    pointer_payload = b"".join(
        relocated[pointer].to_bytes(2, "little") for pointer in original_pointers
    )
    used = len(payload)
    capacity = PRESET_POOL[1] - PRESET_POOL[0]
    if used > capacity:
        raise ValueError(f"Thai naming presets need {used} bytes; pool holds {capacity}")
    payload.extend(b"\xFF" * (capacity - used))
    writes.append(NamingWrite(PRESET_POINTERS, pointer_payload, "naming-preset-pointers"))
    writes.append(NamingWrite(PRESET_POOL[0], bytes(payload), "naming-preset-pool"))

    for write in writes:
        if len(clean[write.pc:write.pc + len(write.payload)]) != len(write.payload):
            raise ValueError(f"naming write outside clean ROM: {write.owner}")

    return writes, {
        "keys": len(key_tokens),
        "row_lengths": list(INPUT_ROW_LENGTHS),
        "input_tables": [f"0x{value:06X}" for value in INPUT_TABLES],
        "labels": label_report,
        "presets": preset_report,
        "pools": [{
            "name": "naming_preset_pool",
            "start": f"0x{PRESET_POOL[0]:06X}",
            "end": f"0x{PRESET_POOL[1]:06X}",
            "capacity": capacity,
            "used": used,
        }],
    }
