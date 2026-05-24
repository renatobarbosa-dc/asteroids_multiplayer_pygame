"""Wire protocol for the WebSocket connection between server and clients.

Every message is a JSON object with the same envelope shape:

    {"type": str, "tick": int, "seq": int, "data": dict}

- ``type``  identifies the message kind (see constants below).
- ``tick``  is the server-global simulation tick when the message was emitted.
- ``seq``   is a per-connection counter, useful for ordering and gap detection.
- ``data``  holds the message payload.

The format is JSON because the project values legibility over wire size at
this stage; a binary or delta-encoded variant can replace this once we have
real bandwidth measurements.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.world import World

# Client -> Server
HELLO = "hello"
INPUT = "input"
BYE = "bye"
RESTART_REQUEST = "restart_request"

# Server -> Client
WELCOME = "welcome"
REJECT = "reject"
SNAPSHOT = "snapshot"


def envelope(msg_type: str, tick: int, seq: int, data: dict[str, Any]) -> str:
    """Serialize a message envelope to a JSON string."""
    return json.dumps({"type": msg_type, "tick": tick, "seq": seq, "data": data})


def parse(raw: str | bytes) -> dict[str, Any] | None:
    """Parse a JSON envelope. Returns None for any malformed input.

    Defensive on purpose: the server should drop bad frames instead of
    crashing the connection handler.
    """
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return None

    if not isinstance(msg, dict):
        return None
    if not isinstance(msg.get("type"), str):
        return None
    if not isinstance(msg.get("tick"), int) or isinstance(msg.get("tick"), bool):
        return None
    if not isinstance(msg.get("seq"), int) or isinstance(msg.get("seq"), bool):
        return None
    if not isinstance(msg.get("data"), dict):
        return None
    return msg


def world_to_snapshot(
    world: World,
    names: dict[int, str] | None = None,
) -> dict[str, Any]:
    """Serialize a World into a JSON-safe dict for the SNAPSHOT message.

    Particles themselves are excluded on purpose: they are short-lived
    visual effects. Instead the snapshot carries the discrete events that
    spawn them (``events: [{kind, x, y}, ...]``) and the client recreates
    the particles locally — that way bandwidth scales with the number of
    explosions, not with the number of particles per explosion.

    The asteroid polygon (`poly`) is also excluded — the client regenerates
    it from (size, position) when reconstructing the world. Polygon jitter
    will differ from the server, but the shape stays consistent with the
    asteroid's size class.

    ``names`` is the server-side mapping of player_id to display name. Tests
    that build snapshots straight from a `World` can omit it; the live
    server always passes its tracked dict.
    """
    return {
        "ships": [
            {
                "player_id": s.player_id,
                "x": s.pos.x,
                "y": s.pos.y,
                "angle": s.angle,
                "vx": s.vel.x,
                "vy": s.vel.y,
                "shield_active": s.shield.active,
                "invuln_active": s.invuln.active,
                "shield_cd_remaining": s.shield_cd.remaining,
            }
            for s in world.ships.values()
        ],
        "bullets": [
            {
                "owner_id": b.owner_id,
                "x": b.pos.x,
                "y": b.pos.y,
                "vx": b.vel.x,
                "vy": b.vel.y,
            }
            for b in world.bullets
        ],
        "asteroids": [
            {
                "x": a.pos.x,
                "y": a.pos.y,
                "vx": a.vel.x,
                "vy": a.vel.y,
                "size": a.size,
            }
            for a in world.asteroids
        ],
        "ufos": [
            {
                "x": u.pos.x,
                "y": u.pos.y,
                "vx": u.vel.x,
                "vy": u.vel.y,
                "small": u.small,
            }
            for u in world.ufos
        ],
        "scores": {str(pid): score for pid, score in world.scores.items()},
        "lives": {str(pid): lives for pid, lives in world.lives.items()},
        "deaths": {str(pid): n for pid, n in world.deaths.items()},
        "respawning": [
            {"player_id": pid, "remaining": cd.remaining} for pid, cd in world.respawning.items()
        ],
        "events": [{"kind": kind, "x": pos.x, "y": pos.y} for kind, pos in world.particle_events],
        "names": {str(pid): name for pid, name in (names or {}).items()},
        "match_state": world.match_state,
        "time_remaining": world.match_timer.remaining,
        "frags": {str(pid): n for pid, n in world.frags.items()},
        "winner_id": world.winner_id,
        "wave": world.wave,
        "game_over": world.game_over,
    }
