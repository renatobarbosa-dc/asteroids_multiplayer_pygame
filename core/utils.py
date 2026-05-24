"""Common game utilities. No pygame here — `core/` stays framework-independent."""

from __future__ import annotations

import math
from random import random, uniform

from core import config as C


class Vec:
    """2D vector with the subset of pygame.math.Vector2 used by the game.

    API is drop-in compatible with `pygame.math.Vector2` for the operations
    the codebase actually uses: construction from (x, y) / from a tuple / from
    another Vec, in-place and out-of-place +, -, * by scalar, attribute access
    on x/y, mutable xy property, length / length_squared / normalize.
    """

    __slots__ = ("x", "y")

    def __init__(self, x: float | tuple[float, float] | Vec = 0.0, y: float = 0.0) -> None:
        if isinstance(x, Vec):
            self.x = x.x
            self.y = x.y
        elif isinstance(x, tuple):
            self.x = float(x[0])
            self.y = float(x[1])
        else:
            self.x = float(x)
            self.y = float(y)

    @property
    def xy(self) -> tuple[float, float]:
        return (self.x, self.y)

    @xy.setter
    def xy(self, value: tuple[float, float]) -> None:
        self.x = float(value[0])
        self.y = float(value[1])

    def __add__(self, other: Vec) -> Vec:
        return Vec(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec) -> Vec:
        return Vec(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vec:
        return Vec(self.x * scalar, self.y * scalar)

    __rmul__ = __mul__

    def __iadd__(self, other: Vec) -> Vec:
        self.x += other.x
        self.y += other.y
        return self

    def __isub__(self, other: Vec) -> Vec:
        self.x -= other.x
        self.y -= other.y
        return self

    def __imul__(self, scalar: float) -> Vec:
        self.x *= scalar
        self.y *= scalar
        return self

    def __repr__(self) -> str:
        return f"Vec({self.x}, {self.y})"

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y)

    def length_squared(self) -> float:
        return self.x * self.x + self.y * self.y

    def normalize(self) -> Vec:
        length = self.length()
        if length == 0.0:
            return Vec(0.0, 0.0)
        return Vec(self.x / length, self.y / length)


class Countdown:
    """Saturating countdown timer driven by dt.

    Construct with the initial seconds (0 means inactive). Call tick(dt) every
    frame; it returns True on the single frame the timer reaches zero. Use
    reset(seconds) to restart it.
    """

    __slots__ = ("_t",)

    def __init__(self, seconds: float = 0.0) -> None:
        self._t = float(seconds)

    def reset(self, seconds: float) -> None:
        self._t = float(seconds)

    def tick(self, dt: float) -> bool:
        if self._t <= 0.0:
            return False
        self._t -= dt
        if self._t <= 0.0:
            self._t = 0.0
            return True
        return False

    @property
    def active(self) -> bool:
        return self._t > 0.0

    @property
    def remaining(self) -> float:
        return self._t


def wrap_pos(pos: Vec) -> Vec:
    return Vec(pos.x % C.WORLD_WIDTH, pos.y % C.WORLD_HEIGHT)


def angle_to_vec(deg: float) -> Vec:
    rad = math.radians(deg)
    return Vec(math.cos(rad), math.sin(rad))


def rand_unit_vec() -> Vec:
    ang = uniform(0, math.tau)
    return Vec(math.cos(ang), math.sin(ang))


def rand_edge_pos() -> Vec:
    if random() < 0.5:
        x = uniform(0, C.WORLD_WIDTH)
        y = 0 if random() < 0.5 else C.WORLD_HEIGHT
    else:
        x = 0 if random() < 0.5 else C.WORLD_WIDTH
        y = uniform(0, C.WORLD_HEIGHT)
    return Vec(x, y)
