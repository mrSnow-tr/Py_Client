"""
statistics.py — In-memory runtime statistics for py_client.

Statistics are updated by ConnectionManager and are available read-only
through Client.statistics.  They are never persisted to disk or a database.
"""
import time


class Statistics:
    """
    Mutable counters and timestamps for one Client instance.

    All fields are plain integers or floats — no locking required since
    the asyncio event loop serialises all updates.
    """

    def __init__(self) -> None:
        # Counters
        self.connection_attempts: int = 0
        self.successful_connections: int = 0
        self.reconnect_count: int = 0
        self.authentication_failures: int = 0
        self.protocol_errors: int = 0
        self.messages_sent: int = 0
        self.messages_received: int = 0
        self.bytes_sent: int = 0
        self.bytes_received: int = 0

        # Timestamps (monotonic; None if never happened)
        self.last_connected: float | None = None
        self.last_disconnected: float | None = None

        # Latency samples (rolling window, last 100)
        self._latency_samples: list[float] = []

        # When this Statistics object was created
        self._created_at: float = time.monotonic()

    # ------------------------------------------------------------------
    # Latency
    # ------------------------------------------------------------------

    def record_latency(self, latency_s: float) -> None:
        """Record a new round-trip latency sample (in seconds)."""
        self._latency_samples.append(latency_s)
        if len(self._latency_samples) > 100:
            self._latency_samples = self._latency_samples[-100:]

    @property
    def average_latency_ms(self) -> float | None:
        """Rolling average of the last 100 latency samples in milliseconds."""
        if not self._latency_samples:
            return None
        return (sum(self._latency_samples) / len(self._latency_samples)) * 1000.0

    @property
    def min_latency_ms(self) -> float | None:
        """Minimum observed latency in milliseconds (rolling window)."""
        if not self._latency_samples:
            return None
        return min(self._latency_samples) * 1000.0

    @property
    def max_latency_ms(self) -> float | None:
        """Maximum observed latency in milliseconds (rolling window)."""
        if not self._latency_samples:
            return None
        return max(self._latency_samples) * 1000.0

    # ------------------------------------------------------------------
    # Uptime
    # ------------------------------------------------------------------

    @property
    def uptime(self) -> float:
        """Seconds since this Statistics object was created."""
        return time.monotonic() - self._created_at

    # ------------------------------------------------------------------
    # Representation (no secrets)
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"Statistics("
            f"connections={self.successful_connections}, "
            f"reconnects={self.reconnect_count}, "
            f"msgs_rx={self.messages_received}, "
            f"msgs_tx={self.messages_sent})"
        )
