"""P2 tests: cluster splitting, the pilot stream, and the decoder's reject rules."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.stockfont import derive_table  # noqa: E402
from srw4.stream import Record, adapter_owner, decode, encode  # noqa: E402
from srw4.text import Branch, Engine, Glyph, Tokenizer, load_stock_codes, segment  # noqa: E402
from srw4.tokens import EncodingError, TokenMap  # noqa: E402

MANIFEST = ROOT / "data" / "font" / "renewal-clusters.json"
ICONS = ROOT / "data" / "font" / "renewal-icons.json"
STOCK = ROOT / "data" / "font" / "renewal-stock.json"


@pytest.fixture(scope="module")
def token_map() -> TokenMap:
    return TokenMap.load(MANIFEST)


@pytest.fixture(scope="module")
def tokenizer() -> Tokenizer:
    icons = set(json.loads(ICONS.read_text())["glyphs"])
    return Tokenizer(icons, load_stock_codes(STOCK))


# --- clusters ---------------------------------------------------------------


def test_marks_attach_to_the_character_before_them():
    assert segment("ไม่") == ["ไ", "ม่"]
    # Two marks stack onto the same base: one cluster, one glyph.
    assert segment("พี่") == ["พี่"]
    assert segment("กา") == ["ก", "า"]


def test_a_leading_vowel_is_its_own_cluster():
    # เ and แ are written before their consonant and stand alone as glyphs.
    assert segment("เกม") == ["เ", "ก", "ม"]


def test_a_mark_with_nothing_before_it_does_not_crash():
    assert segment("่ก") == ["่", "ก"]


# --- token map --------------------------------------------------------------


def test_direct_tokens_encode_to_one_byte(token_map):
    assert token_map.direct_slots == 0xD0
    first = token_map.direct[0]
    assert token_map.encode_glyph(first) == bytes([0])
    assert len(token_map.encode_glyph(token_map.direct[-1])) == 1


def test_extended_tokens_use_the_engines_own_two_byte_escape(token_map):
    assert token_map.extended_pages == 4
    encoded = token_map.encode_glyph(token_map.extended[0])
    assert len(encoded) == 2
    assert encoded[0] == 0xF0
    assert encoded[1] == 0
    # And the code the engine works out from that pair is what the adapter
    # turns back into this token.
    assert token_map.engine_code(token_map.extended[0]) == 0x0100
    assert token_map.from_engine_code(0x0100) == token_map.extended[0]


def test_every_token_survives_the_trip_through_an_engine_code(token_map):
    for token in token_map.tokens:
        assert token_map.from_engine_code(token_map.engine_code(token)) == token


def test_an_unknown_token_is_refused(token_map):
    with pytest.raises(EncodingError, match="not in the manifest"):
        token_map.encode_glyph("cluster:😀")


def test_every_glyph_round_trips_through_its_id(token_map):
    for token in token_map.tokens:
        assert decode(token_map.encode_glyph(token), token_map).tokens == [token]


# --- pilot stream -----------------------------------------------------------


def test_a_plain_line_encodes_to_glyphs_and_a_terminator(tokenizer, token_map):
    result = tokenizer.tokenize("ไม่<ENDFF>", where="t")
    assert result.issues == []
    record = encode(result.pieces, token_map)
    assert record.data.endswith(b"\xff")
    assert decode(record.data, token_map).tokens == ["cluster:ไ", "cluster:ม่"]


def test_engine_bytes_travel_through_untouched(tokenizer, token_map):
    result = tokenizer.tokenize("<FC:05>ก<FE:21:00>ข<ENDF7>", where="t")
    record = encode(result.pieces, token_map)
    assert b"\xfc\x05" in record.data
    assert b"\xfe\x21\x00" in record.data
    assert decode(record.data, token_map).terminator == 0xF7


def test_a_newline_becomes_the_engine_line_break(tokenizer, token_map):
    record = encode(tokenizer.tokenize("ก\nข<ENDFF>", where="t").pieces, token_map)
    assert b"\xf6" in record.data


def test_a_name_escape_becomes_fb_with_a_little_endian_pointer(tokenizer):
    pieces = tokenizer.tokenize("<NAME:$801E><ENDFF>", where="t").pieces
    assert pieces[0] == Engine(b"\xfb\x1e\x80\xff")


def test_an_icon_is_a_glyph_not_a_control(tokenizer, token_map):
    pieces = tokenizer.tokenize("<B>ก<ENDFF>", where="t").pieces
    assert pieces[0] == Glyph("icon:B")
    assert isinstance(pieces[1], Glyph)


def test_a_bare_stock_byte_is_folded_into_one_of_our_glyphs(tokenizer):
    # 0x16 is the stock font's "A": it must not stay a raw byte, or the line
    # would be drawn half by us and half by the game.
    result = tokenizer.tokenize("<16>ก<ENDFF>", where="t")
    assert result.pieces[0] == Glyph("char:A")
    assert [f.byte for f in result.foldings] == [0x16]
    assert result.foldings[0].token == "char:A"


def test_a_stock_byte_we_cannot_map_is_reported_not_dropped_silently(tokenizer):
    result = tokenizer.tokenize("<4B><ENDFF>", where="t")  # 0x4B draws "が"
    assert result.foldings[0].token is None
    assert result.foldings[0].byte == 0x4B


def test_a_latin_byte_the_game_kept_now_folds_into_one_of_our_glyphs(tokenizer):
    # $19 $06 is how the game spells "Dr". Both halves have a glyph of ours
    # now, so neither is dropped on the floor.
    result = tokenizer.tokenize("<19><06><ENDFF>", where="t")
    assert [f.token for f in result.foldings] == ["char:D", "char:r"]


def test_operand_bytes_below_the_split_are_not_mistaken_for_glyphs(tokenizer):
    # FB's two operands are 0x1E and 0x80; neither may become a glyph.
    result = tokenizer.tokenize("<FB:1E80>ก<ENDFF>", where="t")
    assert result.foldings == []
    assert result.pieces[0] == Engine(b"\xfb\x1e\x80")


def test_a_truncated_command_is_reported_rather_than_guessed(tokenizer):
    result = tokenizer.tokenize("<FB:FF>", where="t")
    assert any("operand bytes missing" in issue for issue in result.issues)


# --- branch tables ----------------------------------------------------------


def test_a_branch_table_is_kept_apart_and_marked_for_relocation(tokenizer, token_map):
    table = "".join(f"<{low:02X}><{high:02X}>" for low, high in [(0x10, 0x01)] * 8)
    result = tokenizer.tokenize(f"<FC:08>{table}ก<ENDFF>", where="t",
                                branch_range=range(0x0000, 0x2000))
    assert result.issues == []
    assert any(isinstance(p, Branch) for p in result.pieces)
    record = encode(result.pieces, token_map)
    assert len(record.relocations) == 8
    assert {r.stock_target for r in record.relocations} == {0x0110}
    # The table must not be read as glyphs when the stream is walked back.
    assert decode(record.data, token_map, record.branch_tables).tokens == ["cluster:ก"]


def test_a_branch_target_outside_the_block_is_reported(tokenizer):
    table = "".join("<10><99>" for _ in range(8))
    result = tokenizer.tokenize(f"<FC:08>{table}<ENDFF>", where="t",
                                branch_range=range(0x0000, 0x2000))
    assert any("outside the block" in issue for issue in result.issues)


# --- decoder rules ----------------------------------------------------------


def test_the_reserved_gap_is_rejected(token_map):
    for byte in (0xD0, 0xE0, 0xEB):
        with pytest.raises(EncodingError, match="reserved gap"):
            decode(bytes([byte]), token_map)


def test_an_extended_lead_without_an_index_is_rejected(token_map):
    with pytest.raises(EncodingError, match="no index byte"):
        decode(b"\xf0", token_map)


def test_a_command_missing_its_operands_is_rejected(token_map):
    with pytest.raises(EncodingError, match="operand bytes"):
        decode(b"\xfb\x1e", token_map)


def test_a_glyph_id_past_the_token_map_is_rejected(token_map):
    with pytest.raises(EncodingError, match="past the end"):
        decode(b"\xf3\xff", token_map)


def test_adapter_ownership_matches_the_documented_split(token_map):
    owner = lambda byte: adapter_owner(byte, extended_pages=token_map.extended_pages)
    assert owner(0x00) == "renewal"
    assert owner(0xCF) == "renewal"
    assert owner(0xD0) == "nobody"
    assert owner(0xEB) == "nobody"
    assert owner(0xEC) == "engine"
    assert owner(0xF0) == "renewal"     # the engine's two-byte escape
    assert owner(0xF3) == "renewal"
    assert owner(0xF4) == "engine"      # engine control, not an unallocated glyph page
    assert owner(0xF6) == "engine"      # a line break
    assert owner(0xFF) == "engine"


# --- derived stock font -----------------------------------------------------


def test_the_derived_font_table_agrees_with_the_hand_written_one():
    source = json.loads((ROOT / "data" / "translations" / "script.source.json").read_text())
    table, report = derive_table(source["messages"])
    assert report["ambiguous"] == {}

    fullwidth = {chr(c): chr(c - 0xFEE0) for c in range(0xFF01, 0xFF5F)}
    fullwidth["　"] = " "
    known = json.loads(STOCK.read_text())["glyphs"]

    checked = 0
    for char, entry in known.items():
        derived = table.get(entry["code"])
        if derived is None:
            continue  # that code never appears in the script
        normalised = fullwidth.get(derived, derived)
        if normalised != char:
            # The only accepted differences are deliberate substitutions of a
            # Japanese punctuation glyph for its ASCII equivalent.
            assert char in ",.", f"{char!r} claims code {entry['code']:#04x} which draws {derived!r}"
            continue
        checked += 1
    assert checked > 40
