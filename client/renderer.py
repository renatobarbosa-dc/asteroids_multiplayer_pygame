"""Client-side rendering (pygame)."""

import math

import pygame as pg

from client.camera import Camera
from core import config as C
from core.entities import UFO, Asteroid, Bullet, LaserBeam, LaserPowerup, Particle, Shrapnel, Ship
from core.scene import SceneState
from core.utils import Vec, angle_to_vec


def color_for_player(
    player_id: int,
    palette: tuple[tuple[int, int, int], ...] = C.PLAYER_COLORS,
) -> tuple[int, int, int]:
    """Pick the ship color for ``player_id``.

    Slot 1 takes the first palette entry (red); slot 8 takes the last
    (white); slot 9 wraps to slot 1, etc. Non-positive ids fall back
    to white — used by UFO bullets and other sentinels.
    """
    if player_id <= 0:
        return C.WHITE
    return palette[(player_id - 1) % len(palette)]


class Renderer:
    """Draws scenes and entities without coupling game rules to Game."""

    def __init__(
        self,
        screen: pg.Surface,
        camera: Camera,
        config: object = C,
        fonts: dict[str, pg.font.Font] | None = None,
    ) -> None:
        self.screen = screen
        self.camera = camera
        self.config = config
        safe_fonts = fonts or {}
        self.font = safe_fonts["font"]
        self.big = safe_fonts["big"]

    def clear(self) -> None:
        self.screen.fill(self.config.BLACK)

    def draw_world(self, world: object) -> None:
        # Order matters: bottom layers drawn first.
        for particle in world.particles:
            self._draw_particle(particle)
        for bullet in world.bullets:
            self._draw_bullet(bullet)
        for frag in getattr(world, "shrapnel", []):
            self._draw_shrapnel(frag)
        for asteroid in world.asteroids:
            self._draw_asteroid(asteroid)
        for ufo in world.ufos:
            self._draw_ufo(ufo)
        for powerup in getattr(world, "powerups", []):
            self._draw_powerup(powerup)
        for laser in getattr(world, "lasers", []):
            self._draw_laser_beam(laser)
        for ship in world.ships.values():
            self._draw_ship(ship)
            self._draw_ship_name(ship, world)

    def draw_hud(
        self,
        score: int,
        lives: int,
        wave: int,
        state: SceneState,
        extra_life_remaining: float = 0.0,
    ) -> None:
        if state != SceneState.PLAY:
            return

        text = f"SCORE {score:06d}   LIVES {lives}   WAVE {wave}"
        label = self.font.render(text, True, self.config.WHITE)
        self.screen.blit(label, (10, 10))

        if (
            extra_life_remaining > 0.0
            and int(extra_life_remaining * 6) % 2 == 0
        ):
            notice = self.big.render("EXTRA LIFE", True, self.config.WHITE)
            x = (self.config.WINDOW_WIDTH - notice.get_width()) // 2
            self.screen.blit(notice, (x, 60))

    def draw_menu(self) -> None:
        self._draw_centered(self.big, "ASTEROIDS", 90)

        self._draw_centered(self.font, "ENTER  -  START GAME", 220)

        controls = [
            ("LEFT / RIGHT", "ROTATE"),
            ("UP", "THRUST"),
            ("DOWN", "SHIELD"),
            ("SPACE", "SHOOT"),
            ("LEFT SHIFT", "HYPERSPACE"),
        ]
        maxkey = max(len(k) for k, _ in controls)
        lines = [f"{k:<{maxkey}}  -  {a}" for k, a in controls]
        labels = [
            self.font.render(line, True, self.config.WHITE) for line in lines
        ]
        widest = max(label.get_width() for label in labels)
        x = (self.config.WINDOW_WIDTH - widest) // 2

        y = 290
        for label in labels:
            self.screen.blit(label, (x, y))
            y += 32

        self._draw_centered(self.font, "Q  -  QUIT", y + 20)

    def draw_game_over(self) -> None:
        self._draw_centered(self.big, "GAME OVER", 220)
        self._draw_centered(self.font, "Press any key", 300)

    def _draw_text(
        self,
        font: pg.font.Font,
        text: str,
        x: int,
        y: int,
    ) -> None:
        label = font.render(text, True, self.config.WHITE)
        self.screen.blit(label, (x, y))

    def _draw_centered(self, font: pg.font.Font, text: str, y: int) -> None:
        label = font.render(text, True, self.config.WHITE)
        x = (self.config.WINDOW_WIDTH - label.get_width()) // 2
        self.screen.blit(label, (x, y))

    def _draw_bullet(self, bullet: Bullet) -> None:
        """A bullet adopts its shooter's color via the same palette as
        the ship hull. UFO bullets carry the sentinel ``UFO_BULLET_OWNER``
        (negative); ``color_for_player`` returns WHITE for those, which
        keeps the original UFO-bullet appearance intact."""
        color = color_for_player(bullet.owner_id, self.config.PLAYER_COLORS)
        center = self.camera.world_to_screen(bullet.pos)
        r = max(1, int(bullet.r * self.camera.scale))
        pg.draw.circle(self.screen, color, center, r, width=1)

    def _draw_particle(self, particle: Particle) -> None:
        sx, sy = self.camera.world_to_screen(particle.pos)
        rect = pg.Rect(sx, sy, 2, 2)
        color = getattr(particle, "color", self.config.WHITE)
        self.screen.fill(color, rect)

    def _draw_shrapnel(self, frag: Shrapnel) -> None:
        """Draw a shrapnel fragment as a glowing orange line (streak effect)."""
        cx, cy = self.camera.world_to_screen(frag.pos)
        # Trail: draw a short line opposite to velocity direction
        speed = frag.vel.length()
        if speed > 0:
            streak_len = max(4, int(10 * self.camera.scale))
            nx = -frag.vel.x / speed
            ny = -frag.vel.y / speed
            ex, ey = int(cx + nx * streak_len), int(cy + ny * streak_len)
            # Outer glow (darker orange)
            pg.draw.line(self.screen, (180, 80, 0), (cx, cy), (ex, ey), 3)
            # Inner bright core
            pg.draw.line(self.screen, (255, 180, 40), (cx, cy), (ex, ey), 1)
        r = max(2, int(frag.r * self.camera.scale))
        pg.draw.circle(self.screen, (255, 120, 20), (cx, cy), r)

    def _draw_asteroid(self, asteroid: Asteroid) -> None:
        ox, oy = self.camera.world_to_screen(asteroid.pos)
        scale = self.camera.scale
        points = [
            (ox + int(p.x * scale), oy + int(p.y * scale))
            for p in asteroid.poly
        ]
        color = self.config.RED_ASTEROID_COLOR if asteroid.red else self.config.WHITE
        pg.draw.polygon(self.screen, color, points, width=1)

    def _draw_ship(self, ship: Ship) -> None:
        color = color_for_player(ship.player_id, self.config.PLAYER_COLORS)
        cx, cy = self.camera.world_to_screen(ship.pos)

        # Ship size on screen, with a floor for zoomed-out spectator
        # cameras (where ship.r * scale would otherwise round to a
        # handful of pixels). Player camera has scale=1.0 and never
        # hits the clamp.
        visual_r = max(
            ship.r * self.camera.scale, self.config.MIN_SHIP_VISUAL_R
        )

        dirv = angle_to_vec(ship.angle)
        left = angle_to_vec(ship.angle + self.config.SHIP_NOSE_ANGLE)
        right = angle_to_vec(ship.angle - self.config.SHIP_NOSE_ANGLE)
        nose_r = visual_r * self.config.SHIP_NOSE_SCALE
        points = [
            (cx + dirv.x * visual_r, cy + dirv.y * visual_r),
            (cx + left.x * nose_r, cy + left.y * nose_r),
            (cx + right.x * nose_r, cy + right.y * nose_r),
        ]
        pg.draw.polygon(self.screen, color, points, width=1)

        if ship.invuln.active and int(ship.invuln.remaining * 10) % 2 == 0:
            pg.draw.circle(
                self.screen, color, (cx, cy), int(visual_r + 6), width=1
            )
        if ship.shield.active:
            pg.draw.circle(
                self.screen, color, (cx, cy), int(visual_r + 12), width=2
            )
        if ship.laser.active:
            self._draw_laser_countdown(cx, cy, visual_r, ship.laser.remaining)

    def _draw_ship_name(self, ship: Ship, world: object) -> None:
        """Render the display name centered just below the ship.

        No-op when the world has no name for this player (single-player
        and pre-handshake frames). The name uses the same rainbow color
        as the ship itself so the badge and the body match.
        """
        name = getattr(world, "names", {}).get(ship.player_id)
        if not name:
            return
        color = color_for_player(ship.player_id, self.config.PLAYER_COLORS)
        label = self.font.render(name, True, color)
        anchor_world = Vec(ship.pos.x, ship.pos.y + ship.r + 4)
        sx, sy = self.camera.world_to_screen(anchor_world)
        sx -= label.get_width() // 2
        self.screen.blit(label, (sx, sy))

    def _draw_powerup(self, powerup: LaserPowerup) -> None:
        """Draw the laser powerup as a pulsing cyan circle with a cross."""
        CYAN = (0, 230, 230)
        cx, cy = self.camera.world_to_screen(powerup.pos)
        base_r = max(int(powerup.r * self.camera.scale), 5)
        pulse = math.sin(powerup.ttl * math.pi * 4) * 0.15 + 0.85
        r = max(4, int(base_r * pulse))
        pg.draw.circle(self.screen, CYAN, (cx, cy), r, width=1)
        half = r // 2
        pg.draw.line(self.screen, CYAN, (cx - half, cy), (cx + half, cy), 1)
        pg.draw.line(self.screen, CYAN, (cx, cy - half), (cx, cy + half), 1)

    def _draw_laser_beam(self, laser: LaserBeam) -> None:
        """Draw the laser beam, fading out as TTL expires."""
        color = color_for_player(laser.owner_id, self.config.PLAYER_COLORS)
        alpha = max(0.0, laser.ttl / self.config.LASER_BEAM_TTL)
        draw_color = tuple(int(c * alpha) for c in color)
        start = self.camera.world_to_screen(laser.pos)
        end = self.camera.world_to_screen(laser.end_pos)
        pg.draw.line(self.screen, draw_color, start, end, 2)

    def _draw_laser_countdown(
        self, cx: int, cy: int, visual_r: float, remaining: float
    ) -> None:
        """Draw an arc around the ship representing remaining laser duration."""
        CYAN = (0, 230, 230)
        radius = int(visual_r + 20)
        frac = min(1.0, remaining / self.config.LASER_DURATION)
        if frac <= 0.0:
            return
        stop_angle = math.pi / 2
        start_angle = stop_angle - math.tau * frac
        rect = pg.Rect(0, 0, radius * 2, radius * 2)
        rect.center = (cx, cy)
        pg.draw.arc(self.screen, CYAN, rect, start_angle, stop_angle, 2)

    def _draw_ufo(self, ufo: UFO) -> None:
        cx, cy = self.camera.world_to_screen(ufo.pos)
        scaled_r = max(int(ufo.r * self.camera.scale), 4)
        width = scaled_r * 2
        height = scaled_r

        body = pg.Rect(0, 0, width, height)
        body.center = (cx, cy)
        pg.draw.ellipse(self.screen, self.config.WHITE, body, width=1)

        cup = pg.Rect(0, 0, int(width * 0.5), int(height * 0.7))
        cup.center = (cx, cy - int(height * 0.3))
        pg.draw.ellipse(self.screen, self.config.WHITE, cup, width=1)