"""Game loop e cenas (menu, jogo, game over).

Didático:
- InputMapper converte teclado -> PlayerCommand.
- World atualiza simulação e gera eventos (strings) para o Game.
- Game decide áudio e telas (baixo acoplamento).
"""

import sys

import pygame as pg

from core import config as C
from client.audio import load_sounds
from client.controls import InputMapper
from client.renderer import Renderer
from core.world import World


class Scene:
    """Representa uma tela do jogo."""

    def __init__(self, name: str) -> None:
        self.name = name


class Game:
    """Orquestra input -> update -> draw."""

    def __init__(self) -> None:
        pg.mixer.pre_init(44100, -16, 2, 512)
        pg.init()
        pg.mixer.init()

        self.screen = pg.display.set_mode((C.WIDTH, C.HEIGHT))
        pg.display.set_caption("Asteroids")

        self.clock = pg.time.Clock()
        self.running = True

        self.font = pg.font.SysFont("consolas", 22)
        self.big = pg.font.SysFont("consolas", 64)
        self.renderer = Renderer(
            self.screen,
            config=C,
            fonts={"font": self.font, "big": self.big},
        )

        self.scene = Scene("menu")
        self.world = World()
        self.input_mapper = InputMapper()

        self.sounds = load_sounds(C.SOUND_PATH)

        self._thrust_ch = pg.mixer.Channel(1)
        self._sfx_ch = pg.mixer.Channel(2)
        self._ufo_ch = pg.mixer.Channel(3)

        self._ufo_siren_kind: str | None = None

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(C.FPS) / 1000.0
            self._handle_events()
            self._update(dt)
            self._draw()

        pg.quit()

    def _handle_events(self) -> None:
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self._quit()

            if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                self._quit()

            if self.scene.name == "menu":
                if event.type == pg.KEYDOWN:
                    self.scene = Scene("play")
                continue

            if self.scene.name == "game_over":
                if event.type == pg.KEYDOWN:
                    self.world.reset()
                    self.scene = Scene("play")
                continue

            if self.scene.name == "play":
                self.input_mapper.handle_event(event)

    def _update(self, dt: float) -> None:
        if self.scene.name != "play":
            return

        keys = pg.key.get_pressed()
        cmd = self.input_mapper.build_command(keys)
        commands = {C.LOCAL_PLAYER_ID: cmd}

        self.world.update(dt, commands)

        if self.world.game_over:
            self._stop_loops()
            self.scene = Scene("game_over")
            return

        self._update_thrust(cmd.thrust)
        self._update_ufo_siren()
        self._play_events(self.world.events)

    def _draw(self) -> None:
        self.renderer.clear()

        if self.scene.name == "menu":
            self.renderer.draw_menu()
            pg.display.flip()
            return

        if self.scene.name == "game_over":
            self.renderer.draw_game_over()
            pg.display.flip()
            return

        self.renderer.draw_world(self.world)
        self.renderer.draw_hud(
            self.world.score,
            self.world.lives,
            self.world.wave,
            self.scene.name,
        )
        pg.display.flip()

    def _play_events(self, events: list[str]) -> None:
        for ev in events:
            if ev == "player_shoot":
                self._sfx_ch.play(self.sounds.player_shoot)
            elif ev == "ufo_shoot":
                self._sfx_ch.play(self.sounds.ufo_shoot)
            elif ev == "asteroid_explosion":
                self._sfx_ch.play(self.sounds.asteroid_explosion)
            elif ev == "ship_explosion":
                self._sfx_ch.play(self.sounds.ship_explosion)

    def _update_thrust(self, thrust: bool) -> None:
        if thrust:
            if not self._thrust_ch.get_busy():
                self._thrust_ch.play(self.sounds.thrust_loop, loops=-1)
        else:
            if self._thrust_ch.get_busy():
                self._thrust_ch.stop()

    def _update_ufo_siren(self) -> None:
        kind = self._choose_ufo_siren()
        if kind is None:
            if self._ufo_ch.get_busy():
                self._ufo_ch.stop()
            self._ufo_siren_kind = None
            return

        if self._ufo_siren_kind == kind:
            return

        self._ufo_ch.stop()
        if kind == "small":
            snd = self.sounds.ufo_siren_small
        else:
            snd = self.sounds.ufo_siren_big

        self._ufo_ch.play(snd, loops=-1)
        self._ufo_siren_kind = kind

    def _choose_ufo_siren(self) -> str | None:
        if not getattr(self.world, "ufos", None):
            return None

        ufos = list(self.world.ufos)
        if not ufos:
            return None

        has_small = any(getattr(u, "small", False) for u in ufos)
        return "small" if has_small else "big"

    def _stop_loops(self) -> None:
        if self._thrust_ch.get_busy():
            self._thrust_ch.stop()
        if self._ufo_ch.get_busy():
            self._ufo_ch.stop()
        self._ufo_siren_kind = None

    def _quit(self) -> None:
        self.running = False
        pg.quit()
        sys.exit(0)
