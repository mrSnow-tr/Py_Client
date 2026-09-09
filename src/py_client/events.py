"""
events.py — Lightweight event bus for py_client.

Handlers can be sync or async callables.  Exceptions raised by handlers
are caught, logged, and swallowed so one misbehaving handler cannot crash
the networking system.

Supported events
----------------
state_changed   (old: ConnectionState, new: ConnectionState)
connected       (client_id: str, session_id: str, relay_name: str)
disconnected    (session_id: str | None, reason: str)
reconnecting    (attempt: int, delay: float)
error           (reason: str, exc: Exception | None)
"""
import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    """
    Minimal publish/subscribe event bus.

    Handlers are called in registration order.  An exception in any handler
    is logged but does not prevent subsequent handlers from running.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[..., Any]]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def on(self, event: str, handler: Callable[..., Any]) -> None:
        """Register *handler* for *event*.  Duplicates are allowed."""
        self._handlers.setdefault(event, []).append(handler)

    def off(self, event: str, handler: Callable[..., Any]) -> None:
        """Remove a previously registered handler.  Silent if not found."""
        try:
            self._handlers.get(event, []).remove(handler)
        except ValueError:
            pass

    def clear(self, event: str | None = None) -> None:
        """Remove all handlers for *event*, or all events if None."""
        if event is None:
            self._handlers.clear()
        else:
            self._handlers.pop(event, None)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def emit(self, event: str, **kwargs: Any) -> None:
        """
        Call all registered handlers for *event* with *kwargs*.

        Awaits async handlers.  Exceptions are caught and logged.
        """
        handlers = list(self._handlers.get(event, []))
        for handler in handlers:
            try:
                result = handler(**kwargs)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception(
                    "Unhandled exception in event handler for event=%r "
                    "handler=%r",
                    event,
                    getattr(handler, "__name__", repr(handler)),
                )
