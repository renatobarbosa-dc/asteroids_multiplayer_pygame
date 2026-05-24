"""Client-side rendering (pygame)."""

import pygame as pg

from core import config as C
from core.entities import UFO, Asteroid, Bullet, Particle, Ship
from core.scene import SceneState


class Renderer:
    """Draws scenes and entities without coupling game rules to Game."""

    def __init__(
        self,
        screen: pg.Surface,
        config: object = C,
        fonts: dict[str, pg.font.Font] | None = None,
    ) -> None:
        self.screen = screen
        self.config = config
        safe_fonts = fonts or {}
        self.font = safe_fonts["font"]
        self.big = safe_fonts["big"]

        self._draw_dispatch: dict[type, callable] = {
            Bullet: self._draw_bullet,
            Asteroid: self._draw_asteroid,
            Ship: self._draw_ship,
            UFO: self._draw_ufo,
            Particle: self._draw_particle,
        }

    def clear(self) -> None:
        self.screen.fill(self.config.BLACK)

    def draw_world(self, world: object) -> None:
        for sprite in world.all_sprites:
            drawer = self._draw_dispatch.get(type(sprite))
            if drawer is not None:
                drawer(sprite)

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

        if extra_life_remaining > 0.0 and int(extra_life_remaining * 6) % 2 == 0:
            notice = self.big.render("EXTRA LIFE", True, self.config.WHITE)
            x = (self.config.WIDTH - notice.get_width()) // 2
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
        labels = [self.font.render(line, True, self.config.WHITE) for line in lines]
        widest = max(label.get_width() for label in labels)
        x = (self.config.WIDTH - widest) // 2

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
        x = (self.config.WIDTH - label.get_width()) // 2
        self.screen.blit(label, (x, y))

    def _draw_bullet(self, bullet: Bullet) -> None:
        center = (int(bullet.pos.x), int(bullet.pos.y))
        pg.draw.circle(
            self.screen,
            self.config.WHITE,
            center,
            bullet.r,
            width=1,
        )

    def _draw_particle(self, particle: Particle) -> None:
        rect = pg.Rect(int(particle.pos.x), int(particle.pos.y), 2, 2)
        self.screen.fill(self.config.WHITE, rect)

    def _draw_asteroid(self, asteroid: Asteroid) -> None:
        points = []
        for point in asteroid.poly:
            px = int(asteroid.pos.x + point.x)
            py = int(asteroid.pos.y + point.y)
            points.append((px, py))
        pg.draw.polygon(self.screen, self.config.WHITE, points, width=1)

    def _draw_ship(self, ship: Ship) -> None:
        p1, p2, p3 = ship.ship_points()
        points = [
            (int(p1.x), int(p1.y)),
            (int(p2.x), int(p2.y)),
            (int(p3.x), int(p3.y)),
        ]
        pg.draw.polygon(self.screen, self.config.WHITE, points, width=1)

        if ship.invuln.active and int(ship.invuln.remaining * 10) % 2 == 0:
            center = (int(ship.pos.x), int(ship.pos.y))
            pg.draw.circle(
                self.screen,
                self.config.WHITE,
                center,
                ship.r + 6,
                width=1,
            )

        if ship.shield.active:
            center = (int(ship.pos.x), int(ship.pos.y))
            pg.draw.circle(
                self.screen,
                self.config.WHITE,
                center,
                ship.r + 12,
                width=2,
            )

    def _draw_ufo(self, ufo: UFO) -> None:
        width = ufo.r * 2
        height = ufo.r

        body = pg.Rect(0, 0, width, height)
        body.center = (int(ufo.pos.x), int(ufo.pos.y))
        pg.draw.ellipse(self.screen, self.config.WHITE, body, width=1)

        cup = pg.Rect(0, 0, int(width * 0.5), int(height * 0.7))
        cup.center = (int(ufo.pos.x), int(ufo.pos.y - height * 0.3))
        pg.draw.ellipse(self.screen, self.config.WHITE, cup, width=1)
