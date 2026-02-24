"""Sistemas do jogo (World, colisões, waves, score)."""

import math
from random import uniform
from typing import Dict

import pygame as pg

from core import config as C
from core.commands import PlayerCommand
from core.entities import Asteroid, Ship, UFO, UFO_BULLET_OWNER
from core.utils import Vec, rand_edge_pos, rand_unit_vec

PlayerId = int


class World:
    """Estado do mundo + regras do jogo.

    Multiplayer-ready:
    - World recebe comandos por player_id.
    - World gera eventos (strings) para o cliente (sons/efeitos).
    """

    def __init__(self) -> None:
        self.ships: Dict[PlayerId, Ship] = {}
        self.bullets = pg.sprite.Group()
        self.asteroids = pg.sprite.Group()
        self.ufos = pg.sprite.Group()
        self.all_sprites = pg.sprite.Group()

        self.score = 0
        self.lives = C.START_LIVES
        self.wave = 0
        self.wave_cool = float(C.WAVE_DELAY)
        self.ufo_timer = float(C.UFO_SPAWN_EVERY)

        self.events: list[str] = []

        self.game_over = False

        self.spawn_player(C.LOCAL_PLAYER_ID)

    def begin_frame(self) -> None:
        self.events.clear()

    def reset(self) -> None:
        """Reinicia o mundo (usado pelo Game Over)."""
        self.__init__()

    def spawn_player(self, player_id: PlayerId) -> None:
        pos = Vec(C.WIDTH / 2, C.HEIGHT / 2)
        ship = Ship(player_id, pos)
        ship.invuln = float(C.SAFE_SPAWN_TIME)

        self.ships[player_id] = ship
        self.all_sprites.add(ship)

    def get_ship(self, player_id: PlayerId) -> Ship | None:
        return self.ships.get(player_id)

    def start_wave(self) -> None:
        self.wave += 1
        count = 3 + self.wave

        ship = self.get_ship(C.LOCAL_PLAYER_ID)
        ship_pos = ship.pos if ship else Vec(C.WIDTH / 2, C.HEIGHT / 2)

        for _ in range(count):
            pos = rand_edge_pos()
            while (pos - ship_pos).length() < 150:
                pos = rand_edge_pos()

            ang = uniform(0, math.tau)
            speed = uniform(C.AST_VEL_MIN, C.AST_VEL_MAX)
            vel = Vec(math.cos(ang), math.sin(ang)) * speed
            self.spawn_asteroid(pos, vel, "L")

    def spawn_asteroid(self, pos: Vec, vel: Vec, size: str) -> None:
        ast = Asteroid(pos, vel, size)
        self.asteroids.add(ast)
        self.all_sprites.add(ast)

    def spawn_ufo(self) -> None:
        small = uniform(0, 1) < 0.5
        pos = rand_edge_pos()
        target = self._get_primary_target()
        ufo = UFO(pos, small, target_pos=target)
        self.ufos.add(ufo)

        self.all_sprites.add(ufo)

    def update(
        self,
        dt: float,
        commands_by_player_id: Dict[PlayerId, PlayerCommand],
    ) -> None:
        self.begin_frame()

        if self.game_over:
            return

        self._apply_commands(dt, commands_by_player_id)
        self.all_sprites.update(dt)

        self._update_ufos(dt)
        self._update_timers(dt)
        self._handle_collisions()
        self._maybe_start_next_wave(dt)

    def _apply_commands(
        self,
        dt: float,
        commands_by_player_id: Dict[PlayerId, PlayerCommand],
    ) -> None:
        for player_id, cmd in commands_by_player_id.items():
            ship = self.get_ship(player_id)
            if ship is None:
                continue

            if cmd.hyperspace:
                ship.hyperspace()
                self.score = max(0, self.score - C.HYPERSPACE_COST)

            bullet = ship.apply_command(cmd, dt, self.bullets)
            if bullet is not None:
                self.bullets.add(bullet)
                self.all_sprites.add(bullet)
                self.events.append("player_shoot")

    def _update_ufos(self, dt: float) -> None:
        target = self._get_primary_target()

        for ufo in list(self.ufos):
            ufo.target_pos = target
            ufo.update(dt)
            if not ufo.alive():
                continue

            ufo.target_pos = target
            bullet = ufo.try_fire()
            if bullet is not None:
                self.bullets.add(bullet)
                self.all_sprites.add(bullet)
                self.events.append("ufo_shoot")

            if not ufo.alive():
                self.ufos.remove(ufo)

    def _get_primary_target(self) -> Vec | None:
        ship = self.get_ship(C.LOCAL_PLAYER_ID)
        return ship.pos if ship is not None else None

    def _update_timers(self, dt: float) -> None:
        self.ufo_timer -= dt
        if self.ufo_timer <= 0.0:
            self.spawn_ufo()
            self.ufo_timer = float(C.UFO_SPAWN_EVERY)

    def _maybe_start_next_wave(self, dt: float) -> None:
        if self.asteroids:
            return

        self.wave_cool -= dt
        if self.wave_cool <= 0.0:
            self.start_wave()
            self.wave_cool = float(C.WAVE_DELAY)

    def _handle_collisions(self) -> None:
        self._bullets_vs_asteroids()
        self._ufo_vs_player_bullets()
        self._ufo_vs_asteroids()
        self._ship_vs_asteroids()
        self._ship_vs_ufo_bullets()

    def _bullets_vs_asteroids(self) -> None:
        hits = pg.sprite.groupcollide(
            self.asteroids,
            self.bullets,
            False,
            True,
            collided=lambda a, b: (a.pos - b.pos).length() < a.r,
        )

        for ast, bullets in hits.items():
            if any(b.owner_id == UFO_BULLET_OWNER for b in bullets):
                ast.kill()
                self.events.append("asteroid_explosion")
                continue

            self._split_asteroid(ast, add_score=True)

    def _ufo_vs_player_bullets(self) -> None:
        for ufo in list(self.ufos):
            for bullet in list(self.bullets):
                if bullet.owner_id <= 0:
                    continue
                if (ufo.pos - bullet.pos).length() < (ufo.r + bullet.r):
                    score = (
                        C.UFO_SMALL["score"]
                        if ufo.small
                        else C.UFO_BIG["score"]
                    )
                    self.score += score
                    ufo.kill()
                    bullet.kill()
                    self.events.append("ship_explosion")

    def _ufo_vs_asteroids(self) -> None:
        """UFO colidiu com asteroide.

        - UFO se destrói.
        - Asteroide se comporta como se tivesse tomado um tiro, mas
          sem pontuar.
        """
        for ufo in list(self.ufos):
            for ast in list(self.asteroids):
                if (ufo.pos - ast.pos).length() < (ufo.r + ast.r):
                    ufo.kill()
                    if ufo in self.ufos:
                        self.ufos.remove(ufo)

                    self.events.append("ship_explosion")
                    self._split_asteroid(ast, add_score=False)
                    break

    def _ship_vs_asteroids(self) -> None:
        for ship in self.ships.values():
            if ship.invuln > 0.0:
                continue
            for ast in self.asteroids:
                if (ast.pos - ship.pos).length() < (ast.r + ship.r):
                    self._ship_die(ship)
                    return

    def _ship_vs_ufo_bullets(self) -> None:
        for ship in self.ships.values():
            if ship.invuln > 0.0:
                continue
            for bullet in list(self.bullets):
                if bullet.owner_id != UFO_BULLET_OWNER:
                    continue
                if (bullet.pos - ship.pos).length() < (bullet.r + ship.r):
                    bullet.kill()
                    self._ship_die(ship)
                    return

    def _split_asteroid(
        self,
        ast: Asteroid,
        add_score: bool = True,
    ) -> None:
        """Divide ou destrói asteroide.

        add_score=False é usado quando a UFO colide com asteroide.
        """
        if add_score:
            self.score += C.AST_SIZES[ast.size]["score"]

        split = C.AST_SIZES[ast.size]["split"]
        pos = Vec(ast.pos)
        ast.kill()

        self.events.append("asteroid_explosion")

        for new_size in split:
            dirv = rand_unit_vec()
            speed = uniform(C.AST_VEL_MIN, C.AST_VEL_MAX) * 1.2
            self.spawn_asteroid(pos, dirv * speed, new_size)

    def _ship_die(self, ship: Ship) -> None:
        self.lives -= 1
        ship.pos.xy = (C.WIDTH / 2, C.HEIGHT / 2)
        ship.vel.xy = (0, 0)
        ship.angle = -90.0
        ship.invuln = float(C.SAFE_SPAWN_TIME)

        self.events.append("ship_explosion")
        if self.lives <= 0:
            self.game_over = True

    def draw(self, surf: pg.Surface, font: pg.font.Font) -> None:
        for spr in self.all_sprites:
            spr.draw(surf)
        txt = f"SCORE {self.score:06d}   LIVES {self.lives}   WAVE {self.wave}"
        label = font.render(txt, True, C.WHITE)
        surf.blit(label, (10, 10))
