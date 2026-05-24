"""Player viewport camera.

Translates world coordinates to screen coordinates so the renderer can show
a WINDOW_WIDTH x WINDOW_HEIGHT slice of the (much larger) world centered on
the player's ship.

The world is toroidal — entities wrap at WORLD_WIDTH / WORLD_HEIGHT. The
camera does NOT wrap; it clamps to the world edges so the player sees the
border (and stays away from the visible discontinuity). This matches what
classic arcade games with scrolling cameras do.
"""

from __future__ import annotations

from core import config as C
from core.utils import Vec


class Camera:
    """Holds the screen-space origin in world coordinates."""

    __slots__ = ("origin",)

    def __init__(self) -> None:
        self.origin = Vec(0.0, 0.0)

    def update(self, target: Vec) -> None:
        """Re-center on target, clamped so the camera never sees outside the world."""
        ox = target.x - C.WINDOW_WIDTH / 2
        oy = target.y - C.WINDOW_HEIGHT / 2
        max_ox = C.WORLD_WIDTH - C.WINDOW_WIDTH
        max_oy = C.WORLD_HEIGHT - C.WINDOW_HEIGHT
        self.origin.x = max(0.0, min(ox, max_ox))
        self.origin.y = max(0.0, min(oy, max_oy))

    def world_to_screen(self, world_pos: Vec) -> tuple[int, int]:
        return (int(world_pos.x - self.origin.x), int(world_pos.y - self.origin.y))
