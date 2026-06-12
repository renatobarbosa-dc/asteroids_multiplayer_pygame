"""Audio playback manager for the game client."""

import pygame as pg

from client.audio import SoundPack


class AudioManager:
    """Manages audio channels and event-driven sound playback."""

    def __init__(self, sounds: SoundPack) -> None:
        self.sounds = sounds
        self._thrust_ch = pg.mixer.Channel(1)
        self._sfx_ch = pg.mixer.Channel(2)
        self._ufo_ch = pg.mixer.Channel(3)
        self._ufo_siren_kind: str | None = None
        self.muted = False

    def set_muted(self, muted: bool) -> None:
        """Toggle global mute. When muted, all playback methods are
        no-ops and any currently-playing channel is silenced immediately.
        """
        self.muted = muted
        if muted:
            self._sfx_ch.stop()
            self.stop_all()

    def play_events(self, events: list[str]) -> None:
        if self.muted:
            return
        for ev in events:
            if ev == "player_shoot":
                self._sfx_ch.play(self.sounds.player_shoot)
            elif ev == "ufo_shoot":
                self._sfx_ch.play(self.sounds.ufo_shoot)
            elif ev == "asteroid_explosion":
                self._sfx_ch.play(self.sounds.asteroid_explosion)
            elif ev == "ship_explosion":
                self._sfx_ch.play(self.sounds.ship_explosion)
            elif ev == "laser_pickup":
                self._sfx_ch.play(self.sounds.laser_pickup)
            elif ev == "laser_shoot":
                self._sfx_ch.play(self.sounds.laser_shoot)

    def update_thrust(self, active: bool) -> None:
        if self.muted or not active:
            if self._thrust_ch.get_busy():
                self._thrust_ch.stop()
            return
        if not self._thrust_ch.get_busy():
            self._thrust_ch.play(self.sounds.thrust_loop, loops=-1)

    def update_ufo_siren(self, ufos: list) -> None:
        if self.muted:
            if self._ufo_ch.get_busy():
                self._ufo_ch.stop()
            self._ufo_siren_kind = None
            return
        kind = self._choose_ufo_siren(ufos)
        if kind is None:
            if self._ufo_ch.get_busy():
                self._ufo_ch.stop()
            self._ufo_siren_kind = None
            return

        if self._ufo_siren_kind == kind:
            return

        self._ufo_ch.stop()
        snd = (
            self.sounds.ufo_siren_small
            if kind == "small"
            else self.sounds.ufo_siren_big
        )
        self._ufo_ch.play(snd, loops=-1)
        self._ufo_siren_kind = kind

    def stop_all(self) -> None:
        if self._thrust_ch.get_busy():
            self._thrust_ch.stop()
        if self._ufo_ch.get_busy():
            self._ufo_ch.stop()
        self._ufo_siren_kind = None

    def _choose_ufo_siren(self, ufos: list) -> str | None:
        if not ufos:
            return None
        has_small = any(u.small for u in ufos)
        return "small" if has_small else "big"
