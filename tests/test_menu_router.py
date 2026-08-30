"""The catalog parser route must consume only the private extended pages."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from srw4.asm65816 import assemble  # noqa: E402
from srw4.menu_router import native_command_source, parser_source  # noqa: E402


def test_menu_parser_routes_fa_extended_pages_and_keeps_stock_continuation():
    program = assemble(parser_source(), 0xFD0000)
    assert len(program.code) <= 0x100
    assert b"\xC9\xFA" in program.code
    assert b"\xC9\xF4\x00" in program.code
    assert program.code.endswith(bytes((0x5C, 0x2A, 0x84, 0x81)))


def test_native_command_router_claims_cookie_and_fetches_relocated_first_glyph():
    selection_entry = 0xFB0550
    source = native_command_source(
        table_address=0xFC5500,
        index_table=0xFC5600,
        menu_active=0x7ECED6,
        record_count=0x7ECEE4,
        records=0x7ECEE6,
        max_records=8,
        row_tile=0x7ECEDE,
        row_pending=0x7ECEF0,
        row_stride=18,
        current_record=0x7ECEEE,
        first_token=0x7ECEFA,
        row_rendered=0x7ECEF8,
        selection_entry=selection_entry,
        fallback_entry=0xFD0300,
        menu_entry=0xFE9000,
        active_cookie=0xC7A5,
        stream_base=0x5000,
        overlay_records=15,
        row_count_address=0x7E0E3B,
        recovery_flag=0x7ECEFC,
        frame_ptr=0x7ECEDA,
    )
    program = assemble(source, 0xFE9200)
    assert len(program.code) <= 0x200
    assert b"\xC9\xA5\xC7\xF0" in program.code  # BEQ routes only the full cookie
    fallback_call = bytes((0x22, 0x00, 0x03, 0xFD))
    selection_call = bytes((0x22, 0x50, 0x05, 0xFB))
    assert fallback_call in program.code
    assert selection_call in program.code
    assert program.code.index(fallback_call) < program.code.index(selection_call)
    assert program.code.count(bytes((0x5C, 0x00, 0x03, 0xFD))) == 1
    assert b"\xB7\x1A\x29\xFF\x00\xE6\x1A" in program.code
    assert bytes((0xAF, 0xFC, 0xCE, 0x7E)) in program.code  # scoped recovery flag
    assert bytes((0xAF, 0x3B, 0x0E, 0x7E)) in program.code  # stock row count
    assert bytes((0x69, 0x00, 0x50)) in program.code  # cached private stream base
    assert bytes((0xAF, 0xDA, 0xCE, 0x7E)) in program.code  # cached frame pointer
    assert bytes((0xBF, 0x00, 0xA0, 0x7E)) in program.code  # live-frame proof
    assert bytes((0xC9, 0x13, 0x00)) in program.code  # restored bottom-left proof
