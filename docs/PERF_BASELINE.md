# Performance baseline — pre-F5 measurement

First systematic measurement of the server hot path, taken on
2026-05-24 against the post-F4 state of `main` (commit `33de4dc`,
the PEP 8 79-char normalization).

This is a baseline, not a benchmark suite. The intent is to record
real numbers so future phases — F5 (multi-room) in particular — can
compare against a known starting point.

## 1. Setup

- Hardware: MacBook Air M2, 8 GB RAM.
- Software: Python 3.13, single thread, no display, no network. Tests
  and profiling run against the in-process `World`.
- Workload: synthetic deathmatch with 8 ships, 30 asteroids, 0 UFOs
  initially. All ships issue `thrust=True, shoot=True` every frame.
- Deterministic: `random.seed(42)` for asteroid placement.

## 2. Method

- `World.update` profiled via stdlib `cProfile` over 600 ticks from
  [`scripts/profile_tick.py`](../scripts/profile_tick.py).
- `world_to_snapshot` and `envelope(SNAPSHOT, ..., snap)` measured
  via `timeit.repeat(number=1000, repeat=5)` after warming the world
  for 30 ticks. The reported number is `min()` to filter scheduler
  noise.
- Per-broadcast cost in the live server may also be observed by
  running with `--profile-broadcast`, which prints
  `broadcast tick=N ms=X.XX bytes=Y conns=Z` to stderr at 30 Hz.

## 3. Numbers

### World tick (cProfile over 600 ticks)

| Frame budget at 60 Hz | 16.67 ms |
|-----------------------|---------:|
| Mean tick time        |  0.85 ms |
| Share of budget       |    5.1 % |

Top of cumulative time:

| Site                                       | Cumulative ms | % of tick |
|--------------------------------------------|------:|------:|
| `World.update`                             | 507.7 | 100.0 |
| `_handle_collisions`                       | 429.6 |  84.6 |
| `CollisionManager.resolve`                 | 428.3 |  84.4 |
| `_bullets_vs_asteroids`                    | 310.7 |  61.2 |
| `Vec.__sub__`                              | 246.4 |  48.5 |
| `Vec.__init__`                             | 181.0 |  35.7 |
| `Vec.length()`                             |  73.0 |  14.4 |
| `_ship_vs_asteroids`                       |  59.4 |  11.7 |
| `_bullets_vs_ships`                        |  52.4 |  10.3 |
| `math.sqrt` (inside `Vec.length`)          |  21.8 |   4.3 |

(Numbers are cumulative — `Vec.__sub__` time includes the
`Vec.__init__` it triggers internally, etc.)

### Snapshot serialization

State after 30 warm-up ticks: 8 ships, 24 bullets, 30 asteroids,
0 UFOs, 0 particles.

| Call                                          |   μs/call |
|-----------------------------------------------|----------:|
| `world_to_snapshot(world, names=...)`         |     9.85  |
| `envelope(SNAPSHOT, tick, seq, snap)` (full)  |    87.99  |
| `world_to_snapshot` share of envelope         |    11.2 % |

Envelope payload size: **8 359 bytes**.

### Implied server cost at 30 Hz × 8 clients

- Per broadcast: 8 × 88 μs = 0.70 ms.
- Per second: 30 × 0.70 = 21 ms — about 2.1 % of one second.
- Bandwidth out: 30 × 8 × 8 359 ≈ 2.0 MB/s aggregate (~2 Mbit/client).

For comparison, LAN 100 Mbit/s leaves 95+ % headroom.

## 4. Hotspot analysis vs. activation threshold

Threshold set in the pause-review plan: optimize if a single hotspot
crosses **≥ 10 % of one tick** OR **≥ 30 % of one serialization**.

| Id  | Site                                      | Measured share | Decision  |
|-----|-------------------------------------------|---------------:|-----------|
| P-1 | `world_to_snapshot` of envelope cost      |         11.2 % | **skip** — below 30 % threshold; `json.dumps` dominates and replacing it would require an extra dependency (violates R8/R9) |
| P-2 | `_find_safe_hyperspace_pos`               | not exercised  | **skip** — does not appear in profile because no hyperspace nor PvP death fired in the synthetic run; revisit if a future profile under respawn storms shows it |
| P-3 | `.length()` (sqrt) across collisions      |         14.4 % | **technical match**, behavioural **skip** — total tick is 0.85 ms vs. 16.67 ms budget (5 % usage). R11: optimizing now would shave ~0.1 ms with no observable effect. Revisit when F5 multiplies entity count by N rooms |
| P-4 | `_get_nearest_ship_pos`                   | not in top 25  | **skip** — at 8 ships × 0 UFOs in this scenario the call is invisible. Recheck under UFO-heavy load |
| P-5 | `snapshot_to_world` realloc (client-side) | not measured here | **skip** — server-side baseline first; client-side belongs to a future profile if the networked client lags |

**Conclusion: PR 4 (`perf/<specific>`) is not activated this session.**

The server hot path is at 5 % of the frame budget. Even the suspect
that technically crossed the 10 % share is so cheap in absolute terms
that optimizing it would be premature under R11. The realistic
trigger for revisiting is the F5 multi-room work: a single process
hosting N rooms multiplies tick cost by N. When the baseline column
below shows ≥ 50 % of budget under realistic load, optimization
becomes a legitimate request rather than a guess.

## 5. Threshold rule (verbatim, for future runs)

> Optimize a hotspot only if **one** of the following holds in a
> realistic synthetic load:
>
> 1. The hotspot consumes ≥ 10 % of one `World.update` tick **and**
>    the total tick exceeds 50 % of the frame budget.
> 2. The hotspot consumes ≥ 30 % of one `world_to_snapshot` call
>    **and** broadcasting saturates the host's outbound bandwidth.
>
> Acceptable gain when an optimization runs: ≥ 5 % in the hotspot's
> own time. Sub-5 % rolls back as noise.

The compound condition (1) prevents the trap of "this is 60 % of a
tick that runs in 0.5 ms — let me shave it". The behavioural part of
the threshold matters as much as the share.

## 6. Followup log

Append rows here as future phases re-measure:

| Date | Branch / phase | Tick mean | Snapshot bytes | Decision |
|------|----------------|----------:|---------------:|----------|
| 2026-05-24 | post-F4, post-PEP-8 (`33de4dc`) | 0.85 ms | 8 359 | baseline; no optimization activated |
