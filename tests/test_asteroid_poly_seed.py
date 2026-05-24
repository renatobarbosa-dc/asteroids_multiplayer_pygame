"""Asteroid polygon is deterministic from `poly_seed`.

Without a stable seed, the client rebuilds the polygon on every snapshot
and the asteroid visually flickers at the snapshot rate.
"""

from core.entities import Asteroid
from core.utils import Vec
from core.world import World
from multiplayer.snapshot import snapshot_to_world
from server.protocol import world_to_snapshot


def test_same_seed_produces_same_polygon():
    a = Asteroid(Vec(100, 100), Vec(0, 0), "L", poly_seed=42)
    b = Asteroid(Vec(500, 500), Vec(10, -5), "L", poly_seed=42)
    assert [(p.x, p.y) for p in a.poly] == [(p.x, p.y) for p in b.poly]


def test_default_seed_differs_across_instances():
    a = Asteroid(Vec(0, 0), Vec(0, 0), "L")
    b = Asteroid(Vec(0, 0), Vec(0, 0), "L")
    assert a.poly_seed != b.poly_seed
    assert [(p.x, p.y) for p in a.poly] != [(p.x, p.y) for p in b.poly]


def test_snapshot_roundtrip_preserves_polygon():
    src = World(spawn_default_player=False, deathmatch=True)
    src.spawn_asteroid(Vec(200, 300), Vec(5, -3), "M")
    original = src.asteroids[0]

    snap = world_to_snapshot(src)
    assert snap["asteroids"][0]["poly_seed"] == original.poly_seed

    dst = World(spawn_default_player=False, deathmatch=True)
    snapshot_to_world(snap, dst)
    rebuilt = dst.asteroids[0]

    assert rebuilt.poly_seed == original.poly_seed
    assert [(p.x, p.y) for p in rebuilt.poly] == [
        (p.x, p.y) for p in original.poly
    ]
