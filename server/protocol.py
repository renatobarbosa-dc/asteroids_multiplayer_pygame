"""Wire protocol for the WebSocket connection between server and clients.

Every message is a JSON object with the same envelope shape:

    {"type": str, "tick": int, "seq": int, "data": dict}

- ``type``  identifies the message kind (see constants below).
- ``tick``  is the server-global simulation tick when the message was emitted.
- ``seq``   is a per-connection counter, useful for ordering and gap detection.
- ``data``  holds the message payload.

The format is JSON because the project values legibility over wire size at
this stage; a binary or delta-encoded variant can replace this once we have
real bandwidth measurements.
"""

from __future__ import annotations

import json
from typing import Any

# Client -> Server
HELLO = "hello"
INPUT = "input"
BYE = "bye"

# Server -> Client
WELCOME = "welcome"
REJECT = "reject"
SNAPSHOT = "snapshot"
EVENT = "event"


def envelope(msg_type: str, tick: int, seq: int, data: dict[str, Any]) -> str:
    """Serialize a message envelope to a JSON string."""
    return json.dumps({"type": msg_type, "tick": tick, "seq": seq, "data": data})


def parse(raw: str | bytes) -> dict[str, Any] | None:
    """Parse a JSON envelope. Returns None for any malformed input.

    Defensive on purpose: the server should drop bad frames instead of
    crashing the connection handler.
    """
    try:
        msg = json.loads(raw)
    except (TypeError, ValueError):
        return None

    if not isinstance(msg, dict):
        return None
    if not isinstance(msg.get("type"), str):
        return None
    if not isinstance(msg.get("tick"), int) or isinstance(msg.get("tick"), bool):
        return None
    if not isinstance(msg.get("seq"), int) or isinstance(msg.get("seq"), bool):
        return None
    if not isinstance(msg.get("data"), dict):
        return None
    return msg
