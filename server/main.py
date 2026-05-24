"""Asteroids multiplayer server entry point.

The server owns a single authoritative `World`, advances it at FPS (60 Hz),
and broadcasts a serialized snapshot to every connected client at
SNAPSHOT_HZ (30 Hz). Each client owns one ship — spawned at the welcome
handshake and removed on disconnect — and pushes INPUT messages that the
tick loop applies on the next update.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
import time
from typing import Any

import websockets

from core import config as C
from core.commands import PlayerCommand
from core.world import World
from multiplayer.command_codec import dict_to_command
from server.protocol import (
    HELLO,
    INPUT,
    REJECT,
    RESTART_REQUEST,
    SNAPSHOT,
    WELCOME,
    envelope,
    parse,
    world_to_snapshot,
)

HANDSHAKE_TIMEOUT = 5.0


class Server:
    """Connection lifecycle and per-client handshake.

    ``connections`` is the set of accepted clients indexed by the
    server-assigned ``player_id``. New ids are handed out by an incrementing
    counter; ids are not reused across disconnects (simpler than a free list,
    and there is no reason to reuse them at this stage).
    """

    def __init__(
        self,
        host: str,
        port: int,
        rooms: int = C.DEFAULT_ROOMS,
        profile_broadcast: bool = False,
    ) -> None:
        if rooms < 1:
            raise ValueError(f"rooms must be >= 1, got {rooms}")
        self.host = host
        self.port = port
        self.profile_broadcast = profile_broadcast
        self.tick = 0
        # The websocket connection type differs slightly between websockets
        # 13 (legacy) and 14+ (asyncio). Both expose recv/send/close and
        # async iteration, so Any keeps the API surface narrow.
        self.connections: dict[int, Any] = {}
        self._next_player_id = 1
        self._seq_by_player_id: dict[int, int] = {}
        # Last input seen for each player. Kept sticky between frames so a
        # 30 Hz client still drives a 60 Hz simulation smoothly; the slot
        # is cleared when the player disconnects.
        self._inputs_by_player_id: dict[int, PlayerCommand] = {}
        # Display names from the HELLO handshake, forwarded into every
        # snapshot so each client can render a scoreboard.
        self._names_by_player_id: dict[int, str] = {}
        # Each player_id belongs to exactly one room; populated at handshake
        # acceptance and consulted by tick, broadcast, and cleanup paths.
        self.room_by_player_id: dict[int, int] = {}

        self.worlds: dict[int, World] = {
            i: World(spawn_default_player=False, deathmatch=True)
            for i in range(rooms)
        }

    async def run(self) -> None:
        async with websockets.serve(
            self._handle_connection, self.host, self.port
        ):
            print(
                f"asteroids server listening on ws://{self.host}:{self.port}"
            )
            await asyncio.gather(self._tick_loop(), self._snapshot_loop())

    async def _tick_loop(self) -> None:
        dt = 1.0 / C.FPS
        period = 1.0 / C.FPS
        while True:
            await asyncio.sleep(period)
            for room_id, world in self.worlds.items():
                world.update(dt, self._inputs_for_room(room_id))
            self.tick += 1

    def _inputs_for_room(self, room_id: int) -> dict[int, PlayerCommand]:
        return {
            pid: cmd
            for pid, cmd in self._inputs_by_player_id.items()
            if self.room_by_player_id.get(pid) == room_id
        }

    def _names_for_room(self, room_id: int) -> dict[int, str]:
        return {
            pid: name
            for pid, name in self._names_by_player_id.items()
            if self.room_by_player_id.get(pid) == room_id
        }

    def _pids_in_room(self, room_id: int) -> list[int]:
        return [
            pid
            for pid, rid in self.room_by_player_id.items()
            if rid == room_id
        ]

    async def _snapshot_loop(self) -> None:
        period = 1.0 / C.SNAPSHOT_HZ
        while True:
            await asyncio.sleep(period)
            await self._broadcast_snapshot()

    async def _broadcast_snapshot(self) -> None:
        if not self.connections:
            return
        if self.profile_broadcast:
            t0 = time.perf_counter()
        bytes_total = 0
        for room_id, world in self.worlds.items():
            pids = self._pids_in_room(room_id)
            if not pids:
                continue
            snap = world_to_snapshot(
                world, names=self._names_for_room(room_id)
            )
            for player_id in pids:
                ws = self.connections.get(player_id)
                if ws is None:
                    continue
                seq = self._seq_by_player_id.get(player_id, 0)
                self._seq_by_player_id[player_id] = seq + 1
                payload = envelope(SNAPSHOT, self.tick, seq, snap)
                # Connection handler cleans up its own slot on close;
                # skipping this client for the current frame is the
                # right local response.
                with contextlib.suppress(websockets.ConnectionClosed):
                    await ws.send(payload)
                    bytes_total += len(payload)
        if self.profile_broadcast:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            print(
                f"broadcast tick={self.tick} "
                f"ms={elapsed_ms:.2f} "
                f"bytes={bytes_total} "
                f"conns={len(self.connections)} "
                f"rooms={len(self.worlds)}",
                file=sys.stderr,
            )

    async def _handle_connection(self, ws: Any) -> None:
        result = await self._handshake(ws)
        if result is None:
            return
        player_id, name, room_id = result

        self.connections[player_id] = ws
        self._names_by_player_id[player_id] = name
        self.room_by_player_id[player_id] = room_id
        self.worlds[room_id].spawn_player(player_id)
        try:
            async for raw in ws:
                msg = parse(raw)
                if msg is None:
                    continue
                if msg["type"] == INPUT:
                    self._inputs_by_player_id[player_id] = dict_to_command(
                        msg["data"]
                    )
                elif msg["type"] == RESTART_REQUEST:
                    self._handle_restart_request(player_id)
        finally:
            room_id = self.room_by_player_id.pop(player_id, 0)
            self.connections.pop(player_id, None)
            self._seq_by_player_id.pop(player_id, None)
            self._inputs_by_player_id.pop(player_id, None)
            self._names_by_player_id.pop(player_id, None)
            world = self.worlds.get(room_id)
            if world is not None:
                world.despawn_player(player_id)

    def _handle_restart_request(self, player_id: int) -> None:
        """Reset only the room that ``player_id`` belongs to and re-spawn
        every player currently connected to that room.

        Idempotent: a request that arrives outside ``ended`` is a no-op,
        so duplicate ENTER presses from multiple clients cause one reset.
        """
        room_id = self.room_by_player_id.get(player_id)
        if room_id is None:
            return
        world = self.worlds.get(room_id)
        if world is None or world.match_state != "ended":
            return
        world.reset()
        for pid in self._pids_in_room(room_id):
            world.spawn_player(pid)

    async def _handshake(self, ws: Any) -> tuple[int, str, int] | None:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=HANDSHAKE_TIMEOUT)
        except TimeoutError:
            await ws.close()
            return None
        except websockets.ConnectionClosed:
            return None

        msg = parse(raw)
        if msg is None or msg["type"] != HELLO:
            await ws.close()
            return None

        room_id = msg["data"].get("room_id", 0)
        if not isinstance(room_id, int) or isinstance(room_id, bool):
            await self._reject_and_close(ws, "invalid_room")
            return None
        if room_id not in self.worlds:
            await self._reject_and_close(ws, "invalid_room")
            return None

        if len(self._pids_in_room(room_id)) >= C.MAX_PLAYERS:
            await self._reject_and_close(ws, "room_full")
            return None

        player_id = self._next_player_id
        self._next_player_id += 1

        raw_name = msg["data"].get("name", "")
        name = (raw_name if isinstance(raw_name, str) else "").strip()[:16]
        if not name:
            name = f"P{player_id}"

        await ws.send(
            envelope(WELCOME, self.tick, 0, {"player_id": player_id})
        )
        return player_id, name, room_id

    async def _reject_and_close(self, ws: Any, reason: str) -> None:
        await ws.send(envelope(REJECT, self.tick, 0, {"reason": reason}))
        await ws.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="server",
        description="Asteroids multiplayer server (LAN deathmatch).",
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="bind address (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", default=8765, type=int, help="bind port (default: 8765)"
    )
    parser.add_argument(
        "--rooms",
        default=C.DEFAULT_ROOMS,
        type=int,
        help=f"number of concurrent rooms (default: {C.DEFAULT_ROOMS})",
    )
    parser.add_argument(
        "--profile-broadcast",
        action="store_true",
        help="log ms and bytes per broadcast to stderr",
    )
    args = parser.parse_args()

    server = Server(
        args.host,
        args.port,
        rooms=args.rooms,
        profile_broadcast=args.profile_broadcast,
    )
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
