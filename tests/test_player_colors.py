"""Pure tests for `color_for_player` — the helper that maps a
``player_id`` to one of the eight rainbow slots from
``core.config.PLAYER_COLORS``."""

from __future__ import annotations

from client.renderer import color_for_player
from core import config as C


def test_pid_one_is_red():
    assert color_for_player(1) == C.PLAYER_COLORS[0]


def test_pid_two_is_orange():
    assert color_for_player(2) == C.PLAYER_COLORS[1]


def test_pid_eight_is_white():
    """Slot 8 holds the final color, which is WHITE by design."""
    assert color_for_player(8) == C.PLAYER_COLORS[7]
    assert color_for_player(8) == C.WHITE


def test_pid_nine_wraps_to_red():
    """Beyond the per-room cap, ids wrap modulo the palette length."""
    assert color_for_player(9) == color_for_player(1)


def test_pid_sixteen_wraps_to_white():
    assert color_for_player(16) == color_for_player(8)


def test_non_positive_pid_falls_back_to_white():
    """UFO bullets (pid = UFO_BULLET_OWNER = -10) and sentinels keep
    using WHITE — the rainbow set is for real players only."""
    assert color_for_player(0) == C.WHITE
    assert color_for_player(-1) == C.WHITE
    assert color_for_player(-10) == C.WHITE


def test_palette_has_eight_entries():
    """Sanity: 7 rainbow + 1 white = 8."""
    assert len(C.PLAYER_COLORS) == 8


def test_palette_uses_rgb_tuples_of_three_bytes():
    for color in C.PLAYER_COLORS:
        assert len(color) == 3
        assert all(0 <= channel <= 255 for channel in color)


def test_palette_eighth_slot_is_white():
    assert C.PLAYER_COLORS[-1] == C.WHITE


def test_custom_palette_argument_is_respected():
    """Tests can override the palette without monkey-patching the
    module global."""
    custom = ((1, 1, 1), (2, 2, 2), (3, 3, 3))
    assert color_for_player(1, palette=custom) == (1, 1, 1)
    assert color_for_player(2, palette=custom) == (2, 2, 2)
    assert color_for_player(3, palette=custom) == (3, 3, 3)
    assert color_for_player(4, palette=custom) == (1, 1, 1)  # wraps


def test_ufo_bullet_owner_falls_back_to_white():
    """Bullets fired by UFOs carry the sentinel UFO_BULLET_OWNER = -10.
    The renderer reuses `color_for_player` to look up the bullet's
    color; the non-positive id path must keep those bullets WHITE so
    the original UFO appearance is preserved."""
    from core.entities import UFO_BULLET_OWNER

    assert color_for_player(UFO_BULLET_OWNER) == C.WHITE


def test_player_bullet_color_matches_player_ship_color():
    """Slot N for a ship matches slot N for that player's bullets —
    the same helper drives both, so the visual identity holds."""
    for pid in range(1, 9):
        assert color_for_player(pid) == C.PLAYER_COLORS[pid - 1]
