"""Smoke tests for `scripts/profile_tick.py`.

The script is not a package member but lives next to the codebase
and is imported here via `importlib.util` so a syntax error or a
broken import chain is caught by CI without running cProfile (whose
output is non-deterministic and not worth asserting on).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_profile_tick():
    path = (
        Path(__file__).resolve().parent.parent / "scripts" / "profile_tick.py"
    )
    spec = importlib.util.spec_from_file_location("profile_tick", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_profile_tick_imports():
    """Module loads without raising — guards against import-chain
    breakage after a refactor."""
    module = _load_profile_tick()
    assert hasattr(module, "run")
    assert hasattr(module, "build_world")


def test_profile_tick_runs_smoke():
    """`run` survives a tiny synthetic load — no exception, no
    pygame, no network."""
    module = _load_profile_tick()
    module.run(ticks=2, ships=2, asteroids=3)


def test_build_world_returns_running_deathmatch():
    """`build_world` produces a deathmatch World already in running
    state with the requested number of ships and asteroids."""
    module = _load_profile_tick()
    world = module.build_world(ships=3, asteroids=5)
    assert world.deathmatch is True
    assert world.match_state == "running"
    assert len(world.ships) == 3
    assert len(world.asteroids) == 5
