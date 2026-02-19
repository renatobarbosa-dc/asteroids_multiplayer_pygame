"""Áudio do jogo (cliente).

Didático:
- World não toca som (baixo acoplamento).
- World gera eventos (strings) e Game decide tocar.
"""

from dataclasses import dataclass

import pygame as pg
from core import config as C


@dataclass(slots=True)
class SoundPack:
    player_shoot: pg.mixer.Sound
    ufo_shoot: pg.mixer.Sound
    asteroid_explosion: pg.mixer.Sound
    ship_explosion: pg.mixer.Sound
    thrust_loop: pg.mixer.Sound
    ufo_siren_big: pg.mixer.Sound
    ufo_siren_small: pg.mixer.Sound


def load_sounds(base_path: str) -> SoundPack:
    def s(name: str) -> pg.mixer.Sound:
        return pg.mixer.Sound(f"{base_path}/{name}")

    return SoundPack(
        player_shoot=s(C.PLAYER_SHOOT),
        ufo_shoot=s(C.UFO_SHOOT),
        asteroid_explosion=s(C.ASTEROID_EXPLOSION),
        ship_explosion=s(C.SHIP_EXPLOSION),
        thrust_loop=s(C.THRUST_LOOP),
        ufo_siren_big=s(C.UFO_SIREN_BIG),
        ufo_siren_small=s(C.UFO_SIREN_SMALL),
    )
