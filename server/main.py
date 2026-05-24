"""Asteroids multiplayer server entry point.

PR 1 scope: accept WebSocket connections, run the hello/welcome/reject
handshake, and keep the connection open until the client disconnects.

The world simulation, tick loop, and snapshot push are added in the next PR;
input handling comes after that. Until then the server is a pure handshake
dispatcher.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

import websockets

from core import config as C
from server.protocol import HELLO, REJECT, WELCOME, envelope, parse

HANDSHAKE_TIMEOUT = 5.0


class Server:
    """Connection lifecycle and per-client handshake.

    ``connections`` is the set of accepted clients indexed by the
    server-assigned ``player_id``. New ids are handed out by an incrementing
    counter; ids are not reused across disconnects (simpler than a free list,
    and there is no reason to reuse them at this stage).
    """

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.tick = 0
        # The websocket connection type differs slightly between websockets
        # 13 (legacy) and 14+ (asyncio). Both expose recv/send/close and
        # async iteration, so Any keeps the API surface narrow.
        self.connections: dict[int, Any] = {}
        self._next_player_id = 1

    async def run(self) -> None:
        async with websockets.serve(self._handle_connection, self.host, self.port):
            print(f"asteroids server listening on ws://{self.host}:{self.port}")
            await asyncio.Future()

    async def _handle_connection(self, ws: Any) -> None:
        player_id = await self._handshake(ws)
        if player_id is None:
            return

        self.connections[player_id] = ws
        try:
            async for _ in ws:
                pass  # input handling lands in a later PR
        finally:
            self.connections.pop(player_id, None)

    async def _handshake(self, ws: Any) -> int | None:
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

        if len(self.connections) >= C.MAX_PLAYERS:
            await ws.send(envelope(REJECT, self.tick, 0, {"reason": "server_full"}))
            await ws.close()
            return None

        player_id = self._next_player_id
        self._next_player_id += 1

        await ws.send(envelope(WELCOME, self.tick, 0, {"player_id": player_id}))
        return player_id


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="server",
        description="Asteroids multiplayer server (LAN deathmatch).",
    )
    parser.add_argument("--host", default="0.0.0.0", help="bind address (default: 0.0.0.0)")
    parser.add_argument("--port", default=8765, type=int, help="bind port (default: 8765)")
    args = parser.parse_args()

    try:
        asyncio.run(Server(args.host, args.port).run())
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
