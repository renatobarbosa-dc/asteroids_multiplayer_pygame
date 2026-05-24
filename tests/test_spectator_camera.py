"""Pure-function tests for the spectator camera scaling helpers."""

from __future__ import annotations

import pytest

from client.camera import Camera
from client.spectator_camera import (
    SpectatorCamera,
    compute_offsets,
    compute_scale,
)
from core import config as C
from core.utils import Vec


def test_compute_scale_uses_smaller_axis_ratio():
    """Wider-than-tall window: vertical fit is the bottleneck."""
    assert compute_scale(3840, 1080, 3840, 2160) == pytest.approx(0.5)
    """Taller-than-wide window: horizontal fit is the bottleneck."""
    assert compute_scale(1920, 2160, 3840, 2160) == pytest.approx(0.5)


def test_compute_scale_at_world_aspect_ratio_fills_window():
    """A window matching the world aspect ratio has zero letterbox."""
    scale = compute_scale(1920, 1080, 3840, 2160)
    assert scale == pytest.approx(0.5)
    assert compute_offsets(1920, 1080, 3840, 2160, scale=scale) == (0, 0)


def test_compute_offsets_letterbox_horizontal():
    """Wider-than-world window: horizontal bars left and right."""
    scale = compute_scale(2000, 1080, 3840, 2160)
    off_x, off_y = compute_offsets(2000, 1080, 3840, 2160, scale=scale)
    assert off_x > 0
    assert off_y == 0


def test_compute_offsets_letterbox_vertical():
    """Taller-than-world window: horizontal bars top and bottom."""
    scale = compute_scale(1920, 1200, 3840, 2160)
    off_x, off_y = compute_offsets(1920, 1200, 3840, 2160, scale=scale)
    assert off_x == 0
    assert off_y > 0


def test_compute_offsets_recomputes_scale_when_omitted():
    """Calling without `scale` produces the same result as computing
    the scale first and passing it in."""
    auto = compute_offsets(2000, 1080, 3840, 2160)
    manual_scale = compute_scale(2000, 1080, 3840, 2160)
    manual = compute_offsets(2000, 1080, 3840, 2160, scale=manual_scale)
    assert auto == manual


def test_spectator_camera_inherits_from_camera():
    cam = SpectatorCamera(1920, 1080)
    assert isinstance(cam, Camera)


def test_spectator_camera_uses_default_world_dimensions():
    cam = SpectatorCamera(1920, 1080)
    expected = compute_scale(1920, 1080, C.WORLD_WIDTH, C.WORLD_HEIGHT)
    assert cam.scale == pytest.approx(expected)


def test_world_to_screen_origin_maps_to_offset():
    cam = SpectatorCamera(2000, 1080)  # letterbox horizontal
    sx, sy = cam.world_to_screen(Vec(0, 0))
    assert (sx, sy) == (cam.offset_x, cam.offset_y)


def test_world_to_screen_far_corner_within_window():
    """The bottom-right corner of the world must land near the
    bottom-right of the window (within int truncation)."""
    cam = SpectatorCamera(1920, 1080)
    sx, sy = cam.world_to_screen(Vec(C.WORLD_WIDTH, C.WORLD_HEIGHT))
    assert 0 <= sx <= 1920
    assert 0 <= sy <= 1080
    assert sx >= 1920 - 2  # int truncation allows ±1px
    assert sy >= 1080 - 2


def test_update_is_noop():
    """`update` exists for Renderer compatibility but does not move
    the camera. World→screen output stays identical across calls."""
    cam = SpectatorCamera(1280, 720)
    before = cam.world_to_screen(Vec(1000, 800))
    cam.update(Vec(1, 2))
    cam.update(Vec(C.WORLD_WIDTH, C.WORLD_HEIGHT))
    after = cam.world_to_screen(Vec(1000, 800))
    assert before == after


def test_world_to_screen_scales_linearly():
    """Doubling the world coordinate doubles the offset from
    the camera origin in screen space (post-letterbox)."""
    cam = SpectatorCamera(1920, 1080)
    one = cam.world_to_screen(Vec(100, 200))
    two = cam.world_to_screen(Vec(200, 400))
    # Each axis must grow by 100 * scale = 50 (since scale=0.5).
    dx = two[0] - one[0]
    dy = two[1] - one[1]
    assert dx == pytest.approx(int(100 * cam.scale))
    assert dy == pytest.approx(int(200 * cam.scale))
