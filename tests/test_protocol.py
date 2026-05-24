"""Tests for server.protocol envelope and parsing."""

from server.protocol import HELLO, WELCOME, envelope, parse


def test_envelope_roundtrip_preserves_fields():
    raw = envelope(HELLO, tick=42, seq=7, data={"name": "alice"})
    msg = parse(raw)

    assert msg is not None
    assert msg["type"] == HELLO
    assert msg["tick"] == 42
    assert msg["seq"] == 7
    assert msg["data"] == {"name": "alice"}


def test_envelope_returns_str():
    raw = envelope(WELCOME, tick=0, seq=0, data={})
    assert isinstance(raw, str)


def test_parse_rejects_invalid_json():
    assert parse("not json {") is None


def test_parse_rejects_non_object_payload():
    assert parse('"just a string"') is None
    assert parse("42") is None
    assert parse("[1, 2, 3]") is None


def test_parse_rejects_missing_type():
    assert parse('{"tick": 0, "seq": 0, "data": {}}') is None


def test_parse_rejects_missing_tick():
    assert parse('{"type": "hello", "seq": 0, "data": {}}') is None


def test_parse_rejects_missing_seq():
    assert parse('{"type": "hello", "tick": 0, "data": {}}') is None


def test_parse_rejects_missing_data():
    assert parse('{"type": "hello", "tick": 0, "seq": 0}') is None


def test_parse_rejects_wrong_tick_type():
    assert parse('{"type": "hello", "tick": "0", "seq": 0, "data": {}}') is None


def test_parse_rejects_bool_as_int_for_tick():
    # JSON booleans are also ints in Python; protocol must not accept them
    # as a substitute for the numeric tick counter.
    assert parse('{"type": "hello", "tick": true, "seq": 0, "data": {}}') is None


def test_parse_rejects_non_dict_data():
    assert parse('{"type": "hello", "tick": 0, "seq": 0, "data": []}') is None
    assert parse('{"type": "hello", "tick": 0, "seq": 0, "data": "x"}') is None


def test_parse_accepts_bytes_payload():
    raw = envelope(HELLO, 0, 0, {})
    msg = parse(raw.encode())
    assert msg is not None
    assert msg["type"] == HELLO
