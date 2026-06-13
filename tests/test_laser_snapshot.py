from core.entities import LaserPowerup
from core.utils import Vec
from core.world import World
from server.protocol import world_to_snapshot
from multiplayer.snapshot import snapshot_to_world


def test_snapshot_serializes_laser_powerups():
    world = World(spawn_default_player=False)
    world.powerups.append(LaserPowerup(Vec(100, 200), Vec(0, 0), ttl=10.0))

    snap = world_to_snapshot(world)

    assert "powerups" in snap
    assert len(snap["powerups"]) == 1

    powerup = snap["powerups"][0]
    assert powerup["x"] == 100
    assert powerup["y"] == 200
    assert powerup["vx"] == 0
    assert powerup["vy"] == 0
    assert powerup["ttl"] == 10.0


def test_snapshot_reconstructs_laser_powerups_on_client_world():
    server_world = World(spawn_default_player=False)
    server_world.powerups.append(LaserPowerup(Vec(100, 200), Vec(0, 0), ttl=10.0))

    snap = world_to_snapshot(server_world)

    client_world = World(spawn_default_player=False)
    snapshot_to_world(snap, client_world)

    assert len(client_world.powerups) == 1
    assert client_world.powerups[0].pos.x == 100
    assert client_world.powerups[0].pos.y == 200
    assert client_world.powerups[0].ttl == 10.0