"""
client.py — High-level Client API for py_client.

Usage
-----
::

    from py_client import Client, ClientConfig
    from py_client.config import SecretStr

    config = ClientConfig(
        relay_url="wss://your-relay.onrender.com",
        client_id="my-machine",
        secret=SecretStr("your-auth-secret"),
    )

    client = Client(config)

    async def on_connected(client_id, session_id, relay_name):
        print(f"Connected — session: {session_id}")

    client.on("connected", on_connected)

    await client.start()
    await client.wait_until_connected(timeout=30)

    try:
        await asyncio.Event().wait()   # keep running
    finally:
        await client.stop()

Design notes
------------
Client is a thin façade over ConnectionManager.  It owns the Statistics and
EventBus instances and exposes a clean API that hides internal wiring.
Multiple independent Client instances can coexist in one process; they share
no global state.
"""
import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable

from .config import ClientConfig, validate_config
from .connection import ConnectionManager
from .events import EventBus
from .exceptions import InvalidStateError
from .session import SessionInfo
from .state import ConnectionState
from .statistics import Statistics

__version__ = "0.1.0"


# ---------------------------------------------------------------------------
# ClientStatus — read-only snapshot
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClientStatus:
    """
    Immutable snapshot of the client's current state.

    Never contains secrets, credentials, or mutable internal objects.
    """

    state: ConnectionState
    client_id: str
    relay_url: str
    session_id: str | None
    relay_name: str | None
    connected_since: float | None       # monotonic timestamp
    last_activity: float | None         # monotonic timestamp
    reconnect_attempts: int
    latency_ms: float | None
    bytes_sent: int
    bytes_received: int
    messages_sent: int
    messages_received: int
    auth_failures: int
    last_error: str | None
    uptime: float                        # seconds since Client was created

    # ------------------------------------------------------------------
    # Convenience formatters
    # ------------------------------------------------------------------

    def connected_duration_str(self) -> str:
        """HH:MM:SS of current connection, or '—' if not connected."""
        if self.connected_since is None:
            return "—"
        secs = int(time.monotonic() - self.connected_since)
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def last_activity_str(self) -> str:
        """Human-readable time since last server message."""
        if self.last_activity is None:
            return "—"
        secs = time.monotonic() - self.last_activity
        if secs < 60:
            return f"{secs:.0f}s ago"
        if secs < 3600:
            return f"{secs / 60:.0f}m ago"
        return f"{secs / 3600:.1f}h ago"

    def latency_str(self) -> str:
        """Formatted latency string."""
        if self.latency_ms is None:
            return "—"
        return f"{self.latency_ms:.1f} ms"

    def bytes_sent_str(self) -> str:
        return _fmt_bytes(self.bytes_sent)

    def bytes_received_str(self) -> str:
        return _fmt_bytes(self.bytes_received)


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 ** 2:.1f} MB"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class Client:
    """
    Production-grade WebSocket relay client.

    Lifecycle
    ---------
    ::

        client = Client(config)
        await client.start()           # connect + authenticate in background
        await client.wait_until_connected()
        # ... application runs ...
        await client.stop()            # graceful shutdown

    ``start()`` and ``stop()`` are idempotent — safe to call multiple times.

    Event handlers
    --------------
    Register async or sync callables with ``client.on(event, handler)``.

    Events: ``state_changed``, ``connected``, ``disconnected``,
    ``reconnecting``, ``error``.
    """

    def __init__(self, config: ClientConfig) -> None:
        validate_config(config)
        self._config = config
        self._stats = Statistics()
        self._events = EventBus()
        self._manager = ConnectionManager(config, self._stats, self._events)
        self._created_at = time.monotonic()

    # ------------------------------------------------------------------
    # Event registration
    # ------------------------------------------------------------------

    def on(self, event: str, handler: Callable[..., Any]) -> None:
        """Register an event handler.  Duplicate registrations are allowed."""
        self._events.on(event, handler)

    def off(self, event: str, handler: Callable[..., Any]) -> None:
        """Remove a previously registered event handler."""
        self._events.off(event, handler)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """
        Start the client (connect + authenticate) as a background task.

        Returns immediately.  Use ``wait_until_connected()`` to block until
        the relay connection is ready.

        Raises InvalidStateError if the client is already running.
        """
        await self._manager.start()

    async def stop(self) -> None:
        """
        Gracefully shut down the client.

        Sends a DISCONNECT to the relay, closes the WebSocket, and cancels
        background tasks.  Idempotent — safe to call multiple times.
        """
        await self._manager.stop()

    async def connect(self) -> None:
        """Alias for ``start()``."""
        await self.start()

    async def disconnect(self) -> None:
        """Alias for ``stop()``."""
        await self.stop()

    async def wait_until_connected(
        self, timeout: float | None = None
    ) -> None:
        """
        Block until CONNECTED state is reached.

        Parameters
        ----------
        timeout:
            Maximum seconds to wait.  None means wait indefinitely.

        Raises ConnectionTimeout if the timeout expires first.
        """
        await self._manager.wait_until_connected(timeout=timeout)

    # ------------------------------------------------------------------
    # State & status
    # ------------------------------------------------------------------

    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self._manager.state

    @property
    def session(self) -> SessionInfo | None:
        """Session info if currently connected, else None."""
        return self._manager.session

    @property
    def status(self) -> ClientStatus:
        """Return a fresh immutable status snapshot."""
        session = self._manager.session
        return ClientStatus(
            state=self._manager.state,
            client_id=self._config.client_id,
            relay_url=self._config.relay_url,
            session_id=session.session_id if session else None,
            relay_name=session.relay_name if session else None,
            connected_since=session.connected_at if session else None,
            last_activity=self._manager.last_activity or None,
            reconnect_attempts=self._manager.reconnect_attempts,
            latency_ms=self._manager.last_latency_ms,
            bytes_sent=self._stats.bytes_sent,
            bytes_received=self._stats.bytes_received,
            messages_sent=self._stats.messages_sent,
            messages_received=self._stats.messages_received,
            auth_failures=self._stats.authentication_failures,
            last_error=self._manager.last_error,
            uptime=time.monotonic() - self._created_at,
        )

    @property
    def statistics(self) -> Statistics:
        """Raw statistics object (read-only by convention)."""
        return self._stats

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"Client(client_id={self._config.client_id!r}, "
            f"state={self._manager.state.value!r})"
        )
