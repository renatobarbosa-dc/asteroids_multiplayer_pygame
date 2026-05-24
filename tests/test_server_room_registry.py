"""Tests for the multi-room server registry introduced in F5 PR 1.

Most of these cover plumbing that does not need a real WebSocket — the
``_handshake``/``_handle_connection`` flow exposes its decisions
through ``Server`` state (``self.worlds``, ``self.room_by_player_id``)
which can be probed directly with a tiny in-process fake.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from typing import Any

import pytest

from core import config as C
from core.commands import PlayerCommand
from server.main import Server


class FakeWebSocket:
    """Minimal async-iterable WebSocket double used by handshake tests.

    Replays a queue of incoming text frames through ``recv()``;
    captures everything sent by the server into ``sent``.
    """

    def __init__(self, incoming: list[str]) -> None:
        self._incoming = deque(incoming)
        self.sent: list[str] = []
        self.closed = False

    async def recv(self) -> str:
        if not self._incoming:
            raise asyncio.CancelledError("no more frames")
        return self._incoming.popleft()

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    async def close(self) -> None:
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if not self._incoming:
            raise StopAsyncIteration
        return self._incoming.popleft()


def _hello(name: str = "alice", **data: Any) -> str:
    payload = {"name": name, **data}
    return json.dumps({"type": "hello", "tick": 0, "seq": 0, "data": payload})


def _last_reject_reason(ws: FakeWebSocket) -> str | None:
    for raw in reversed(ws.sent):
        msg = json.loads(raw)
        if msg["type"] == "reject":
            return msg["data"].get("reason")
    return None


def test_server_creates_n_worlds_on_boot():
    server = Server("127.0.0.1", 0, rooms=3)
    assert set(server.worlds.keys()) == {0, 1, 2}
    for world in server.worlds.values():
        assert world.deathmatch is True
        assert world.match_state == "lobby"


def test_server_rejects_zero_or_negative_rooms():
    with pytest.raises(ValueError):
        Server("127.0.0.1", 0, rooms=0)


def test_inputs_for_room_filters_by_room_id():
    server = Server("127.0.0.1", 0, rooms=2)
    cmd_a = PlayerCommand(thrust=True)
    cmd_b = PlayerCommand(shoot=True)
    server._inputs_by_player_id = {1: cmd_a, 2: cmd_b, 3: cmd_a}
    server.room_by_player_id = {1: 0, 2: 1, 3: 0}

    assert server._inputs_for_room(0) == {1: cmd_a, 3: cmd_a}
    assert server._inputs_for_room(1) == {2: cmd_b}


def test_pids_in_room_returns_only_matching_players():
    server = Server("127.0.0.1", 0, rooms=2)
    server.room_by_player_id = {1: 0, 2: 1, 3: 0, 4: 1}
    assert sorted(server._pids_in_room(0)) == [1, 3]
    assert sorted(server._pids_in_room(1)) == [2, 4]


def test_handshake_accepts_valid_room_id():
    server = Server("127.0.0.1", 0, rooms=2)
    ws = FakeWebSocket([_hello(name="alice", room_id=1)])

    result = asyncio.run(server._handshake(ws))

    assert result is not None
    player_id, name, room_id = result
    assert name == "alice"
    assert room_id == 1
    welcome = json.loads(ws.sent[-1])
    assert welcome["type"] == "welcome"
    assert welcome["data"]["player_id"] == player_id


def test_handshake_defaults_room_id_to_zero_when_missing():
    """Pre-F5 clients omit room_id; server falls back to room 0."""
    server = Server("127.0.0.1", 0, rooms=1)
    ws = FakeWebSocket([_hello(name="legacy")])

    result = asyncio.run(server._handshake(ws))

    assert result is not None
    _, _, room_id = result
    assert room_id == 0


def test_handshake_rejects_invalid_room_id():
    server = Server("127.0.0.1", 0, rooms=2)
    ws = FakeWebSocket([_hello(name="x", room_id=99)])

    result = asyncio.run(server._handshake(ws))

    assert result is None
    assert _last_reject_reason(ws) == "invalid_room"
    assert ws.closed is True


def test_handshake_rejects_non_int_room_id():
    server = Server("127.0.0.1", 0, rooms=2)
    ws = FakeWebSocket([_hello(name="x", room_id="zero")])

    result = asyncio.run(server._handshake(ws))

    assert result is None
    assert _last_reject_reason(ws) == "invalid_room"


def test_handshake_rejects_bool_as_room_id():
    """A JSON `true` is `int` in Python; explicit guard keeps it out."""
    server = Server("127.0.0.1", 0, rooms=2)
    raw = (
        '{"type":"hello","tick":0,"seq":0,"data":{"name":"x","room_id":true}}'
    )
    ws = FakeWebSocket([raw])

    result = asyncio.run(server._handshake(ws))

    assert result is None
    assert _last_reject_reason(ws) == "invalid_room"


def test_handshake_rejects_when_room_is_full():
    server = Server("127.0.0.1", 0, rooms=2)
    # Saturate room 0.
    server.room_by_player_id = {pid: 0 for pid in range(1, C.MAX_PLAYERS + 1)}
    ws = FakeWebSocket([_hello(name="x", room_id=0)])

    result = asyncio.run(server._handshake(ws))

    assert result is None
    assert _last_reject_reason(ws) == "room_full"


def test_handshake_accepts_when_target_room_has_space():
    """Room 0 is full but room 1 should still accept."""
    server = Server("127.0.0.1", 0, rooms=2)
    server.room_by_player_id = {pid: 0 for pid in range(1, C.MAX_PLAYERS + 1)}
    ws = FakeWebSocket([_hello(name="x", room_id=1)])

    result = asyncio.run(server._handshake(ws))

    assert result is not None
    _, _, room_id = result
    assert room_id == 1


def test_despawn_only_touches_correct_room():
    """Disconnect cleanup must not leak across rooms."""
    server = Server("127.0.0.1", 0, rooms=2)
    server.worlds[0].spawn_player(1)
    server.worlds[1].spawn_player(2)
    server.room_by_player_id[1] = 0
    server.room_by_player_id[2] = 1

    # Mimic the finally branch of `_handle_connection` for pid=1.
    room_id = server.room_by_player_id.pop(1)
    server.worlds[room_id].despawn_player(1)

    assert 1 not in server.worlds[0].ships
    assert 2 in server.worlds[1].ships
    assert server.worlds[1].scores[2] == 0


def test_restart_request_only_resets_owning_room():
    server = Server("127.0.0.1", 0, rooms=2)
    # Both rooms reach `ended`.
    for room_id, world in server.worlds.items():
        world.spawn_player(10 + room_id)
        world.match_state = "ended"
        world.winner_id = 10 + room_id
        world.frags[10 + room_id] = C.FRAG_LIMIT
        server.room_by_player_id[10 + room_id] = room_id

    server._handle_restart_request(10)  # restarts only room 0

    assert server.worlds[0].match_state == "lobby"
    assert server.worlds[0].winner_id is None
    assert server.worlds[1].match_state == "ended"
    assert server.worlds[1].winner_id == 11


def test_restart_request_noop_when_match_not_ended():
    server = Server("127.0.0.1", 0, rooms=1)
    server.worlds[0].spawn_player(1)
    server.room_by_player_id[1] = 0
    # match_state is "lobby" right after spawn_player

    server._handle_restart_request(1)

    assert server.worlds[0].match_state == "lobby"  # unchanged


def test_restart_request_noop_for_unknown_player():
    """Idempotent — unknown pid (e.g. ghost connection) is a no-op."""
    server = Server("127.0.0.1", 0, rooms=1)
    server._handle_restart_request(999)
    # nothing raised, no state mutated
    assert server.worlds[0].match_state == "lobby"
