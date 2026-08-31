"""Thai pilot and unit catalogs for the pinned English ROM."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import re

from .atlas import AtlasBuilder
from .en_dialogue_font import (
    CATALOG_CLUSTER_SUPPLEMENT_SLOTS,
    SLOT as SUPPLEMENT_SLOT,
    WEAPON_ATTRIBUTE_SLOTS,
)
from .en_text import EN_DIRECT_REVERSE, encode_en_direct
from .en_th_renderer import (
    CATALOG_BATTLE_PAGE_STATE,
    CATALOG_BATTLE_RENDERER_PC,
    LOCK_PC,
    ORDINARY_RENDERER_PC,
    SHIFT_LEFT_PC,
    SHIFT_RIGHT_PC,
    SUPPLEMENT_ADVANCE_PC,
    SUPPLEMENT_PAGE_PC,
    build_ordinary_renderer,
)
from .proven.catalog_router import (
    build_classifier,
    build_en_cluster_width,
    build_halfwidth,
    build_ordinary_dispatch,
    build_parser_1,
    build_parser_1_alt,
    build_parser_2,
    build_route_tables,
    hook_jml,
    hook_jsl,
)
from .proven.catalogs import ATTRIBUTE_ICONS, NAME_CONTROL_RE, CatalogEncoder
from .proven.manifest import load_hooks
from .proven.renderer65816 import (
    Asm,
    BATTLE_STATE_BASE,
    ORDINARY_STATE_BASE,
    build_renderer,
    pc_to_cpu,
    shift_tables,
)
from .proven.stock_fb import (
    BATTLE_HOOK_EXPECTED,
    BATTLE_HOOK_SITE,
    ORDINARY_HOOK_EXPECTED,
    ORDINARY_HOOK_SITE,
    build_battle_stock_fb,
    build_ordinary_stock_fb,
    hook_jump,
)
from .proven.text.stock import StockCatalog
from .proven.text.stock import encode_stock
from .text import Glyph as TextGlyph
from .text import Tokenizer, load_stock_codes


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
FONT_ROOT = DATA / "font"
HOOKS = DATA / "config" / "hooks.json"

# Verified erased runs in the pinned EN image.  Keep data, adapters, lookup
# tables, and the bank-$FF renderer separate so every placement can assert FF.
STOCK_TABLE_PC = 0x3D9200
STOCK_POOL_PC = STOCK_TABLE_PC + 0x300
# Part help adds exact-case EN stock runs to the shared $FB table.  Leave the
# verified $FD:9500-$FD:99FF range to that pool, then keep the adapter's prior
# 0x900-byte capacity in the adjacent erased block.
ADAPTER_BASE_PC = 0x3D9A00
ADAPTER_LIMIT_PC = 0x3DA300
# Per-byte routing distinguishes the cluster pages. The 240 profiles alternate
# between two atlases often enough that their bitmaps no longer fit beside the
# bank-$FD adapters; bank $EC:8000-$EC:FFFF is a verified erased route block.
ROUTE_TABLE_PC = 0x2C9000
ROUTE_TABLE_LIMIT_PC = 0x2D0000

# The English patch uses its own bank-$FE name catalogs.  The stock $D2
# tables still present in the ROM are Japanese leftovers and are not the
# source used by EN battle quotes or EN status screens.
EN_UNIT_TABLE_PC = 0x3E8200
EN_UNIT_COUNT = 304
EN_UNIT_POOL_PC = 0x3E8460
EN_UNIT_POOL_END_PC = 0x3E90EA
EN_PILOT_TABLE_PC = 0x3E90EA
EN_PILOT_COUNT = 320
EN_PILOT_POOL_PC = 0x3E936A
EN_PILOT_POOL_END_PC = 0x3EA0F1
EN_BATTLE_PILOT_TABLE_PC = 0x3EA0F1
EN_BATTLE_PILOT_COUNT = 320
EN_BATTLE_PILOT_POOL_PC = 0x3EA371
EN_BATTLE_PILOT_POOL_END_PC = 0x3EAAD0
EN_WEAPON_TABLE_PC = 0x3EAAD1
EN_WEAPON_COUNT = 656
EN_WEAPON_POOL_PC = 0x3EAFF1
EN_WEAPON_POOL_END_PC = 0x3ECB42
EN_SPIRIT_POINTER_TABLE_PC = 0x3E0100
EN_SPIRIT_COUNT = 29
EN_SPIRIT_POOL_PC = 0x3E2303
EN_SPIRIT_POOL_END_PC = 0x3E285C
EN_SPIRIT_NAME_TABLE_PC = 0x3ED341
EN_SPIRIT_NAME_COUNT = 30
EN_SPIRIT_NAME_POOL_PC = 0x3ED6BF
EN_SPIRIT_NAME_POOL_END_PC = 0x3ED788
# The Spirit picker uses three 60-pixel columns.  Its text inset leaves a
# measured 56-pixel content width; this is the real surface contract, not the
# incidental 45-pixel width of the longest English label.
EN_SPIRIT_NAME_FIELD_WIDTH = 56
# Supplement codes currently occupy $00-$4D.  Reserve a parser-safe blank,
# zero-advance cell for fixed records that must retain their source length.
EN_ORDINARY_DRAW_HOOK_PC = 0x0184E4
EN_ORDINARY_DRAW_HOOK_EXPECTED = bytes.fromhex("22 45 E0 F0")
EN_CLUSTER_PAGE_PC = 0x3FE000
EN_CLUSTER_WIDTH_PC = 0x3FF000
EN_CLUSTER_ADVANCE_PC = 0x3FF100
EN_CLUSTER_RENDERER_PC = 0x3FF200
EN_SUPPLEMENT_RENDERER_PC = 0x3FF400
EN_CATALOG_RENDERER_PC = 0x3FF800
EN_CATALOG_PAGE_STATE = ORDINARY_STATE_BASE + 0x1C
# Bank $EC is erased in the EN image and is deliberately excluded from the
# story repacker's banks ($EB, $F1-$FA).  Keep the page, metrics, renderer and
# absolute-indexed shift tables together so DB never crosses an asset bank.
EN_SPIRIT_NAME_WIDTH_PC = 0x2C0000
EN_SPIRIT_NAME_ADVANCE_PC = 0x2C0100
EN_SPIRIT_NAME_RENDERER_PC = 0x2C0200
EN_SPIRIT_NAME_PAGE_PC = 0x2C1000
EN_SPIRIT_NAME_SHIFT_RIGHT_PC = 0x2C2000
EN_SPIRIT_NAME_SHIFT_LEFT_PC = 0x2C2800
EN_PROFILE_PAGE_1_PC = 0x2C3000
EN_PROFILE_PAGE_2_PC = 0x2C4000
EN_PROFILE_ADVANCE_1_PC = 0x2C5000
EN_PROFILE_ADVANCE_2_PC = 0x2C5100
EN_PROFILE_SHIFT_RIGHT_PC = 0x2C5800
EN_PROFILE_SHIFT_LEFT_PC = 0x2C6000
EN_PROFILE_RENDERER_PC = 0x2C6800
EN_PROFILE_RENDERER_1_PC = 0x2C7800
EN_PROFILE_RENDERER_2_PC = 0x2C7810
EN_PROFILE_SUPPLEMENT_RENDERER_PC = 0x2C7900
EN_VWF_PC = 0x30E045
EN_VWF_END_PC = 0x30E1B2


def build_part_stock_catalog() -> tuple[StockCatalog, frozenset[str]]:
    """Extend the locked stock IDs with exact EN runs used by Part help."""
    base = StockCatalog.locked()
    document = json.loads(
        (DATA / "translations" / "part-effects.th.json").read_text(encoding="utf-8")
    )
    direct_runs: set[str] = set()
    for lines in document["records"].values():
        for text in lines:
            run = ""
            for char in str(text):
                if char in EN_DIRECT_REVERSE:
                    run += char
                    continue
                if run:
                    direct_runs.add(run)
                    run = ""
            if run:
                direct_runs.add(run)
    extras = tuple(sorted(direct_runs - set(base.runs)))
    if len(base.runs) + len(extras) > 256:
        raise ValueError("EN Part stock runs exceed the 256-entry catalog")
    return StockCatalog(base.runs + extras), frozenset(extras)


@dataclass(frozen=True)
class CatalogReport:
    unit_records: int
    pilot_records: int
    battle_pilot_records: int
    weapon_records: int
    spirit_name_records: int
    spirit_help_records: int
    data_bytes: int
    adapter_bytes: int
    route_bytes: int
    ordinary_renderer_bytes: int
    battle_info_labels: int


@dataclass(frozen=True)
class _NameCatalog:
    owner: str
    table_pc: int
    table: bytes
    pool_pc: int
    pool: bytes
    records: int
    thai_routes: tuple[tuple[int, int], ...]
    supplement_routes: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class _SpiritHelpCatalog:
    table_pc: int
    table: bytes
    pool_pc: int
    pool: bytes
    records: int
    routes: tuple[tuple[int, int], ...]
    supplement_routes: tuple[tuple[int, int], ...]


class _SpiritNameEncoder:
    """Build the isolated bitmap page used only by the 30 Spirit names."""

    def __init__(self, clean: bytes) -> None:
        self.tokenizer = Tokenizer(
            set(json.loads((FONT_ROOT / "renewal-icons.json").read_text())["glyphs"]),
            load_stock_codes(FONT_ROOT / "renewal-stock.json"),
            engine="catalog",
        )
        document = json.loads(
            (DATA / "translations" / "spirit-descriptions.th.json").read_text(
                encoding="utf-8"
            )
        )
        tokens: set[str] = set()
        for entry in document["spirits"]:
            parsed = self.tokenizer.tokenize(
                str(entry["translation"]), where="EN Spirit name"
            )
            if parsed.issues:
                raise ValueError("EN Spirit-name tokenization failed: " + "; ".join(parsed.issues))
            for piece in parsed.pieces:
                if not isinstance(piece, TextGlyph) or not piece.token.startswith("cluster:"):
                    raise ValueError(f"EN Spirit name must use Thai clusters only: {piece!r}")
                tokens.add(piece.token)
        if len(tokens) > 0xEC:
            raise ValueError(f"EN Spirit-name page needs {len(tokens)} glyphs; holds 236")
        self.codes = {token: code for code, token in enumerate(sorted(tokens))}

        atlas = AtlasBuilder(FONT_ROOT, clean)
        page = bytearray(0x1000)
        widths = bytearray(0x100)
        advances = bytearray(0x100)
        for token, code in self.codes.items():
            glyph = atlas.build(token)
            page[code * 16:(code + 1) * 16] = bytes(glyph.rows)
            widths[code] = glyph.advance - 1
            advances[code] = glyph.advance
        self.page = bytes(page)
        self.widths = bytes(widths)
        self.advances = bytes(advances)

    def name(self, entry: dict[str, object]) -> tuple[bytes, int, tuple[int, ...]]:
        parsed = self.tokenizer.tokenize(
            str(entry["translation"]), where=f"EN Spirit name {entry['id']}"
        )
        payload = bytearray()
        width = 0
        for piece in parsed.pieces:
            if not isinstance(piece, TextGlyph) or piece.token not in self.codes:
                raise ValueError(f"EN Spirit name contains unsupported token {piece!r}")
            code = self.codes[piece.token]
            payload.append(code)
            width += self.advances[code]
        payload.append(0xFF)
        return bytes(payload), width, (1,) * (len(payload) - 1) + (0,)


class _ClusterCatalogEncoder:
    """Encode translated EN UI text as one bitmap per Thai cluster."""

    def __init__(
        self,
        clean: bytes,
        stock: StockCatalog,
        *,
        include_weapon_reference: bool = False,
        include_part_effects: bool = False,
        en_direct_stock_runs: frozenset[str] = frozenset(),
    ) -> None:
        self.stock = stock
        self.en_direct_stock_runs = en_direct_stock_runs
        self.tokenizer = Tokenizer(
            set(json.loads((FONT_ROOT / "renewal-icons.json").read_text())["glyphs"]),
            load_stock_codes(FONT_ROOT / "renewal-stock.json"),
            engine="catalog",
        )
        tokens: set[str] = set()
        # Production preserves the weapon catalog from the English ROM and
        # must not depend on weapons.th.json.  The opt-in path is retained
        # solely for validating the dormant translation asset and encoder.
        for file_name in (("weapons.th.json",) if include_weapon_reference else ()):
            for entry in _load_translation(file_name):
                text = str(entry["translation"]).removeprefix("<FB>")
                for piece in self.tokenizer.tokenize(text, where=file_name).pieces:
                    if isinstance(piece, TextGlyph) and piece.token.startswith("cluster:"):
                        tokens.add(piece.token)
        if include_part_effects:
            part_effects = json.loads(
                (DATA / "translations" / "part-effects.th.json").read_text(
                    encoding="utf-8"
                )
            )
            for lines in part_effects["records"].values():
                for text in lines:
                    parsed = self.tokenizer.tokenize(
                        str(text), where="part-effects.th.json"
                    )
                    if parsed.issues:
                        raise ValueError(
                            "EN Part-effect tokenization failed: "
                            + "; ".join(parsed.issues)
                        )
                    for piece in parsed.pieces:
                        if (
                            isinstance(piece, TextGlyph)
                            and piece.token.startswith("cluster:")
                        ):
                            tokens.add(piece.token)
        spirit_help = json.loads(
            (DATA / "translations" / "spirit-descriptions.th.json").read_text(
                encoding="utf-8"
            )
        )
        for entry in spirit_help["script_messages"]:
            for piece in self.tokenizer.tokenize(
                str(entry["translation"]), where="spirit-descriptions.th.json"
            ).pieces:
                if isinstance(piece, TextGlyph) and piece.token.startswith("cluster:"):
                    tokens.add(piece.token)
        battle_info = json.loads(
            (DATA / "translations" / "en-battle-info.th.json").read_text(
                encoding="utf-8"
            )
        )
        for field in battle_info["fields"]:
            if field.get("keep_original"):
                continue
            for piece in self.tokenizer.tokenize(
                str(field["translation"]), where="en-battle-info.th.json"
            ).pieces:
                if isinstance(piece, TextGlyph) and piece.token.startswith("cluster:"):
                    tokens.add(piece.token)
        # Weapon badges stay on the supplement page; the live weapon-list
        # path does not reliably render tail codes $E8-$EA.
        tokens.difference_update(CATALOG_CLUSTER_SUPPLEMENT_SLOTS)
        if len(tokens) > 0xEC:
            raise ValueError(f"EN catalog cluster page needs {len(tokens)} glyphs; holds 236")
        self.codes = {token: code for code, token in enumerate(sorted(tokens))}

        atlas = AtlasBuilder(FONT_ROOT, clean)
        self.supplement_codes = dict(SUPPLEMENT_SLOT)
        self.supplement_widths = {
            char: atlas.build(f"char:{char}").advance
            for char in self.supplement_codes
        }
        self.supplement_cluster_codes = {
            **CATALOG_CLUSTER_SUPPLEMENT_SLOTS,
        }
        self.supplement_cluster_widths = {
            token: atlas.build(token).advance
            for token in self.supplement_cluster_codes
        }
        self.supplement_icon_codes = dict(WEAPON_ATTRIBUTE_SLOTS)
        self.supplement_icon_widths = {
            name: atlas.build(f"icon:{name}").advance
            for name in self.supplement_icon_codes
        }
        page = bytearray(0x1000)
        widths = bytearray(0x100)
        advances = bytearray(0x100)
        for token, code in self.codes.items():
            glyph = atlas.build(token)
            page[code * 16:(code + 1) * 16] = bytes(glyph.rows)
            widths[code] = glyph.advance - 1
            advances[code] = glyph.advance
        self.page = bytes(page)
        self.widths = bytes(widths)
        self.advances = bytes(advances)


    def part_runs(self, text: str) -> tuple[list[tuple[bytes, bool]], int]:
        """Encode Part help with FB-bounded EN runs and catalog Thai clusters."""
        tokenized = self.tokenizer.tokenize(text, where="EN Part effect")
        if tokenized.issues:
            raise ValueError(
                "EN Part-effect tokenization failed: " + "; ".join(tokenized.issues)
            )
        runs: list[tuple[bytes, bool]] = []
        width = 0
        stock_run = ""

        def append(payload: bytes, thai: bool) -> None:
            if runs and runs[-1][1] == thai:
                runs[-1] = (runs[-1][0] + payload, thai)
            else:
                runs.append((payload, thai))

        def flush_stock() -> None:
            nonlocal stock_run, width
            if not stock_run:
                return
            append(self.stock.control(stock_run), False)
            width += len(stock_run) * 8
            stock_run = ""

        for piece in tokenized.pieces:
            if not isinstance(piece, TextGlyph):
                raise ValueError(f"EN Part effect contains engine token {piece!r}")
            if piece.token.startswith("char:"):
                char = piece.token.split(":", 1)[1]
                if char not in EN_DIRECT_REVERSE:
                    raise ValueError(f"EN Part effect has no direct glyph for {char!r}")
                stock_run += char
                continue
            flush_stock()
            try:
                code = self.codes[piece.token]
            except KeyError as error:
                raise ValueError(
                    f"EN Part effect has no cluster code for {piece.token!r}"
                ) from error
            append(bytes((code,)), True)
            width += self.advances[code]
        flush_stock()
        return runs, width

    def encode_stock_run(self, run: str) -> bytes:
        """Encode dynamic Part runs with EN glyphs; retain proven JP codes otherwise."""
        if run in self.en_direct_stock_runs:
            return encode_en_direct(run)
        return encode_stock(run)


    def visible(self, text: str) -> tuple[bytes, int, tuple[int, ...]]:
        payload = bytearray()
        routes: list[int] = []
        width = 0
        stock_run = ""

        def flush_stock() -> None:
            nonlocal stock_run, width
            if not stock_run:
                return
            encoded = self.stock.control(stock_run)
            payload.extend(encoded)
            routes.extend([0] * len(encoded))
            width += len(stock_run) * 8
            stock_run = ""

        tokenized = self.tokenizer.tokenize(text, where="EN catalog")
        if tokenized.issues:
            raise ValueError("EN catalog tokenization failed: " + "; ".join(tokenized.issues))
        for piece in tokenized.pieces:
            if not isinstance(piece, TextGlyph):
                raise ValueError(f"EN catalog visible text contains engine token {piece!r}")
            if piece.token.startswith("char:"):
                char = piece.token.split(":", 1)[1]
                code = self.supplement_codes.get(char)
                if code is None:
                    stock_run += char
                    continue
                flush_stock()
                payload.append(code)
                routes.append(2)
                width += self.supplement_widths[char]
                continue
            supplement_cluster = self.supplement_cluster_codes.get(piece.token)
            if supplement_cluster is not None:
                flush_stock()
                payload.append(supplement_cluster)
                routes.append(2)
                width += self.supplement_cluster_widths[piece.token]
                continue
            flush_stock()
            code = self.codes[piece.token]
            payload.append(code)
            routes.append(1)
            width += self.widths[code] + 1
        flush_stock()
        return bytes(payload), width, tuple(routes)

    def name(self, entry: dict[str, object]) -> tuple[bytes, int, tuple[int, ...]]:
        translation = str(entry["translation"])
        payload = bytearray()
        routes: list[int] = []
        width = 0
        cursor = 0
        for match in NAME_CONTROL_RE.finditer(translation):
            visible, pixels, visible_routes = self.visible(
                translation[cursor:match.start()]
            )
            payload.extend(visible)
            routes.extend(visible_routes)
            width += pixels
            address = int(match.group(1), 16)
            payload.extend((0xFB, address & 0xFF, address >> 8))
            routes.extend((0, 0, 0))
            cursor = match.end()
        visible, pixels, visible_routes = self.visible(translation[cursor:])
        payload.extend(visible)
        routes.extend(visible_routes)
        payload.append(0xFF)
        routes.append(0)
        return bytes(payload), width + pixels, tuple(routes)

    def weapon(self, entry: dict[str, object]) -> tuple[bytes, int, tuple[int, ...]]:
        translation = str(entry["translation"])
        payload = bytearray()
        routes: list[int] = []
        if translation.startswith("<FB>"):
            payload.extend((0xFB, 0x00, 0x80))
            routes.extend((0, 0, 0))
            translation = translation[4:]
        visible, width, visible_routes = self.visible(translation)
        payload.extend(visible)
        routes.extend(visible_routes)
        source = bytes.fromhex(str(entry["source_hex"]))
        attributes: list[int] = []
        cursor = len(source) - 2
        while cursor >= 0 and source[cursor] in ATTRIBUTE_ICONS:
            attributes.append(source[cursor])
            cursor -= 1
        for attribute in reversed(attributes):
            name = ATTRIBUTE_ICONS[attribute][1:-1]
            payload.append(self.supplement_icon_codes[name])
            routes.append(2)
        payload.append(0xFF)
        routes.append(0)
        return bytes(payload), width + sum(
            self.supplement_icon_widths[ATTRIBUTE_ICONS[attribute][1:-1]]
            for attribute in attributes
        ), tuple(routes)

    def spirit_line(self, text: str) -> tuple[bytes, list[int], int, int, str]:
        """Encode one fixed Spirit-help line for the relocated EN VWF."""
        payload = bytearray()
        routes: list[int] = []
        width = 0
        stock_text = ""
        stock_run = ""

        def flush_stock() -> None:
            nonlocal stock_run, stock_text, width
            if not stock_run:
                return
            encoded = encode_stock(stock_run)
            payload.extend(encoded)
            routes.extend([0] * len(encoded))
            stock_text += stock_run
            width += len(stock_run) * 8
            stock_run = ""

        tokenized = self.tokenizer.tokenize(text, where="EN Spirit help")
        if tokenized.issues:
            raise ValueError(
                "EN Spirit help tokenization failed: " + "; ".join(tokenized.issues)
            )
        for piece in tokenized.pieces:
            if not isinstance(piece, TextGlyph):
                raise ValueError(f"EN Spirit help contains engine token {piece!r}")
            if piece.token.startswith("char:"):
                char = piece.token.split(":", 1)[1]
                code = self.supplement_codes.get(char)
                if code is None:
                    stock_run += char
                    continue
                flush_stock()
                payload.append(code)
                routes.append(2)
                width += self.supplement_widths[char]
                continue
            supplement_cluster = self.supplement_cluster_codes.get(piece.token)
            if supplement_cluster is not None:
                flush_stock()
                payload.append(supplement_cluster)
                routes.append(2)
                width += self.supplement_cluster_widths[piece.token]
                continue
            flush_stock()
            code = self.codes[piece.token]
            payload.append(code)
            routes.append(1)
            width += self.widths[code] + 1
        flush_stock()
        return bytes(payload), routes, width, 0, stock_text


ClusterCatalogEncoder = _ClusterCatalogEncoder


class ProfileCatalogEncoder:
    """Encode Character Archives with two Thai pages and one supplement page."""

    _CONTROL = re.compile(r"<[^>]+>")

    def __init__(self, clean: bytes, texts: list[str]) -> None:
        self.supplement_codes = dict(SUPPLEMENT_SLOT)
        self.tokenizer = Tokenizer(
            set(json.loads((FONT_ROOT / "renewal-icons.json").read_text())["glyphs"]),
            load_stock_codes(FONT_ROOT / "renewal-stock.json"),
            engine="catalog",
        )
        tokens: set[str] = set()
        for index, text in enumerate(texts):
            parsed = self.tokenizer.tokenize(
                self._CONTROL.sub("", text).replace("\n", ""),
                where=f"EN profile {index}",
            )
            if parsed.issues:
                raise ValueError("EN profile tokenization failed: " + "; ".join(parsed.issues))
            for piece in parsed.pieces:
                if not isinstance(piece, TextGlyph):
                    continue
                if piece.token.startswith("cluster:"):
                    tokens.add(piece.token)
                    continue
                char = piece.token.split(":", 1)[1]
                if char not in self.supplement_codes:
                    raise ValueError(
                        f"EN profile character {char!r} has no supplement slot"
                    )
        ordered = sorted(tokens)
        if len(ordered) > 0xEC * 2:
            raise ValueError(f"EN profile pages need {len(ordered)} glyphs; hold {0xEC * 2}")
        self.codes = {
            **{token: (1, code) for code, token in enumerate(ordered[:0xEC])},
            **{token: (3, code) for code, token in enumerate(ordered[0xEC:])},
        }
        atlas = AtlasBuilder(FONT_ROOT, clean)
        pages = [bytearray(0x1000), bytearray(0x1000)]
        advances = [bytearray(0x100), bytearray(0x100)]
        for token, (route, code) in self.codes.items():
            glyph = atlas.build(token)
            page_index = 0 if route == 1 else 1
            pages[page_index][code * 16:(code + 1) * 16] = bytes(glyph.rows)
            advances[page_index][code] = glyph.advance
        self.pages = tuple(map(bytes, pages))
        self.advances = tuple(map(bytes, advances))

    @staticmethod
    def _control(tag: str) -> bytes:
        if tag == "<ENDFF>": return b"\xFF"
        if tag == "<ENDF7>": return b"\xF7"
        try:
            return bytes.fromhex(tag[1:-1].replace(":", ""))
        except ValueError as error:
            raise ValueError(f"invalid profile control {tag}") from error

    def _visible(self, text: str) -> tuple[bytes, tuple[int, ...]]:
        payload = bytearray()
        routes: list[int] = []

        for line_index, line in enumerate(text.split("\n")):
            if line_index:
                payload.append(0xF6)
                routes.append(0)
            parsed = self.tokenizer.tokenize(line, where="EN profile")
            if parsed.issues:
                raise ValueError("EN profile tokenization failed: " + "; ".join(parsed.issues))
            for piece in parsed.pieces:
                if not isinstance(piece, TextGlyph):
                    raise ValueError(f"EN profile visible text contains engine token {piece!r}")
                entry = self.codes.get(piece.token)
                if entry is None:
                    if not piece.token.startswith("char:"):
                        raise ValueError(f"EN profile has unassigned glyph {piece.token}")
                    char = piece.token.split(":", 1)[1]
                    try:
                        code = self.supplement_codes[char]
                    except KeyError as error:
                        raise ValueError(
                            f"EN profile character {char!r} has no supplement slot"
                        ) from error
                    payload.append(code)
                    routes.append(2)
                    continue
                route, code = entry
                payload.append(code)
                routes.append(route)
        return bytes(payload), tuple(routes)

    def record(self, text: str) -> tuple[bytes, tuple[int, ...]]:
        payload = bytearray()
        routes: list[int] = []
        cursor = 0
        for match in self._CONTROL.finditer(text):
            visible, visible_routes = self._visible(text[cursor:match.start()])
            payload.extend(visible)
            routes.extend(visible_routes)
            control = self._control(match.group())
            payload.extend(control)
            routes.extend((0,) * len(control))
            cursor = match.end()
        visible, visible_routes = self._visible(text[cursor:])
        payload.extend(visible)
        routes.extend(visible_routes)
        if not payload or payload[-1] not in (0xF7, 0xFF):
            raise ValueError("profile stream has no authored terminator")
        return bytes(payload), tuple(routes)


def _place_fill(image: bytearray, pc: int, payload: bytes, owner: str) -> None:
    if image[pc:pc + len(payload)] != b"\xFF" * len(payload):
        raise ValueError(f"{owner} overlaps occupied EN ROM bytes at {pc:#08x}")
    image[pc:pc + len(payload)] = payload


def _patch_clean(
    image: bytearray, clean: bytes, pc: int, payload: bytes, owner: str
) -> None:
    expected = clean[pc:pc + len(payload)]
    if image[pc:pc + len(payload)] != expected:
        raise ValueError(f"{owner} EN source contract changed at {pc:#08x}")
    image[pc:pc + len(payload)] = payload


def _build_catalog_page_entry(
    page_pc: int, renderer_pc: int = EN_CATALOG_RENDERER_PC
) -> bytes:
    """Select a bitmap page without disturbing the live glyph in A."""
    page_base = page_pc & 0xFFFF
    target = pc_to_cpu(renderer_pc)
    return bytes((
        0x48,                                      # PHA
        0xA9, page_base & 0xFF, page_base >> 8,    # LDA #page base
        0x8F, EN_CATALOG_PAGE_STATE & 0xFF,
        (EN_CATALOG_PAGE_STATE >> 8) & 0xFF,
        EN_CATALOG_PAGE_STATE >> 16,
        0x68,                                      # PLA
        0x5C, target & 0xFF, (target >> 8) & 0xFF, target >> 16,
    ))


def _build_cluster_page_dispatch() -> bytes:
    """Select the isolated Spirit page from the live bank-$FE source pointer."""
    asm = Asm(EN_CLUSTER_RENDERER_PC)
    asm.emit(0x48)  # PHA: keep the glyph code intact while selecting a page.
    asm.emit(0xA5, 0x1C, 0x29, 0xFF, 0x00, 0xC9, 0xFE, 0x00)
    asm.branch(0xD0, "catalog")
    asm.emit(0xA5, 0x1A)
    asm.emit(0xC9, (EN_SPIRIT_NAME_POOL_PC + 1) & 0xFF,
             ((EN_SPIRIT_NAME_POOL_PC + 1) >> 8) & 0xFF)
    asm.branch(0x90, "catalog")
    asm.emit(0xC9, (EN_SPIRIT_NAME_POOL_END_PC + 1) & 0xFF,
             ((EN_SPIRIT_NAME_POOL_END_PC + 1) >> 8) & 0xFF)
    asm.branch(0xB0, "catalog")
    spirit_page = EN_SPIRIT_NAME_PAGE_PC & 0xFFFF
    asm.emit(0xA9, spirit_page & 0xFF, spirit_page >> 8)
    asm.emit(
        0x8F,
        EN_CATALOG_PAGE_STATE & 0xFF,
        (EN_CATALOG_PAGE_STATE >> 8) & 0xFF,
        EN_CATALOG_PAGE_STATE >> 16,
        0x68,
    )
    target = pc_to_cpu(EN_SPIRIT_NAME_RENDERER_PC)
    asm.emit(0x5C, target & 0xFF, (target >> 8) & 0xFF, target >> 16)
    asm.label("catalog")
    page = EN_CLUSTER_PAGE_PC & 0xFFFF
    asm.emit(0xA9, page & 0xFF, page >> 8)
    asm.emit(
        0x8F,
        EN_CATALOG_PAGE_STATE & 0xFF,
        (EN_CATALOG_PAGE_STATE >> 8) & 0xFF,
        EN_CATALOG_PAGE_STATE >> 16,
        0x68,
    )
    target = pc_to_cpu(EN_CATALOG_RENDERER_PC)
    asm.emit(0x5C, target & 0xFF, (target >> 8) & 0xFF, target >> 16)
    return asm.finish()


def _build_catalog_renderer() -> bytes:
    """One persistent ordinary VWF body for cluster and supplement pages."""
    return build_renderer(
        EN_CATALOG_RENDERER_PC,
        source_base=0,
        advance=EN_CLUSTER_ADVANCE_PC,
        lock=LOCK_PC,
        state_base=ORDINARY_STATE_BASE,
        battle=False,
        source_page_state=EN_CATALOG_PAGE_STATE,
        alternate_advance=(SUPPLEMENT_PAGE_PC & 0xFFFF, SUPPLEMENT_ADVANCE_PC),
        caller_reuses_cell_cursor=True,
        entry_cursor_is_cell=True,
        shift_tables_base=(SHIFT_RIGHT_PC, SHIFT_LEFT_PC),
    )


def _build_battle_catalog_renderer() -> bytes:
    """Battle VWF for precomposed name clusters and supplement glyphs."""
    return build_renderer(
        CATALOG_BATTLE_RENDERER_PC,
        source_base=0,
        advance=EN_CLUSTER_ADVANCE_PC,
        lock=LOCK_PC,
        state_base=BATTLE_STATE_BASE,
        battle=True,
        source_page_state=CATALOG_BATTLE_PAGE_STATE,
        alternate_advance=(SUPPLEMENT_PAGE_PC & 0xFFFF, SUPPLEMENT_ADVANCE_PC),
        shift_tables_base=(SHIFT_RIGHT_PC, SHIFT_LEFT_PC),
    )


def _build_spirit_name_renderer() -> bytes:
    """Persistent VWF body whose metrics belong only to Spirit-name clusters."""
    return build_renderer(
        EN_SPIRIT_NAME_RENDERER_PC,
        source_base=0,
        advance=EN_SPIRIT_NAME_ADVANCE_PC,
        lock=LOCK_PC,
        state_base=ORDINARY_STATE_BASE,
        battle=False,
        source_page_state=EN_CATALOG_PAGE_STATE,
        alternate_advance=(
            EN_SPIRIT_NAME_PAGE_PC & 0xFFFF,
            EN_SPIRIT_NAME_ADVANCE_PC,
        ),
        caller_reuses_cell_cursor=True,
        entry_cursor_is_cell=True,
        compact_grid=True,
        shift_tables_base=(EN_SPIRIT_NAME_SHIFT_RIGHT_PC, EN_SPIRIT_NAME_SHIFT_LEFT_PC),
        source_bank=pc_to_cpu(EN_SPIRIT_NAME_PAGE_PC) >> 16,
    )


def _load_translation(file_name: str) -> list[dict[str, object]]:
    return list(json.loads((DATA / "translations" / file_name).read_text(encoding="utf-8")))


def _catalog_layout(layout: dict[str, object]) -> dict[str, object]:
    """Keep EN names as literal glyph streams.

    Catalog fields have enough room without shorthand.  Literal components also
    avoid expanding a combined byte inside the stock name cursor/render path.
    """
    result = dict(layout)
    result["shorthand"] = {}
    result["phrases"] = {}
    result["phrase_expansions"] = {}
    return result


def _battle_name(
    entry: dict[str, object],
    cluster_encoder: _ClusterCatalogEncoder,
) -> tuple[bytes, int, tuple[int, ...]]:
    """Encode battle-screen names for the cluster page that renders them."""
    return cluster_encoder.name(entry)


def _route_spans(
    routes: list[int], pool_pc: int, kind: int
) -> tuple[tuple[int, int], ...]:
    """Convert per-byte route ownership to post-read CPU address ranges."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(routes):
        if routes[cursor] != kind:
            cursor += 1
            continue
        start = cursor
        while cursor < len(routes) and routes[cursor] == kind:
            cursor += 1
        spans.append(
            (
                ((pool_pc + start) & 0xFFFF) + 1,
                ((pool_pc + cursor) & 0xFFFF) + 1,
            )
        )
    return tuple(spans)


def _build_battle_info_labels(
    clean: bytes, encoder: _ClusterCatalogEncoder
) -> tuple[list[tuple[int, bytes, str]], dict[int, tuple[tuple[int, int], ...]],
           dict[int, tuple[tuple[int, int], ...]]]:
    """Encode active EN battle-preview labels in bank $FE."""
    document = json.loads(
        (DATA / "translations" / "en-battle-info.th.json").read_text(encoding="utf-8")
    )
    if document.get("schema_version") != 1:
        raise ValueError("unsupported EN battle-info translation schema")

    patches: list[tuple[int, bytes, str]] = []
    thai: list[tuple[int, int]] = []
    supplement: list[tuple[int, int]] = []
    for field in document["fields"]:
        pc = int(str(field["address"]), 0)
        expected = bytes.fromhex(str(field["source_hex"]))
        if clean[pc:pc + len(expected)] != expected:
            raise ValueError(f"EN battle-info source changed for {field['key']}")
        # Labels marked as original remain on the stock English data and
        # renderer paths.  Do not encode or register routes for these spans.
        if field.get("keep_original"):
            if field.get("translation") != field.get("source"):
                raise ValueError(
                    f"EN battle-info {field['key']} original label drifted"
                )
            continue
        payload, width, routes = encoder.visible(str(field["translation"]))
        if len(payload) > len(expected):
            raise ValueError(
                f"EN battle-info {field['key']} needs {len(payload)} bytes; "
                f"field holds {len(expected)}"
            )
        padding = len(expected) - len(payload)
        if width > int(field["max_width_px"]):
            raise ValueError(
                f"EN battle-info {field['key']} is {width}px; "
                f"limit is {field['max_width_px']}px"
            )
        # These labels are inline fixed-size records. Fill their unused source
        # bytes with real blank glyphs so the renderer clears the English tail.
        # A zero-advance placeholder leaves the last live VWF cell visible.
        space_code = encoder.supplement_codes[" "]
        payload += bytes([space_code]) * padding
        routes += (2,) * padding
        patches.append((pc, payload, f"EN battle-info:{field['key']}"))
        thai.extend(_route_spans(list(routes), pc, 1))
        supplement.extend(_route_spans(list(routes), pc, 2))
    return patches, {0xFE: tuple(thai)}, {0xFE: tuple(supplement)}


def _build_catalog(
    clean: bytes,
    encode_entry: Callable[
        [dict[str, object]],
        tuple[bytes, int] | tuple[bytes, int, tuple[int, ...]],
    ],
    *,
    owner: str,
    file_name: str,
    id_key: str,
    count: int,
    table_pc: int,
    pool_pc: int,
    pool_end_pc: int,
    max_width: int | None = None,
) -> _NameCatalog:
    if table_pc + count * 2 != pool_pc:
        raise ValueError(f"{owner} EN table does not end at its pool")
    if pool_pc >> 16 != 0x3E or pool_end_pc >> 16 != 0x3E:
        raise ValueError(f"{owner} EN catalog escaped bank $FE")

    # Prove the pinned EN table owns exactly this pool before replacing it.
    for item_id in range(count):
        at = table_pc + item_id * 2
        source = int.from_bytes(clean[at:at + 2], "little") + 0x3E0000
        if not pool_pc <= source < pool_end_pc:
            raise ValueError(f"{owner} EN pointer {item_id} escaped its source pool")
        if clean.find(b"\xFF", source, pool_end_pc) < 0:
            raise ValueError(f"{owner} EN source {item_id} has no terminator")

    table = bytearray(count * 2)
    pool = bytearray()
    pool_routes: list[int] = []
    assigned: set[int] = set()
    deduplicated: dict[tuple[bytes, tuple[int, ...], int, int | None], int] = {}
    records = _load_translation(file_name)
    for entry in records:
        encoded = encode_entry(entry)
        if len(encoded) == 2:
            payload, width = encoded
            routes = tuple(1 for _ in payload)
        else:
            payload, width, routes = encoded
        if len(routes) != len(payload):
            raise ValueError(f"{owner} route mask does not match its payload")
        if max_width is not None and width > max_width:
            raise ValueError(
                f"{owner} entry {entry[id_key]} is {width}px; limit is {max_width}px"
            )
        reserved = int(entry.get("en_pool_bytes", len(payload)))
        if reserved < len(payload):
            raise ValueError(
                f"{owner} entry {entry[id_key]} needs {len(payload)} bytes; "
                f"compatibility reservation holds {reserved}"
            )
        pinned_pointer = (
            int(str(entry["en_pool_pointer"]), 0)
            if "en_pool_pointer" in entry else None
        )
        if pinned_pointer is not None:
            current_pointer = (pool_pc + len(pool)) & 0xFFFF
            if not current_pointer <= pinned_pointer < (pool_end_pc & 0xFFFF):
                raise ValueError(
                    f"{owner} cannot pin {entry[id_key]} at {pinned_pointer:#06x}; "
                    f"current pointer is {current_pointer:#06x}"
                )
            gap = pinned_pointer - current_pointer
            pool.extend(b"\xFF" * gap)
            pool_routes.extend([0] * gap)
        key = (payload, routes, reserved, pinned_pointer)
        pointer = deduplicated.get(key)
        if pointer is None:
            pointer = (pool_pc + len(pool)) & 0xFFFF
            if pool_pc + len(pool) + reserved > pool_end_pc:
                raise ValueError(f"{owner} Thai names overflow the EN pool")
            pool.extend(payload)
            pool_routes.extend(routes)
            # Savestates can retain a direct pointer into these EN pools.
            # Keep later records address-stable when a reviewed name shrinks;
            # bytes after the first terminator are never rendered.
            padding = reserved - len(payload)
            pool.extend(b"\xFF" * padding)
            pool_routes.extend([0] * padding)
            deduplicated[key] = pointer
        for raw_id in entry[id_key]:
            item_id = int(raw_id)
            if not 0 <= item_id < count or item_id in assigned:
                raise ValueError(f"{owner} invalid or duplicate ID {item_id}")
            assigned.add(item_id)
            at = item_id * 2
            table[at:at + 2] = pointer.to_bytes(2, "little")
    missing = sorted(set(range(count)) - assigned)
    if missing:
        raise ValueError(f"{owner} translation misses IDs {missing}")
    return _NameCatalog(
        owner, table_pc, bytes(table), pool_pc, bytes(pool), len(records),
        _route_spans(pool_routes, pool_pc, 1),
        _route_spans(pool_routes, pool_pc, 2),
    )


def _build_en_spirit_help(
    clean: bytes, encoder: _ClusterCatalogEncoder
) -> _SpiritHelpCatalog:
    """Repack the active EN Spirit-help pointer table and bank-$FE pool."""
    source_pointers = [
        int.from_bytes(
            clean[
                EN_SPIRIT_POINTER_TABLE_PC + spirit_id * 2:
                EN_SPIRIT_POINTER_TABLE_PC + spirit_id * 2 + 2
            ],
            "little",
        )
        for spirit_id in range(1, EN_SPIRIT_COUNT + 2)
    ]
    if source_pointers[0] != (EN_SPIRIT_POOL_PC & 0xFFFF):
        raise ValueError("EN Spirit-help pool start changed")
    if source_pointers[-1] != (EN_SPIRIT_POOL_END_PC & 0xFFFF):
        raise ValueError("EN Spirit-help pool end changed")
    for index, (start, end) in enumerate(
        zip(source_pointers, source_pointers[1:]), start=1
    ):
        source = 0x3E0000 + start
        if end <= start or clean[0x3E0000 + end - 1] != 0xFF:
            raise ValueError(f"EN Spirit-help source record {index} changed")

    document = json.loads(
        (DATA / "translations" / "spirit-descriptions.th.json").read_text(
            encoding="utf-8"
        )
    )
    messages = sorted(document["script_messages"], key=lambda item: int(item["spirit_id"]))
    if [int(item["spirit_id"]) for item in messages] != list(
        range(1, EN_SPIRIT_COUNT + 1)
    ):
        raise ValueError("EN Spirit help must cover IDs 1-29 exactly")

    line_width = int(document["_layout"]["help_box"]["line_width_px"])
    max_lines = int(document["_layout"]["help_box"]["max_lines"])
    expected_wrapped = [
        int(value) for value in document["_layout"]["help_box"]["wrapped_ids"]
    ]
    table = bytearray()
    pool = bytearray()
    route_flags: list[int] = []
    wrapped: list[int] = []
    for item in messages:
        lines = str(item["translation"]).split("\n")
        if not 1 <= len(lines) <= max_lines or any(not line for line in lines):
            raise ValueError(f"EN Spirit-help ID {item['spirit_id']} has invalid lines")
        pointer = (EN_SPIRIT_POOL_PC + len(pool)) & 0xFFFF
        table.extend(pointer.to_bytes(2, "little"))
        for line_index, line in enumerate(lines):
            payload, flags, width, _guards, _stock = encoder.spirit_line(line)
            if width > line_width:
                raise ValueError(
                    f"EN Spirit-help ID {item['spirit_id']} is {width}px; "
                    f"line holds {line_width}px"
                )
            pool.extend(payload)
            route_flags.extend(flags)
            if line_index + 1 < len(lines):
                pool.append(0xF6)
                route_flags.append(0)
        if len(lines) == 2:
            wrapped.append(int(item["spirit_id"]))
        pool.append(0xFF)
        route_flags.append(0)
    if wrapped != expected_wrapped:
        raise ValueError(f"EN Spirit-help wrapped IDs changed: {wrapped!r}")
    if EN_SPIRIT_POOL_PC + len(pool) > EN_SPIRIT_POOL_END_PC:
        raise ValueError("Thai EN Spirit-help messages overflow their source pool")

    routes = _route_spans(route_flags, EN_SPIRIT_POOL_PC, 1)
    supplement_routes = _route_spans(route_flags, EN_SPIRIT_POOL_PC, 2)
    padded_pool = bytes(pool) + b"\xFF" * (
        EN_SPIRIT_POOL_END_PC - EN_SPIRIT_POOL_PC - len(pool)
    )
    return _SpiritHelpCatalog(
        EN_SPIRIT_POINTER_TABLE_PC + 2,
        bytes(table),
        EN_SPIRIT_POOL_PC,
        padded_pool,
        len(messages),
        routes,
        supplement_routes,
    )


def _preserve_en_spirit_names(clean: bytes) -> _NameCatalog:
    """Keep the active English Spirit-name table and pool byte-identical."""
    pointers = [
        int.from_bytes(
            clean[
                EN_SPIRIT_NAME_TABLE_PC + index * 2:
                EN_SPIRIT_NAME_TABLE_PC + index * 2 + 2
            ],
            "little",
        )
        for index in range(EN_SPIRIT_NAME_COUNT + 1)
    ]
    if pointers[0] != (EN_SPIRIT_NAME_POOL_PC & 0xFFFF):
        raise ValueError("EN Spirit-name pool start changed")
    if pointers[-1] != (EN_SPIRIT_NAME_POOL_END_PC & 0xFFFF):
        raise ValueError("EN Spirit-name pool end changed")
    for index, (start, end) in enumerate(zip(pointers, pointers[1:]), start=1):
        if end <= start or clean[0x3E0000 + end - 1] != 0xFF:
            raise ValueError(f"EN Spirit-name source record {index} changed")

    table_end = EN_SPIRIT_NAME_TABLE_PC + EN_SPIRIT_NAME_COUNT * 2
    table = clean[EN_SPIRIT_NAME_TABLE_PC:table_end]
    pool = clean[EN_SPIRIT_NAME_POOL_PC:EN_SPIRIT_NAME_POOL_END_PC]
    return _NameCatalog(
        "preserved English Spirit names",
        EN_SPIRIT_NAME_TABLE_PC,
        table,
        EN_SPIRIT_NAME_POOL_PC,
        pool,
        EN_SPIRIT_NAME_COUNT,
        (),
        (),
    )


def _preserve_en_name_catalog(
    clean: bytes,
    *,
    owner: str,
    count: int,
    table_pc: int,
    pool_pc: int,
    pool_end_pc: int,
) -> _NameCatalog:
    """Keep one active English name table and pool byte-identical."""
    table_end = table_pc + count * 2
    if table_end > pool_pc:
        raise ValueError(f"{owner} pointer table overlaps its pool")
    table = clean[table_pc:table_end]
    pool = clean[pool_pc:pool_end_pc]
    if len(table) != count * 2 or len(pool) != pool_end_pc - pool_pc:
        raise ValueError(f"{owner} source is truncated")
    pool_start = pool_pc & 0xFFFF
    pool_end = pool_end_pc & 0xFFFF
    for index in range(count):
        pointer = int.from_bytes(table[index * 2:index * 2 + 2], "little")
        if not pool_start <= pointer < pool_end:
            raise ValueError(f"{owner} pointer {index} is outside its English pool")
        if clean.find(b"\xFF", 0x3E0000 + pointer, pool_end_pc) < 0:
            raise ValueError(f"{owner} record {index} has no terminator")
    return _NameCatalog(
        f"preserved {owner}",
        table_pc,
        table,
        pool_pc,
        pool,
        count,
        (),
        (),
    )


def _catalog_routes(
    catalogs: tuple[_NameCatalog, ...],
    extra_thai: dict[int, tuple[tuple[int, int], ...]] | None = None,
    extra_supplement: dict[int, tuple[tuple[int, int], ...]] | None = None,
) -> tuple[
    dict[int, tuple[tuple[int, int], ...]],
    dict[int, tuple[tuple[int, int], ...]],
]:
    thai = {0xFE: tuple(sorted(
        span for catalog in catalogs for span in catalog.thai_routes
    ))}
    supplement = {0xFE: tuple(sorted(
        span for catalog in catalogs for span in catalog.supplement_routes
    ))}
    for result, extra in (
        (thai, extra_thai or {}),
        (supplement, extra_supplement or {}),
    ):
        for bank, entries in extra.items():
            result[bank] = tuple(sorted((*result.get(bank, ()), *entries)))
    return thai, supplement


def _pack_adapters(
    route_tables_cpu: int,
    stock_table_pc: int,
    *,
    ordinary_private_banks: tuple[int, ...] = (),
) -> tuple[list[tuple[int, bytes, str]], int]:
    cursor = ADAPTER_BASE_PC
    payloads: list[tuple[int, bytes, str]] = []

    def add(owner: str, builder) -> int:
        nonlocal cursor
        pc = cursor
        payload = builder(pc)
        payloads.append((pc, payload, owner))
        cursor = (pc + len(payload) + 0x0F) & ~0x0F
        return pc

    entries = {
        "parser_1": add(
            "EN catalog parser 1",
            lambda pc: build_parser_1(
                pc, route_tables_cpu,
                include_alternate=bool(ordinary_private_banks),
            ),
        ),
        "parser_1_alt": add(
            "EN catalog parser 1 alternate",
            lambda pc: build_parser_1_alt(
                pc, route_tables_cpu,
                include_alternate=bool(ordinary_private_banks),
            ),
        ),
        "parser_2": add(
            "EN catalog parser 2",
            lambda pc: build_parser_2(
                pc, route_tables_cpu,
                include_alternate=bool(ordinary_private_banks),
            ),
        ),
        "classifier_1": add(
            "EN catalog classifier 1",
            lambda pc: build_classifier(
                pc, 0x1A, 0x8184F7, ORDINARY_RENDERER_PC, route_tables_cpu,
                fixed_renderer_pc=EN_SUPPLEMENT_RENDERER_PC,
                alternate_renderer_pc=(
                    EN_PROFILE_RENDERER_2_PC if ordinary_private_banks else None
                ),
            ),
        ),
        "classifier_2": add(
            "EN catalog classifier 2",
            lambda pc: build_classifier(
                pc, 0xCB, 0x8187B8, ORDINARY_RENDERER_PC, route_tables_cpu,
                fixed_renderer_pc=EN_SUPPLEMENT_RENDERER_PC,
                alternate_renderer_pc=(
                    EN_PROFILE_RENDERER_2_PC if ordinary_private_banks else None
                ),
            ),
        ),
        "width_1": add(
            "EN catalog width 1",
            lambda pc: build_en_cluster_width(
                pc,
                0x26,
                0x81845B,
                include_fixed=True,
                include_alternate=bool(ordinary_private_banks),
            ),
        ),
        "halfwidth_left": add(
            "EN catalog halfwidth left",
            lambda pc: build_halfwidth(
                pc, 0x8184B9, 0x8184E0,
                include_alternate=bool(ordinary_private_banks),
            ),
        ),
        "halfwidth_right": add(
            "EN catalog halfwidth right",
            lambda pc: build_halfwidth(
                pc, 0x8184D0, 0x8184E0,
                include_alternate=bool(ordinary_private_banks),
            ),
        ),
        "ordinary_dispatch": add(
            "EN ordinary Thai draw dispatcher",
            lambda pc: build_ordinary_dispatch(
                pc, EN_CLUSTER_RENDERER_PC, route_tables_cpu,
                stock_renderer_cpu=0xF0E045,
                fixed_renderer_pc=EN_SUPPLEMENT_RENDERER_PC,
                alternate_renderer_pc=(
                    EN_PROFILE_RENDERER_2_PC if ordinary_private_banks else None
                ),
                private_renderer_pc=(
                    EN_PROFILE_RENDERER_1_PC if ordinary_private_banks else None
                ),
                private_fixed_renderer_pc=(
                    EN_PROFILE_SUPPLEMENT_RENDERER_PC
                    if ordinary_private_banks else None
                ),
                private_banks=ordinary_private_banks,
            ),
        ),
        "stock_fb_ordinary": add(
            "EN catalog ordinary stock-run adapter",
            lambda pc: build_ordinary_stock_fb(pc, stock_table_pc),
        ),
        "stock_fb_battle": add(
            "EN catalog battle stock-run adapter",
            lambda pc: build_battle_stock_fb(pc, stock_table_pc),
        ),
    }
    if cursor > ADAPTER_LIMIT_PC:
        raise ValueError(
            "EN pilot/unit catalog adapters overflow their reserved block: "
            f"{cursor - ADAPTER_BASE_PC} bytes > {ADAPTER_LIMIT_PC - ADAPTER_BASE_PC}"
        )
    return payloads, entries


def install(
    image: bytearray,
    clean: bytes,
    *,
    extra_thai_routes: dict[int, tuple[tuple[int, int], ...]] | None = None,
    extra_supplement_routes: dict[int, tuple[tuple[int, int], ...]] | None = None,
    extra_alternate_routes: dict[int, tuple[tuple[int, int], ...]] | None = None,
    profile_encoder: ProfileCatalogEncoder | None = None,
    profile_banks: tuple[int, ...] = (),
    cluster_encoder: ClusterCatalogEncoder | None = None,
) -> CatalogReport:
    """Install translated UI catalogs while preserving all active EN names."""
    if cluster_encoder is None:
        stock, en_direct_runs = build_part_stock_catalog()
        cluster_encoder = _ClusterCatalogEncoder(
            clean,
            stock,
            include_part_effects=True,
            en_direct_stock_runs=en_direct_runs,
        )
    else:
        stock = cluster_encoder.stock
    catalogs = (
        _preserve_en_name_catalog(
            clean, owner="English unit names", count=EN_UNIT_COUNT,
            table_pc=EN_UNIT_TABLE_PC, pool_pc=EN_UNIT_POOL_PC,
            pool_end_pc=EN_UNIT_POOL_END_PC,
        ),
        _preserve_en_name_catalog(
            clean, owner="English pilot names", count=EN_PILOT_COUNT,
            table_pc=EN_PILOT_TABLE_PC, pool_pc=EN_PILOT_POOL_PC,
            pool_end_pc=EN_PILOT_POOL_END_PC,
        ),
        _preserve_en_name_catalog(
            clean, owner="English battle pilot names", count=EN_BATTLE_PILOT_COUNT,
            table_pc=EN_BATTLE_PILOT_TABLE_PC,
            pool_pc=EN_BATTLE_PILOT_POOL_PC,
            pool_end_pc=EN_BATTLE_PILOT_POOL_END_PC,
        ),
        _preserve_en_name_catalog(
            clean, owner="English weapon names", count=EN_WEAPON_COUNT,
            table_pc=EN_WEAPON_TABLE_PC, pool_pc=EN_WEAPON_POOL_PC,
            pool_end_pc=EN_WEAPON_POOL_END_PC,
        ),
    )
    for catalog in catalogs:
        _patch_clean(image, clean, catalog.table_pc, catalog.table, f"{catalog.owner} table")
        _patch_clean(image, clean, catalog.pool_pc, catalog.pool, f"{catalog.owner} pool")

    spirit_names = _preserve_en_spirit_names(clean)
    _patch_clean(
        image, clean, spirit_names.table_pc, spirit_names.table,
        "EN Spirit-name pointer table",
    )
    _patch_clean(
        image, clean, spirit_names.pool_pc, spirit_names.pool,
        "EN Spirit-name pool",
    )

    spirit_help = _build_en_spirit_help(clean, cluster_encoder)
    _patch_clean(
        image, clean, spirit_help.table_pc, spirit_help.table,
        "EN Spirit-help pointer table",
    )
    _patch_clean(
        image, clean, spirit_help.pool_pc, spirit_help.pool,
        "EN Spirit-help pool",
    )

    battle_info_patches, battle_info_thai, battle_info_supplement = (
        _build_battle_info_labels(clean, cluster_encoder)
    )
    for pc, payload, owner in battle_info_patches:
        _patch_clean(image, clean, pc, payload, owner)

    _place_fill(image, EN_CLUSTER_PAGE_PC, cluster_encoder.page, "EN catalog cluster page")
    _place_fill(image, EN_CLUSTER_WIDTH_PC, cluster_encoder.widths, "EN catalog cluster widths")
    _place_fill(
        image,
        EN_CLUSTER_ADVANCE_PC,
        cluster_encoder.advances,
        "EN catalog cluster advances",
    )
    _place_fill(
        image,
        EN_CLUSTER_RENDERER_PC,
        _build_cluster_page_dispatch(),
        "EN catalog/Spirit cluster-page dispatcher",
    )
    _place_fill(
        image,
        EN_SUPPLEMENT_RENDERER_PC,
        _build_catalog_page_entry(SUPPLEMENT_PAGE_PC),
        "EN catalog supplement-page entry",
    )
    battle_catalog_renderer = _build_battle_catalog_renderer()
    if CATALOG_BATTLE_RENDERER_PC + len(battle_catalog_renderer) > EN_CATALOG_RENDERER_PC:
        raise ValueError("EN battle catalog renderer overlaps ordinary catalog renderer")
    _place_fill(
        image,
        CATALOG_BATTLE_RENDERER_PC,
        battle_catalog_renderer,
        "EN battle-name catalog VWF",
    )
    catalog_renderer = _build_catalog_renderer()
    if EN_CATALOG_RENDERER_PC + len(catalog_renderer) > 0x400000:
        raise ValueError("unified EN catalog renderer crosses bank $FF")
    _place_fill(
        image,
        EN_CATALOG_RENDERER_PC,
        catalog_renderer,
        "EN catalog unified VWF",
    )
    stock_table, stock_pool, _ = stock.assets(
        STOCK_POOL_PC, encoder=cluster_encoder.encode_stock_run
    )
    if len(stock_table) != STOCK_POOL_PC - STOCK_TABLE_PC:
        raise ValueError("EN stock-run pointer table size changed")
    if STOCK_POOL_PC + len(stock_pool) > ADAPTER_BASE_PC:
        raise ValueError("EN stock-run strings overflow their reserved block")
    _place_fill(image, STOCK_TABLE_PC, stock_table, "EN catalog stock-run pointers")
    _place_fill(image, STOCK_POOL_PC, stock_pool, "EN catalog stock-run strings")

    ordinary_extras = {
        bank: tuple(spans) for bank, spans in (extra_thai_routes or {}).items()
    }
    ordinary_extras[0xFE] = tuple(sorted((
        *ordinary_extras.get(0xFE, ()),
        *battle_info_thai[0xFE],
        *spirit_help.routes,
        *spirit_names.thai_routes,
    )))
    supplement_extras = {
        bank: tuple(spans)
        for bank, spans in (extra_supplement_routes or {}).items()
    }
    supplement_extras[0xFE] = tuple(sorted((
        *supplement_extras.get(0xFE, ()),
        *battle_info_supplement[0xFE],
        *spirit_help.supplement_routes,
    )))
    thai_routes, supplement_routes = _catalog_routes(
        catalogs,
        ordinary_extras,
        supplement_extras,
    )
    alternate_routes = {
        bank: tuple(sorted(spans))
        for bank, spans in (extra_alternate_routes or {}).items()
    }
    route_data = build_route_tables(
        thai_routes, supplement_routes, alternate_routes
    )
    if ROUTE_TABLE_PC + len(route_data) > ROUTE_TABLE_LIMIT_PC:
        raise ValueError(
            f"EN pilot/unit route table needs {len(route_data)} bytes; "
            f"holds {ROUTE_TABLE_LIMIT_PC - ROUTE_TABLE_PC}"
        )
    _place_fill(image, ROUTE_TABLE_PC, route_data, "EN pilot/unit route table")

    ordinary_renderer = build_ordinary_renderer()
    _place_fill(image, ORDINARY_RENDERER_PC, ordinary_renderer, "EN ordinary Thai renderer")
    if profile_encoder is not None:
        profile_shift_right, profile_shift_left = shift_tables()
        for pc, payload, owner in (
            (EN_PROFILE_PAGE_1_PC, profile_encoder.pages[0], "EN profile cluster page 1"),
            (EN_PROFILE_PAGE_2_PC, profile_encoder.pages[1], "EN profile cluster page 2"),
            (EN_PROFILE_ADVANCE_1_PC, profile_encoder.advances[0], "EN profile advances 1"),
            (EN_PROFILE_ADVANCE_2_PC, profile_encoder.advances[1], "EN profile advances 2"),
            (EN_PROFILE_SHIFT_RIGHT_PC, profile_shift_right, "EN profile shift right"),
            (EN_PROFILE_SHIFT_LEFT_PC, profile_shift_left, "EN profile shift left"),
        ):
            _place_fill(image, pc, payload, owner)
        profile_renderer = build_renderer(
            EN_PROFILE_RENDERER_PC,
            source_base=0,
            advance=EN_PROFILE_ADVANCE_1_PC,
            lock=LOCK_PC,
            state_base=ORDINARY_STATE_BASE,
            battle=False,
            source_page_state=EN_CATALOG_PAGE_STATE,
            alternate_advance=(
                EN_PROFILE_PAGE_2_PC & 0xFFFF,
                EN_PROFILE_ADVANCE_2_PC,
            ),
            caller_reuses_cell_cursor=True,
            entry_cursor_is_cell=True,
            shift_tables_base=(EN_PROFILE_SHIFT_RIGHT_PC, EN_PROFILE_SHIFT_LEFT_PC),
            source_bank=0xEC,
        )
        if len(profile_renderer) > 0x1000:
            raise ValueError("EN profile renderer exceeds its 4 KiB slot")
        _place_fill(
            image, EN_PROFILE_RENDERER_PC, profile_renderer, "EN profile renderer"
        )
        _place_fill(
            image,
            EN_PROFILE_RENDERER_1_PC,
            _build_catalog_page_entry(EN_PROFILE_PAGE_1_PC, EN_PROFILE_RENDERER_PC),
            "EN profile page-1 entry",
        )
        _place_fill(
            image,
            EN_PROFILE_RENDERER_2_PC,
            _build_catalog_page_entry(EN_PROFILE_PAGE_2_PC, EN_PROFILE_RENDERER_PC),
            "EN profile page-2 entry",
        )
        profile_supplement_renderer = build_renderer(
            EN_PROFILE_SUPPLEMENT_RENDERER_PC,
            source_base=SUPPLEMENT_PAGE_PC & 0xFFFF,
            advance=SUPPLEMENT_ADVANCE_PC,
            lock=LOCK_PC,
            state_base=ORDINARY_STATE_BASE,
            battle=False,
            caller_reuses_cell_cursor=True,
            entry_cursor_is_cell=True,
            shift_tables_base=(EN_PROFILE_SHIFT_RIGHT_PC, EN_PROFILE_SHIFT_LEFT_PC),
            source_bank=pc_to_cpu(SUPPLEMENT_PAGE_PC) >> 16,
        )
        if EN_PROFILE_SUPPLEMENT_RENDERER_PC + len(
            profile_supplement_renderer
        ) > ROUTE_TABLE_PC:
            raise ValueError("EN profile supplement renderer overlaps route tables")
        _place_fill(
            image,
            EN_PROFILE_SUPPLEMENT_RENDERER_PC,
            profile_supplement_renderer,
            "EN profile supplement renderer",
        )
    adapters, entries = _pack_adapters(
        pc_to_cpu(ROUTE_TABLE_PC),
        STOCK_TABLE_PC,
        ordinary_private_banks=profile_banks,
    )
    for pc, payload, owner in adapters:
        _place_fill(image, pc, payload, owner)

    hook_map = {item["id"]: item for item in load_hooks(HOOKS)["hooks"]}
    for hook_id, entry_name in (
        ("text_parser_1", "parser_1"),
        ("text_parser_1_alt", "parser_1_alt"),
        ("text_parser_2", "parser_2"),
        ("font_classifier_1", "classifier_1"),
        ("font_classifier_2", "classifier_2"),
        ("glyph_width_1", "width_1"),
        ("thai_halfwidth_left", "halfwidth_left"),
        ("thai_halfwidth_right", "halfwidth_right"),
    ):
        hook = hook_map[hook_id]
        pc = int(hook["pc"], 16)
        expected = bytes.fromhex(hook["expected"])
        if clean[pc:pc + len(expected)] != expected:
            raise ValueError(f"{hook_id} clean EN hook contract changed")
        if image[pc:pc + len(expected)] != expected:
            raise ValueError(f"{hook_id} is already occupied in the EN build")
        image[pc:pc + len(expected)] = hook_jml(entries[entry_name])
    for pc, expected, entry_name, owner in (
        (ORDINARY_HOOK_SITE, ORDINARY_HOOK_EXPECTED, "stock_fb_ordinary", "ordinary_stock_fb"),
        (BATTLE_HOOK_SITE, BATTLE_HOOK_EXPECTED, "stock_fb_battle", "battle_stock_fb"),
    ):
        if clean[pc:pc + len(expected)] != expected:
            raise ValueError(f"{owner} clean EN contract changed")
        _patch_clean(image, clean, pc, hook_jump(entries[entry_name]), owner)
    if clean[
        EN_ORDINARY_DRAW_HOOK_PC:EN_ORDINARY_DRAW_HOOK_PC + 4
    ] != EN_ORDINARY_DRAW_HOOK_EXPECTED:
        raise ValueError("EN ordinary draw hook contract changed")
    _patch_clean(
        image,
        clean,
        EN_ORDINARY_DRAW_HOOK_PC,
        hook_jsl(entries["ordinary_dispatch"]),
        "EN ordinary Thai draw dispatch",
    )

    return CatalogReport(
        unit_records=catalogs[0].records,
        pilot_records=catalogs[1].records,
        battle_pilot_records=catalogs[2].records,
        weapon_records=catalogs[3].records,
        spirit_name_records=spirit_names.records,
        spirit_help_records=spirit_help.records,
        data_bytes=(
            sum(len(catalog.table) + len(catalog.pool) for catalog in catalogs)
            + len(stock_table) + len(stock_pool)
            + len(spirit_help.table) + len(spirit_help.pool)
            + len(spirit_names.table) + len(spirit_names.pool)
        ),
        adapter_bytes=sum(len(payload) for _, payload, _ in adapters),
        route_bytes=len(route_data),
        ordinary_renderer_bytes=len(ordinary_renderer),
        battle_info_labels=len(battle_info_patches),
    )
