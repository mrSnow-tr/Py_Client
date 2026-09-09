"""
reconnect.py — Reconnection policy with exponential backoff and jitter.

Delay schedule (defaults)
--------------------------
Attempt  Delay before connect (s)
   1     1.0  + jitter(0–2)
   2     2.0  + jitter(0–2)
   3     4.0  + jitter(0–2)
   4     8.0  + jitter(0–2)
   5     16.0 + jitter(0–2)
   6     30.0 + jitter(0–2)   ← cap (reconnect_max_delay)
   7+    30.0 + jitter(0–2)

All values are configurable via ClientConfig.
``attempt`` counter is reset when a connection is stable.
"""
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import ClientConfig


class ReconnectPolicy:
    """
    Tracks reconnect attempt count and computes backoff delays.

    Usage::

        policy = ReconnectPolicy(config)

        while not policy.should_give_up():
            delay = policy.next_delay()
            await asyncio.sleep(delay)
            try:
                await connect()
                policy.reset()   # connection stable — reset counter
                break
            except Exception:
                pass  # loop continues
    """

    def __init__(self, config: "ClientConfig") -> None:
        self._config = config
        self._attempt: int = 0

    @property
    def attempt(self) -> int:
        """Number of reconnect attempts made since the last reset."""
        return self._attempt

    def reset(self) -> None:
        """Reset the attempt counter (call after a stable connection)."""
        self._attempt = 0

    def should_give_up(self) -> bool:
        """
        True when the maximum number of attempts has been reached.

        Always False when ``max_reconnect_attempts == 0`` (unlimited).
        """
        limit = self._config.max_reconnect_attempts
        if limit == 0:
            return False
        return self._attempt >= limit

    def next_delay(self) -> float:
        """
        Increment the attempt counter and return the next backoff delay.

        Delay = min(initial * 2^(attempt-1), max_delay) + uniform(0, jitter)
        """
        self._attempt += 1
        base = min(
            self._config.reconnect_initial_delay
            * (2.0 ** (self._attempt - 1)),
            self._config.reconnect_max_delay,
        )
        jitter = random.uniform(0.0, self._config.reconnect_jitter)
        return base + jitter
