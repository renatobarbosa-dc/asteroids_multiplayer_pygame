"""Tests for the freeze power-up logic, physics, and networking."""

from core import config as C
from core.collisions import CollisionManager
from core.entities import UFO, Asteroid, Bullet, FreezePowerup, Ship
from core.utils import Vec
from core.world import World
from server.protocol import world_to_snapshot
from multiplayer.snapshot import snapshot_to_world


def test_ship_collects_freeze_powerup():
    cm = CollisionManager()
    ship = Ship(1, Vec(100, 100))
    ship.invuln.reset(0.0)
    powerup = FreezePowerup(Vec(100, 100))

    result = cm.resolve(
        ships={1: ship},
        bullets=[],
        asteroids=[],
        ufos=[],
        freeze_powerups=[powerup],
    )

    assert not powerup.alive
    assert "powerup_acquired" in result.events
    assert "freeze" in result.powerups_to_apply


def test_world_activates_freeze_on_collision():
    world = World(spawn_default_player=True, deathmatch=False)
    world.asteroids.clear()
    world.ufos.clear()
    world.freeze_powerups.clear()

    ship = world.get_ship(C.LOCAL_PLAYER_ID)
    ship.pos = Vec(100, 100)
    ship.invuln.reset(0.0)

    fp = FreezePowerup(Vec(100, 100))
    world.freeze_powerups.append(fp)

    assert not world.freeze_timer.active

    world.update(0.1, {})

    assert not fp.alive
    assert len(world.freeze_powerups) == 0
    assert world.freeze_timer.active
    assert abs(world.freeze_timer.remaining - C.FREEZE_DURATION) < 1e-6


def test_frozen_asteroids_and_ufos_do_not_move():
    world = World(spawn_default_player=False, deathmatch=False)
    world.asteroids.clear()
    world.ufos.clear()

    ast = Asteroid(Vec(100, 100), Vec(50, 50), "L")
    ufo = UFO(Vec(200, 200), small=False, setup_position=False)
    ufo.vel = Vec(100, 0)
    world.asteroids.append(ast)
    world.ufos.append(ufo)

    world.freeze_timer.reset(C.FREEZE_DURATION)
    assert world.freeze_timer.active

    world.update(0.5, {})

    assert ast.pos.xy == (100.0, 100.0)
    assert ufo.pos.xy == (200.0, 200.0)

    # After the freeze expires entities move again
    world.update(C.FREEZE_DURATION + 0.1, {})
    assert not world.freeze_timer.active

    world.update(0.5, {})
    assert ast.pos != Vec(100, 100)


def test_freeze_pauses_ufo_spawning_and_wave_generation():
    world = World(spawn_default_player=False, deathmatch=False)
    world.asteroids.clear()
    world.ufos.clear()

    world.ufo_timer.reset(0.1)
    world.wave_cool.reset(0.1)
    world.freeze_timer.reset(C.FREEZE_DURATION)

    world.update(0.2, {})

    assert not world.ufos
    assert world.wave == 0


def test_freeze_powerup_snapshot_roundtrip():
    world_src = World(spawn_default_player=False, deathmatch=True)
    world_src.freeze_powerups.append(FreezePowerup(Vec(150, 250)))
    world_src.freeze_timer.reset(2.5)

    snap = world_to_snapshot(world_src, names={})

    assert "freeze_powerups" in snap
    assert len(snap["freeze_powerups"]) == 1
    assert snap["freeze_powerups"][0]["x"] == 150
    assert snap["freeze_powerups"][0]["y"] == 250
    assert snap["freeze_remaining"] == 2.5

    world_dst = World(spawn_default_player=False, deathmatch=True)
    snapshot_to_world(snap, world_dst)

    assert len(world_dst.freeze_powerups) == 1
    assert world_dst.freeze_powerups[0].pos.xy == (150.0, 250.0)
    assert world_dst.freeze_timer.remaining == 2.5


def test_asteroid_split_drops_freeze_powerup():
    old_chance = C.FREEZE_POWERUP_DROP_CHANCE_ASTEROID

    # 0% chance — no drop
    C.FREEZE_POWERUP_DROP_CHANCE_ASTEROID = 0.0
    try:
        cm = CollisionManager()
        ast = Asteroid(Vec(100, 100), Vec(0, 0), "L")
        b = Bullet(1, Vec(100, 100), Vec(0, 0))
        result = cm.resolve(ships={}, bullets=[b], asteroids=[ast], ufos=[])
        assert not result.freeze_powerups_to_spawn
    finally:
        C.FREEZE_POWERUP_DROP_CHANCE_ASTEROID = old_chance

    C.FREEZE_POWERUP_DROP_CHANCE_ASTEROID = 1.0
    try:
        cm = CollisionManager()
        ast = Asteroid(Vec(100, 100), Vec(0, 0), "L")
        b = Bullet(1, Vec(100, 100), Vec(0, 0))
        result = cm.resolve(ships={}, bullets=[b], asteroids=[ast], ufos=[])
        assert len(result.freeze_powerups_to_spawn) >= 1
    finally:
        C.FREEZE_POWERUP_DROP_CHANCE_ASTEROID = old_chance