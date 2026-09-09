"""
session.py — SessionInfo: immutable record of one authenticated relay session.

Distinction between identity, session, and connection
------------------------------------------------------
client_id   Persistent logical identity chosen by the operator (e.g. "router-01").
            Stable across reconnects.

session_id  UUID assigned by the relay for one connection.  Changes on every
            reconnect (relay V1 does not support session resumption).

connection  The underlying WebSocket.  May be replaced on reconnect.

SessionInfo is created when AUTH_OK is received and discarded when the
connection closes.  A fresh SessionInfo is created on every successful
reconnect.
"""
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionInfo:
    """
    Immutable snapshot of a successfully established relay session.

    Never contains secrets or mutable objects.
    """

    session_id: str
    """UUID assigned by the relay for this specific connection."""

    client_id: str
    """The client's persistent logical identity."""

    relay_name: str
    """Human-readable name of the relay (from the HELLO payload)."""

    connected_at: float
    """Monotonic timestamp of the moment AUTH_OK was received."""

    def uptime(self) -> float:
        """Seconds since this session was established."""
        return time.monotonic() - self.connected_at
