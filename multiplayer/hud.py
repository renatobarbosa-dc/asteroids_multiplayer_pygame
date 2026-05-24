"""Networked-client HUD: local stats on the top-left, scoreboard on
the top-right.

Lives in `multiplayer/` so the single-player UI in `client/` stays
unaffected. The `*_lines` helpers are pure functions that can be tested
without pygame; the `draw_*` wrappers are thin renderers built on top.
"""

from __future__ import annotations

import pygame as pg

from core import config as C
from core.world import World

_PADDING = 10
_LINE_GAP = 2
_NAME_WIDTH = 10


def local_hud_lines(world: World, player_id: int | None) -> list[str]:
    """Three-line summary for the local player: score, deaths, wave.

    Falls back to zeros when the player has no state yet — keeps the HUD
    width stable during the handshake handful of frames.
    """
    if player_id is None or player_id not in world.scores:
        return ["SCORE 000000", "DEATHS 00", "WAVE 00"]
    score = world.scores[player_id]
    deaths = world.deaths.get(player_id, 0)
    return [
        f"SCORE {score:06d}",
        f"DEATHS {deaths:02d}",
        f"WAVE {world.wave:02d}",
    ]


def scoreboard_lines(world: World, local_player_id: int | None) -> list[str]:
    """One line per connected player, sorted by score desc then pid asc.

    The local player is marked with a leading ``> ``. Players currently
    waiting to respawn show ``RESPAWN X.Xs``.
    """
    sorted_pids = sorted(world.scores.items(), key=lambda kv: (-kv[1], kv[0]))
    lines: list[str] = []
    for pid, score in sorted_pids:
        marker = "> " if pid == local_player_id else "  "
        name = world.names.get(pid, f"P{pid}")[:_NAME_WIDTH]
        deaths = world.deaths.get(pid, 0)
        timer = world.respawning.get(pid)
        status = f"RESPAWN {timer.remaining:.1f}s" if timer is not None else ""
        lines.append(f"{marker}{name:<{_NAME_WIDTH}} {score:>6} D{deaths:02d} {status}".rstrip())
    return lines


def draw_local_hud(
    screen: pg.Surface,
    font: pg.font.Font,
    world: World,
    player_id: int | None,
    color: tuple[int, int, int],
) -> None:
    x, y = _PADDING, _PADDING
    for line in local_hud_lines(world, player_id):
        label = font.render(line, True, color)
        screen.blit(label, (x, y))
        y += font.get_height() + _LINE_GAP


def draw_scoreboard(
    screen: pg.Surface,
    font: pg.font.Font,
    world: World,
    local_player_id: int | None,
    color: tuple[int, int, int],
) -> None:
    lines = scoreboard_lines(world, local_player_id)
    if not lines:
        return
    max_w = max(font.size(line)[0] for line in lines)
    x = screen.get_width() - max_w - _PADDING
    y = _PADDING
    for line in lines:
        label = font.render(line, True, color)
        screen.blit(label, (x, y))
        y += font.get_height() + _LINE_GAP


def waiting_lines(world: World) -> list[str]:
    """Lobby screen text: a header plus a ``N / MIN`` progress line."""
    return [
        "WAITING FOR PLAYERS",
        f"{len(world.ships)} / {C.MIN_PLAYERS_TO_START}",
    ]


def match_overlay_lines(world: World, local_pid: int | None) -> list[str]:
    """One-line overlay showing the time left and the current leader."""
    seconds = max(0, int(world.match_timer.remaining))
    mm, ss = divmod(seconds, 60)
    leader = _current_leader(world)
    if leader is None:
        return [f"TIME {mm}:{ss:02d}"]
    name = world.names.get(leader, f"P{leader}")[:_NAME_WIDTH]
    frags = world.frags.get(leader, 0)
    return [f"TIME {mm}:{ss:02d}   FRAGS {name} {frags}"]


def match_end_lines(world: World) -> list[str]:
    """End-of-match screen: title, winner row, restart hint."""
    if world.winner_id is None:
        winner_line = "NO WINNER"
    else:
        name = world.names.get(world.winner_id, f"P{world.winner_id}")
        winner_line = f"WINNER: {name}"
    return ["MATCH OVER", winner_line, "Press ENTER to restart"]


def _current_leader(world: World) -> int | None:
    """Player with the most frags right now; ties broken by smaller pid.

    Mirrors `World._pick_winner` but is kept local so the HUD does not
    reach into a private helper. The duplication is four lines.
    """
    if not world.frags:
        return None
    return max(world.frags.keys(), key=lambda pid: (world.frags[pid], -pid))


def _draw_centered_block(
    screen: pg.Surface,
    fonts: list[pg.font.Font],
    lines: list[str],
    color: tuple[int, int, int],
) -> None:
    labels = [f.render(line, True, color) for f, line in zip(fonts, lines, strict=True)]
    block_h = sum(label.get_height() + _LINE_GAP for label in labels) - _LINE_GAP
    y = (screen.get_height() - block_h) // 2
    for label in labels:
        x = (screen.get_width() - label.get_width()) // 2
        screen.blit(label, (x, y))
        y += label.get_height() + _LINE_GAP


def draw_waiting_screen(
    screen: pg.Surface,
    font: pg.font.Font,
    big: pg.font.Font,
    world: World,
    color: tuple[int, int, int],
) -> None:
    lines = waiting_lines(world)
    fonts = [big] + [font] * (len(lines) - 1)
    _draw_centered_block(screen, fonts, lines, color)


def draw_match_overlay(
    screen: pg.Surface,
    font: pg.font.Font,
    world: World,
    local_pid: int | None,
    color: tuple[int, int, int],
) -> None:
    lines = match_overlay_lines(world, local_pid)
    for i, line in enumerate(lines):
        label = font.render(line, True, color)
        x = (screen.get_width() - label.get_width()) // 2
        y = _PADDING + i * (font.get_height() + _LINE_GAP)
        screen.blit(label, (x, y))


def draw_match_end_screen(
    screen: pg.Surface,
    font: pg.font.Font,
    big: pg.font.Font,
    world: World,
    color: tuple[int, int, int],
) -> None:
    lines = match_end_lines(world)
    fonts = [big] + [font] * (len(lines) - 1)
    _draw_centered_block(screen, fonts, lines, color)
