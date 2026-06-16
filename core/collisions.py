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
    LaserBeam,
    LaserPowerup,
    PlayerId,
    SHRAPNEL_OWNER,
    Shrapnel,
    Ship,
)
from core.utils import Vec, rand_unit_vec


def _segment_circle_hit(
    seg_a: Vec, seg_b: Vec, center: Vec, radius: float
) -> bool:
    """Return True when segment AB intersects a circle at center with radius."""
    ab = seg_b - seg_a
    ac = center - seg_a
    ab_len_sq = ab.length_squared()
    if ab_len_sq < 1e-10:
        return ac.length() < radius
    t = (ac.x * ab.x + ac.y * ab.y) / ab_len_sq
    t = max(0.0, min(1.0, t))
    closest_x = seg_a.x + ab.x * t
    closest_y = seg_a.y + ab.y * t
    dx = center.x - closest_x
    dy = center.y - closest_y
    return dx * dx + dy * dy < radius * radius


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
    # (player_id, powerup_pos) pairs for each laser powerup collected this tick.
    powerup_pickups: list[tuple[PlayerId, Vec]] = field(default_factory=list)
    # Shrapnel fragments spawned by red-asteroid explosions.
    shrapnel_to_spawn: list[tuple[Vec, Vec]] = field(default_factory=list)


class CollisionManager:
    """Resolves all collisions between game entities."""

    def resolve(
        self,
        ships: dict[PlayerId, Ship],
        bullets: list[Bullet],
        asteroids: list[Asteroid],
        ufos: list[UFO],
        powerups: list[LaserPowerup] | None = None,
        lasers: list[LaserBeam] | None = None,
    ) -> CollisionResult:
        result = CollisionResult()
        if powerups is not None:
            self._ship_vs_powerups(ships, powerups, result)
        if lasers:
            self._laser_vs_asteroids(lasers, asteroids, result, ships=ships)
            self._laser_vs_ufos(lasers, ufos, result)
            self._laser_vs_ships(lasers, ships, result)
            for laser in lasers:
                laser.resolved = True
        self._bullets_vs_asteroids(bullets, asteroids, result, ships=ships)
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
        ships: dict | None = None,
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
            self._split_asteroid(ast, scorer_id=scorer, result=result, all_asteroids=asteroids, ships=ships)

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
                    self._split_asteroid(ast, result=result, all_asteroids=asteroids)
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
                        self._split_asteroid(ast, result=result, all_asteroids=asteroids)
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

    def _ship_vs_powerups(
        self,
        ships: dict[PlayerId, Ship],
        powerups: list[LaserPowerup],
        result: CollisionResult,
    ) -> None:
        """Ship overlaps laser powerup: powerup is collected."""
        for powerup in powerups:
            if not powerup.alive:
                continue
            for ship in ships.values():
                if (ship.pos - powerup.pos).length() < (ship.r + powerup.r):
                    powerup.kill()
                    result.powerup_pickups.append(
                        (ship.player_id, Vec(powerup.pos))
                    )
                    break

    def _laser_vs_asteroids(
        self,
        lasers: list[LaserBeam],
        asteroids: list[Asteroid],
        result: CollisionResult,
        ships: dict | None = None,
    ) -> None:
        """Laser beam hits all asteroids along its path."""
        for laser in lasers:
            if not laser.alive or laser.resolved:
                continue
            for ast in asteroids:
                if not ast.alive:
                    continue
                if _segment_circle_hit(laser.pos, laser.end_pos, ast.pos, ast.r):
                    self._split_asteroid(ast, scorer_id=laser.owner_id, result=result, all_asteroids=asteroids, ships=ships)

    def _laser_vs_ufos(
        self,
        lasers: list[LaserBeam],
        ufos: list[UFO],
        result: CollisionResult,
    ) -> None:
        """Laser beam destroys all UFOs along its path."""
        for laser in lasers:
            if not laser.alive or laser.resolved:
                continue
            for ufo in ufos:
                if not ufo.alive:
                    continue
                if _segment_circle_hit(laser.pos, laser.end_pos, ufo.pos, float(ufo.r)):
                    score = (
                        C.UFO_SMALL["score"] if ufo.small else C.UFO_BIG["score"]
                    )
                    result.score_deltas[laser.owner_id] = (
                        result.score_deltas.get(laser.owner_id, 0) + score
                    )
                    self._destroy_ufo(ufo, result)

    def _laser_vs_ships(
        self,
        lasers: list[LaserBeam],
        ships: dict[PlayerId, Ship],
        result: CollisionResult,
    ) -> None:
        """Laser beam kills enemy ships it crosses (deathmatch frag)."""
        for laser in lasers:
            if not laser.alive or laser.resolved:
                continue
            for ship in ships.values():
                if ship.player_id == laser.owner_id:
                    continue
                if ship.invuln.active or ship.shield.active:
                    continue
                if _segment_circle_hit(laser.pos, laser.end_pos, ship.pos, float(ship.r)):
                    result.score_deltas[laser.owner_id] = (
                        result.score_deltas.get(laser.owner_id, 0) + C.FRAG_SCORE
                    )
                    result.frag_deltas[laser.owner_id] = (
                        result.frag_deltas.get(laser.owner_id, 0) + 1
                    )
                    result.ship_deaths.append(ship.player_id)

    def resolve_shrapnel(
        self,
        shrapnel: list["Shrapnel"],
        asteroids: list[Asteroid],
        ships: dict[PlayerId, "Ship"],
        result: CollisionResult,
    ) -> None:
        """Resolve shrapnel fragments against asteroids and ships.

        Each fragment that hits an asteroid splits it (no score).
        Each fragment that hits a ship kills the ship (respects shield/invuln).
        Fragments are consumed on first hit.
        """
        for frag in shrapnel:
            if not frag.alive:
                continue
            # vs asteroids
            for ast in asteroids:
                if not ast.alive:
                    continue
                if (ast.pos - frag.pos).length() < ast.r + frag.r:
                    frag.kill()
                    self._split_asteroid(ast, result=result, all_asteroids=asteroids)
                    break
            if not frag.alive:
                continue
            # vs ships
            for ship in ships.values():
                if ship.invuln.active:
                    continue
                if (ship.pos - frag.pos).length() < ship.r + frag.r:
                    frag.kill()
                    if not ship.shield.active:
                        result.ship_deaths.append(ship.player_id)
                    break

    def _split_asteroid(
        self,
        ast: Asteroid,
        result: CollisionResult,
        scorer_id: PlayerId | None = None,
        all_asteroids: list[Asteroid] | None = None,
        ships: dict | None = None,
    ) -> None:
        """Split or destroy an asteroid.

        scorer_id=None means no score is awarded (e.g. UFO-asteroid collision).
        If ast.red is True, the asteroid explodes and destroys all asteroids
        and ships within RED_EXPLOSION_RADIUS instead of splitting.
        """
        if scorer_id is not None:
            result.score_deltas[scorer_id] = (
                result.score_deltas.get(scorer_id, 0)
                + C.AST_SIZES[ast.size]["score"]
            )

        pos = Vec(ast.pos)
        ast.kill()

        if ast.red:
            result.events.append("red_explosion")
            # Eject shrapnel fragments in all directions.
            for _ in range(C.SHRAPNEL_COUNT):
                dirv = rand_unit_vec()
                speed = uniform(C.SHRAPNEL_SPEED_MIN, C.SHRAPNEL_SPEED_MAX)
                result.shrapnel_to_spawn.append((pos, dirv * speed))
            # Kill ships within RED_EXPLOSION_RADIUS (respects shield/invuln).
            if ships is not None:
                for ship in ships.values():
                    if ship.invuln.active:
                        continue
                    if (ship.pos - pos).length() < C.RED_EXPLOSION_RADIUS:
                        if ship.shield.active:
                            continue
                        result.ship_deaths.append(ship.player_id)
            # Destroy all asteroids within RED_EXPLOSION_RADIUS and award score.
            if all_asteroids is not None:
                for other in list(all_asteroids):
                    if not other.alive or other is ast:
                        continue
                    if (other.pos - pos).length() < C.RED_EXPLOSION_RADIUS:
                        if scorer_id is not None:
                            result.score_deltas[scorer_id] = (
                                result.score_deltas.get(scorer_id, 0)
                                + C.AST_SIZES[other.size]["score"]
                            )
                        self._split_asteroid(
                            other,
                            result=result,
                            scorer_id=scorer_id,
                            all_asteroids=all_asteroids,
                            ships=ships,
                        )
            return

        split = C.AST_SIZES[ast.size]["split"]
        result.events.append("asteroid_explosion")
        result.particles_to_spawn.append((pos, "asteroid"))

        for new_size in split:
            dirv = rand_unit_vec()
            speed = (
                uniform(C.AST_VEL_MIN, C.AST_VEL_MAX) * C.AST_SPLIT_SPEED_MULT
            )
            result.asteroids_to_spawn.append((pos, dirv * speed, new_size))