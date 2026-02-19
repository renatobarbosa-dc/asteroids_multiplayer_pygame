"""Entidades do jogo (sprites)."""

import math
from random import choice, random, uniform

import pygame as pg

from core import config as C
from core.commands import PlayerCommand
from core.utils import Vec, angle_to_vec, wrap_pos

PlayerId = int
UFO_BULLET_OWNER = -10


def rotate_vec(v: Vec, deg: float) -> Vec:
    rad = math.radians(deg)
    c = math.cos(rad)
    s = math.sin(rad)
    return Vec(v.x * c - v.y * s, v.x * s + v.y * c)


class Bullet(pg.sprite.Sprite):
    """Tiro genérico."""

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
        self.rect = pg.Rect(0, 0, self.r * 2, self.r * 2)

    def update(self, dt: float) -> None:
        self.pos += self.vel * dt
        self.pos = wrap_pos(self.pos)
        self.ttl -= dt
        if self.ttl <= 0.0:
            self.kill()
            return
        self.rect.center = (int(self.pos.x), int(self.pos.y))


class Asteroid(pg.sprite.Sprite):
    """Asteroide com polígono irregular."""

    def __init__(self, pos: Vec, vel: Vec, size: str) -> None:
        super().__init__()
        self.pos = Vec(pos)
        self.vel = Vec(vel)
        self.size = size
        self.r = int(C.AST_SIZES[size]["r"])
        self.poly = self._make_poly()
        self.rect = pg.Rect(0, 0, self.r * 2, self.r * 2)

    def _make_poly(self) -> list[Vec]:
        steps = 12 if self.size == "L" else 10 if self.size == "M" else 8
        pts: list[Vec] = []
        for i in range(steps):
            ang = i * (360 / steps)
            jitter = uniform(0.75, 1.2)
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
        self.rect.center = (int(self.pos.x), int(self.pos.y))


class Ship(pg.sprite.Sprite):
    """Nave controlada por comando (não lê teclado)."""

    def __init__(self, player_id: PlayerId, pos: Vec) -> None:
        super().__init__()
        self.player_id = player_id
        self.pos = Vec(pos)
        self.vel = Vec(0, 0)
        self.angle = -90.0
        self.cool = 0.0
        self.target_pos: Vec | None = None
        self.invuln = 0.0
        self.r = int(C.SHIP_RADIUS)
        self.rect = pg.Rect(0, 0, self.r * 2, self.r * 2)

    def apply_command(
        self,
        cmd: PlayerCommand,
        dt: float,
        bullets: pg.sprite.Group,
    ) -> "Bullet | None":
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

    def _try_fire(self, bullets: pg.sprite.Group) -> "Bullet | None":
        if self.cool > 0.0:
            return None

        count = 0
        for bullet in bullets:
            if getattr(bullet, "owner_id", None) == self.player_id:
                count += 1

        if count >= C.MAX_BULLETS_PER_PLAYER:
            return None

        dirv = angle_to_vec(self.angle)
        pos = self.pos + dirv * (self.r + 6)
        vel = self.vel + dirv * C.SHIP_BULLET_SPEED

        self.cool = float(C.SHIP_FIRE_RATE)
        return Bullet(self.player_id, pos, vel, ttl=C.BULLET_TTL)

    def hyperspace(self) -> None:
        self.pos = Vec(uniform(0, C.WIDTH), uniform(0, C.HEIGHT))
        self.vel.xy = (0, 0)
        self.invuln = float(C.SAFE_SPAWN_TIME)

    def update(self, dt: float) -> None:
        if self.cool > 0.0:
            self.cool -= dt
            if self.cool < 0.0:
                self.cool = 0.0

        if self.invuln > 0.0:
            self.invuln -= dt
            if self.invuln < 0.0:
                self.invuln = 0.0

        self.pos += self.vel * dt
        self.pos = wrap_pos(self.pos)
        self.rect.center = (int(self.pos.x), int(self.pos.y))

    def ship_points(self) -> tuple[Vec, Vec, Vec]:
        """Retorna os 3 pontos do triângulo da nave."""
        dirv = angle_to_vec(self.angle)
        left = angle_to_vec(self.angle + 140.0)
        right = angle_to_vec(self.angle - 140.0)

        p1 = self.pos + dirv * self.r
        p2 = self.pos + left * self.r * 0.9
        p3 = self.pos + right * self.r * 0.9
        return p1, p2, p3


class UFO(pg.sprite.Sprite):
    """UFO com dois comportamentos e tiro."""

    def __init__(self, pos: Vec, small: bool) -> None:
        super().__init__()
        self.small = small
        cfg = C.UFO_SMALL if small else C.UFO_BIG
        self.r = int(cfg["r"])

        self.pos = Vec(pos)
        self.vel = Vec(0, 0)
        self.speed = float(C.UFO_SPEED_SMALL if small else C.UFO_SPEED_BIG)
        self.cool = 0.0

        self.target_pos: Vec | None = None

        self._setup_crossing_if_needed()
        self.rect = pg.Rect(0, 0, self.r * 2, self.r * 2)

    def _setup_crossing_if_needed(self) -> None:
        if self.small:
            return

        mode = choice(["h", "v", "d"])
        if mode == "h":
            y = uniform(0, C.HEIGHT)
            left_to_right = uniform(0, 1) < 0.5
            self.pos = Vec(0 if left_to_right else C.WIDTH, y)
            self.vel = Vec(1 if left_to_right else -1, 0) * self.speed
            return

        if mode == "v":
            x = uniform(0, C.WIDTH)
            top_to_bottom = uniform(0, 1) < 0.5
            self.pos = Vec(x, 0 if top_to_bottom else C.HEIGHT)
            self.vel = Vec(0, 1 if top_to_bottom else -1) * self.speed
            return

        corners = [
            Vec(0, 0),
            Vec(C.WIDTH, 0),
            Vec(0, C.HEIGHT),
            Vec(C.WIDTH, C.HEIGHT),
        ]
        start = choice(corners)
        target = Vec(C.WIDTH - start.x, C.HEIGHT - start.y)
        self.pos = Vec(start)
        dirv = (target - start)
        if dirv.length_squared() > 0:
            dirv = dirv.normalize()
        self.vel = dirv * self.speed

    def update(self, dt: float) -> None:
        if self.cool > 0.0:
            self.cool -= dt
            if self.cool < 0.0:
                self.cool = 0.0

        if self.small:
            self._update_pursue(dt)
        else:
            self._update_cross(dt)

        self.rect.center = (int(self.pos.x), int(self.pos.y))

    def _update_pursue(self, dt: float) -> None:
        if self.target_pos is not None:
            to_target = self.target_pos - self.pos
            if to_target.length_squared() > 1e-6:
                desired = to_target.normalize() * self.speed
                self.vel = self.vel.lerp(desired, 0.08)

        self.pos += self.vel * dt
        self.pos = wrap_pos(self.pos)

    def _update_cross(self, dt: float) -> None:
        self.pos += self.vel * dt
        margin = 60
        out_x = self.pos.x < -margin or self.pos.x > C.WIDTH + margin
        out_y = self.pos.y < -margin or self.pos.y > C.HEIGHT + margin
        if out_x or out_y:
            self.kill()

    def try_fire(self) -> "Bullet | None":
        if self.cool > 0.0:
            return None

        target_pos = self.target_pos
        if target_pos is None:
            return None
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
        self.cool = float(rate)

        return Bullet(UFO_BULLET_OWNER, self.pos, vel, ttl=ttl)
