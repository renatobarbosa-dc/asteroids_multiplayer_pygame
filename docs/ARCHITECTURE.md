# ARCHITECTURE

Project: `asteroids_multiplayer`

## 1. Purpose

This document describes the current architecture of the project: a
client-server multiplayer Asteroids deathmatch for up to 8 players,
written in Python with `asyncio` and WebSockets. It is a didactic fork
of [`asteroids_single-player`](https://github.com/jucimarjr/asteroids_single-player)
(frozen at `v0.1.0`) and still ships a working single-player mode.

Scope:
- Python code in `core/`, `client/`, `server/`, `multiplayer/`, and
  `main.py`
- Helper scripts in `scripts/`
- Tests in `tests/`
- Documentation in `docs/`
- Assets in `assets/`

The defining property of the architecture is a clean split between a
**headless simulation** (`core/`, no pygame, no networking) and the
**two front-ends** that drive it: the local pygame client and the
networked client-server pair. Everything below follows from that split.

## 2. Repository Structure

```text
asteroids_multiplayer/
├── main.py                  # single-player entry point
├── pyproject.toml
├── requirements.txt
├── core/                    # headless simulation (pure Python, no pygame)
│   ├── collisions.py
│   ├── commands.py
│   ├── config.py
│   ├── entities.py
│   ├── scene.py
│   ├── utils.py
│   └── world.py
├── client/                  # pygame front-end (rendering, input, audio)
│   ├── audio.py
│   ├── audio_manager.py
│   ├── camera.py
│   ├── controls.py
│   ├── game.py
│   ├── renderer.py
│   └── spectator_camera.py
├── server/                  # authoritative server (headless, no pygame)
│   ├── __main__.py
│   ├── auth.py
│   ├── main.py
│   └── protocol.py
├── multiplayer/             # networked clients + netcode
│   ├── command_codec.py
│   ├── hud.py
│   ├── player.py
│   ├── prediction.py
│   ├── snapshot.py
│   └── spectator.py
├── scripts/
│   ├── profile_tick.py      # cProfile harness for World.update
│   └── server_health.py     # liveness probe for a running server
├── tests/                   # pytest suite (17 modules, 256 tests)
├── assets/
│   └── sounds/              # WAV effects used by the pygame clients
└── docs/
    ├── ARCHITECTURE.md
    ├── CODE_REVIEW.md
    ├── COMO_JOGAR.md        # player guide (PT-BR)
    ├── DEPLOY.md            # VPS / systemd deployment guide
    ├── DEVELOPMENT_WORKFLOW.md
    └── PERF_BASELINE.md
```

Audio files in `assets/sounds/`: `player_shoot.wav`,
`asteroid_explosion.wav`, `ship_explosion.wav`, `thrust_loop.wav`,
`ufo_shoot.wav`, `ufo_siren_big.wav`, `ufo_siren_small.wav`.

## 3. The Two Runtime Paths

The same `core/` simulation runs in two configurations.

**Single-player** (`python main.py`):

```
main.py → client.game.Game → core.world.World
                            → client.{renderer, controls, audio, camera}
```

`Game` owns the pygame loop, reads input into a `PlayerCommand`, calls
`World.update`, and renders the result. No network involved.

**Multiplayer** (`python -m server` + `python -m multiplayer.player`):

```
server.main.Server ── owns one core.world.World per room, steps it at 60 Hz
        │  (authoritative; headless; no pygame)
        │  broadcasts a full-state snapshot at 30 Hz, acks last input
        ▼
   WebSocket (JSON envelopes, server.protocol)
        ▼
multiplayer.player ── applies snapshots to a local read-only World,
        │  predicts the local ship, interpolates remote ships,
        │  renders through client.{renderer, camera}
        ▼
   pygame window
```

The server is authoritative: it owns the only `World` that actually
simulates. The networked client never calls `world.update`; it rebuilds
a local `World` from each snapshot purely for rendering (see
`multiplayer/snapshot.py`). The single-player path and the multiplayer
path share `core/` and the rendering half of `client/`, but neither
front-end touches the other.

## 4. Responsibilities by Module

### `core/` — headless simulation (no pygame)

- **`world.py`** — `World`: holds all game state (ships, bullets,
  asteroids, UFOs, particles, scores, frags, deaths) and advances it one
  tick at a time (`update`). Wave spawning, `spawn_player` /
  `despawn_player`, the respawn loop, and the lobby → running → ended
  match lifecycle. Emits string events in `world.events`. Pure Python,
  so it runs identically in the client and the server.
- **`entities.py`** — `Ship`, `Asteroid`, `Bullet`, `UFO`, `Particle`.
  Each owns its state and physics, exposes `update(dt)` and an `alive`
  flag; dead entities are purged at the end of the tick (no
  `pygame.sprite`).
- **`collisions.py`** — `CollisionManager` runs every collision check in
  a single pass and returns a `CollisionResult` (kills, frags, score
  deltas, events). Bullet-vs-ship filters on `owner_id` so a player
  never frags themselves.
- **`commands.py`** — `PlayerCommand`, a frozen dataclass of input flags
  (rotate, thrust, shoot, hyperspace, shield). No behavior, so it
  serializes cleanly over the wire.
- **`scene.py`** — `SceneState`, the enum for the single-player scene
  machine (`MENU`, `PLAY`, `GAME_OVER`).
- **`utils.py`** — `Vec`, the project's own 2D vector (replacing
  `pygame.math.Vector2`), `Countdown`, and geometry helpers like
  `wrap_pos` for the toroidal world. Importing it never pulls in pygame.
- **`config.py`** — every tunable constant: world/viewport size, frame
  and snapshot rates, match rules, entity parameters, player colors,
  asset paths. Imported as `C` across the codebase.

### `client/` — pygame front-end

- **`game.py`** — `Game`: owns the pygame window, clock, and fonts, runs
  the 60 FPS single-player loop, switches scenes via `SceneState`, and
  feeds input to `World.update`. Entry point of `python main.py`.
- **`renderer.py`** — `Renderer`: draws the world, HUD, and scenes
  through a `Camera`. Per-player ship/bullet colors come from
  `color_for_player`. The only module that issues pygame draw calls.
- **`controls.py`** — `InputMapper`: reads pygame key state each frame
  and builds the immutable `PlayerCommand` (continuous keys for
  rotate/thrust/shield, edge-triggered for shoot/hyperspace).
- **`audio.py`** — `SoundPack` (a dataclass of loaded sounds) and
  `load_sounds(base_path)`. No playback policy, just loading.
- **`audio_manager.py`** — `AudioManager`: maps `world.events` to
  playback over pygame mixer channels (one-shots plus thrust / UFO
  loops) and handles mute. Used by both clients.
- **`camera.py`** — `Camera`: translates world coordinates to screen
  coordinates and clamps to the world edges, so the 1280×720 viewport is
  a window onto the full 3840×2160 world.
- **`spectator_camera.py`** — `SpectatorCamera` extends `Camera` to
  scale the whole 3840×2160 world into an arbitrary window with
  letterbox padding instead of following one ship. Used by the spectator
  client.

### `server/` — authoritative server (headless, no pygame)

- **`main.py`** — `Server`: hosts one `World` per room, steps every
  room at 60 Hz, and broadcasts a full-state snapshot to that room's
  clients at 30 Hz (`SNAPSHOT_HZ`). Token handshake, per-room input
  queues, and an `ack` of the last input processed for client-side
  reconciliation. Single asyncio event loop, no threads: one task per
  room plus one connection handler per client. Any exception in a tick
  brings the process down, so it is meant to run under a supervisor (see
  `docs/DEPLOY.md`).
- **`protocol.py`** — the wire format. Every message is a JSON envelope
  `{"type", "tick", "seq", "data"}`; provides `envelope()`, a defensive
  `parse()`, the message-type constants, and `world_to_snapshot()`.
- **`auth.py`** — `load_tokens(path)`: reads a newline-separated token
  allowlist (blank lines and `#` comments skipped). The server rejects
  any HELLO whose token is not in the set.
- **`__main__.py`** — makes `python -m server --host --port --rooms
  --tokens-file` work by calling `server.main.main()`.

### `multiplayer/` — networked clients + netcode

Pure-logic modules (no pygame import, unit-tested without a display):

- **`snapshot.py`** — `snapshot_to_world`: rebuilds a local `World` from
  a decoded snapshot each frame. Ships are reused by `player_id` (so the
  camera reference survives); everything else is rebuilt.
- **`command_codec.py`** — `command_to_dict` / `dict_to_command`:
  convert the `PlayerCommand` carried by the `input` message. Tiny and
  dependency-free, so both client and server use it.
- **`prediction.py`** — the netcode math, all pygame-free. Client-side
  prediction for the local ship (`PredictedInput`, `ShipPredictor`,
  `simulate_from_authority`, `ease_toward`, `toroidal_delta/distance`)
  **and** remote-ship interpolation (`interpolate_ships`). Reuses
  `Ship.apply_command` + `Ship.update` as the single source of truth for
  physics; it never reimplements movement.

Pygame modules:

- **`hud.py`** — the networked-client HUD. Pure `*_lines` builders
  (`local_hud_lines`, `scoreboard_lines`, `waiting_lines`,
  `match_overlay_lines`, `match_end_lines`) are testable without a
  display; thin `draw_*` wrappers render them with pygame.
- **`player.py`** — the networked player. Single asyncio loop shared by
  pygame and the websocket: sends input every frame, applies snapshots,
  predicts the local ship, interpolates remote ships, renders through
  `client/`. Launched with `python -m multiplayer.player`.
- **`spectator.py`** — read-only spectator: never spawns a ship, never
  sends input, fits the whole world into its window via
  `client.spectator_camera`. Launched with `python -m
  multiplayer.spectator`.

## 5. Module Dependencies

Allowed import directions (higher layers depend on lower, never the
reverse):

```
core/         →  (stdlib only — no pygame, no project deps)
client/       →  core/                          + pygame
server/       →  core/, multiplayer.command_codec, server.protocol  + websockets
multiplayer/  →  core/, client/, server.protocol  + pygame, websockets
```

Invariants worth protecting:

- **`core/` is headless.** It imports no pygame and no networking, so
  the same simulation runs in the single-player client and the server.
  `grep -rn "import pygame" core/` must stay empty.
- **`server/` is headless.** It imports `core/`, `websockets`, and the
  pure `multiplayer.command_codec` decoder — never pygame, never the
  pygame parts of `client/` — so it runs on a VPS with no display.
- **`client/` never imports `server/` or `multiplayer/`.** Rendering and
  input know nothing about the network.
- **No circular imports.** `multiplayer/` is the only package that
  depends on three others, and it sits at the top.

## 6. Wire Protocol

One WebSocket per client. Every message is a JSON envelope:

```json
{"type": "snapshot", "tick": 1234, "seq": 56, "data": {}}
```

- Client → server: `hello` (token + room + name), `input` (a
  `PlayerCommand` plus its seq), `restart_request`, `bye`.
- Server → client: `welcome` (assigns `player_id`), `reject` (with a
  reason: `unauthorized`, `invalid_room`, `room_full`), `snapshot`
  (full room state, plus the per-client `ack`).

The snapshot is **full state**, not a delta — chosen for legibility over
wire size at this stage. Coordinates are rounded to one decimal to cut
bytes. See `server/protocol.py` and `docs/PERF_BASELINE.md`.

## 7. Netcode Model

The networked client hides latency with three textbook techniques, all
in `multiplayer/prediction.py` and layered on top of the authoritative
snapshots without changing the server's role as source of truth:

1. **Client-side prediction** — the local ship reacts to input
   immediately, simulated with the same `Ship` physics the server uses.
2. **Reconciliation** — each snapshot carries an `ack` of the last input
   the server processed; the client replays its unacknowledged inputs on
   top of the authoritative state and eases out any residual error.
3. **Remote interpolation** (`interpolate_ships`) — other players' ships
   are rendered a fixed delay in the past, interpolated between
   snapshots, so 30 Hz updates look smooth at 60 FPS. Ships only —
   asteroids/bullets/UFOs have no stable id and fall back to
   extrapolation.

Honest limits (kept deliberately, as teaching material): correction is
near-exact but not bit-exact under packet loss, and interpolation adds a
fixed delay to remote ships.

## 8. Testing & Tooling

- `tests/` holds 17 pytest modules (256 tests). The headless design pays
  off here: `core/` and the pure `multiplayer/` modules (snapshot,
  command_codec, prediction) are tested without a display or a network,
  and the `*_lines` HUD builders are tested without rendering. CI runs
  `ruff check`, `ruff format --check`, and `pytest` on every push and PR.
- `scripts/profile_tick.py` profiles `World.update` under cProfile;
  `scripts/server_health.py` probes a running server (sends a HELLO,
  expects a reply) and exits 0/1.
- `docs/PERF_BASELINE.md` records the measured tick budget and the
  rationale (per the project's "optimize only with measurement" rule)
  for why no CPU hotspot has justified optimization.

## 9. Lineage

This project began as a single-player codebase whose `core/` was coupled
to pygame (`pygame.sprite.Sprite`, `pygame.math.Vector2`). The
multiplayer conversion (phases F1–F6) decoupled `core/` from pygame,
extracted the `CollisionManager`, made score/lives/frags per-player,
added the authoritative server and networked clients, the match
lifecycle, multi-room support with a token allowlist, and finally the
prediction/reconciliation/interpolation netcode. The single-player mode
(`python main.py`) is preserved across all of it.
