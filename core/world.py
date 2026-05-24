"""Game systems (World, waves, score). No pygame here."""

from __future__ import annotations

import math
from random import uniform

from core import config as C
from core.collisions import CollisionManager
from core.commands import PlayerCommand
from core.entities import UFO, Asteroid, Bullet, Particle, Ship
from core.utils import Countdown, Vec, rand_edge_pos

PlayerId = int


class World:
    """World state and game rules.

    Multiplayer-ready:
    - World receives commands indexed by player_id.
    - World generates events (strings) for the client (sounds/effects).
    - Entities live in typed lists; dead ones (alive=False) are purged at the
      end of each update tick.
    """

    def __init__(self) -> None:
        self.ships: dict[PlayerId, Ship] = {}
        self.bullets: list[Bullet] = []
        self.asteroids: list[Asteroid] = []
        self.ufos: list[UFO] = []
        self.particles: list[Particle] = []

        self.scores: dict[PlayerId, int] = {}
        self.lives: dict[PlayerId, int] = {}
        self.extra_lives_awarded: dict[PlayerId, int] = {}
        self.wave = 0
        self.wave_cool = Countdown(C.WAVE_DELAY)
        self.ufo_timer = Countdown(C.UFO_SPAWN_EVERY)
        self.extra_life_notice = Countdown()

        self.events: list[str] = []
        self._collision_mgr = CollisionManager()

        self.game_over = False

        self.spawn_player(C.LOCAL_PLAYER_ID)

    def begin_frame(self) -> None:
        self.events.clear()

    def reset(self) -> None:
        """Reset the world (used on Game Over)."""
        self.__init__()

    def spawn_player(self, player_id: PlayerId) -> None:
        pos = Vec(C.WORLD_WIDTH / 2, C.WORLD_HEIGHT / 2)
        ship = Ship(player_id, pos)
        ship.invuln.reset(C.SAFE_SPAWN_TIME)

        self.ships[player_id] = ship
        self.scores[player_id] = 0
        self.lives[player_id] = C.START_LIVES
        self.extra_lives_awarded[player_id] = 0

    def get_ship(self, player_id: PlayerId) -> Ship | None:
        return self.ships.get(player_id)

    def start_wave(self) -> None:
        self.wave += 1
        count = C.WAVE_BASE_COUNT + self.wave

        ship_positions = [s.pos for s in self.ships.values()]

        for _ in range(count):
            pos = rand_edge_pos()
            while any((pos - sp).length() < C.AST_MIN_SPAWN_DIST for sp in ship_positions):
                pos = rand_edge_pos()

            ang = uniform(0, math.tau)
            speed = uniform(C.AST_VEL_MIN, C.AST_VEL_MAX)
            vel = Vec(math.cos(ang), math.sin(ang)) * speed
            self.spawn_asteroid(pos, vel, "L")

    def spawn_asteroid(self, pos: Vec, vel: Vec, size: str) -> None:
        self.asteroids.append(Asteroid(pos, vel, size))

    def spawn_ufo(self) -> None:
        small = uniform(0, 1) < 0.5
        pos = rand_edge_pos()
        target = self._get_nearest_ship_pos(pos)
        self.ufos.append(UFO(pos, small, target_pos=target))

    def update(
        self,
        dt: float,
        commands_by_player_id: dict[PlayerId, PlayerCommand],
    ) -> None:
        self.begin_frame()

        if self.game_over:
            return

        self._apply_commands(dt, commands_by_player_id)

        for ship in self.ships.values():
            ship.update(dt)
        for asteroid in self.asteroids:
            asteroid.update(dt)
        for bullet in self.bullets:
            bullet.update(dt)
        for particle in self.particles:
            particle.update(dt)

        self._update_ufos(dt)
        self._update_timers(dt)
        self._handle_collisions()
        self._maybe_start_next_wave(dt)
        self._purge_dead()

    def _apply_commands(
        self,
        dt: float,
        commands_by_player_id: dict[PlayerId, PlayerCommand],
    ) -> None:
        for player_id, cmd in commands_by_player_id.items():
            ship = self.get_ship(player_id)
            if ship is None:
                continue

            if cmd.hyperspace:
                ship.hyperspace(self._find_safe_hyperspace_pos(ship))
                self.scores[player_id] = max(0, self.scores[player_id] - C.HYPERSPACE_COST)

            if cmd.shield and ship.try_activate_shield():
                self.events.append("shield_on")

            bullet = ship.apply_command(cmd, dt, self.bullets)
            if bullet is not None:
                self.bullets.append(bullet)
                self.events.append("player_shoot")

    def _update_ufos(self, dt: float) -> None:
        for ufo in self.ufos:
            if not ufo.alive:
                continue
            ufo.target_pos = self._get_nearest_ship_pos(ufo.pos)
            ufo.update(dt)
            if not ufo.alive:
                continue

            bullet = ufo.try_fire()
            if bullet is not None:
                self.bullets.append(bullet)
                self.events.append("ufo_shoot")

    def _get_nearest_ship_pos(self, from_pos: Vec) -> Vec | None:
        """Return position of the nearest living ship to from_pos."""
        nearest = None
        min_dist = float("inf")
        for ship in self.ships.values():
            d = (ship.pos - from_pos).length()
            if d < min_dist:
                min_dist = d
                nearest = ship
        return nearest.pos if nearest else None

    def _find_safe_hyperspace_pos(self, ship: Ship) -> Vec:
        """Pick a random position that is not on top of an asteroid.

        Tries HYPERSPACE_ATTEMPTS times. Falls back to an unchecked random
        position if no clear spot is found, which only happens when the screen
        is saturated with asteroids.
        """
        for _ in range(C.HYPERSPACE_ATTEMPTS):
            pos = Vec(uniform(0, C.WORLD_WIDTH), uniform(0, C.WORLD_HEIGHT))
            if all(
                (pos - ast.pos).length() > (ast.r + ship.r + C.HYPERSPACE_SAFE_MARGIN)
                for ast in self.asteroids
            ):
                return pos
        return Vec(uniform(0, C.WORLD_WIDTH), uniform(0, C.WORLD_HEIGHT))

    def _update_timers(self, dt: float) -> None:
        if self.ufo_timer.tick(dt):
            self.spawn_ufo()
            self.ufo_timer.reset(C.UFO_SPAWN_EVERY)
        self.extra_life_notice.tick(dt)

    def _maybe_start_next_wave(self, dt: float) -> None:
        if self.asteroids:
            return

        if self.wave_cool.tick(dt):
            self.start_wave()
            self.wave_cool.reset(C.WAVE_DELAY)

    def _handle_collisions(self) -> None:
        result = self._collision_mgr.resolve(
            self.ships,
            self.bullets,
            self.asteroids,
            self.ufos,
        )

        self.events.extend(result.events)

        for player_id, delta in result.score_deltas.items():
            if player_id in self.scores:
                self.scores[player_id] += delta
                self._maybe_award_extra_life(player_id)

        for pos, vel, size in result.asteroids_to_spawn:
            self.spawn_asteroid(pos, vel, size)

        for pos, kind in result.particles_to_spawn:
            self._spawn_particles(pos, kind)

        for player_id in result.ship_deaths:
            ship = self.get_ship(player_id)
            if ship is not None:
                self._spawn_particles(Vec(ship.pos), "ship")
                self._ship_die(ship)

    def _spawn_particles(self, pos: Vec, kind: str) -> None:
        count, sp_min, sp_max, ttl = {
            "asteroid": C.PARTICLE_ASTEROID,
            "ufo": C.PARTICLE_UFO,
            "ship": C.PARTICLE_SHIP,
        }[kind]
        for _ in range(count):
            ang = uniform(0.0, math.tau)
            speed = uniform(sp_min, sp_max)
            vel = Vec(math.cos(ang), math.sin(ang)) * speed
            self.particles.append(Particle(pos, vel, ttl))

    def _ship_die(self, ship: Ship) -> None:
        pid = ship.player_id
        self.lives[pid] = self.lives[pid] - 1
        ship.pos.xy = (C.WORLD_WIDTH / 2, C.WORLD_HEIGHT / 2)
        ship.vel.xy = (0, 0)
        ship.angle = -90.0
        ship.invuln.reset(C.SAFE_SPAWN_TIME)

        self.events.append("ship_explosion")
        if all(v <= 0 for v in self.lives.values()):
            self.game_over = True

    def _maybe_award_extra_life(self, player_id: PlayerId) -> None:
        """Grant one extra life per EXTRA_LIFE_EVERY-point threshold crossed."""
        total = self.scores[player_id]
        already = self.extra_lives_awarded[player_id]
        target = total // C.EXTRA_LIFE_EVERY
        if target <= already:
            return
        gained = target - already
        self.lives[player_id] += gained
        self.extra_lives_awarded[player_id] = target
        self.extra_life_notice.reset(C.EXTRA_LIFE_NOTICE_TIME)
        self.events.append("extra_life")

    def _purge_dead(self) -> None:
        """Drop dead entities at the end of the tick. Keeps lists from growing."""
        self.bullets = [b for b in self.bullets if b.alive]
        self.asteroids = [a for a in self.asteroids if a.alive]
        self.ufos = [u for u in self.ufos if u.alive]
        self.particles = [p for p in self.particles if p.alive]
