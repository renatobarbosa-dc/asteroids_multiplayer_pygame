"""Tests for multiplayer.hud — local HUD and 1-room scoreboard.

These exercise the pure `*_lines` helpers so the drawing primitives can
be verified without touching pygame.
"""

from core.utils import Countdown
from core.world import World
from multiplayer.hud import (
    local_hud_lines,
    match_end_lines,
    match_overlay_lines,
    scoreboard_lines,
    waiting_lines,
)


def test_local_hud_lines_uses_world_state():
    w = World(spawn_default_player=False)
    w.scores[7] = 250
    w.deaths[7] = 1
    w.wave = 2
    assert local_hud_lines(w, 7) == ["SCORE 000250", "DEATHS 01", "WAVE 02"]


def test_local_hud_lines_falls_back_to_zeros_for_unknown_player():
    w = World(spawn_default_player=False)
    assert local_hud_lines(w, 99) == ["SCORE 000000", "DEATHS 00", "WAVE 00"]
    assert local_hud_lines(w, None) == ["SCORE 000000", "DEATHS 00", "WAVE 00"]


def test_scoreboard_sorts_by_score_desc_then_pid_asc():
    w = World(spawn_default_player=False)
    w.scores = {1: 200, 2: 500, 3: 200}
    lines = scoreboard_lines(w, local_player_id=None)
    assert "500" in lines[0]
    assert "P2" in lines[0]
    assert "P1" in lines[1]
    assert "P3" in lines[2]


def test_scoreboard_marks_local_player_with_leading_arrow():
    w = World(spawn_default_player=False)
    w.scores = {1: 100, 2: 100}
    lines = scoreboard_lines(w, local_player_id=2)
    pid2 = next(line for line in lines if "P2" in line)
    pid1 = next(line for line in lines if "P1" in line)
    assert pid2.startswith("> ")
    assert pid1.startswith("  ")


def test_scoreboard_uses_name_when_present():
    w = World(spawn_default_player=False)
    w.scores = {1: 100}
    w.names[1] = "Alice"
    assert "Alice" in scoreboard_lines(w, local_player_id=None)[0]


def test_scoreboard_falls_back_to_pid_when_name_missing():
    w = World(spawn_default_player=False)
    w.scores = {1: 100}
    assert "P1" in scoreboard_lines(w, local_player_id=None)[0]


def test_scoreboard_shows_respawn_status_when_player_in_respawning():
    w = World(spawn_default_player=False)
    w.scores = {1: 100}
    w.respawning[1] = Countdown(2.5)
    line = scoreboard_lines(w, local_player_id=None)[0]
    assert "RESPAWN" in line
    assert "2.5" in line


def test_scoreboard_displays_deaths_counter():
    w = World(spawn_default_player=False)
    w.scores = {1: 100}
    w.deaths[1] = 4
    assert "D04" in scoreboard_lines(w, local_player_id=None)[0]


def test_scoreboard_empty_world_returns_empty_list():
    assert scoreboard_lines(World(spawn_default_player=False), None) == []


def test_waiting_lines_shows_player_count():
    w = World(spawn_default_player=False, deathmatch=True)
    w.spawn_player(1)
    lines = waiting_lines(w)
    assert lines[0] == "WAITING FOR PLAYERS"
    assert "1 / 2" in lines[1]


def test_waiting_lines_progresses_with_each_join():
    w = World(spawn_default_player=False, deathmatch=True)
    assert "0 / 2" in waiting_lines(w)[1]
    w.spawn_player(1)
    assert "1 / 2" in waiting_lines(w)[1]
    w.spawn_player(2)
    assert "2 / 2" in waiting_lines(w)[1]


def test_match_overlay_formats_mm_ss():
    w = World(spawn_default_player=False, deathmatch=True)
    w.match_timer.reset(83.7)
    line = match_overlay_lines(w, local_pid=None)[0]
    assert "TIME 1:23" in line


def test_match_overlay_shows_leader_name_and_frags():
    w = World(spawn_default_player=False, deathmatch=True)
    w.match_timer.reset(60.0)
    w.frags = {1: 3, 2: 1}
    w.names = {1: "Alice", 2: "Bob"}
    line = match_overlay_lines(w, local_pid=None)[0]
    assert "Alice" in line
    assert "3" in line


def test_match_overlay_handles_zero_frags():
    """Tied at zero across two players: leader by pid asc, shown with 0."""
    w = World(spawn_default_player=False, deathmatch=True)
    w.match_timer.reset(120.0)
    w.frags = {1: 0, 2: 0}
    w.names = {1: "Alice", 2: "Bob"}
    line = match_overlay_lines(w, local_pid=None)[0]
    assert "Alice" in line
    assert " 0" in line


def test_match_overlay_handles_empty_frags():
    """No spawned players yet — overlay is just the timer."""
    w = World(spawn_default_player=False, deathmatch=True)
    w.match_timer.reset(60.0)
    line = match_overlay_lines(w, local_pid=None)[0]
    assert "FRAGS" not in line
    assert "TIME" in line


def test_match_end_shows_winner_name():
    w = World(spawn_default_player=False, deathmatch=True)
    w.spawn_player(2)
    w.names[2] = "Bob"
    w.winner_id = 2
    lines = match_end_lines(w)
    assert lines[0] == "MATCH OVER"
    assert "WINNER: Bob" in lines[1]
    assert "Press ENTER" in lines[2]


def test_match_end_falls_back_to_pid_when_name_missing():
    w = World(spawn_default_player=False, deathmatch=True)
    w.winner_id = 5
    assert "P5" in match_end_lines(w)[1]


def test_match_end_handles_no_winner():
    w = World(spawn_default_player=False, deathmatch=True)
    w.winner_id = None
    assert "NO WINNER" in match_end_lines(w)[1]
