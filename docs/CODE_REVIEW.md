# Code Review — pre-F5 pause

Audit performed on 2026-05-24 against the post-F4 state of `main`
(commit `4083388`, 21 PRs merged, 143 tests green, CI clean).

Goal: catalogue findings before Phase 5 (multi-room) multiplies the
shape of the simulation. Each finding has a unique id (`F-<n>`) so
follow-up PRs can reference it directly.

## 1. Executive summary

| Category            | Count |
|---------------------|------:|
| Confirmed bugs      |     0 |
| Code smells         |     4 |
| Perf candidates     |     5 |
| Style violations    |    85 |
| TODO/FIXME/XXX      |     0 |
| Swallowed errors    |     0 |

Overall: the codebase is healthy. The 85 line-length violations are
mechanical and resolved in PR 2 (`style/pep8-line-length-79`). No
finding warrants a hotfix; all action items are scheduled into the
pause-review plan with explicit thresholds.

## 2. Methodology

- Manual read of every `*.py` file under `core/`, `client/`, `server/`,
  `multiplayer/`, `tests/`.
- `grep` for usual suspects: `TODO|FIXME|XXX`, `except:` (bare),
  mutable defaults in function signatures, `len(x) > 0`,
  identity-vs-equality (`is None`, `== None`).
- `awk 'length>79'` per file for style violations.
- Cross-checked F1-F4 PR descriptions for design intent on grey areas.
- No profiling here; perf candidates are flagged for measurement in
  PR 3 (`chore/perf-instrumentation`).

## 3. Findings — High priority (confirmed bugs)

**None.** The audit passes started from suspicions and ruled each one
out:

- `_get_nearest_ship_pos` not filtering on a `ship.alive` flag — in
  deathmatch the ship is popped out of `world.ships` before any
  consumer can see it, so iterating `world.ships.values()` returns
  live entries only. Not a bug.
- `_pick_winner` over a dict of all-zero frags — `max(... key=...)`
  on a non-empty dict always returns a winner; the `(frags, -pid)`
  tiebreak is total and deterministic. Documented behaviour.
- UFO `try_fire` against a `None` target — guarded explicitly at the
  top of `try_fire`. Not a bug.

If a future PR uncovers a real bug, append it here as `F-1`, `F-2`,
etc. with the schema below.

Schema for future entries:

> **`F-<n>` — Title**
> - File: `path/to/file.py:line`
> - Evidence: snippet or repro
> - Recommendation: what fixes it
> - Effort: trivial / small / medium

## 4. Findings — Medium (code smells, no fix required)

### S-1 — `World.reset()` re-invokes `__init__`

- File: `core/world.py:81-86`
- Evidence: `self.__init__(spawn_default_player=not deathmatch, deathmatch=deathmatch)` —
  every attribute introduced in `__init__` is implicitly part of the
  reset contract. Adding a new attribute and forgetting to initialize
  it in `__init__` would silently break `reset()`.
- Recommendation: acceptable for now (tests cover the contract via
  `test_restart_via_world_reset_returns_to_lobby` and the F4 lifecycle
  suite). Watch for new attributes in F5+ that need explicit handling.
- Effort: none. Documentation item only.

### S-2 — `server/main.py` cleanup repeats `pop` eight times

- File: `server/main.py:117-127`
- Evidence: the `finally` block of `_handle_connection` performs eight
  `pop(player_id, None)` calls across `connections`, `_seq_by_player_id`,
  `_inputs_by_player_id`, `_names_by_player_id`, `world.ships`,
  `world.scores`, `world.lives`, `world.deaths`, `world.frags`,
  `world.respawning`, `world.extra_lives_awarded`. Each F1-F4 phase
  added one. F5 will add at least `room_id` membership.
- Recommendation: candidate for PR 5 (`refactor/<specific>`) — extract
  `World.despawn_player(pid)` so each dict is owned by one method.
  The pop count crossed the 3rd-occurrence threshold of R2.
- Effort: small.

### S-3 — `_bullets_vs_ships` returns on first hit

- File: `core/collisions.py:184-214`
- Evidence: the inner loop `break`s after one hit, but the outer
  iteration over `ships.values()` continues. Reading the code, the
  intent is "one bullet kills one ship; bullets after the killing
  shot keep travelling toward other ships in this tick". This matches
  the behaviour the F3 tests exercise.
- Recommendation: add a one-line comment above the `break` clarifying
  intent. Not a refactor.
- Effort: trivial (rolls into PR 2 if a manual reformat touches the
  block, otherwise skip).

### S-4 — `multiplayer/player.py:_draw` branch by `match_state` grows

- File: `multiplayer/player.py:170-194`
- Evidence: 3-arm `if/elif/else` over `match_state`. F5 introduces at
  least one more arm (spectator from a different client, possibly
  per-room snapshot routing). The block already approaches 25 lines.
- Recommendation: don't refactor yet (R2 — second occurrence, third
  would be the F5 spectator path). If F5 adds the spectator arm,
  extract a `dispatch_draw(state) -> Callable` table at that point.
- Effort: none now. Tracked for F5 audit.

## 5. Findings — Perf candidates (require measurement before action)

Each item carries a working hypothesis. The decision to optimize or
skip belongs to PR 3 (`chore/perf-instrumentation`), which records the
threshold-vs-measurement outcome in `docs/PERF_BASELINE.md`.

Activation thresholds (set in the pause-review plan):

- Cumulative cost ≥ 10% of one `World.update` tick **OR**
- Cumulative cost ≥ 30% of one `world_to_snapshot` call.

### P-1 — `world_to_snapshot` rebuilds ten list/dict comprehensions

- Site: `server/protocol.py:75-156`
- Hypothesis: 30 Hz broadcast × ten comprehensions × N entities is the
  largest single call in the server hot path.
- Measurement plan: `cProfile` over 600 ticks at 8 ships / 30
  asteroids / 2 UFOs; record cumulative time of `world_to_snapshot`
  and absolute bytes after `json.dumps`.
- Threshold: ≥ 30% of serialization time → optimize candidate;
  options include precomputed templates, `__slots__` access via
  attrgetter, or batching the dict assembly.

### P-2 — `_find_safe_hyperspace_pos` iterates up to 20× N asteroids

- Site: `core/world.py:255-271`
- Hypothesis: hyperspace (rare) and respawn (3 s cooldown) both call
  it. With 30 asteroids the worst case is 600 distance comparisons.
- Measurement plan: time the call site within a synthetic respawn
  storm (force 8 ships to die simultaneously).
- Threshold: ≥ 10% of a tick that performs a respawn.

### P-3 — `.length()` vs `.length_squared()` across CollisionManager

- Site: `core/collisions.py` — eight occurrences in
  `_bullets_vs_asteroids`, `_ufo_vs_player_bullets`,
  `_ufo_vs_asteroids`, `_ship_vs_asteroids`, `_ship_vs_ufos`,
  `_ship_vs_ufo_bullets`, `_bullets_vs_ships`.
- Hypothesis: each call computes `sqrt`. Comparing squared distances
  against squared sums is algebraically equivalent and avoids the
  square root.
- Measurement plan: `cProfile` finds `length` in the top-N callers.
- Threshold: ≥ 10% of `_handle_collisions` time.

### P-4 — `_get_nearest_ship_pos` recomputed per UFO per tick

- Site: `core/world.py:199-208`, called from `_update_ufos`.
- Hypothesis: with K UFOs and N ships the loop is O(K·N) per tick.
  Probably trivial at K ≤ 2, N ≤ 8; worth confirming.
- Measurement plan: profile against a worst-case scenario (4 UFOs, 8
  ships) to check the call cost.
- Threshold: ≥ 10% of one tick.

### P-5 — `snapshot_to_world` reallocates lists each frame on the client

- Site: `multiplayer/snapshot.py:25-55`
- Hypothesis: 30 Hz × full reallocation of bullets/asteroids/ufos is
  cheap for typical match sizes but might dominate the client tick if
  bullets get dense.
- Measurement plan: client-side timer around `snapshot_to_world`
  during a saturated match (8 players firing).
- Threshold: ≥ 10% of one client frame.

## 6. Findings — Style violations (PEP 8 line length)

Configured limit today: 100 (`pyproject.toml:28`). Target: 79 (PEP 8
§3.4 strict; project standard per memory feedback `line-length-79`).

| File | > 79 | > 88 |
|------|----:|----:|
| `multiplayer/player.py`         | 14 |  6 |
| `tests/test_collisions.py`      | 11 |  3 |
| `core/collisions.py`            |  9 |  3 |
| `server/main.py`                |  7 |  2 |
| `tests/test_protocol.py`        |  5 |  2 |
| `core/world.py`                 |  5 |  1 |
| `client/renderer.py`            |  5 |  2 |
| `server/protocol.py`            |  4 |  2 |
| `core/entities.py`              |  4 |  1 |
| `tests/test_world_respawn.py`   |  3 |  0 |
| `tests/test_snapshot_roundtrip.py` |  3 |  0 |
| `multiplayer/snapshot.py`       |  3 |  1 |
| `multiplayer/hud.py`            |  3 |  1 |
| `tests/test_match_lifecycle.py` |  2 |  0 |
| `core/utils.py`                 |  2 |  1 |
| `client/camera.py`              |  2 |  0 |
| `core/config.py`                |  1 |  1 |
| `client/game.py`                |  1 |  0 |
| `client/audio_manager.py`       |  1 |  0 |
| **Total**                       | **85** | **26** |

Resolution: PR 2 (`style/pep8-line-length-79`) updates
`pyproject.toml` and runs `ruff format`. Manual fixes expected for
3-5 lines where the automated wrap is ugly (f-strings with multiple
fields).

## 7. Recommendations ordered

| Step | PR branch                       | Acceptance criterion |
|----:|----------------------------------|---|
| 1 | `docs/code-review-audit` (this) | this document merged |
| 2 | `style/pep8-line-length-79`     | `ruff format --check` clean at 79; 143 tests green |
| 3 | `chore/perf-instrumentation`    | `docs/PERF_BASELINE.md` filled with measurements; PR 4 activation declared |
| 4 | `perf/<specific>` (conditional) | only if P-1..P-5 cross threshold; ≥ 5% gain in the hotspot |
| 5 | `refactor/<specific>` (conditional) | S-2 (despawn_player) most likely; only one finding per PR |

PR 6 (`docs/teaching-code-review`) is intentionally skipped this
session; rescheduled for between F5 and F6 once multi-room
measurements add richer didactic content.

## 8. Followup log

Append resolution notes here as PRs land:

- _(empty — first entry will be PR 2)_
