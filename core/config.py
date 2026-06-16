"""Game configuration constants."""

import os

# World is the simulation playfield (4K). Window is the slice the player sees.
WORLD_WIDTH = 3840
WORLD_HEIGHT = 2160
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
FPS = 60
SNAPSHOT_HZ = 30

# Client-side prediction (F6): the local ship is simulated ahead of the
# server so input feels instant, then eased back toward each snapshot.
PREDICTION_SNAP_DIST = 150.0  # px; above this error snap instead of ease
PREDICTION_SMOOTH = 15.0  # exponential correction rate (1/s)
# The server consumes one queued input per player per tick; the queue is
# a small jitter buffer. The cap bounds added input latency under bursts.
INPUT_QUEUE_CAP = 8
# Remote ships are rendered this many seconds in the past, interpolated
# between the two buffered snapshots that straddle that time — smoother
# than extrapolation, at the cost of a little latency on other players.
# 0.035 is about one 30 Hz snapshot interval (33 ms) plus a small margin;
# kept low because the measured network jitter is well under 1 ms.
INTERP_DELAY = 0.035

# Per-room cap from F5 onward; before F5 this was the global server
# cap. Single-room servers (default `--rooms 1`) keep the same effect.
MAX_PLAYERS = 8
LOCAL_PLAYER_ID = 1
DEFAULT_ROOMS = 1

START_LIVES = 3
SAFE_SPAWN_TIME = 2.0
WAVE_DELAY = 2.0
# Wave count tuned for the 4K world: 32x larger than the original
# 800x600, so roughly 4x the spawn rate (one asteroid per 1.3 Mpx).
WAVE_BASE_COUNT = 20
EXTRA_LIFE_EVERY = 5000
EXTRA_LIFE_NOTICE_TIME = 1.5
FRAG_SCORE = 100
RESPAWN_DELAY = 3.0
MIN_PLAYERS_TO_START = 2
MATCH_DURATION = 120.0
FRAG_LIMIT = 5

SHIP_RADIUS = 15
SHIP_TURN_SPEED = 220.0
SHIP_THRUST = 220.0
SHIP_FRICTION = 0.995
SHIP_FIRE_RATE = 0.2
SHIP_BULLET_SPEED = 420.0
SHIP_PUSH_STRENGTH = 150.0
HYPERSPACE_COST = 250
HYPERSPACE_ATTEMPTS = 20
HYPERSPACE_SAFE_MARGIN = 20
SHIELD_DURATION = 3.0
SHIELD_COOLDOWN = 10.0

# Explosion particles: (count, speed_min, speed_max, ttl)
PARTICLE_ASTEROID = (8, 60.0, 140.0, 0.6)
PARTICLE_UFO = (12, 100.0, 200.0, 0.8)
PARTICLE_SHIP = (16, 80.0, 220.0, 1.2)
SHIP_NOSE_ANGLE = 140.0
SHIP_NOSE_SCALE = 0.9
BULLET_SPAWN_OFFSET = 6

# Minimum on-screen radius for a ship triangle. The spectator camera
# zooms the world to 1/3 size; without this floor each ship would be
# a 5-pixel speck. Players use scale=1.0 and never hit the clamp.
MIN_SHIP_VISUAL_R = 12

AST_VEL_MIN = 30.0
AST_VEL_MAX = 90.0
AST_POLY_STEPS = {"L": 12, "M": 10, "S": 8}
AST_POLY_JITTER_MIN = 0.75
AST_POLY_JITTER_MAX = 1.2
AST_MIN_SPAWN_DIST = 300
AST_SPLIT_SPEED_MULT = 1.2
AST_SIZES = {
    "L": {"r": 46, "score": 20, "split": ["M", "M"]},
    "M": {"r": 24, "score": 50, "split": ["S", "S"]},
    "S": {"r": 12, "score": 100, "split": []},
}

BULLET_RADIUS = 2
BULLET_TTL = 1.0
MAX_BULLETS_PER_PLAYER = 4

UFO_SPAWN_EVERY = 8.0
UFO_SPEED_BIG = 95.0
UFO_SPEED_SMALL = 120.0
UFO_BIG = {"r": 18, "score": 200}
UFO_SMALL = {"r": 12, "score": 1000}

UFO_FIRE_RATE_BIG = 0.8
UFO_FIRE_RATE_SMALL = 0.55
UFO_BULLET_SPEED = 360.0
UFO_BULLET_TTL = 1.3

# Aim: small UFO is precise, big UFO is inaccurate.
UFO_AIM_JITTER_DEG_BIG = 28.0
UFO_AIM_JITTER_DEG_SMALL = 6.0
UFO_BIG_MISS_CHANCE = 0.35

WHITE = (240, 240, 240)
BLACK = (0, 0, 0)

# Per-player ship colors, indexed by `(player_id - 1) % len(PLAYER_COLORS)`.
# Seven rainbow hues for slots 1-7; slot 8 is white. Wraps for pid >= 9,
# which only happens across rooms in multi-room servers — within a room
# the per-room cap of MAX_PLAYERS=8 keeps colors unique.
PLAYER_COLORS: tuple[tuple[int, int, int], ...] = (
    (235, 64, 52),  # red
    (235, 134, 52),  # orange
    (235, 213, 52),  # yellow
    (76, 200, 76),  # green
    (80, 140, 235),  # blue
    (110, 80, 200),  # indigo
    (180, 90, 220),  # violet
    (240, 240, 240),  # white (slot 8)
)

# Audio mixer settings
AUDIO_FREQUENCY = 44100
AUDIO_SIZE = -16
AUDIO_CHANNELS = 2
AUDIO_BUFFER = 512

# UI layout
FONT_SIZE_SMALL = 22
FONT_SIZE_LARGE = 64
FONT_NAME = "consolas"

RANDOM_SEED = None

# Laser powerup
LASER_POWERUP_RADIUS = 14
LASER_POWERUP_TTL = 15.0
LASER_POWERUP_SPAWN_EVERY = 20.0
LASER_DURATION = 8.0
LASER_BEAM_TTL = 0.15
LASER_FIRE_RATE = 0.5

# Paths (work from any execution directory).
# config.py lives in core/, so we go one level up to the project root.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOUND_PATH = os.path.join(BASE_DIR, "assets", "sounds")

# Sounds
PLAYER_SHOOT = "player_shoot.wav"
UFO_SHOOT = "ufo_shoot.wav"
ASTEROID_EXPLOSION = "asteroid_explosion.wav"
SHIP_EXPLOSION = "ship_explosion.wav"
THRUST_LOOP = "thrust_loop.wav"
UFO_SIREN_BIG = "ufo_siren_big.wav"
UFO_SIREN_SMALL = "ufo_siren_small.wav"
LASER_PICKUP = "laser_pickup.wav"
LASER_SHOOT = "laser_shoot.wav"
