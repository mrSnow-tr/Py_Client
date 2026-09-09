"""
heartbeat.py — HeartbeatMonitor for py_client.

Tracks the timestamp of the last message received from the relay.
Used to detect dead connections: if no message has arrived for
``heartbeat_timeout`` seconds the connection is considered dead
and the message loop should trigger a reconnect.

Note: py_relay sends HEARTBEAT every ``HEARTBEAT_INTERVAL`` seconds
(default 25 s).  The client's heartbeat_timeout (default 70 s) should
be comfortably longer than the relay's interval so normal latency spikes
do not cause false positives.
"""
import time


class HeartbeatMonitor:
    """
    Tracks server-side activity to detect connection failure.

    ``touch()`` is called by the message loop on every received message.
    ``reset()`` is called when a new connection is established.
    ``is_dead()`` returns True when the connection has been silent too long.
    """

    def __init__(self, timeout: float) -> None:
        """
        Parameters
        ----------
        timeout:
            Seconds of silence after which ``is_dead()`` returns True.
        """
        self._timeout = timeout
        self._last_activity: float = time.monotonic()

    def reset(self) -> None:
        """Mark activity at the current moment (call on new connection)."""
        self._last_activity = time.monotonic()

    def touch(self) -> None:
        """Update the last-seen timestamp (call on every received message)."""
        self._last_activity = time.monotonic()

    def idle_seconds(self) -> float:
        """Seconds since the last server message was received."""
        return time.monotonic() - self._last_activity

    def is_dead(self) -> bool:
        """True when silence has exceeded the configured timeout."""
        return self.idle_seconds() > self._timeout
