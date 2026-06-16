"""Game entities. Plain Python classes — no pygame coupling."""

from __future__ import annotations

import math
from random import Random, choice, random, randrange, uniform

from core import config as C
from core.commands import PlayerCommand
from core.utils import Countdown, Vec, angle_to_vec, wrap_pos

PlayerId = int

# Sentinel owner_id for UFO-fired bullets. Negative so it never collides with a
# real PlayerId (which is always > 0); -10 instead of -1 leaves a buffer for
# other non-player owners (e.g. environment, debug spawns) if they ever appear.
UFO_BULLET_OWNER = -10
SHRAPNEL_OWNER = -20  # Sentinel owner_id for red-asteroid shrapnel.


def rotate_vec(v: Vec, deg: float) -> Vec:
    rad = math.radians(deg)
    c = math.cos(rad)
    s = math.sin(rad)
    return Vec(v.x * c - v.y * s, v.x * s + v.y * c)


class Entity:
    """Base for every per-frame-updated entity. Owns `alive` flag.

    The World keeps entities in typed lists and purges those with alive=False
    at the end of each tick. This replaces the previous pg.sprite.Sprite +
    pg.sprite.Group machinery with a plain Python pattern, so core/ stays
    framework-independent.
    """

    __slots__ = ("alive",)

    def __init__(self) -> None:
        self.alive = True

    def kill(self) -> None:
        self.alive = False


class Particle(Entity):
    """Short-lived debris particle for explosion effects. Non-interacting.

    Particles don't wrap the screen — they live ~1s and travel ≤200px, so
    wrapping would teleport stray particles to the opposite edge and look
    like a bug.
    """

    __slots__ = ("pos", "vel", "ttl", "color")

    def __init__(
        self,
        pos: Vec,
        vel: Vec,
        ttl: float,
        color: tuple[int, int, int] = (255, 255, 255),
    ) -> None:
        super().__init__()
        self.pos = Vec(pos)
        self.vel = Vec(vel)
        self.ttl = float(ttl)
        self.color = color

    def update(self, dt: float) -> None:
        self.pos += self.vel * dt
        self.ttl -= dt
        if self.ttl <= 0.0:
            self.kill()


class Bullet(Entity):
    """Generic projectile.

    Bullets do not wrap the screen. Their range is bounded by TTL, so wrapping
    would let a shot fired at one edge instantly reappear on the opposite side
    and hit something the player never aimed at.
    """

    __slots__ = ("owner_id", "pos", "vel", "ttl", "r")

    def __init__(
        self,
        owner_id: PlayerId,
        pos: Vec,
        vel: Vec,
        ttl: float = C.BULLET_TTL,
    ) -> None:
        super().__init__()
        self.owner_id = owner_id
        self.pos = Vec(pos)
        self.vel = Vec(vel)
        self.ttl = float(ttl)
        self.r = int(C.BULLET_RADIUS)

    def update(self, dt: float) -> None:
        self.pos += self.vel * dt
        self.ttl -= dt
        if self.ttl <= 0.0:
            self.kill()


def _laser_end_pos(start: Vec, dirv: Vec) -> Vec:
    """Return the world-boundary intersection point of a ray from start in dirv."""
    t = float("inf")
    if dirv.x > 0:
        t = min(t, (C.WORLD_WIDTH - start.x) / dirv.x)
    elif dirv.x < 0:
        t = min(t, -start.x / dirv.x)
    if dirv.y > 0:
        t = min(t, (C.WORLD_HEIGHT - start.y) / dirv.y)
    elif dirv.y < 0:
        t = min(t, -start.y / dirv.y)
    if t == float("inf") or t <= 0:
        t = float(max(C.WORLD_WIDTH, C.WORLD_HEIGHT))
    return start + dirv * t


class LaserBeam(Entity):
    """Instantaneous laser beam fired from a ship with the laser powerup.

    Collision is resolved only on the first tick (resolved flag). The entity
    remains alive for LASER_BEAM_TTL seconds so the renderer can draw the
    visual flash.
    """

    __slots__ = ("owner_id", "pos", "end_pos", "ttl", "resolved")

    def __init__(
        self,
        owner_id: PlayerId,
        pos: Vec,
        end_pos: Vec,
        ttl: float = C.LASER_BEAM_TTL,
    ) -> None:
        super().__init__()
        self.owner_id = owner_id
        self.pos = Vec(pos)
        self.end_pos = Vec(end_pos)
        self.ttl = float(ttl)
        self.resolved = False

    def update(self, dt: float) -> None:
        self.ttl -= dt
        if self.ttl <= 0.0:
            self.kill()


class LaserPowerup(Entity):
    """Collectible powerup that grants the ship a laser weapon for LASER_DURATION seconds."""

    __slots__ = ("pos", "vel", "ttl", "r")

    def __init__(
        self,
        pos: Vec,
        vel: Vec,
        ttl: float = C.LASER_POWERUP_TTL,
    ) -> None:
        super().__init__()
        self.pos = Vec(pos)
        self.vel = Vec(vel)
        self.ttl = float(ttl)
        self.r = int(C.LASER_POWERUP_RADIUS)

    def update(self, dt: float) -> None:
        self.pos += self.vel * dt
        self.pos = wrap_pos(self.pos)
        self.ttl -= dt
        if self.ttl <= 0.0:
            self.kill()



class Shrapnel(Entity):
    """A debris fragment ejected by a red-asteroid explosion.

    Behaves like a bullet: it travels, wraps the world, and can kill ships
    and split asteroids.  Uses SHRAPNEL_OWNER so collision code can identify
    it without treating it as a player shot.
    """

    __slots__ = ("pos", "vel", "ttl", "r")

    def __init__(self, pos: Vec, vel: Vec) -> None:
        super().__init__()
        self.pos = Vec(pos)
        self.vel = Vec(vel)
        self.ttl = float(C.SHRAPNEL_TTL)
        self.r = int(C.SHRAPNEL_RADIUS)

    def update(self, dt: float) -> None:
        self.pos += self.vel * dt
        self.pos = wrap_pos(self.pos)
        self.ttl -= dt
        if self.ttl <= 0.0:
            self.kill()


class Asteroid(Entity):
    """Asteroid with irregular polygon shape.

    ``poly_seed`` makes the polygon deterministic: the server picks a
    seed at spawn, sends it in every snapshot, and the client rebuilds
    the same shape on each frame instead of jittering at the snapshot
    rate. Default ``None`` generates a fresh seed — used by single-player
    and tests.

    ``red`` marks a "meteoro vermelho": a cosmetic variant the renderer
    draws in red. Defaults to ``False`` so existing callers (snapshot
    rebuild, tests, splits) are unaffected.
    """

    __slots__ = ("pos", "vel", "size", "r", "poly_seed", "poly", "red")

    def __init__(
        self,
        pos: Vec,
        vel: Vec,
        size: str,
        poly_seed: int | None = None,
        red: bool = False,
    ) -> None:
        super().__init__()
        self.pos = Vec(pos)
        self.vel = Vec(vel)
        self.size = size
        self.r = int(C.AST_SIZES[size]["r"])
        self.poly_seed = (
            poly_seed if poly_seed is not None else randrange(2**31)
        )
        self.poly = self._make_poly()
        self.red = red

    def _make_poly(self) -> list[Vec]:
        steps = C.AST_POLY_STEPS[self.size]
        rng = Random(self.poly_seed)
        pts: list[Vec] = []
        for i in range(steps):
            ang = i * (360 / steps)
            jitter = rng.uniform(C.AST_POLY_JITTER_MIN, C.AST_POLY_JITTER_MAX)
            rr = self.r * jitter
            v = Vec(
                math.cos(math.radians(ang)),
                math.sin(math.radians(ang)),
            )
            pts.append(v * rr)
        return pts

    def update(self, dt: float) -> None:
        self.pos += self.vel * dt
        self.pos = wrap_pos(self.pos)


class Ship(Entity):
    """Ship controlled by command (does not read keyboard)."""

    __slots__ = (
        "player_id",
        "pos",
        "vel",
        "angle",
        "cool",
        "target_pos",
        "invuln",
        "shield",
        "shield_cd",
        "r",
        "laser",
    )

    def __init__(self, player_id: PlayerId, pos: Vec) -> None:
        super().__init__()
        self.player_id = player_id
        self.pos = Vec(pos)
        self.vel = Vec(0, 0)
        self.angle = -90.0
        self.cool = Countdown()
        self.target_pos: Vec | None = None
        self.invuln = Countdown()
        self.shield = Countdown()
        self.shield_cd = Countdown()
        self.r = int(C.SHIP_RADIUS)
        self.laser = Countdown()

    def apply_command(
        self,
        cmd: PlayerCommand,
        dt: float,
        bullets: list[Bullet],
    ) -> "Bullet | LaserBeam | None":
        if cmd.rotate_left and not cmd.rotate_right:
            self.angle -= C.SHIP_TURN_SPEED * dt
        elif cmd.rotate_right and not cmd.rotate_left:
            self.angle += C.SHIP_TURN_SPEED * dt
        if cmd.thrust:
            self.vel += angle_to_vec(self.angle) * C.SHIP_THRUST * dt
        self.vel *= C.SHIP_FRICTION
        if cmd.shoot:
            return self._try_fire(bullets)
        return None

    def _try_fire(self, bullets: list[Bullet]) -> "Bullet | LaserBeam | None":
        if self.cool.active:
            return None
        dirv = angle_to_vec(self.angle)
        spawn = self.pos + dirv * (self.r + C.BULLET_SPAWN_OFFSET)
        if self.laser.active:
            end = _laser_end_pos(spawn, dirv)
            self.cool.reset(C.LASER_FIRE_RATE)
            return LaserBeam(self.player_id, spawn, end)
        count = sum(1 for b in bullets if b.owner_id == self.player_id)
        if count >= C.MAX_BULLETS_PER_PLAYER:
            return None
        vel = self.vel + dirv * C.SHIP_BULLET_SPEED
        self.cool.reset(C.SHIP_FIRE_RATE)
        return Bullet(self.player_id, spawn, vel, ttl=C.BULLET_TTL)

    def hyperspace(self, pos: Vec) -> None:
        """Teleport to the given position. Caller picks a safe spot."""
        self.pos = Vec(pos)
        self.vel.xy = (0, 0)
        self.invuln.reset(C.SAFE_SPAWN_TIME)

    def try_activate_shield(self) -> bool:
        """Start the shield if its cooldown elapsed. True on success."""
        if self.shield_cd.active:
            return False
        self.shield.reset(C.SHIELD_DURATION)
        self.shield_cd.reset(C.SHIELD_COOLDOWN)
        return True

    def update(self, dt: float) -> None:
        self.cool.tick(dt)
        self.invuln.tick(dt)
        self.shield.tick(dt)
        self.shield_cd.tick(dt)
        self.laser.tick(dt)
        self.pos += self.vel * dt
        self.pos = wrap_pos(self.pos)

    def ship_points(self) -> tuple[Vec, Vec, Vec]:
        """Return the 3 vertices of the ship triangle."""
        dirv = angle_to_vec(self.angle)
        left = angle_to_vec(self.angle + C.SHIP_NOSE_ANGLE)
        right = angle_to_vec(self.angle - C.SHIP_NOSE_ANGLE)
        p1 = self.pos + dirv * self.r
        p2 = self.pos + left * self.r * C.SHIP_NOSE_SCALE
        p3 = self.pos + right * self.r * C.SHIP_NOSE_SCALE
        return p1, p2, p3


class UFO(Entity):
    """UFO with two movement behaviors and shooting."""

    __slots__ = (
        "small",
        "r",
        "pos",
        "vel",
        "speed",
        "cool",
        "move_dir",
        "target_pos",
    )

    def __init__(
        self,
        pos: Vec,
        small: bool,
        target_pos: Vec | None = None,
        setup_position: bool = True,
    ) -> None:
        super().__init__()
        self.small = small
        cfg = C.UFO_SMALL if small else C.UFO_BIG
        self.r = int(cfg["r"])
        self.pos = Vec(pos)
        self.vel = Vec(0, 0)
        self.speed = float(C.UFO_SPEED_SMALL if small else C.UFO_SPEED_BIG)
        self.cool = Countdown()
        self.move_dir: Vec | None = None
        self.target_pos: Vec | None = None
        # When reconstructing a UFO from a server snapshot we keep pos/vel
        # exactly as received; the crossing/pursue setup would otherwise
        # randomize them.
        if setup_position:
            if self.small:
                self._lock_small_move_dir(target_pos)
            self._setup_crossing_if_needed()

    def _lock_small_move_dir(self, target_pos: Vec | None) -> None:
        if target_pos is None:
            ang = uniform(0.0, 360.0)
            self.move_dir = Vec(
                math.cos(math.radians(ang)),
                math.sin(math.radians(ang)),
            )
            return
        to_target = Vec(target_pos) - self.pos
        if to_target.length_squared() < 1e-6:
            ang = uniform(0.0, 360.0)
            self.move_dir = Vec(
                math.cos(math.radians(ang)),
                math.sin(math.radians(ang)),
            )
            return
        self.move_dir = to_target.normalize()

    def _setup_crossing_if_needed(self) -> None:
        if self.small:
            return
        mode = choice(["h", "v", "d"])
        if mode == "h":
            y = uniform(0, C.WORLD_HEIGHT)
            left_to_right = uniform(0, 1) < 0.5
            self.pos = Vec(0 if left_to_right else C.WORLD_WIDTH, y)
            self.vel = Vec(1 if left_to_right else -1, 0) * self.speed
            return
        if mode == "v":
            x = uniform(0, C.WORLD_WIDTH)
            top_to_bottom = uniform(0, 1) < 0.5
            self.pos = Vec(x, 0 if top_to_bottom else C.WORLD_HEIGHT)
            self.vel = Vec(0, 1 if top_to_bottom else -1) * self.speed
            return
        corners = [
            Vec(0, 0),
            Vec(C.WORLD_WIDTH, 0),
            Vec(0, C.WORLD_HEIGHT),
            Vec(C.WORLD_WIDTH, C.WORLD_HEIGHT),
        ]
        start = choice(corners)
        target = Vec(C.WORLD_WIDTH - start.x, C.WORLD_HEIGHT - start.y)
        self.pos = Vec(start)
        dirv = target - start
        if dirv.length_squared() > 0:
            dirv = dirv.normalize()
        self.vel = dirv * self.speed

    def update(self, dt: float) -> None:
        self.cool.tick(dt)
        if self.small:
            self._update_pursue(dt)
        else:
            self._update_cross(dt)

    def _update_pursue(self, dt: float) -> None:
        if self.move_dir is not None:
            self.vel = self.move_dir * self.speed
        self.pos += self.vel * dt
        self._kill_if_outside_screen()

    def _update_cross(self, dt: float) -> None:
        self.pos += self.vel * dt
        self._kill_if_outside_screen()

    def _kill_if_outside_screen(self) -> None:
        margin = self.r
        out_x = self.pos.x < -margin or self.pos.x > C.WORLD_WIDTH + margin
        out_y = self.pos.y < -margin or self.pos.y > C.WORLD_HEIGHT + margin
        if out_x or out_y:
            self.kill()

    def try_fire(self) -> Bullet | None:
        if self.cool.active:
            return None
        target_pos = self.target_pos
        if target_pos is None:
            return None
        if not self.small and random() < C.UFO_BIG_MISS_CHANCE:
            ang = uniform(0.0, 360.0)
            dirv = Vec(
                math.cos(math.radians(ang)),
                math.sin(math.radians(ang)),
            )
        else:
            to_target = target_pos - self.pos
            if to_target.length_squared() < 1e-6:
                return None
            dirv = to_target.normalize()
            jitter = (
                C.UFO_AIM_JITTER_DEG_SMALL
                if self.small
                else C.UFO_AIM_JITTER_DEG_BIG
            )
            dirv = rotate_vec(dirv, uniform(-jitter, jitter))
        vel = dirv * C.UFO_BULLET_SPEED
        ttl = float(C.UFO_BULLET_TTL)
        rate = C.UFO_FIRE_RATE_SMALL if self.small else C.UFO_FIRE_RATE_BIG
        self.cool.reset(rate)
        return Bullet(UFO_BULLET_OWNER, self.pos, vel, ttl=ttl)