"""Build verified Thai weapon, unit and pilot catalog data."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path

from .text.encoding import advance_table, encode
from .text.japanese import CatalogDecoder, read_catalog_string
from .text.stock import StockCatalog, encode_mixed


WEAPON_POINTER_TABLE = 0x0C7760
WEAPON_POINTER_COUNT = 656
UNIT_POINTER_TABLE = 0x126050
UNIT_POINTER_COUNT = 304
PILOT_POINTER_TABLE = 0x126B34
PILOT_POINTER_COUNT = 320
BATTLE_PILOT_POINTER_TABLE = 0x12772B
BATTLE_PILOT_POINTER_COUNT = 320

# The weapon attribute badges.  Left as raw source bytes they fall past
# CONTROL_BASE into the original handler, which composes its cells out of the
# same dynamic tile pool the VWF is filling: one badge claimed four cells,
# shifted every later tile index in the panel by $18, and tore the bottom row
# off the list.  Drawn from the Thai page instead they are ordinary 8px glyphs,
# one byte each exactly as before, and the pen never leaves the grid.
ATTRIBUTE_ICONS = {
    0xEC: "<MAP_L>",
    0xED: "<MAP_R>",
    0xEE: "<B>",
    0xEF: "<P>",
}

WEAPON_POOLS = (
    (0x0C7C80, 0x0C8E88, "original_weapon_pool", False),
    (0x0CFD42, 0x0D0000, "verified_weapon_bank_end", True),
    (0x0C4409, 0x0C4600, "verified_weapon_mid_bank", True),
)
NAME_POOLS = (
    (0x1262B0, 0x126B34, "original_unit_pool", False),
    (0x126DB4, 0x12772B, "original_pilot_pool", False),
    (0x12E78F, 0x12EA80, "verified_name_run", True),
    (0x125E5F, 0x125E80, "verified_name_pre_table", True),
    # Keep the bank-end run untouched for the later spirit-name adapter.  The
    # old combined build used 114/125 bytes there before allocating catalogs.
    (0x12FF83, 0x130000, "reserved_name_bank_end", True),
)
BATTLE_NAME_POOLS = (
    (0x1279AB, 0x127F03, "original_battle_pilot_pool", False),
)

NAME_CONTROL_RE = re.compile(r"<NAME:\$([0-9A-Fa-f]{4})>")
DASHES = str.maketrans({"－": "ー", "‐": "ー", "—": "ー", "―": "ー"})


@dataclass(frozen=True)
class Write:
    pc: int
    payload: bytes
    owner: str
    expected_ff: bool


class PoolAllocator:
    def __init__(self, clean: bytes, pools: tuple[tuple[int, int, str, bool], ...]) -> None:
        self.clean = clean
        self.pools = [
            {"start": start, "end": end, "cursor": start, "name": name, "ff": ff}
            for start, end, name, ff in pools
        ]
        for pool in self.pools:
            if pool["ff"]:
                start, end = int(pool["start"]), int(pool["end"])
                if clean[start:end] != b"\xFF" * (end - start):
                    raise ValueError(f"verified pool {pool['name']} is not FF-filled")
        self.writes: list[Write] = []

    def allocate(self, payload: bytes, owner: str) -> tuple[int, str]:
        for pool in self.pools:
            cursor, end = int(pool["cursor"]), int(pool["end"])
            if cursor + len(payload) > end:
                continue
            self.writes.append(Write(cursor, payload, owner, bool(pool["ff"])))
            pool["cursor"] = cursor + len(payload)
            return cursor, str(pool["name"])
        raise ValueError(f"catalog pools overflow while allocating {owner} ({len(payload)} bytes)")

    def report(self) -> list[dict[str, object]]:
        return [
            {
                "name": str(pool["name"]),
                "start": f"0x{int(pool['start']):06X}",
                "end": f"0x{int(pool['end']):06X}",
                "capacity": int(pool["end"]) - int(pool["start"]),
                "used": int(pool["cursor"]) - int(pool["start"]),
            }
            for pool in self.pools
        ]


class CatalogEncoder:
    def __init__(self, model: dict, layout: dict, stock: StockCatalog) -> None:
        self.layout = layout
        self.stock = stock
        self.advance = advance_table(model, layout)

    def visible(self, text: str) -> tuple[bytes, int]:
        width = 0

        def thai(part: str) -> bytes:
            nonlocal width
            payload = encode(
                part,
                self.layout["codes"],
                self.layout.get("shorthand"),
                self.layout.get("phrases"),
            )
            width += sum(self.advance[code] for code in payload)
            return payload

        payload, stock_width = encode_mixed(text, thai, self.stock)
        return payload, width + stock_width

    def weapon(self, entry: dict[str, object]) -> tuple[bytes, int]:
        translation = str(entry["translation"])
        payload = bytearray()
        if translation.startswith("<FB>"):
            payload.extend((0xFB, 0x00, 0x80))
            translation = translation[4:]
        visible, width = self.visible(translation)
        payload.extend(visible)

        source = bytes.fromhex(str(entry["source_hex"]))
        attributes = []
        cursor = len(source) - 2
        while cursor >= 0 and 0xEC <= source[cursor] <= 0xEF:
            attributes.append(source[cursor])
            cursor -= 1
        attributes.reverse()
        # Each badge is a glyph on the Thai page now, so the renderer advances
        # the pen for it like any other 8px cell and nothing has to be nudged
        # onto the grid first.  The old code inserted a space here whenever the
        # name's last glyph had crossed a cell boundary with ink to spare; that
        # never addressed the real fault and only widened the name.
        payload.extend(
            self.layout["codes"][ATTRIBUTE_ICONS[code]] for code in attributes
        )
        payload.append(0xFF)
        return bytes(payload), width + len(attributes) * 8

    def name(self, entry: dict[str, object]) -> tuple[bytes, int]:
        translation = str(entry["translation"])
        payload = bytearray()
        width = 0
        cursor = 0
        for match in NAME_CONTROL_RE.finditer(translation):
            visible, pixels = self.visible(translation[cursor:match.start()])
            payload.extend(visible)
            width += pixels
            address = int(match.group(1), 16)
            payload.extend((0xFB, address & 0xFF, address >> 8))
            cursor = match.end()
        visible, pixels = self.visible(translation[cursor:])
        payload.extend(visible)
        width += pixels
        payload.append(0xFF)
        return bytes(payload), width


def _load(path: Path) -> list[dict[str, object]]:
    return list(json.loads(path.read_text(encoding="utf-8")))


def _load_terms(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    terms: dict[str, str] = {}
    for group, entries in raw.items():
        if group.startswith("_"):
            continue
        terms.update({
            str(key).translate(DASHES): str(value)
            for key, value in entries.items()
        })
    return terms


def _name_glossary(translation_dir: Path) -> dict[str, str]:
    """Build the reviewed catalog/battle-label glossary deterministically."""
    terms: dict[str, str] = {}
    for file_name in ("pilots.th.json", "units.th.json"):
        for entry in _load(translation_dir / file_name):
            source = str(entry.get("source") or "").strip().translate(DASHES)
            thai = str(entry.get("translation") or "").strip()
            if not source or not thai or source.startswith("<"):
                continue
            terms[source] = thai
            if "＝" in source:
                parts, words = source.split("＝"), thai.split()
                if len(parts) == len(words):
                    for part, word in zip(parts, words):
                        terms.setdefault(part, word)
    terms.update(_load_terms(translation_dir / "glossary.th.json"))
    overrides = _load_terms(translation_dir / "rom-glossary.th.json")
    unknown = sorted(set(overrides) - set(terms))
    if unknown:
        raise ValueError(f"ROM glossary overrides unknown canonical terms: {unknown}")
    terms.update(overrides)
    return terms


def _battle_translation(
    source_pointer: int,
    source: bytes,
    source_text: str,
    glossary: dict[str, str],
) -> tuple[str, str]:
    body = source[:-1]
    if not body or set(body) == {0x11}:
        return "", "blank_placeholder"
    if body[0] == 0xFB:
        if len(body) != 3:
            raise ValueError(f"unexpected dynamic battle name at {source_pointer:#06x}")
        return f"<NAME:${body[2]:02X}{body[1]:02X}>", "dynamic_name"
    key = source_text.translate(DASHES)
    if key not in glossary:
        raise ValueError(
            f"battle label {source_text!r} at {source_pointer:#06x} has no reviewed translation"
        )
    return glossary[key], "reviewed_glossary"


def _verify_source(clean: bytes, entry: dict[str, object], bank: int, owner: str) -> None:
    expected = bytes.fromhex(str(entry["source_hex"]))
    pc = bank + int(str(entry["source_pointer"]), 16)
    if clean[pc:pc + len(expected)] != expected:
        raise ValueError(f"source mismatch for {owner} at {pc:#08x}")


def _repoint(
    clean: bytes,
    table_pc: int,
    count: int,
    pointer_map: dict[int, int],
    owner: str,
) -> bytes:
    table = bytearray(clean[table_pc:table_pc + count * 2])
    for item_id in range(count):
        at = item_id * 2
        source = int.from_bytes(table[at:at + 2], "little")
        if source not in pointer_map:
            raise ValueError(f"missing {owner} source pointer {source:#06x} for ID {item_id}")
        table[at:at + 2] = pointer_map[source].to_bytes(2, "little")
    return bytes(table)


def build_catalog_data(
    root: Path,
    clean: bytes,
    *,
    font_dir: Path | None = None,
    translation_dir: Path | None = None,
    kanji_path: Path | None = None,
) -> tuple[list[Write], dict[str, object]]:
    """Return asserted pool/table writes without mutating a ROM image."""
    font_dir = font_dir or root / "font"
    translation_dir = translation_dir or root / "translations"
    kanji_path = kanji_path or font_dir / "jp-kanji.json"
    layout = json.loads((font_dir / "encoding.json").read_text(encoding="utf-8"))
    model = json.loads((font_dir / "thai.json").read_text(encoding="utf-8"))
    stock = StockCatalog.locked()
    encoder = CatalogEncoder(model, layout, stock)

    reports: dict[str, list[dict[str, object]]] = {
        "weapons": [], "units": [], "pilots": [], "battle_pilots": []
    }
    writes: list[Write] = []

    weapon_allocator = PoolAllocator(clean, WEAPON_POOLS)
    weapon_map: dict[int, int] = {}
    weapon_dedup: dict[bytes, tuple[int, str]] = {}
    for entry in _load(translation_dir / "weapons.th.json"):
        source_pointer = int(str(entry["source_pointer"]), 16)
        if entry.get("kind") == "non_text_sentinel":
            weapon_map[source_pointer] = source_pointer
            continue
        _verify_source(clean, entry, 0x0C0000, f"weapon:{source_pointer:04X}")
        payload, width = encoder.weapon(entry)
        if payload in weapon_dedup:
            target, pool = weapon_dedup[payload]
            deduplicated = True
        else:
            target, pool = weapon_allocator.allocate(payload, f"weapon:{source_pointer:04X}")
            weapon_dedup[payload] = (target, pool)
            deduplicated = False
        weapon_map[source_pointer] = target & 0xFFFF
        reports["weapons"].append({
            "source_pointer": f"0x{source_pointer:04X}",
            "target_pointer": f"0x{target & 0xFFFF:04X}",
            "translation": entry["translation"],
            "bytes": len(payload),
            "width_px": width,
            "pool": pool,
            "deduplicated": deduplicated,
        })
    writes.extend(weapon_allocator.writes)
    weapon_table = _repoint(
        clean, WEAPON_POINTER_TABLE, WEAPON_POINTER_COUNT, weapon_map, "weapon"
    )
    writes.append(Write(WEAPON_POINTER_TABLE, weapon_table, "weapon-pointer-table", False))

    name_allocator = PoolAllocator(clean, NAME_POOLS)
    name_dedup: dict[bytes, tuple[int, str]] = {}
    for kind, file_name, table_pc, count, id_key in (
        ("units", "units.th.json", UNIT_POINTER_TABLE, UNIT_POINTER_COUNT, "unit_ids"),
        ("pilots", "pilots.th.json", PILOT_POINTER_TABLE, PILOT_POINTER_COUNT, "pilot_ids"),
    ):
        pointer_map: dict[int, int] = {}
        for entry in _load(translation_dir / file_name):
            source_pointer = int(str(entry["source_pointer"]), 16)
            _verify_source(clean, entry, 0x120000, f"{kind}:{source_pointer:04X}")
            payload, width = encoder.name(entry)
            if payload in name_dedup:
                target, pool = name_dedup[payload]
                deduplicated = True
            else:
                target, pool = name_allocator.allocate(payload, f"{kind}:{source_pointer:04X}")
                name_dedup[payload] = (target, pool)
                deduplicated = False
            pointer_map[source_pointer] = target & 0xFFFF
            reports[kind].append({
                "source_pointer": f"0x{source_pointer:04X}",
                "target_pointer": f"0x{target & 0xFFFF:04X}",
                "translation": entry["translation"],
                "bytes": len(payload),
                "width_px": width,
                "ids": entry[id_key],
                "pool": pool,
                "deduplicated": deduplicated,
            })
        table = _repoint(clean, table_pc, count, pointer_map, kind)
        writes.append(Write(table_pc, table, f"{kind}-pointer-table", False))
    writes.extend(name_allocator.writes)

    battle_allocator = PoolAllocator(clean, BATTLE_NAME_POOLS)
    decoder = CatalogDecoder(kanji_path)
    glossary = _name_glossary(translation_dir)
    references: dict[int, list[int]] = {}
    for pilot_id in range(BATTLE_PILOT_POINTER_COUNT):
        at = BATTLE_PILOT_POINTER_TABLE + pilot_id * 2
        source_pointer = int.from_bytes(clean[at:at + 2], "little")
        references.setdefault(source_pointer, []).append(pilot_id)

    battle_map: dict[int, int] = {}
    for source_pointer, pilot_ids in references.items():
        source = read_catalog_string(clean, 0x120000, source_pointer)
        source_text = decoder.decode(source)
        translation, method = _battle_translation(
            source_pointer, source, source_text, glossary
        )
        payload, width = encoder.name({"translation": translation})
        if payload in name_dedup:
            target, pool = name_dedup[payload]
            deduplicated = True
        else:
            target, pool = battle_allocator.allocate(
                payload, f"battle-pilot:{source_pointer:04X}"
            )
            name_dedup[payload] = (target, pool)
            deduplicated = False
        battle_map[source_pointer] = target & 0xFFFF
        reports["battle_pilots"].append({
            "source_pointer": f"0x{source_pointer:04X}",
            "source": source_text,
            "source_hex": source.hex(" ").upper(),
            "target_pointer": f"0x{target & 0xFFFF:04X}",
            "translation": translation,
            "method": method,
            "bytes": len(payload),
            "width_px": width,
            "pilot_ids": pilot_ids,
            "pool": pool,
            "deduplicated": deduplicated,
        })
    battle_table = _repoint(
        clean,
        BATTLE_PILOT_POINTER_TABLE,
        BATTLE_PILOT_POINTER_COUNT,
        battle_map,
        "battle pilot",
    )
    writes.extend(battle_allocator.writes)
    writes.append(Write(
        BATTLE_PILOT_POINTER_TABLE,
        battle_table,
        "battle-pilots-pointer-table",
        False,
    ))

    return writes, {
        "entries": {key: len(value) for key, value in reports.items()},
        "pools": (
            weapon_allocator.report()
            + name_allocator.report()
            + battle_allocator.report()
        ),
        "stock_runs": len(stock.runs),
        "catalogs": reports,
    }
