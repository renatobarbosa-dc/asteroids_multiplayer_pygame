"""Tests for snapshot_to_world reconstruction and command codec."""

from core.commands import PlayerCommand
from core.entities import Ship
from core.utils import Vec
from core.world import World
from multiplayer.command_codec import command_to_dict, dict_to_command
from multiplayer.snapshot import snapshot_to_world

EMPTY_SNAPSHOT = {
    "ships": [],
    "bullets": [],
    "asteroids": [],
    "ufos": [],
    "scores": {},
    "lives": {},
    "deaths": {},
    "frags": {},
    "respawning": [],
    "events": [],
    "names": {},
    "match_state": "running",
    "time_remaining": 0.0,
    "winner_id": None,
    "wave": 0,
    "game_over": False,
}


def _snapshot(**overrides):
    return {**EMPTY_SNAPSHOT, **overrides}


def test_world_can_skip_default_player_spawn():
    w = World(spawn_default_player=False)
    assert w.ships == {}
    assert w.scores == {}
    assert w.lives == {}


def test_snapshot_to_world_creates_ship_for_new_player_id():
    w = World(spawn_default_player=False)
    snap = _snapshot(
        ships=[
            {
                "player_id": 7,
                "x": 100,
                "y": 200,
                "angle": 45.0,
                "vx": 1,
                "vy": 2,
                "shield_active": False,
                "invuln_active": True,
                "shield_cd_remaining": 0.5,
            }
        ]
    )

    snapshot_to_world(snap, w)

    assert 7 in w.ships
    s = w.ships[7]
    assert (s.pos.x, s.pos.y) == (100, 200)
    assert (s.vel.x, s.vel.y) == (1, 2)
    assert s.angle == 45.0
    assert s.invuln.active
    assert not s.shield.active
    assert s.shield_cd.remaining == 0.5


def test_snapshot_to_world_reuses_existing_ship_object():
    w = World(spawn_default_player=False)
    original = Ship(1, Vec(0, 0))
    w.ships[1] = original

    snapshot_to_world(
        _snapshot(
            ships=[
                {
                    "player_id": 1,
                    "x": 500,
                    "y": 600,
                    "angle": 90.0,
                    "vx": 0,
                    "vy": 0,
                    "shield_active": False,
                    "invuln_active": False,
                    "shield_cd_remaining": 0,
                }
            ]
        ),
        w,
    )

    assert w.ships[1] is original
    assert (original.pos.x, original.pos.y) == (500, 600)


def test_snapshot_to_world_removes_disconnected_players():
    w = World(spawn_default_player=False)
    w.ships[1] = Ship(1, Vec(0, 0))

    snapshot_to_world(_snapshot(), w)

    assert 1 not in w.ships


def test_snapshot_to_world_rebuilds_bullets():
    w = World(spawn_default_player=False)
    snapshot_to_world(
        _snapshot(
            bullets=[{"owner_id": 9, "x": 10, "y": 20, "vx": 5, "vy": 6}]
        ),
        w,
    )

    assert len(w.bullets) == 1
    b = w.bullets[0]
    assert b.owner_id == 9
    assert (b.pos.x, b.pos.y) == (10, 20)
    assert (b.vel.x, b.vel.y) == (5, 6)


def test_snapshot_to_world_rebuilds_asteroids_with_size():
    w = World(spawn_default_player=False)
    snapshot_to_world(
        _snapshot(
            asteroids=[
                {
                    "x": 30,
                    "y": 40,
                    "vx": 1,
                    "vy": 2,
                    "size": "M",
                    "poly_seed": 7,
                }
            ]
        ),
        w,
    )

    assert len(w.asteroids) == 1
    a = w.asteroids[0]
    assert a.size == "M"
    assert (a.pos.x, a.pos.y) == (30, 40)
    assert a.poly_seed == 7
    assert a.poly, "asteroid should regenerate its polygon locally"


def test_snapshot_to_world_keeps_ufo_position_against_random_setup():
    w = World(spawn_default_player=False)
    snapshot_to_world(
        _snapshot(ufos=[{"x": 50, "y": 60, "vx": 1, "vy": 2, "small": True}]),
        w,
    )

    assert len(w.ufos) == 1
    u = w.ufos[0]
    assert u.small is True
    assert (u.pos.x, u.pos.y) == (50, 60)
    assert (u.vel.x, u.vel.y) == (1, 2)


def test_snapshot_to_world_propagates_scoreboard_state():
    w = World(spawn_default_player=False)
    snapshot_to_world(
        _snapshot(scores={"5": 250}, lives={"5": 2}, wave=3, game_over=True),
        w,
    )

    assert w.scores == {5: 250}
    assert w.lives == {5: 2}
    assert w.wave == 3
    assert w.game_over is True


def test_command_codec_roundtrip_all_flags_set():
    cmd = PlayerCommand(
        rotate_left=True,
        rotate_right=False,
        thrust=True,
        shoot=True,
        hyperspace=False,
        shield=True,
    )

    assert dict_to_command(command_to_dict(cmd)) == cmd


def test_command_codec_roundtrip_default_command():
    cmd = PlayerCommand()
    assert dict_to_command(command_to_dict(cmd)) == cmd


def test_command_codec_treats_missing_keys_as_false():
    cmd = dict_to_command({})
    assert cmd == PlayerCommand()


def test_snapshot_to_world_preserves_deaths():
    w = World(spawn_default_player=False)
    snapshot_to_world(_snapshot(deaths={"5": 4, "7": 1}), w)
    assert w.deaths == {5: 4, 7: 1}


def test_snapshot_to_world_preserves_respawning_remaining():
    w = World(spawn_default_player=False)
    snapshot_to_world(
        _snapshot(respawning=[{"player_id": 5, "remaining": 2.4}]),
        w,
    )
    assert 5 in w.respawning
    assert w.respawning[5].active
    assert w.respawning[5].remaining == 2.4


def test_snapshot_to_world_spawns_local_particles_from_events():
    from core import config as C

    w = World(spawn_default_player=False)
    snapshot_to_world(
        _snapshot(events=[{"kind": "asteroid", "x": 10, "y": 20}]),
        w,
    )
    expected_count, *_ = C.PARTICLE_ASTEROID
    assert len(w.particles) == expected_count
    assert (w.particles[0].pos.x, w.particles[0].pos.y) == (10, 20)


def test_snapshot_to_world_omits_respawning_when_field_missing():
    """Older snapshots without a `respawning` field must not crash."""
    w = World(spawn_default_player=False)
    snap = {**EMPTY_SNAPSHOT}
    del snap["respawning"]
    snapshot_to_world(snap, w)
    assert w.respawning == {}


def test_snapshot_to_world_preserves_names():
    w = World(spawn_default_player=False)
    snapshot_to_world(_snapshot(names={"1": "Alice", "2": "Bob"}), w)
    assert w.names == {1: "Alice", 2: "Bob"}


def test_snapshot_to_world_applies_match_state():
    w = World(spawn_default_player=False)
    snapshot_to_world(_snapshot(match_state="ended"), w)
    assert w.match_state == "ended"


def test_snapshot_to_world_applies_time_remaining():
    w = World(spawn_default_player=False)
    snapshot_to_world(_snapshot(time_remaining=42.5), w)
    assert w.match_timer.remaining == 42.5


def test_snapshot_to_world_applies_frags():
    w = World(spawn_default_player=False)
    snapshot_to_world(_snapshot(frags={"1": 3, "2": 1}), w)
    assert w.frags == {1: 3, 2: 1}


def test_snapshot_to_world_applies_winner_id():
    w = World(spawn_default_player=False)
    snapshot_to_world(_snapshot(winner_id=7), w)
    assert w.winner_id == 7


def test_snapshot_to_world_defaults_match_state_for_legacy_payloads():
    """A snapshot without match_state must not crash; defaults to running
    so legacy payloads keep working through the F4 transition."""
    w = World(spawn_default_player=False)
    snap = {**EMPTY_SNAPSHOT}
    del snap["match_state"]
    snapshot_to_world(snap, w)
    assert w.match_state == "running"
