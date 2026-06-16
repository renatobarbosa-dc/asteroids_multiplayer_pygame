"""Reconstruct a `World` from a server snapshot dict.

The networked client keeps a local World it never simulates. Each snapshot
overwrites the read-only entity lists in place. Ship objects are reused
across snapshots so anything holding a reference (e.g. the camera target)
stays valid; non-ship entities are rebuilt because they are short-lived
and identifying them across frames is not worth the complexity at this
stage.
"""

from __future__ import annotations

from typing import Any

from core.entities import UFO, Asteroid, Bullet, FreezePowerup, LaserBeam, LaserPowerup, Ship
from core.utils import Countdown, Vec
from core.world import World

# Brief lifetime used to flip a Countdown's `.active` to True for one
# snapshot interval. The next snapshot either refreshes it or lets it
# decay; the renderer reads `.active` only.
_ACTIVE_PULSE = 0.1


def snapshot_to_world(snap: dict[str, Any], world: World) -> None:
    """Mutate `world` in place to match `snap`."""
    _apply_ships(snap["ships"], world)
    world.bullets = [
        Bullet(b["owner_id"], Vec(b["x"], b["y"]), Vec(b["vx"], b["vy"]))
        for b in snap["bullets"]
    ]
    world.asteroids = [
        Asteroid(
            Vec(a["x"], a["y"]),
            Vec(a["vx"], a["vy"]),
            a["size"],
            poly_seed=a["poly_seed"],
        )
        for a in snap["asteroids"]
    ]
    world.ufos = [_build_ufo(u) for u in snap["ufos"]]

    world.powerups = [
        LaserPowerup(Vec(p["x"], p["y"]), Vec(p["vx"], p["vy"]), ttl=p["ttl"])
        for p in snap.get("powerups", [])
    ]
    world.freeze_powerups = [
        FreezePowerup(Vec(fp["x"], fp["y"]), ttl=fp["ttl"])
        for fp in snap.get("freeze_powerups", [])
    ]
    world.freeze_timer.reset(snap.get("freeze_remaining", 0.0))
    for ev in snap.get("laser_events", []):
        world.lasers.append(
            LaserBeam(ev["owner_id"], Vec(ev["x"], ev["y"]), Vec(ev["ex"], ev["ey"]))
        )

    world.scores = {int(pid): score for pid, score in snap["scores"].items()}
    world.lives = {int(pid): lives for pid, lives in snap["lives"].items()}
    world.deaths = {int(pid): n for pid, n in snap.get("deaths", {}).items()}
    world.frags = {int(pid): n for pid, n in snap.get("frags", {}).items()}
    world.respawning = {
        int(entry["player_id"]): Countdown(entry["remaining"])
        for entry in snap.get("respawning", [])
    }
    world.names = {
        int(pid): name for pid, name in snap.get("names", {}).items()
    }
    world.match_state = snap.get("match_state", "running")
    world.match_timer.reset(snap.get("time_remaining", 0.0))
    world.winner_id = snap.get("winner_id")
    world.wave = snap["wave"]
    world.game_over = snap["game_over"]

    # Audio events are tagged strings the client's AudioManager consumes
    # once per snapshot. Overwrite (don't extend) so a missed render
    # frame doesn't replay sounds at the next one.
    world.events = list(snap.get("audio_events", []))

    # Particles are not transported in the snapshot itself — only the
    # discrete events that spawn them. The client materializes them by
    # calling the same _spawn_particles the server used.
    for ev in snap.get("events", []):
        world._spawn_particles(Vec(ev["x"], ev["y"]), ev["kind"])


def _apply_ships(ships_snap: list[dict[str, Any]], world: World) -> None:
    new_ships: dict[int, Ship] = {}
    for s in ships_snap:
        pid = s["player_id"]
        ship = world.ships.get(pid) or Ship(pid, Vec(0.0, 0.0))
        ship.pos.xy = (s["x"], s["y"])
        ship.vel.xy = (s["vx"], s["vy"])
        ship.angle = s["angle"]
        ship.shield.reset(_ACTIVE_PULSE if s["shield_active"] else 0.0)
        ship.invuln.reset(_ACTIVE_PULSE if s["invuln_active"] else 0.0)
        ship.shield_cd.reset(s["shield_cd_remaining"])
        ship.laser.reset(s.get("laser_remaining", 0.0))
        new_ships[pid] = ship
    world.ships = new_ships


def _build_ufo(u: dict[str, Any]) -> UFO:
    ufo = UFO(Vec(u["x"], u["y"]), u["small"], setup_position=False)
    ufo.vel.xy = (u["vx"], u["vy"])
    return ufo
