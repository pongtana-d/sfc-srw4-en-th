from __future__ import annotations

from srw4.en_dialogue_codec import ESCAPE, build


def test_dictionary_round_trip_and_escape_rejection() -> None:
    streams = [b"\xC0\x10\xC0\x11\xFF", b"\xC0\x10\xC0\x11\xF7"]
    codec = build(streams, entries=4)
    assert codec.entries
    assert all(codec.decode(codec.encode(stream)) == stream for stream in streams)
    try:
        codec.encode(bytes((ESCAPE, 0x00)))
    except ValueError as error:
        assert "$FA" in str(error)
    else:
        raise AssertionError("reserved escape must reject raw data")
