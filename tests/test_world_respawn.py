"""Tests for the deathmatch respawn lifecycle and the single-player
death path that must not regress.

The world's behavior splits on the `deathmatch` flag:

- single-player (default): _ship_die decrements lives, respawns in place,
  triggers game over when all lives reach zero;
- deathmatch:               _ship_die removes the ship, increments a
  per-player deaths counter, and schedules a respawn after RESPAWN_DELAY
  seconds at a position chosen by _find_safe_hyperspace_pos.
"""

from __future__ import annotations

import random

import pytest

from core import config as C
from core.entities import Asteroid
from core.utils import Vec
from core.world import World


def test_single_player_ship_die_decrements_lives():
    world = World()  # deathmatch=False default; default player is spawned
    pid = C.LOCAL_PLAYER_ID
    assert world.lives[pid] == C.START_LIVES

    world._ship_die(world.ships[pid])

    assert world.lives[pid] == C.START_LIVES - 1
    assert pid in world.ships, "single-player keeps the ship in place"
    assert world.game_over is False


def test_single_player_lives_zero_triggers_game_over():
    world = World()
    pid = C.LOCAL_PLAYER_ID
    world.lives[pid] = 1

    world._ship_die(world.ships[pid])

    assert world.lives[pid] == 0
    assert world.game_over is True


def test_deathmatch_ship_die_removes_ship_and_starts_timer():
    world = World(spawn_default_player=False, deathmatch=True)
    world.spawn_player(7)
    ship = world.ships[7]

    world._ship_die(ship)

    assert 7 not in world.ships
    assert 7 in world.respawning
    assert world.respawning[7].remaining == pytest.approx(C.RESPAWN_DELAY)
    assert world.deaths[7] == 1
    assert world.game_over is False


def test_deathmatch_respawn_after_delay_reinstates_ship():
    world = World(spawn_default_player=False, deathmatch=True)
    world.spawn_player(7)
    world.match_state = (
        "running"  # bypass the lobby gate for an isolated respawn check
    )
    world.scores[7] = 250
    world._ship_die(world.ships[7])
    assert 7 not in world.ships

    world.update(C.RESPAWN_DELAY + 0.05, {})

    assert 7 in world.ships
    assert 7 not in world.respawning
    assert world.ships[7].invuln.active, (
        "respawned ship gets safe-spawn invuln"
    )
    assert world.scores[7] == 250, "score preserved across respawn"


def test_deathmatch_respawn_position_avoids_asteroids():
    random.seed(42)
    world = World(spawn_default_player=False, deathmatch=True)
    world.spawn_player(7)
    world.match_state = "running"
    # Sparse field — _find_safe_hyperspace_pos has room to maneuver.
    world.asteroids.append(Asteroid(Vec(100, 100), Vec(0, 0), "L"))
    world.asteroids.append(Asteroid(Vec(2000, 2000), Vec(0, 0), "L"))
    ship_before = world.ships[7]

    world._ship_die(ship_before)
    world.update(C.RESPAWN_DELAY + 0.05, {})

    respawned = world.ships[7]
    assert respawned is not ship_before, (
        "respawn creates a fresh ship instance"
    )
    for ast in world.asteroids:
        d = (respawned.pos - ast.pos).length()
        assert d > (ast.r + respawned.r + C.HYPERSPACE_SAFE_MARGIN), (
            f"respawn at {respawned.pos} too close to asteroid at {ast.pos}"
        )


def test_deathmatch_no_extra_life_awarded():
    world = World(spawn_default_player=False, deathmatch=True)
    world.spawn_player(7)
    world.scores[7] = C.EXTRA_LIFE_EVERY * 3
    initial_lives = world.lives[7]

    world._maybe_award_extra_life(7)

    assert world.lives[7] == initial_lives, "deathmatch grants no extra lives"
    assert "extra_life" not in world.events
    assert world.extra_lives_awarded[7] == 0


def test_deathmatch_repeated_deaths_increment_deaths_counter():
    random.seed(7)
    world = World(spawn_default_player=False, deathmatch=True)
    world.spawn_player(7)
    world.match_state = "running"

    world._ship_die(world.ships[7])
    assert world.deaths[7] == 1

    world.update(C.RESPAWN_DELAY + 0.05, {})
    assert 7 in world.ships

    world._ship_die(world.ships[7])
    assert world.deaths[7] == 2
    assert 7 not in world.ships
    assert 7 in world.respawning


def test_spawn_particles_records_particle_events():
    world = World(spawn_default_player=False)
    world._spawn_particles(Vec(10, 20), "asteroid")
    world._spawn_particles(Vec(30, 40), "ship")
    assert len(world.particle_events) == 2
    kind0, pos0 = world.particle_events[0]
    kind1, pos1 = world.particle_events[1]
    assert (kind0, pos0.x, pos0.y) == ("asteroid", 10, 20)
    assert (kind1, pos1.x, pos1.y) == ("ship", 30, 40)


def test_begin_frame_clears_particle_events():
    world = World(spawn_default_player=False)
    world._spawn_particles(Vec(10, 20), "asteroid")
    assert world.particle_events

    world.begin_frame()

    assert world.particle_events == []
