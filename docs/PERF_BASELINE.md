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
| 2026-05-24 | post-F5 (`6322f5a`) | 0.81 ms (1 room) → 0.30 ms (8 rooms) | unchanged | F5 multi-room **reduces** tick cost when load is split; no optimization activated |
| 2026-05-29 | post-F6 netcode (`dd680e1`) | 0.81 ms (unchanged) | 4 288 → 3 298 (−23 %, #50) | no optimization activated; latency hidden by prediction; INTERP_DELAY 50→35 ms (#49) |

## 7. F5 multi-room measurement

Re-run after F5 closes the roadmap, against the same synthetic
load (`600 ticks`, `8 ships` and `30 asteroids` **total**, split
evenly across `--rooms` so the room composition shrinks as the
count grows).

### Method

```
python scripts/profile_tick.py --ticks 600 --ships 8 --asteroids 30 --rooms 1
python scripts/profile_tick.py --ticks 600 --ships 8 --asteroids 30 --rooms 2
python scripts/profile_tick.py --ticks 600 --ships 8 --asteroids 30 --rooms 4
python scripts/profile_tick.py --ticks 600 --ships 8 --asteroids 30 --rooms 8
```

The script mirrors `Server._tick_loop`: each iteration loops over
the `rooms` worlds and calls `world.update(dt, inputs_for_room)`
once per room. The total wall time is the cost of advancing **all
rooms** by one tick.

### Numbers (MacBook Air M2, Python 3.13, single thread)

| Rooms | Ships / room | Asteroids / room | Total `run` time | Mean tick total |
|------:|-------------:|-----------------:|-----------------:|----------------:|
|     1 |            8 |               30 |          0.484 s |         0.807 ms |
|     2 |            4 |               15 |          0.290 s |         0.483 ms |
|     4 |            2 |                7 |          0.235 s |         0.392 ms |
|     8 |            1 |                3 |          0.179 s |         0.298 ms |

Top hotspot in every run: `_bullets_vs_asteroids` inside
`CollisionManager.resolve`. The cumulative time of that call drops
linearly with the per-room ship count because the inner loop is
O(ships × asteroids); splitting the same load across more rooms
shrinks the dominant `O(N²)` term inside each room without
introducing meaningful overhead between rooms.

### Hotspot analysis vs. threshold

Threshold from §5 unchanged: optimize when one hotspot consumes
≥ 10 % of one tick **and** the total tick exceeds 50 % of the
60 Hz frame budget (16.67 ms).

| Configuration                | Tick mean | % of 60 Hz budget | Decision |
|------------------------------|----------:|------------------:|----------|
| 1 room × 8 ships             | 0.81 ms   |             4.8 % | **skip** — well below threshold; equivalent to F4 baseline |
| 2 rooms × 4 ships            | 0.48 ms   |             2.9 % | **skip** |
| 4 rooms × 2 ships            | 0.39 ms   |             2.3 % | **skip** |
| 8 rooms × 1 ship             | 0.30 ms   |             1.8 % | **skip** |

**Decision**: F5 multi-room does not trigger any optimization. The
counter-intuitive result is the right outcome: splitting load
across rooms is cheaper than concentrating it because the dominant
cost in `_handle_collisions` scales super-linearly with the per-room
ship and asteroid counts.

### When would this revisit?

The number to watch is **ships per room**, not rooms total. If a
future build raises `MAX_PLAYERS` above 8 or if `WAVE_BASE_COUNT`
grows past ~30 asteroids per room, the per-room cost climbs as
`O(ships × asteroids)` and the threshold can flip. Re-run this
section before changing either constant.

## 8. F6 netcode review (prediction, reconciliation, interpolation)

Re-measured after F6 shipped client-side prediction, server
reconciliation (input ack), and remote-ship interpolation. F6 added a
new cost surface — per-frame work on the client — so this section
covers both the server tick and the client frame, plus the snapshot
size after the float-rounding change.

### Method

```
.venv/bin/python scripts/profile_tick.py --ticks 600 --ships 8 --asteroids 30 --rooms 1
```

Plus microbenchmarks of the client per-frame functions, and a
before/after byte count of `world_to_snapshot` on a representative
world (4 ships, a 20-asteroid wave, 8 bullets), with positions advanced
180 ticks so they carry realistic float representations.

### Numbers (MacBook Air M2, Python 3.13, single thread)

Server tick is unchanged from §7: F6's input-queue drain and per-player
ack injection are negligible.

| Path | Cost | % of 60 Hz budget (16.67 ms) | Decision |
|------|-----:|-----------------------------:|----------|
| Server tick (1 room × 8 ships) | 0.807 ms | 4.85 % | **skip** |
| Client `simulate_from_authority` (8-input replay, per frame) | 8.5 µs | 3.06 % | **skip** |
| Client `interpolate_ships` (8 snapshots, 4 ships, per frame) | 0.26 µs | 0.09 % | **skip** |
| Client `snapshot_to_world` rebuild (per 30 Hz snapshot) | 227 µs | < 0.05 % amortized | **skip** |

Total client per-frame cost stays under 5 % of the frame budget.

Snapshot size, before and after rounding wire floats to 1 decimal (#50):

| Snapshot | Bytes | At 30 Hz × 8 players |
|----------|------:|---------------------:|
| Full precision | 4 288 | 1.03 Mbit/s |
| Rounded (1 dp)  | 3 298 | 0.79 Mbit/s |

About 23 % smaller. Asteroids dominate the payload and their positions
carry the longest float representations, so they account for most of
the saving.

### Hotspot analysis vs. threshold

Threshold from §5 unchanged. No path, server or client, reaches it: the
server tick is 4.85 % of budget and the hottest client function is 3 %
of one frame. **No CPU optimization is activated**, the same outcome as
the pre-F5 review.

### What F6 changed instead

The felt problem on the public VPS (~140-180 ms RTT) was latency, not
CPU. F6 hides it with prediction rather than optimizing code. Two small
follow-ups cut the remaining latency and bandwidth without touching any
hot path:

- **#49** — `INTERP_DELAY` 50 ms → 35 ms: removes ~15 ms from the
  perceived latency of remote ships, safe because measured jitter is
  well under 1 ms.
- **#50** — round snapshot floats: ~23 % smaller snapshots, less queuing
  delay and jitter for players on congested connections.

### When would this revisit?

Same trigger as §7 for the server (ships per room). On the client,
`simulate_from_authority` scales with the unconfirmed-input count, which
is bounded by RTT × send rate; even at a ~16-input worst case it stays
under 6 % of one frame. Revisit only if latency compensation ever has
to replay a much longer history.
