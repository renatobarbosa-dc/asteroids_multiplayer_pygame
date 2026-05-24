# Asteroids

Single-player Asteroids in Python with pygame. Vector polygons, two UFO behaviors, wave-based progression, and a `core/` layer that holds game state and rules with no rendering code.

## Quick start

Requires Python 3.10 or newer.

```
pip install -r requirements.txt
python main.py
```

## Controls

| Key      | Action |
| -------- | ------ |
| `←` `→`  | Rotate |
| `↑`      | Thrust |
| `Space`  | Shoot  |
| `H`      | Hyperspace (costs 250 points, may drop you on top of an asteroid) |
| `Esc`    | Quit |

## How it works

The repository keeps the simulation away from pygame:

- [`core/`](core/) holds game state, entities, collisions, and the per-frame update. It emits string events (`"player_shoot"`, `"asteroid_explosion"`) that the client reacts to.
- [`client/`](client/) wires pygame to the simulation. It maps input, runs the 60 FPS loop, renders polygons, and plays audio from `world.events`.

`World.update` accepts a `dict[player_id, PlayerCommand]`, so the simulation is already shaped for multiple players. The pygame client only ever sends one entry.

Key files:

- [`core/world.py`](core/world.py): simulation tick, wave spawning, score and lives.
- [`core/entities.py`](core/entities.py): `Ship`, `Asteroid`, `Bullet`, `UFO`.
- [`core/collisions.py`](core/collisions.py): `CollisionManager` resolves every collision in a single pass and returns a `CollisionResult`.
- [`client/game.py`](client/game.py): game loop and scene transitions (menu, play, game over).

A known bug: hyperspace can teleport the ship inside an asteroid.

## Project layout

```
asteroids_single-player/
├── main.py
├── pyproject.toml
├── core/        # game state, rules, entities, collisions
├── client/      # pygame loop, renderer, input, audio
├── assets/      # WAV sound effects
└── docs/        # ARCHITECTURE.md, DEVELOPMENT_WORKFLOW.md
```

## Contributing

Read [`docs/DEVELOPMENT_WORKFLOW.md`](docs/DEVELOPMENT_WORKFLOW.md) before opening a PR. It defines branch prefixes, commit conventions in en-US, and the review checklist. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) walks through module dependencies and the multiplayer roadmap.
