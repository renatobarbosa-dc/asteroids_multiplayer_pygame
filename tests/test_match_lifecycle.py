"""Tests for the match lifecycle: lobby -> running -> ended transitions,
frag counter behavior, winner selection, and single-player non-regression.
"""

from __future__ import annotations

import random

import pytest

from core import config as C
from core.commands import PlayerCommand
from core.entities import Asteroid, Bullet
from core.utils import Vec
from core.world import World


def test_world_starts_in_lobby_when_deathmatch():
    w = World(spawn_default_player=False, deathmatch=True)
    assert w.match_state == "lobby"


def test_world_starts_running_when_not_deathmatch():
    """Single-player worlds must not see the lobby gate."""
    w = World()
    assert w.match_state == "running"


def test_lobby_update_is_noop_for_entities():
    random.seed(0)
    w = World(spawn_default_player=False, deathmatch=True)
    w.spawn_player(1)
    ast = Asteroid(Vec(100, 100), Vec(50, 0), "L")
    w.asteroids.append(ast)
    before = (ast.pos.x, ast.pos.y)

    w.update(1.0, {})

    assert w.match_state == "lobby"
    assert (ast.pos.x, ast.pos.y) == before, "asteroid must not move during lobby"


def test_lobby_update_ignores_player_commands():
    w = World(spawn_default_player=False, deathmatch=True)
    w.spawn_player(1)
    ship = w.ships[1]
    before_vel = (ship.vel.x, ship.vel.y)

    w.update(0.5, {1: PlayerCommand(thrust=True)})

    assert (ship.vel.x, ship.vel.y) == before_vel, "thrust must not apply during lobby"


def test_lobby_transitions_to_running_at_min_players():
    w = World(spawn_default_player=False, deathmatch=True)
    for pid in range(1, C.MIN_PLAYERS_TO_START + 1):
        w.spawn_player(pid)

    w.update(0.01, {})

    assert w.match_state == "running"


def test_lobby_stays_when_below_min_players():
    w = World(spawn_default_player=False, deathmatch=True)
    w.spawn_player(1)

    w.update(0.01, {})

    assert w.match_state == "lobby"


def test_spawn_player_initializes_frags():
    w = World(spawn_default_player=False, deathmatch=True)
    w.spawn_player(7)
    assert w.frags[7] == 0


def test_handle_collisions_increments_world_frags():
    """End-to-end through _handle_collisions: a frag in CollisionResult
    must reach world.frags after the tick logic runs."""
    w = World(spawn_default_player=False, deathmatch=True)
    w.spawn_player(1)
    w.spawn_player(2)
    target = w.ships[2]
    target.invuln.reset(0.0)  # disable post-spawn invuln so the hit lands
    w.bullets.append(Bullet(1, Vec(target.pos.x, target.pos.y), Vec(0, 0)))

    w._handle_collisions()

    assert w.frags[1] == 1
    assert w.frags[2] == 0


def test_handle_collisions_ignores_self_bullet_frags():
    """A bullet whose owner matches the ship's player_id never registers
    a frag, even if the geometry would otherwise overlap."""
    w = World(spawn_default_player=False, deathmatch=True)
    w.spawn_player(1)
    ship = w.ships[1]
    ship.invuln.reset(0.0)
    w.bullets.append(Bullet(1, Vec(ship.pos.x, ship.pos.y), Vec(0, 0)))

    w._handle_collisions()

    assert w.frags[1] == 0


def test_match_timer_resets_on_running_transition():
    w = World(spawn_default_player=False, deathmatch=True)
    for pid in range(1, C.MIN_PLAYERS_TO_START + 1):
        w.spawn_player(pid)
    assert not w.match_timer.active

    w.update(0.01, {})  # lobby -> running; timer reset, not yet ticked

    assert w.match_state == "running"
    assert w.match_timer.active
    assert w.match_timer.remaining == pytest.approx(C.MATCH_DURATION)


def test_running_to_ended_on_frag_limit():
    w = World(spawn_default_player=False, deathmatch=True)
    w.spawn_player(1)
    w.spawn_player(2)
    w.match_state = "running"
    w.match_timer.reset(C.MATCH_DURATION)
    w.frags[1] = C.FRAG_LIMIT

    w.update(0.01, {})

    assert w.match_state == "ended"
    assert w.winner_id == 1


def test_running_to_ended_on_timer_expiry():
    w = World(spawn_default_player=False, deathmatch=True)
    w.spawn_player(1)
    w.spawn_player(2)
    w.match_state = "running"
    w.match_timer.reset(0.01)

    w.update(0.05, {})

    assert w.match_state == "ended"


def test_winner_id_uses_frags_pid_tiebreak():
    w = World(spawn_default_player=False, deathmatch=True)
    w.spawn_player(1)
    w.spawn_player(2)
    w.match_state = "running"
    w.match_timer.reset(0.01)
    w.frags = {1: 3, 2: 3}

    w.update(0.05, {})

    assert w.match_state == "ended"
    assert w.winner_id == 1, "tied frags must resolve to the smaller pid"


def test_winner_id_none_when_no_frags_and_timer_expires():
    w = World(spawn_default_player=False, deathmatch=True)
    w.match_state = "running"
    w.match_timer.reset(0.01)
    # no spawn -> empty frags dict

    w.update(0.05, {})

    assert w.match_state == "ended"
    assert w.winner_id is None


def test_ended_update_is_noop():
    w = World(spawn_default_player=False, deathmatch=True)
    w.spawn_player(1)
    w.match_state = "ended"
    ship = w.ships[1]
    before_vel = (ship.vel.x, ship.vel.y)

    w.update(0.5, {1: PlayerCommand(thrust=True)})

    assert (ship.vel.x, ship.vel.y) == before_vel
    assert w.match_state == "ended"


def test_restart_via_world_reset_returns_to_lobby():
    """A reset() on an ended deathmatch world must wipe match data and
    drop back to the lobby — that's what the server does on a restart
    request."""
    w = World(spawn_default_player=False, deathmatch=True)
    w.spawn_player(1)
    w.match_state = "ended"
    w.winner_id = 1
    w.frags[1] = C.FRAG_LIMIT
    w.scores[1] = 500

    w.reset()

    assert w.match_state == "lobby"
    assert w.winner_id is None
    assert w.frags == {}
    assert w.scores == {}
    assert w.match_timer.remaining == 0.0


def test_post_restart_with_enough_players_transitions_running():
    """After a reset and re-spawn, the next update should immediately
    flip back to running because the player count is already at the
    minimum."""
    w = World(spawn_default_player=False, deathmatch=True)
    w.spawn_player(1)
    w.spawn_player(2)
    w.match_state = "ended"

    w.reset()
    w.spawn_player(1)
    w.spawn_player(2)
    w.update(0.01, {})

    assert w.match_state == "running"
    assert w.match_timer.active
