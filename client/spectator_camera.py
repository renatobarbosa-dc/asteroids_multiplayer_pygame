"""Camera used by the spectator client: shows the entire world in
the window, with letterbox padding when the aspect ratios differ.

Inherits from `Camera` so the existing `Renderer` can use either
interchangeably. The difference is conceptual:

- `Camera` translates a world viewport onto the window, clamped to
  the world bounds (used by the playing client).
- `SpectatorCamera` fits the *entire* world into the window — same
  call signature, different math. `update(target)` is a no-op
  because the spectator does not follow a ship.

The two helpers `compute_scale` and `compute_offsets` are pure so
they can be unit-tested without pygame.
"""

from __future__ import annotations

from client.camera import Camera
from core import config as C
from core.utils import Vec


def compute_scale(
    window_w: int,
    window_h: int,
    world_w: int = C.WORLD_WIDTH,
    world_h: int = C.WORLD_HEIGHT,
) -> float:
    """Largest uniform scale that fits the world inside the window."""
    return min(window_w / world_w, window_h / world_h)


def compute_offsets(
    window_w: int,
    window_h: int,
    world_w: int = C.WORLD_WIDTH,
    world_h: int = C.WORLD_HEIGHT,
    scale: float | None = None,
) -> tuple[int, int]:
    """Pixels of letterbox padding so the scaled world sits centered.

    When ``scale`` is omitted, recomputes it from the window/world
    dimensions; passing it in lets callers avoid the duplicate
    computation in performance-sensitive code.
    """
    if scale is None:
        scale = compute_scale(window_w, window_h, world_w, world_h)
    used_w = world_w * scale
    used_h = world_h * scale
    return (
        int((window_w - used_w) / 2),
        int((window_h - used_h) / 2),
    )


class SpectatorCamera(Camera):
    """Static, scaled camera covering the entire world."""

    def __init__(self, window_width: int, window_height: int) -> None:
        super().__init__()
        self.window_width = int(window_width)
        self.window_height = int(window_height)
        self.scale = compute_scale(self.window_width, self.window_height)
        self.offset_x, self.offset_y = compute_offsets(
            self.window_width,
            self.window_height,
            scale=self.scale,
        )

    def update(self, target: Vec) -> None:
        """No-op — the spectator never follows a moving target."""
        return

    def world_to_screen(self, world_pos: Vec) -> tuple[int, int]:
        return (
            int(world_pos.x * self.scale + self.offset_x),
            int(world_pos.y * self.scale + self.offset_y),
        )
