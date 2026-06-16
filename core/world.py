"""Game systems (World, waves, score). No pygame here."""

from __future__ import annotations

import math
from random import random, uniform

from core import config as C
from core.collisions import CollisionManager
from core.commands import PlayerCommand
from core.entities import UFO, Asteroid, Bullet, LaserBeam, LaserPowerup, Particle, Shrapnel, Ship
from core.utils import Countdown, Vec, rand_edge_pos, wrap_pos

PlayerId = int


class World:
    """World state and game rules.

    Multiplayer-ready:
    - World receives commands indexed by player_id.
    - World generates events (strings) for the client (sounds/effects).
    - Entities live in typed lists; dead ones (alive=False) are purged at the
      end of each update tick.
    """

    def __init__(
        self,
        spawn_default_player: bool = True,
        deathmatch: bool = False,
    ) -> None:
        self.deathmatch = deathmatch
        # Match lifecycle: deathmatch worlds wait in "lobby" until enough
        # players join; single-player worlds start in "running" so the
        # update loop drives the simulation from the first tick.
        self.match_state: str = "lobby" if deathmatch else "running"
        self.ships: dict[PlayerId, Ship] = {}
        self.bullets: list[Bullet] = []
        self.shrapnel: list[Shrapnel] = []
        self.asteroids: list[Asteroid] = []
        self.ufos: list[UFO] = []
        self.particles: list[Particle] = []
        self.powerups: list[LaserPowerup] = []
        self.lasers: list[LaserBeam] = []
        self.scores: dict[PlayerId, int] = {}
        self.lives: dict[PlayerId, int] = {}
        self.deaths: dict[PlayerId, int] = {}
        self.frags: dict[PlayerId, int] = {}
        self.respawning: dict[PlayerId, Countdown] = {}
        self.extra_lives_awarded: dict[PlayerId, int] = {}
        # Display names of connected players, keyed by player_id. Populated
        # by the server from the HELLO payload and ferried through the
        # snapshot; single-player keeps this empty.
        self.names: dict[PlayerId, str] = {}
        self.wave = 0
        self.wave_cool = Countdown(C.WAVE_DELAY)
        self.ufo_timer = Countdown(C.UFO_SPAWN_EVERY)
        self.extra_life_notice = Countdown()
        # Match-end clock; reset on lobby -> running, ticked only while
        # the match is running, latched once the match ends.
        self.match_timer: Countdown = Countdown(0.0)
        self.winner_id: int | None = None
        self.events: list[str] = []
        # Particle-spawning events recorded each tick; the server ships them
        # in the snapshot so the networked client can recreate visuals
        # without simulating collisions itself.
        self.particle_events: list[tuple[str, Vec]] = []
        # Laser beam events recorded each tick: (owner_id, start, end).
        # Sent in the snapshot so the networked client can render the beam.
        self.laser_events: list[tuple[int, Vec, Vec]] = []
        self.powerup_timer = Countdown(C.LASER_POWERUP_SPAWN_EVERY)
        self._collision_mgr = CollisionManager()
        self.game_over = False
        # Single-player keeps the implicit local ship; server and networked
        # client opt out and let real connections drive ship lifecycle.
        if spawn_default_player:
            self.spawn_player(C.LOCAL_PLAYER_ID)

    def begin_frame(self) -> None:
        self.events.clear()
        self.particle_events.clear()
        self.laser_events.clear()

    def reset(self) -> None:
        """Reset the world. Single-player game-over keeps the implicit
        local ship; deathmatch worlds stay empty so the server can
        re-spawn each connection explicitly."""
        deathmatch = self.deathmatch
        self.__init__(
            spawn_default_player=not deathmatch, deathmatch=deathmatch
        )

    def spawn_player(self, player_id: PlayerId) -> None:
        if self.deathmatch:
            temp = Ship(player_id, Vec(0, 0))
            pos = self._find_safe_hyperspace_pos(temp)
        else:
            pos = Vec(C.WORLD_WIDTH / 2, C.WORLD_HEIGHT / 2)
        ship = Ship(player_id, pos)
        ship.invuln.reset(C.SAFE_SPAWN_TIME)
        self.ships[player_id] = ship
        self.scores[player_id] = 0
        self.lives[player_id] = C.START_LIVES
        self.deaths[player_id] = 0
        self.frags[player_id] = 0
        self.extra_lives_awarded[player_id] = 0

    def despawn_player(self, player_id: PlayerId) -> None:
        """Drop every World-owned slot for ``player_id``.

        Symmetric to ``spawn_player`` and idempotent — adding a new
        per-player dict here is the single change required when a
        future feature introduces one.
        """
        self.ships.pop(player_id, None)
        self.scores.pop(player_id, None)
        self.lives.pop(player_id, None)
        self.deaths.pop(player_id, None)
        self.frags.pop(player_id, None)
        self.respawning.pop(player_id, None)
        self.extra_lives_awarded.pop(player_id, None)

    def get_ship(self, player_id: PlayerId) -> Ship | None:
        return self.ships.get(player_id)

    def start_wave(self) -> None:
        self.wave += 1
        count = C.WAVE_BASE_COUNT + self.wave
        ship_positions = [s.pos for s in self.ships.values()]
        for _ in range(count):
            pos = rand_edge_pos()
            while any(
                (pos - sp).length() < C.AST_MIN_SPAWN_DIST
                for sp in ship_positions
            ):
                pos = rand_edge_pos()
            ang = uniform(0, math.tau)
            speed = uniform(C.AST_VEL_MIN, C.AST_VEL_MAX)
            vel = Vec(math.cos(ang), math.sin(ang)) * speed
            # Cada meteoro grande tem RED_ASTEROID_CHANCE de nascer vermelho.
            is_red = random() < C.RED_ASTEROID_CHANCE
            self.spawn_asteroid(pos, vel, "L", red=is_red)

    def spawn_asteroid(
        self, pos: Vec, vel: Vec, size: str, red: bool = False
    ) -> None:
        self.asteroids.append(Asteroid(pos, vel, size, red=red))

    def spawn_ufo(self) -> None:
        small = uniform(0, 1) < 0.5
        pos = rand_edge_pos()
        target = self._get_nearest_ship_pos(pos)
        self.ufos.append(UFO(pos, small, target_pos=target))

    def update_local_visual(
        self, dt: float, local_player_id: PlayerId | None = None
    ) -> None:
        """Smooth motion between authoritative snapshots for rendering.

        The networked client never runs the authoritative `update` —
        snapshots arrive at SNAPSHOT_HZ and overwrite every entity list.
        This advances positions purely for rendering, and decays particle
        ttl locally (particles are not transmitted; the client spawns
        them from events and must age them out itself, otherwise they
        accumulate forever).

        Remote ships are dead-reckoned by their velocity too, so other
        players stop stuttering between 30 Hz snapshots. The local ship
        is skipped: the client predicts it from input instead (passing
        `local_player_id`). With no id given, every ship advances.
        """
        for pid, s in self.ships.items():
            if pid == local_player_id:
                continue
            s.pos = wrap_pos(s.pos + s.vel * dt)
        for a in self.asteroids:
            a.pos = wrap_pos(a.pos + a.vel * dt)
        for b in self.bullets:
            b.pos += b.vel * dt
        for s in self.shrapnel:
            s.pos = wrap_pos(s.pos + s.vel * dt)
        for u in self.ufos:
            u.pos = wrap_pos(u.pos + u.vel * dt)
        for p in self.particles:
            p.pos += p.vel * dt
            p.ttl -= dt
            if p.ttl <= 0.0:
                p.kill()
        self.particles = [p for p in self.particles if p.alive]
        for powerup in self.powerups:
            powerup.pos = wrap_pos(powerup.pos + powerup.vel * dt)
        for laser in self.lasers:
            laser.ttl -= dt
            if laser.ttl <= 0.0:
                laser.kill()
        self.lasers = [l for l in self.lasers if l.alive]

    def update(
        self,
        dt: float,
        commands_by_player_id: dict[PlayerId, PlayerCommand],
    ) -> None:
        self.begin_frame()
        if self.game_over:
            return
        if self.match_state == "lobby":
            self._maybe_start_match()
            return
        if self.match_state == "ended":
            return
        self._apply_commands(dt, commands_by_player_id)
        for ship in self.ships.values():
            ship.update(dt)
        for asteroid in self.asteroids:
            asteroid.update(dt)
        for bullet in self.bullets:
            bullet.update(dt)
        for frag in self.shrapnel:
            frag.update(dt)
        for particle in self.particles:
            particle.update(dt)
        for powerup in self.powerups:
            powerup.update(dt)
        for laser in self.lasers:
            laser.update(dt)
        self._update_ufos(dt)
        self._update_timers(dt)
        self._update_respawns(dt)
        self._handle_collisions()
        self._handle_shrapnel()
        self._maybe_end_match(dt)
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
                self.scores[player_id] = max(
                    0, self.scores[player_id] - C.HYPERSPACE_COST
                )
            if cmd.shield and ship.try_activate_shield():
                self.events.append("shield_on")
            shot = ship.apply_command(cmd, dt, self.bullets)
            if isinstance(shot, LaserBeam):
                self.lasers.append(shot)
                self.laser_events.append(
                    (shot.owner_id, Vec(shot.pos), Vec(shot.end_pos))
                )
                self.events.append("laser_shoot")
            elif shot is not None:
                self.bullets.append(shot)
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

    def _maybe_start_match(self) -> None:
        """Move from lobby to running once enough players have connected."""
        if len(self.ships) >= C.MIN_PLAYERS_TO_START:
            self.match_state = "running"
            self.match_timer.reset(C.MATCH_DURATION)
            self.winner_id = None

    def _maybe_end_match(self, dt: float) -> None:
        """End the match on timer expiry or once any player hits FRAG_LIMIT."""
        if self.match_state != "running":
            return
        expired = self.match_timer.tick(dt)
        over_limit = any(v >= C.FRAG_LIMIT for v in self.frags.values())
        if expired or over_limit:
            self.match_state = "ended"
            self.winner_id = self._pick_winner()

    def _pick_winner(self) -> int | None:
        """Player with the most frags wins; ties broken by smaller pid."""
        if not self.frags:
            return None
        return max(self.frags.keys(), key=lambda pid: (self.frags[pid], -pid))

    def _update_respawns(self, dt: float) -> None:
        for pid, timer in list(self.respawning.items()):
            if timer.tick(dt):
                self._respawn_player(pid)
                self.respawning.pop(pid, None)

    def _respawn_player(self, pid: PlayerId) -> None:
        """Bring a dead deathmatch player back at a safe random position."""
        temp = Ship(pid, Vec(0, 0))
        pos = self._find_safe_hyperspace_pos(temp)
        ship = Ship(pid, pos)
        ship.invuln.reset(C.SAFE_SPAWN_TIME)
        self.ships[pid] = ship

    def _find_safe_hyperspace_pos(self, ship: Ship) -> Vec:
        """Pick a random position not on top of an asteroid or other ship.

        Other ships matter for deathmatch (initial spawn, respawn, and
        hyperspace would otherwise stack two players on the same pixel).
        Single-player has only one ship, so the filter is a no-op there.

        Tries HYPERSPACE_ATTEMPTS times. Falls back to an unchecked random
        position if no clear spot is found, which only happens when the
        world is saturated.
        """
        others = [
            s for s in self.ships.values() if s.player_id != ship.player_id
        ]
        for _ in range(C.HYPERSPACE_ATTEMPTS):
            pos = Vec(uniform(0, C.WORLD_WIDTH), uniform(0, C.WORLD_HEIGHT))
            asteroids_clear = all(
                (pos - ast.pos).length()
                > (ast.r + ship.r + C.HYPERSPACE_SAFE_MARGIN)
                for ast in self.asteroids
            )
            ships_clear = all(
                (pos - other.pos).length()
                > (other.r + ship.r + C.HYPERSPACE_SAFE_MARGIN)
                for other in others
            )
            if asteroids_clear and ships_clear:
                return pos
        return Vec(uniform(0, C.WORLD_WIDTH), uniform(0, C.WORLD_HEIGHT))

    def _update_timers(self, dt: float) -> None:
        if self.ufo_timer.tick(dt):
            self.spawn_ufo()
            self.ufo_timer.reset(C.UFO_SPAWN_EVERY)
        if self.powerup_timer.tick(dt):
            self._spawn_laser_powerup()
            self.powerup_timer.reset(C.LASER_POWERUP_SPAWN_EVERY)
        self.extra_life_notice.tick(dt)

    def _spawn_laser_powerup(self) -> None:
        """Spawn a laser powerup near an active ship."""
        alive_ships = list(self.ships.values())
        if alive_ships:
            ship = alive_ships[int(uniform(0, len(alive_ships)))]
            offset = Vec(
                uniform(-C.WINDOW_WIDTH / 3, C.WINDOW_WIDTH / 3),
                uniform(-C.WINDOW_HEIGHT / 3, C.WINDOW_HEIGHT / 3),
            )
            pos = wrap_pos(ship.pos + offset)
        else:
            pos = Vec(uniform(0, C.WORLD_WIDTH), uniform(0, C.WORLD_HEIGHT))
        self.powerups.append(LaserPowerup(pos, Vec(0, 0)))

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
            self.powerups,
            self.lasers,
        )
        self.events.extend(result.events)
        for player_id, delta in result.score_deltas.items():
            if player_id in self.scores:
                self.scores[player_id] += delta
                self._maybe_award_extra_life(player_id)
        for player_id, delta in result.frag_deltas.items():
            if player_id in self.frags:
                self.frags[player_id] += delta
        for pos, vel, size in result.asteroids_to_spawn:
            self.spawn_asteroid(pos, vel, size)
        for pos, vel in result.shrapnel_to_spawn:
            self.shrapnel.append(Shrapnel(pos, vel))
        for pos, kind in result.particles_to_spawn:
            self._spawn_particles(pos, kind)
        for player_id, _ in result.powerup_pickups:
            ship = self.get_ship(player_id)
            if ship is not None:
                ship.laser.reset(C.LASER_DURATION)
                self.events.append("laser_pickup")
        for player_id in result.ship_deaths:
            ship = self.get_ship(player_id)
            if ship is not None:
                self._spawn_particles(Vec(ship.pos), "ship")
                self._ship_die(ship)

    def _spawn_particles(self, pos: Vec, kind: str) -> None:
        self.particle_events.append((kind, Vec(pos)))
        count, sp_min, sp_max, ttl = {
            "asteroid": C.PARTICLE_ASTEROID,
            "ufo": C.PARTICLE_UFO,
            "ship": C.PARTICLE_SHIP,
            "red_explosion": C.PARTICLE_RED_EXPLOSION,
        }[kind]
        color = C.RED_ASTEROID_COLOR if kind == "red_explosion" else (255, 255, 255)
        for _ in range(count):
            ang = uniform(0.0, math.tau)
            speed = uniform(sp_min, sp_max)
            vel = Vec(math.cos(ang), math.sin(ang)) * speed
            self.particles.append(Particle(pos, vel, ttl, color))

    def _ship_die(self, ship: Ship) -> None:
        pid = ship.player_id
        self.events.append("ship_explosion")
        if self.deathmatch:
            self.deaths[pid] = self.deaths.get(pid, 0) + 1
            self.ships.pop(pid, None)
            self.respawning[pid] = Countdown(C.RESPAWN_DELAY)
            return
        # Single-player: respawn-in-place with a life consumed.
        self.lives[pid] = self.lives[pid] - 1
        ship.pos.xy = (C.WORLD_WIDTH / 2, C.WORLD_HEIGHT / 2)
        ship.vel.xy = (0, 0)
        ship.angle = -90.0
        ship.invuln.reset(C.SAFE_SPAWN_TIME)
        ship.laser.reset(0.0)
        if all(v <= 0 for v in self.lives.values()):
            self.game_over = True

    def _maybe_award_extra_life(self, player_id: PlayerId) -> None:
        """Grant one extra life per EXTRA_LIFE_EVERY-point threshold crossed.

        Disabled in deathmatch: respawns are infinite there, so lives are
        not the scoring resource.
        """
        if self.deathmatch:
            return
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

    def _handle_shrapnel(self) -> None:
        """Resolve live shrapnel fragments against asteroids and ships each tick."""
        if not self.shrapnel:
            return
        from core.collisions import CollisionResult as CR
        sr = CR()
        self._collision_mgr.resolve_shrapnel(
            self.shrapnel, self.asteroids, self.ships, sr
        )
        self.events.extend(sr.events)
        for pos, kind in sr.particles_to_spawn:
            self._spawn_particles(pos, kind)
        for pos, vel, size in sr.asteroids_to_spawn:
            self.spawn_asteroid(pos, vel, size)
        for player_id in sr.ship_deaths:
            ship = self.get_ship(player_id)
            if ship is not None:
                self._spawn_particles(Vec(ship.pos), "ship")
                self._ship_die(ship)

    def _purge_dead(self) -> None:
        """Drop dead entities at end of tick to keep lists bounded."""
        self.bullets = [b for b in self.bullets if b.alive]
        self.shrapnel = [s for s in self.shrapnel if s.alive]
        self.asteroids = [a for a in self.asteroids if a.alive]
        self.ufos = [u for u in self.ufos if u.alive]
        self.particles = [p for p in self.particles if p.alive]
        self.powerups = [p for p in self.powerups if p.alive]
        self.lasers = [l for l in self.lasers if l.alive]