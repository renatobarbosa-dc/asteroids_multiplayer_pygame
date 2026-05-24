"""Collision detection and resolution. No pygame here."""

from __future__ import annotations

from dataclasses import dataclass, field
from random import uniform

from core import config as C
from core.entities import (
    UFO,
    UFO_BULLET_OWNER,
    Asteroid,
    Bullet,
    PlayerId,
    Ship,
)
from core.utils import Vec, rand_unit_vec


@dataclass
class CollisionResult:
    """Outcome of a single collision resolution pass."""

    events: list[str] = field(default_factory=list)
    score_deltas: dict[PlayerId, int] = field(default_factory=dict)
    # PvP frag counter, applied separately from score. A frag is one shooter
    # killing another player's ship; UFO/asteroid kills do not count here.
    frag_deltas: dict[PlayerId, int] = field(default_factory=dict)
    ship_deaths: list[PlayerId] = field(default_factory=list)
    asteroids_to_spawn: list[tuple[Vec, Vec, str]] = field(
        default_factory=list
    )
    # (position, kind) — kind is "asteroid", "ufo", or "ship"; World looks up
    # the count/speed/ttl tuple in core.config and spawns the particles.
    particles_to_spawn: list[tuple[Vec, str]] = field(default_factory=list)


class CollisionManager:
    """Resolves all collisions between game entities."""

    def resolve(
        self,
        ships: dict[PlayerId, Ship],
        bullets: list[Bullet],
        asteroids: list[Asteroid],
        ufos: list[UFO],
    ) -> CollisionResult:
        result = CollisionResult()
        self._bullets_vs_asteroids(bullets, asteroids, result)
        self._ufo_vs_player_bullets(ufos, bullets, result)
        self._bullets_vs_ships(ships, bullets, result)
        self._ufo_vs_asteroids(ufos, asteroids, result)
        self._ship_vs_asteroids(ships, asteroids, result)
        self._ship_vs_ufos(ships, ufos, result)
        self._ship_vs_ufo_bullets(ships, bullets, result)
        return result

    def _bullets_vs_asteroids(
        self,
        bullets: list[Bullet],
        asteroids: list[Asteroid],
        result: CollisionResult,
    ) -> None:
        for ast in asteroids:
            if not ast.alive:
                continue
            hit_bullets: list[Bullet] = []
            for b in bullets:
                if not b.alive:
                    continue
                if (ast.pos - b.pos).length() < ast.r:
                    hit_bullets.append(b)
            if not hit_bullets:
                continue

            # Kill all bullets that hit this asteroid.
            for b in hit_bullets:
                b.kill()

            if any(b.owner_id == UFO_BULLET_OWNER for b in hit_bullets):
                pos = Vec(ast.pos)
                ast.kill()
                result.events.append("asteroid_explosion")
                result.particles_to_spawn.append((pos, "asteroid"))
                continue

            player_bullets = [b for b in hit_bullets if b.owner_id > 0]
            scorer = player_bullets[0].owner_id if player_bullets else None
            self._split_asteroid(ast, scorer_id=scorer, result=result)

    def _destroy_ufo(self, ufo: UFO, result: CollisionResult) -> None:
        """Kill a UFO and emit its explosion event + particles.

        Helper shared by the three destruction sites: player bullet,
        asteroid contact, and shield.
        """
        pos = Vec(ufo.pos)
        ufo.kill()
        result.events.append("ship_explosion")
        result.particles_to_spawn.append((pos, "ufo"))

    def _ufo_vs_player_bullets(
        self,
        ufos: list[UFO],
        bullets: list[Bullet],
        result: CollisionResult,
    ) -> None:
        for ufo in ufos:
            if not ufo.alive:
                continue
            for bullet in bullets:
                if not bullet.alive or bullet.owner_id <= 0:
                    continue
                if (ufo.pos - bullet.pos).length() < (ufo.r + bullet.r):
                    score = (
                        C.UFO_SMALL["score"]
                        if ufo.small
                        else C.UFO_BIG["score"]
                    )
                    result.score_deltas[bullet.owner_id] = (
                        result.score_deltas.get(bullet.owner_id, 0) + score
                    )
                    bullet.kill()
                    self._destroy_ufo(ufo, result)
                    break

    def _ufo_vs_asteroids(
        self,
        ufos: list[UFO],
        asteroids: list[Asteroid],
        result: CollisionResult,
    ) -> None:
        """UFO hits asteroid: UFO dies, asteroid splits without score."""
        for ufo in ufos:
            if not ufo.alive:
                continue
            for ast in asteroids:
                if not ast.alive:
                    continue
                if (ufo.pos - ast.pos).length() < (ufo.r + ast.r):
                    self._destroy_ufo(ufo, result)
                    self._split_asteroid(ast, result=result)
                    break

    def _ship_vs_asteroids(
        self,
        ships: dict[PlayerId, Ship],
        asteroids: list[Asteroid],
        result: CollisionResult,
    ) -> None:
        for ship in ships.values():
            if ship.invuln.active:
                continue
            for ast in asteroids:
                if not ast.alive:
                    continue
                if (ast.pos - ship.pos).length() < (ast.r + ship.r):
                    if ship.shield.active:
                        # Shield deflects: asteroid splits, no score,
                        # ship survives.
                        self._split_asteroid(ast, result=result)
                        continue
                    result.ship_deaths.append(ship.player_id)
                    return

    def _ship_vs_ufos(
        self,
        ships: dict[PlayerId, Ship],
        ufos: list[UFO],
        result: CollisionResult,
    ) -> None:
        """Active shield destroys any UFO that touches the ship. No score."""
        for ship in ships.values():
            if not ship.shield.active:
                continue
            for ufo in ufos:
                if not ufo.alive:
                    continue
                if (ufo.pos - ship.pos).length() < (ufo.r + ship.r):
                    self._destroy_ufo(ufo, result)

    def _ship_vs_ufo_bullets(
        self,
        ships: dict[PlayerId, Ship],
        bullets: list[Bullet],
        result: CollisionResult,
    ) -> None:
        for ship in ships.values():
            if ship.invuln.active:
                continue
            for bullet in bullets:
                if not bullet.alive or bullet.owner_id != UFO_BULLET_OWNER:
                    continue
                if (bullet.pos - ship.pos).length() < (bullet.r + ship.r):
                    bullet.kill()
                    if ship.shield.active:
                        continue
                    result.ship_deaths.append(ship.player_id)
                    return

    def _bullets_vs_ships(
        self,
        ships: dict[PlayerId, Ship],
        bullets: list[Bullet],
        result: CollisionResult,
    ) -> None:
        """Player bullet hits another player's ship (deathmatch frag).

        Skips UFO bullets (handled in _ship_vs_ufo_bullets) and the shooter's
        own ship (no auto-kill — the bullet passes through harmlessly).
        """
        for ship in ships.values():
            if ship.invuln.active:
                continue
            for bullet in bullets:
                if not bullet.alive or bullet.owner_id <= 0:
                    continue
                if bullet.owner_id == ship.player_id:
                    continue
                if (bullet.pos - ship.pos).length() < (bullet.r + ship.r):
                    bullet.kill()
                    if ship.shield.active:
                        continue
                    result.score_deltas[bullet.owner_id] = (
                        result.score_deltas.get(bullet.owner_id, 0)
                        + C.FRAG_SCORE
                    )
                    result.frag_deltas[bullet.owner_id] = (
                        result.frag_deltas.get(bullet.owner_id, 0) + 1
                    )
                    result.ship_deaths.append(ship.player_id)
                    break

    def _split_asteroid(
        self,
        ast: Asteroid,
        result: CollisionResult,
        scorer_id: PlayerId | None = None,
    ) -> None:
        """Split or destroy an asteroid.

        scorer_id=None means no score is awarded (e.g. UFO-asteroid collision).
        """
        if scorer_id is not None:
            result.score_deltas[scorer_id] = (
                result.score_deltas.get(scorer_id, 0)
                + C.AST_SIZES[ast.size]["score"]
            )

        split = C.AST_SIZES[ast.size]["split"]
        pos = Vec(ast.pos)
        ast.kill()

        result.events.append("asteroid_explosion")
        result.particles_to_spawn.append((pos, "asteroid"))

        for new_size in split:
            dirv = rand_unit_vec()
            speed = (
                uniform(C.AST_VEL_MIN, C.AST_VEL_MAX) * C.AST_SPLIT_SPEED_MULT
            )
            result.asteroids_to_spawn.append((pos, dirv * speed, new_size))
