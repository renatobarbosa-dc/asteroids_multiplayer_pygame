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
    return json.dumps(
        {"type": msg_type, "tick": tick, "seq": seq, "data": data}
    )


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
    if not isinstance(msg.get("tick"), int) or isinstance(
        msg.get("tick"), bool
    ):
        return None
    if not isinstance(msg.get("seq"), int) or isinstance(msg.get("seq"), bool):
        return None
    if not isinstance(msg.get("data"), dict):
        return None
    return msg


def _r(v: float) -> float:
    """Round a wire float to 1 decimal to trim snapshot bytes.

    0.1-unit precision is invisible in a 3840x2160 world and far below
    the client's prediction snap threshold, but positions/velocities
    dominate the JSON payload, so rounding them cuts a large fraction of
    the bytes.
    """
    return round(v, 1)


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

    Audio events (``audio_events: [str, ...]``) are tagged strings the
    client feeds into its `AudioManager` — `"player_shoot"`,
    `"asteroid_explosion"`, etc. The server already collects them into
    `world.events` for the same reason particles use events: keeping
    sound out of the core simulation.

    The asteroid polygon (`poly`) is excluded but `poly_seed` is included
    so the client regenerates the exact same shape. Without the seed the
    client would jitter the polygon on every snapshot at the snapshot
    rate.

    ``names`` is the server-side mapping of player_id to display name. Tests
    that build snapshots straight from a `World` can omit it; the live
    server always passes its tracked dict.
    """
    return {
        "ships": [
            {
                "player_id": s.player_id,
                "x": _r(s.pos.x),
                "y": _r(s.pos.y),
                "angle": _r(s.angle),
                "vx": _r(s.vel.x),
                "vy": _r(s.vel.y),
                "shield_active": s.shield.active,
                "invuln_active": s.invuln.active,
                "shield_cd_remaining": _r(s.shield_cd.remaining),
                "laser_remaining": _r(s.laser.remaining),
            }
            for s in world.ships.values()
        ],
        "bullets": [
            {
                "owner_id": b.owner_id,
                "x": _r(b.pos.x),
                "y": _r(b.pos.y),
                "vx": _r(b.vel.x),
                "vy": _r(b.vel.y),
            }
            for b in world.bullets
        ],
        "asteroids": [
            {
                "x": _r(a.pos.x),
                "y": _r(a.pos.y),
                "vx": _r(a.vel.x),
                "vy": _r(a.vel.y),
                "size": a.size,
                "poly_seed": a.poly_seed,
            }
            for a in world.asteroids
        ],
        "ufos": [
            {
                "x": _r(u.pos.x),
                "y": _r(u.pos.y),
                "vx": _r(u.vel.x),
                "vy": _r(u.vel.y),
                "small": u.small,
            }
            for u in world.ufos
        ],
        "scores": {str(pid): score for pid, score in world.scores.items()},
        "lives": {str(pid): lives for pid, lives in world.lives.items()},
        "deaths": {str(pid): n for pid, n in world.deaths.items()},
        "respawning": [
            {"player_id": pid, "remaining": _r(cd.remaining)}
            for pid, cd in world.respawning.items()
        ],
        "events": [
            {"kind": kind, "x": _r(pos.x), "y": _r(pos.y)}
            for kind, pos in world.particle_events
        ],
        "powerups": [
            {
                "x": _r(p.pos.x),
                "y": _r(p.pos.y),
                "vx": _r(p.vel.x),
                "vy": _r(p.vel.y),
                "ttl": _r(p.ttl),
            }
            for p in world.powerups
        ],
         "freeze_powerups": [
            {
                "x": _r(fp.pos.x),
                "y": _r(fp.pos.y),
                "ttl": _r(fp.ttl),
            }
            for fp in getattr(world, "freeze_powerups", [])
        ],  
        "freeze_remaining": _r(
            world.freeze_timer.remaining
            if hasattr(world, "freeze_timer")
            else 0.0
        ),
        "laser_events": [
            {
                "owner_id": oid,
                "x": _r(s.x),
                "y": _r(s.y),
                "ex": _r(e.x),
                "ey": _r(e.y),
            }
            for oid, s, e in world.laser_events
        ],
        "audio_events": list(world.events),
        "names": {str(pid): name for pid, name in (names or {}).items()},
        "match_state": world.match_state,
        "time_remaining": _r(world.match_timer.remaining),
        "frags": {str(pid): n for pid, n in world.frags.items()},
        "winner_id": world.winner_id,
        "wave": world.wave,
        "game_over": world.game_over,
    }
