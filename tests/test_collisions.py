"""Tests for the CollisionManager.

These exercise core/ in pure Python — no pygame display needed. The
decoupling work in F1.1 and F1.2 is what makes this possible.
"""

from core import config as C
from core.collisions import CollisionManager
from core.entities import UFO, UFO_BULLET_OWNER, Asteroid, Bullet, Ship
from core.utils import Vec


def make_ship(player_id=1, pos=(100, 100)):
    s = Ship(player_id, Vec(*pos))
    s.invuln.reset(0.0)  # remove post-spawn invulnerability for test clarity
    return s


def test_player_bullet_splits_large_asteroid_and_scores():
    cm = CollisionManager()
    ast = Asteroid(Vec(100, 100), Vec(0, 0), "L")
    b = Bullet(1, Vec(100, 100), Vec(0, 0))
    r = cm.resolve(ships={}, bullets=[b], asteroids=[ast], ufos=[])
    assert not ast.alive, "asteroid was hit"
    assert not b.alive, "bullet consumed"
    assert r.score_deltas.get(1) == C.AST_SIZES["L"]["score"]
    # L splits to 2 M
    assert len(r.asteroids_to_spawn) == 2
    assert all(sz == "M" for _, _, sz in r.asteroids_to_spawn)
    assert any(ev == "asteroid_explosion" for ev in r.events)
    assert tuple(kind for _, kind in r.particles_to_spawn) == ("asteroid",)


def test_ufo_bullet_destroys_asteroid_without_split_or_score():
    cm = CollisionManager()
    ast = Asteroid(Vec(100, 100), Vec(0, 0), "M")
    ufo_bullet = Bullet(UFO_BULLET_OWNER, Vec(100, 100), Vec(0, 0))
    r = cm.resolve(ships={}, bullets=[ufo_bullet], asteroids=[ast], ufos=[])
    assert not ast.alive
    assert not r.asteroids_to_spawn, "no split"
    assert r.score_deltas == {}, "no score awarded"
    assert any(ev == "asteroid_explosion" for ev in r.events)


def test_ship_hits_asteroid_records_death():
    cm = CollisionManager()
    ship = make_ship(pos=(200, 200))
    ast = Asteroid(Vec(200, 200), Vec(0, 0), "L")
    r = cm.resolve(ships={1: ship}, bullets=[], asteroids=[ast], ufos=[])
    assert 1 in r.ship_deaths


def test_invuln_ship_does_not_die_on_asteroid_contact():
    cm = CollisionManager()
    ship = Ship(1, Vec(200, 200))
    ship.invuln.reset(C.SAFE_SPAWN_TIME)  # post-spawn invuln active
    ast = Asteroid(Vec(200, 200), Vec(0, 0), "L")
    r = cm.resolve(ships={1: ship}, bullets=[], asteroids=[ast], ufos=[])
    assert r.ship_deaths == []


def test_shielded_ship_deflects_asteroid_into_split():
    cm = CollisionManager()
    ship = make_ship(pos=(300, 300))
    ship.shield.reset(C.SHIELD_DURATION)
    ast = Asteroid(Vec(300, 300), Vec(0, 0), "L")
    r = cm.resolve(ships={1: ship}, bullets=[], asteroids=[ast], ufos=[])
    assert r.ship_deaths == [], "shield must save ship"
    assert not ast.alive, "asteroid was damaged"
    assert len(r.asteroids_to_spawn) == 2, (
        "L splits to 2 M even on shield contact"
    )
    assert r.score_deltas == {}, "defensive split does not score"


def test_player_bullet_kills_small_ufo_and_scores():
    cm = CollisionManager()
    ufo = UFO(Vec(400, 400), small=True, target_pos=None)
    b = Bullet(1, Vec(400, 400), Vec(0, 0))
    r = cm.resolve(ships={}, bullets=[b], asteroids=[], ufos=[ufo])
    assert not ufo.alive
    assert r.score_deltas.get(1) == C.UFO_SMALL["score"]


def test_ufo_kills_asteroid_on_contact():
    cm = CollisionManager()
    ufo = UFO(Vec(500, 500), small=True, target_pos=None)
    ast = Asteroid(Vec(500, 500), Vec(0, 0), "M")
    r = cm.resolve(ships={}, bullets=[], asteroids=[ast], ufos=[ufo])
    assert not ufo.alive
    assert not ast.alive
    # M splits to 2 S
    assert len(r.asteroids_to_spawn) == 2


def test_shielded_ship_destroys_ufo_on_contact():
    cm = CollisionManager()
    ship = make_ship(pos=(600, 600))
    ship.shield.reset(C.SHIELD_DURATION)
    ufo = UFO(Vec(600, 600), small=True, target_pos=None)
    r = cm.resolve(ships={1: ship}, bullets=[], asteroids=[], ufos=[ufo])
    assert not ufo.alive, "shielded ship destroys touched UFO"
    assert r.ship_deaths == []


def test_unshielded_ship_does_not_collide_with_ufo():
    """Without a shield, ship vs UFO contact does not happen (preserved
    behavior from single-player)."""
    cm = CollisionManager()
    ship = make_ship(pos=(700, 700))
    ufo = UFO(Vec(700, 700), small=True, target_pos=None)
    r = cm.resolve(ships={1: ship}, bullets=[], asteroids=[], ufos=[ufo])
    assert ufo.alive, "no shield, no collision"
    assert r.ship_deaths == []


def test_ufo_bullet_kills_unshielded_ship():
    cm = CollisionManager()
    ship = make_ship(pos=(800, 400))
    ufo_bullet = Bullet(UFO_BULLET_OWNER, Vec(800, 400), Vec(0, 0))
    r = cm.resolve(
        ships={1: ship}, bullets=[ufo_bullet], asteroids=[], ufos=[]
    )
    assert not ufo_bullet.alive
    assert r.ship_deaths == [1]


def test_shielded_ship_absorbs_ufo_bullet():
    cm = CollisionManager()
    ship = make_ship(pos=(800, 400))
    ship.shield.reset(C.SHIELD_DURATION)
    ufo_bullet = Bullet(UFO_BULLET_OWNER, Vec(800, 400), Vec(0, 0))
    r = cm.resolve(
        ships={1: ship}, bullets=[ufo_bullet], asteroids=[], ufos=[]
    )
    assert not ufo_bullet.alive, "bullet was absorbed"
    assert r.ship_deaths == [], "shield saved the ship"


def test_player_bullet_ignores_ufo_when_ufo_bullet_also_hits():
    """When a player and a UFO bullet hit the same asteroid in the same
    frame, the asteroid dies (UFO bullet rule) and no split happens. No
    score either (player bullet is consumed but not credited)."""
    cm = CollisionManager()
    ast = Asteroid(Vec(100, 100), Vec(0, 0), "L")
    player_bullet = Bullet(1, Vec(100, 100), Vec(0, 0))
    ufo_bullet = Bullet(UFO_BULLET_OWNER, Vec(100, 100), Vec(0, 0))
    r = cm.resolve(
        ships={}, bullets=[player_bullet, ufo_bullet], asteroids=[ast], ufos=[]
    )
    assert not ast.alive
    assert not r.asteroids_to_spawn, "UFO bullet rule wins; no split"
    assert r.score_deltas == {}


def test_player_bullet_kills_other_ship_and_awards_frag():
    cm = CollisionManager()
    shooter = make_ship(player_id=1, pos=(100, 100))
    target = make_ship(player_id=2, pos=(500, 500))
    bullet = Bullet(1, Vec(500, 500), Vec(0, 0))
    r = cm.resolve(
        ships={1: shooter, 2: target}, bullets=[bullet], asteroids=[], ufos=[]
    )
    assert not bullet.alive, "bullet consumed by frag"
    assert r.ship_deaths == [2]
    assert r.score_deltas == {1: C.FRAG_SCORE}


def test_player_bullet_does_not_self_kill():
    cm = CollisionManager()
    ship = make_ship(player_id=1, pos=(300, 300))
    bullet = Bullet(1, Vec(300, 300), Vec(0, 0))
    r = cm.resolve(ships={1: ship}, bullets=[bullet], asteroids=[], ufos=[])
    assert bullet.alive, "own bullet passes through, not consumed"
    assert r.ship_deaths == []
    assert r.score_deltas == {}


def test_shielded_ship_blocks_frag():
    cm = CollisionManager()
    shooter = make_ship(player_id=1, pos=(100, 100))
    target = make_ship(player_id=2, pos=(500, 500))
    target.shield.reset(C.SHIELD_DURATION)
    bullet = Bullet(1, Vec(500, 500), Vec(0, 0))
    r = cm.resolve(
        ships={1: shooter, 2: target}, bullets=[bullet], asteroids=[], ufos=[]
    )
    assert not bullet.alive, "shield absorbs the bullet"
    assert r.ship_deaths == []
    assert r.score_deltas == {}


def test_invuln_ship_immune_to_frag():
    cm = CollisionManager()
    shooter = make_ship(player_id=1, pos=(100, 100))
    target = Ship(2, Vec(500, 500))
    target.invuln.reset(C.SAFE_SPAWN_TIME)
    bullet = Bullet(1, Vec(500, 500), Vec(0, 0))
    r = cm.resolve(
        ships={1: shooter, 2: target}, bullets=[bullet], asteroids=[], ufos=[]
    )
    assert bullet.alive, "invuln ship is skipped wholesale; bullet survives"
    assert r.ship_deaths == []
    assert r.score_deltas == {}


def test_ufo_bullet_does_not_award_frag_in_bullets_vs_ships():
    """UFO bullets stay routed through _ship_vs_ufo_bullets; _bullets_vs_ships
    must skip them and never credit UFO_BULLET_OWNER as a frag scorer."""
    cm = CollisionManager()
    ship = make_ship(player_id=2, pos=(800, 400))
    ufo_bullet = Bullet(UFO_BULLET_OWNER, Vec(800, 400), Vec(0, 0))
    r = cm.resolve(
        ships={2: ship}, bullets=[ufo_bullet], asteroids=[], ufos=[]
    )
    assert UFO_BULLET_OWNER not in r.score_deltas, (
        "UFO bullets must not yield frags"
    )
    assert r.score_deltas == {}


def test_bullets_vs_ships_records_frag_delta():
    cm = CollisionManager()
    shooter = make_ship(player_id=1, pos=(100, 100))
    target = make_ship(player_id=2, pos=(500, 500))
    bullet = Bullet(1, Vec(500, 500), Vec(0, 0))
    r = cm.resolve(
        ships={1: shooter, 2: target}, bullets=[bullet], asteroids=[], ufos=[]
    )
    assert r.frag_deltas == {1: 1}


def test_self_bullet_does_not_record_frag_delta():
    cm = CollisionManager()
    ship = make_ship(player_id=1, pos=(300, 300))
    bullet = Bullet(1, Vec(300, 300), Vec(0, 0))
    r = cm.resolve(ships={1: ship}, bullets=[bullet], asteroids=[], ufos=[])
    assert r.frag_deltas == {}


def test_shielded_target_does_not_grant_frag_delta():
    cm = CollisionManager()
    shooter = make_ship(player_id=1, pos=(100, 100))
    target = make_ship(player_id=2, pos=(500, 500))
    target.shield.reset(C.SHIELD_DURATION)
    bullet = Bullet(1, Vec(500, 500), Vec(0, 0))
    r = cm.resolve(
        ships={1: shooter, 2: target}, bullets=[bullet], asteroids=[], ufos=[]
    )
    assert r.frag_deltas == {}
