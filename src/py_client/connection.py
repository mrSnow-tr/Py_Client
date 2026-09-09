"""
connection.py — ConnectionManager: the core of py_client.

Implements the full connection lifecycle as an explicit state machine:

    STOPPED ──► CONNECTING ──► AUTHENTICATING ──► CONNECTED
                                                       │
                                                  (loss/error)
                                                       │
                                                  RECONNECTING
                                                       │
                                                  CONNECTING (next attempt)
         STOPPED ◄── DISCONNECTING ◄── CONNECTED (stop() called)
         FAILED  (terminal: repeated auth failures or max retries exceeded)

Generation IDs
--------------
Each connection attempt increments ``_generation``.  Background tasks
(heartbeat loop, message handlers) capture their generation at start and
check it before any state-mutating operation.  This prevents a stale
connection from writing to a newer connection's state.

Pending PINGs
-------------
The heartbeat task sends PING with a unique request_id.  When PONG arrives
in the message loop, the matching asyncio.Future is resolved with the
receive timestamp.  The heartbeat task computes latency from send→receive.

Reconnect storm protection
--------------------------
- Exponential backoff with jitter via ReconnectPolicy.
- Consecutive authentication failures are tracked separately.  After
  ``_MAX_CONSECUTIVE_AUTH_FAILURES`` (5), the client enters FAILED state
  and stops reconnecting to avoid hammering the relay with invalid creds.
- Non-auth failures reset the auth failure counter.

HEARTBEAT behaviour
-------------------
py_relay sends one-way HEARTBEAT messages as keep-alives.  Its dispatcher
does NOT handle HEARTBEAT_ACK from clients (it returns an ERROR instead).
Therefore this client does NOT send HEARTBEAT_ACK in response to relay
HEARTBEATs — doing so would trigger spurious ERROR messages.

The client sends its own PING messages for latency measurement.  Each
PING → PONG round-trip also acts as a keep-alive, resetting the relay's
CLIENT_TIMEOUT timer (via the relay's message-received accounting).
"""
import asyncio
import logging
import time
import uuid
from typing import Any

try:
    import websockets.exceptions
except ImportError:  # pragma: no cover
    websockets = None  # type: ignore[assignment]

from .auth import compute_credential
from .config import ClientConfig
from .events import EventBus
from .exceptions import (
    AuthenticationError,
    ClientShutdown,
    ConnectionTimeout,
    InvalidStateError,
    ProtocolError,
    ServerUnavailable,
    TransportError,
)
from .heartbeat import HeartbeatMonitor
from .protocol.codec import build_message, parse_message
from .protocol.messages import MessageType
from .reconnect import ReconnectPolicy
from .session import SessionInfo
from .state import ConnectionState
from .statistics import Statistics
from .transport.websocket import create_websocket_connection

logger = logging.getLogger(__name__)

_MAX_CONSECUTIVE_AUTH_FAILURES = 5


class ConnectionManager:
    """
    Manages the full WebSocket connection lifecycle for one Client.

    Usage
    -----
    ::

        mgr = ConnectionManager(config, stats, events)
        await mgr.start()          # launches background task; returns immediately
        await mgr.wait_until_connected(timeout=30)
        # ... client is active ...
        await mgr.stop()           # graceful shutdown
    """

    def __init__(
        self,
        config: ClientConfig,
        stats: Statistics,
        events: EventBus,
    ) -> None:
        self._config = config
        self._stats = stats
        self._events = events

        # ---- State ----
        self._state: ConnectionState = ConnectionState.STOPPED
        self._generation: int = 0          # monotonic; incremented per attempt
        self._ws: Any = None               # current WebSocket (or None)

        # ---- Session ----
        self._session: SessionInfo | None = None
        self._last_activity: float = 0.0

        # ---- Heartbeat ----
        self._hb_monitor = HeartbeatMonitor(config.heartbeat_timeout)

        # ---- Pending PING responses ----
        # request_id → Future that resolves with recv timestamp (monotonic)
        self._pending_pings: dict[str, asyncio.Future[float]] = {}

        # ---- Latency ----
        self._last_latency_ms: float | None = None

        # ---- Error tracking ----
        self._last_error: str | None = None

        # ---- Control ----
        self._stop_event: asyncio.Event = asyncio.Event()
        self._connected_event: asyncio.Event = asyncio.Event()
        self._main_task: asyncio.Task[None] | None = None

        # ---- Reconnect ----
        self._reconnect_policy = ReconnectPolicy(config)
        self._consecutive_auth_failures: int = 0

    # ------------------------------------------------------------------
    # Read-only properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def session(self) -> SessionInfo | None:
        return self._session

    @property
    def last_activity(self) -> float:
        return self._last_activity

    @property
    def last_latency_ms(self) -> float | None:
        return self._last_latency_ms

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def reconnect_attempts(self) -> int:
        return self._reconnect_policy.attempt

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """
        Start the connection manager.

        Returns immediately — the connection loop runs as a background task.

        Raises InvalidStateError if already running (not STOPPED or FAILED).
        """
        if self._state not in (
            ConnectionState.STOPPED, ConnectionState.FAILED
        ):
            raise InvalidStateError(
                f"Cannot start in state {self._state.value!r}; "
                "must be STOPPED or FAILED"
            )

        self._stop_event.clear()
        self._connected_event.clear()
        self._reconnect_policy.reset()
        self._consecutive_auth_failures = 0
        self._last_error = None

        self._main_task = asyncio.create_task(
            self._run_loop(),
            name=f"py_client.connection[{self._config.client_id}]",
        )

    async def stop(self) -> None:
        """
        Stop the connection manager gracefully.  Idempotent — safe to call
        multiple times or from any state.
        """
        if self._state in (
            ConnectionState.STOPPED, ConnectionState.FAILED
        ):
            if self._main_task and not self._main_task.done():
                await self._main_task
            return

        logger.info(
            "Stopping connection manager: client_id=%r",
            self._config.client_id,
        )
        await self._transition(ConnectionState.DISCONNECTING)
        self._stop_event.set()
        self._connected_event.clear()

        if self._main_task and not self._main_task.done():
            try:
                await asyncio.wait_for(self._main_task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning(
                    "Connection manager shutdown timed out; cancelling task."
                )
                self._main_task.cancel()
                try:
                    await self._main_task
                except asyncio.CancelledError:
                    pass

        self._main_task = None

    async def wait_until_connected(
        self, timeout: float | None = None
    ) -> None:
        """
        Block until the client reaches CONNECTED state.

        Parameters
        ----------
        timeout:
            Maximum seconds to wait.  If None, waits indefinitely.

        Raises ConnectionTimeout if the timeout expires before connecting.
        """
        if self._state == ConnectionState.CONNECTED:
            return
        try:
            if timeout is not None:
                await asyncio.wait_for(
                    self._connected_event.wait(), timeout=timeout
                )
            else:
                await self._connected_event.wait()
        except asyncio.TimeoutError:
            raise ConnectionTimeout(
                f"Timed out after {timeout}s waiting for connection"
            )

    # ------------------------------------------------------------------
    # Main reconnect loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Main connection/reconnect loop.  Runs until stopped or FAILED."""
        try:
            while not self._stop_event.is_set():
                self._generation += 1
                gen = self._generation

                try:
                    await self._connect_and_run(gen)

                except asyncio.CancelledError:
                    raise

                except ClientShutdown:
                    break

                except AuthenticationError as exc:
                    self._consecutive_auth_failures += 1
                    self._last_error = str(exc)
                    self._stats.authentication_failures += 1
                    logger.warning(
                        "Authentication failed (consecutive=%d): %s",
                        self._consecutive_auth_failures,
                        exc,
                    )
                    await self._events.emit(
                        "error", reason=str(exc), exc=exc
                    )

                    if (
                        self._consecutive_auth_failures
                        >= _MAX_CONSECUTIVE_AUTH_FAILURES
                    ):
                        logger.error(
                            "Too many consecutive auth failures (%d); "
                            "entering FAILED state.  "
                            "Verify AUTH_SECRET and client_id.",
                            _MAX_CONSECUTIVE_AUTH_FAILURES,
                        )
                        await self._transition(ConnectionState.FAILED)
                        return

                    # Longer backoff for auth failures.
                    auth_backoff = min(
                        self._config.reconnect_initial_delay
                        * (2.0 ** self._consecutive_auth_failures),
                        self._config.reconnect_max_delay,
                    )
                    logger.info(
                        "Waiting %.1fs before retry after auth failure.",
                        auth_backoff,
                    )
                    if await self._sleep_or_stop(auth_backoff):
                        break
                    continue

                except Exception as exc:
                    self._consecutive_auth_failures = 0
                    self._last_error = str(exc)
                    logger.warning(
                        "Connection failed: client_id=%r error=%s",
                        self._config.client_id,
                        exc,
                    )
                    await self._events.emit(
                        "error", reason=str(exc), exc=exc
                    )

                if self._stop_event.is_set():
                    break
                if self._state == ConnectionState.FAILED:
                    return

                # ---- Begin reconnect backoff ----
                await self._transition(ConnectionState.RECONNECTING)
                self._connected_event.clear()

                if self._reconnect_policy.should_give_up():
                    logger.error(
                        "Maximum reconnect attempts (%d) reached; "
                        "entering FAILED state.",
                        self._config.max_reconnect_attempts,
                    )
                    await self._transition(ConnectionState.FAILED)
                    return

                delay = self._reconnect_policy.next_delay()
                attempt = self._reconnect_policy.attempt

                logger.info(
                    "Reconnecting in %.1fs (attempt %d): client_id=%r",
                    delay,
                    attempt,
                    self._config.client_id,
                )
                self._stats.reconnect_count += 1
                await self._events.emit(
                    "reconnecting", attempt=attempt, delay=delay
                )

                if await self._sleep_or_stop(delay):
                    break

        except asyncio.CancelledError:
            pass
        finally:
            self._connected_event.clear()
            self._session = None
            await self._close_current_ws()
            if self._state not in (
                ConnectionState.FAILED,
                ConnectionState.STOPPED,
            ):
                await self._transition(ConnectionState.STOPPED)

    async def _sleep_or_stop(self, delay: float) -> bool:
        """
        Sleep for *delay* seconds, or return early if stop is requested.

        Returns True if the stop event fired, False if the delay elapsed.
        """
        try:
            await asyncio.wait_for(
                self._stop_event.wait(), timeout=delay
            )
            return True  # stop requested
        except asyncio.TimeoutError:
            return False  # normal delay elapsed

    # ------------------------------------------------------------------
    # Single connection attempt
    # ------------------------------------------------------------------

    async def _connect_and_run(self, gen: int) -> None:
        """
        Perform one full connect → authenticate → message-loop cycle.

        All exceptions propagate to the caller (_run_loop).
        The finally block ensures the WebSocket is always closed and
        session state is cleared.
        """
        await self._transition(ConnectionState.CONNECTING)
        self._stats.connection_attempts += 1

        logger.info(
            "Connecting to %s (gen=%d): client_id=%r",
            self._config.relay_url,
            gen,
            self._config.client_id,
        )

        # Open WebSocket
        try:
            ws = await create_websocket_connection(self._config)
        except asyncio.TimeoutError as exc:
            raise ConnectionTimeout(
                f"TCP/WebSocket connection timed out "
                f"({self._config.connect_timeout}s)"
            ) from exc
        except OSError as exc:
            raise ServerUnavailable(
                f"Cannot connect to relay: {exc}"
            ) from exc

        self._ws = ws

        try:
            await self._transition(ConnectionState.AUTHENTICATING)
            session = await self._authenticate(ws, gen)

            # ---- Authenticated ----
            self._session = session
            self._last_activity = time.monotonic()
            self._hb_monitor.reset()
            self._consecutive_auth_failures = 0
            self._reconnect_policy.reset()
            self._stats.successful_connections += 1
            self._stats.last_connected = time.monotonic()

            await self._transition(ConnectionState.CONNECTED)
            self._connected_event.set()

            logger.info(
                "Connected: client_id=%r session_id=%r relay=%r",
                self._config.client_id,
                session.session_id,
                session.relay_name,
            )
            await self._events.emit(
                "connected",
                client_id=self._config.client_id,
                session_id=session.session_id,
                relay_name=session.relay_name,
            )

            # Run message loop + heartbeat concurrently.
            await self._run_connected(ws, gen)

        finally:
            old_session = self._session
            self._session = None
            self._connected_event.clear()
            self._cancel_pending_pings()

            if self._ws is ws:
                self._ws = None
            await _safe_close(ws)

            if old_session is not None:
                self._stats.last_disconnected = time.monotonic()
                await self._events.emit(
                    "disconnected",
                    session_id=old_session.session_id,
                    reason=self._last_error or "Connection closed",
                )

    async def _run_connected(self, ws: Any, gen: int) -> None:
        """Run message loop and heartbeat side-by-side."""
        hb_task = asyncio.create_task(
            self._heartbeat_loop(ws, gen),
            name=f"py_client.heartbeat[{self._config.client_id}]",
        )
        try:
            await self._message_loop(ws, gen)
        finally:
            hb_task.cancel()
            try:
                await hb_task
            except (asyncio.CancelledError, Exception):
                pass

    # ------------------------------------------------------------------
    # Authentication handshake
    # ------------------------------------------------------------------

    async def _authenticate(self, ws: Any, gen: int) -> SessionInfo:
        """
        Run the HELLO → AUTH → AUTH_OK handshake.

        Returns a SessionInfo on success.
        Raises AuthenticationError or ProtocolError on failure.
        """
        # Receive HELLO
        try:
            raw = await asyncio.wait_for(
                ws.recv(), timeout=self._config.auth_timeout
            )
        except asyncio.TimeoutError:
            raise ConnectionTimeout(
                f"Timed out waiting for HELLO ({self._config.auth_timeout}s)"
            )
        except websockets.exceptions.ConnectionClosed as exc:
            raise TransportError(
                f"Connection closed before HELLO: code={exc.code}"
            ) from exc

        self._stats.messages_received += 1
        self._stats.bytes_received += len(raw.encode("utf-8") if isinstance(raw, str) else raw)

        try:
            hello = parse_message(raw, self._config.max_message_size)
        except ProtocolError as exc:
            raise ProtocolError(f"Invalid HELLO: {exc}") from exc

        if hello.msg_type != MessageType.HELLO:
            raise ProtocolError(
                f"Expected HELLO, got {hello.msg_type!r}"
            )

        nonce = hello.payload.get("nonce")
        relay_name = str(hello.payload.get("relay", "unknown"))
        relay_version = hello.payload.get("version")

        if not isinstance(nonce, str) or not nonce:
            raise ProtocolError("HELLO payload missing valid 'nonce' field")
        if relay_version != 1:
            raise ProtocolError(
                f"Unsupported relay protocol version: {relay_version}"
            )

        logger.debug(
            "HELLO received: relay=%r nonce=%s…%s",
            relay_name,
            nonce[:8],
            nonce[-4:],
        )

        # Compute HMAC credential
        credential = compute_credential(
            nonce=nonce,
            client_id=self._config.client_id,
            secret=self._config.secret.get_secret_value(),
        )

        # Send AUTH
        auth_msg = build_message(
            MessageType.AUTH,
            payload={
                "client_id": self._config.client_id,
                "credential": credential,
            },
        )

        try:
            await ws.send(auth_msg)
            self._stats.messages_sent += 1
            self._stats.bytes_sent += len(auth_msg.encode("utf-8"))
        except websockets.exceptions.ConnectionClosed as exc:
            raise TransportError(
                f"Connection closed while sending AUTH: code={exc.code}"
            ) from exc

        logger.debug("AUTH sent: client_id=%r", self._config.client_id)

        # Receive AUTH_OK or AUTH_FAILED
        try:
            raw = await asyncio.wait_for(
                ws.recv(), timeout=self._config.auth_timeout
            )
        except asyncio.TimeoutError:
            raise ConnectionTimeout(
                f"Timed out waiting for AUTH response "
                f"({self._config.auth_timeout}s)"
            )
        except websockets.exceptions.ConnectionClosed as exc:
            raise TransportError(
                f"Connection closed waiting for AUTH response: code={exc.code}"
            ) from exc

        self._stats.messages_received += 1
        self._stats.bytes_received += len(raw.encode("utf-8") if isinstance(raw, str) else raw)

        try:
            response = parse_message(raw, self._config.max_message_size)
        except ProtocolError as exc:
            raise ProtocolError(f"Invalid AUTH response: {exc}") from exc

        if response.msg_type == MessageType.AUTH_OK:
            session_id = response.payload.get("session_id")
            if not isinstance(session_id, str) or not session_id:
                raise ProtocolError(
                    "AUTH_OK missing valid 'session_id' field"
                )
            logger.debug("AUTH_OK: session_id=%r", session_id)
            return SessionInfo(
                session_id=session_id,
                client_id=self._config.client_id,
                relay_name=relay_name,
                connected_at=time.monotonic(),
            )

        if response.msg_type == MessageType.AUTH_FAILED:
            reason = response.payload.get(
                "reason", "Authentication failed"
            )
            raise AuthenticationError(reason)

        raise ProtocolError(
            f"Expected AUTH_OK or AUTH_FAILED; got {response.msg_type!r}"
        )

    # ------------------------------------------------------------------
    # Message loop
    # ------------------------------------------------------------------

    async def _message_loop(self, ws: Any, gen: int) -> None:
        """Receive and dispatch messages until the WebSocket closes."""
        try:
            async for raw in ws:
                if gen != self._generation:
                    logger.debug(
                        "Discarding message from stale connection gen=%d", gen
                    )
                    return
                if self._stop_event.is_set():
                    return

                # Track activity
                self._last_activity = time.monotonic()
                self._hb_monitor.touch()

                # Decode bytes
                if isinstance(raw, bytes):
                    try:
                        raw = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        logger.warning(
                            "Non-UTF-8 binary message: client_id=%r",
                            self._config.client_id,
                        )
                        self._stats.protocol_errors += 1
                        continue

                byte_len = len(raw.encode("utf-8"))
                self._stats.bytes_received += byte_len
                self._stats.messages_received += 1

                # Parse
                try:
                    message = parse_message(raw, self._config.max_message_size)
                except ProtocolError as exc:
                    logger.warning(
                        "Protocol error: client_id=%r error=%s",
                        self._config.client_id,
                        exc,
                    )
                    self._stats.protocol_errors += 1
                    continue

                await self._dispatch(message, ws, gen)

        except websockets.exceptions.ConnectionClosedOK:
            logger.info(
                "Connection closed cleanly: client_id=%r session_id=%r",
                self._config.client_id,
                self._session.session_id if self._session else None,
            )
        except websockets.exceptions.ConnectionClosedError as exc:
            logger.warning(
                "Connection closed with error: client_id=%r code=%s reason=%r",
                self._config.client_id,
                exc.code,
                exc.reason,
            )
            self._last_error = f"Connection error (code {exc.code})"
        except asyncio.CancelledError:
            raise

    # ------------------------------------------------------------------
    # Message dispatch
    # ------------------------------------------------------------------

    async def _dispatch(self, message: Any, ws: Any, gen: int) -> None:
        """Route a parsed message to the correct handler."""
        t = message.msg_type

        if t == MessageType.HEARTBEAT:
            await self._on_heartbeat(message, ws, gen)
        elif t == MessageType.HEARTBEAT_ACK:
            # Server normally doesn't send HEARTBEAT_ACK; accept silently.
            pass
        elif t == MessageType.PONG:
            self._on_pong(message)
        elif t == MessageType.PING:
            await self._on_ping(message, ws, gen)
        elif t == MessageType.DISCONNECT:
            await self._on_disconnect(message)
        elif t == MessageType.ERROR:
            await self._on_error(message)
        else:
            logger.warning(
                "Unexpected message type %r: client_id=%r",
                t,
                self._config.client_id,
            )
            self._stats.protocol_errors += 1

    async def _on_heartbeat(self, message: Any, ws: Any, gen: int) -> None:
        """
        Relay sent HEARTBEAT — update activity tracking only.

        IMPORTANT: py_relay's dispatcher does NOT handle HEARTBEAT_ACK
        received from clients (it returns an ERROR instead).  Therefore
        we do NOT send HEARTBEAT_ACK here.

        The relay sends HEARTBEAT as a one-way keep-alive.  Activity is
        already tracked by the message-loop via _hb_monitor.touch() and
        _last_activity updates.  Sending PING periodically (see
        _heartbeat_loop) keeps the relay's CLIENT_TIMEOUT from firing.
        """
        logger.debug(
            "HEARTBEAT received: client_id=%r session_id=%r",
            self._config.client_id,
            self._session.session_id if self._session else "?",
        )

    async def _on_ping(self, message: Any, ws: Any, gen: int) -> None:
        """Relay sent PING → respond with PONG."""
        if gen != self._generation:
            return
        pong = build_message(
            MessageType.PONG, request_id=message.request_id
        )
        try:
            await ws.send(pong)
            self._stats.messages_sent += 1
            self._stats.bytes_sent += len(pong.encode("utf-8"))
        except websockets.exceptions.ConnectionClosed:
            pass

    def _on_pong(self, message: Any) -> None:
        """Resolve a pending PING Future with the receive timestamp."""
        req_id = message.request_id
        if req_id and req_id in self._pending_pings:
            fut = self._pending_pings.pop(req_id)
            if not fut.done():
                fut.set_result(time.monotonic())

    async def _on_disconnect(self, message: Any) -> None:
        """Relay sent DISCONNECT — record reason and let the loop end."""
        reason = message.payload.get("reason", "Server disconnected")
        logger.info("Server sent DISCONNECT: reason=%r", reason)
        self._last_error = f"Server disconnected: {reason}"
        # WebSocket will close shortly; message loop exits naturally.

    async def _on_error(self, message: Any) -> None:
        """Relay sent ERROR — log and emit event."""
        reason = message.payload.get("reason", "Unknown server error")
        logger.warning(
            "Server error: reason=%r client_id=%r",
            reason,
            self._config.client_id,
        )
        self._last_error = f"Server error: {reason}"
        await self._events.emit("error", reason=reason, exc=None)

    # ------------------------------------------------------------------
    # Client-initiated heartbeat (PING → PONG latency measurement)
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self, ws: Any, gen: int) -> None:
        """
        Periodically send PING to measure latency and detect dead connections.

        Also monitors idle time independently of PING responses — if no
        server message has been received for heartbeat_timeout seconds the
        connection is forcibly closed to trigger reconnect.
        """
        while True:
            await asyncio.sleep(self._config.heartbeat_interval)

            if gen != self._generation or self._stop_event.is_set():
                return

            # Dead connection check (no server activity for too long)
            if self._hb_monitor.is_dead():
                logger.warning(
                    "Connection appears dead (idle %.1fs > timeout %.1fs): "
                    "client_id=%r — closing to trigger reconnect.",
                    self._hb_monitor.idle_seconds(),
                    self._config.heartbeat_timeout,
                    self._config.client_id,
                )
                self._last_error = (
                    f"Heartbeat timeout: no server activity for "
                    f"{self._hb_monitor.idle_seconds():.1f}s"
                )
                try:
                    await ws.close(1001, "Heartbeat timeout")
                except Exception:
                    pass
                return

            # Send PING for latency measurement
            try:
                latency_s = await self._send_ping(ws, gen)
                latency_ms = latency_s * 1000.0
                self._last_latency_ms = latency_ms
                self._stats.record_latency(latency_s)
                logger.debug(
                    "PING latency %.1fms: client_id=%r",
                    latency_ms,
                    self._config.client_id,
                )
            except asyncio.CancelledError:
                raise
            except ConnectionTimeout:
                logger.warning(
                    "PING timed out: client_id=%r — closing connection.",
                    self._config.client_id,
                )
                self._last_error = "PING timeout"
                try:
                    await ws.close(1001, "PING timeout")
                except Exception:
                    pass
                return
            except Exception as exc:
                logger.warning("PING error: %s", exc)
                return

    async def _send_ping(
        self, ws: Any, gen: int, timeout: float = 10.0
    ) -> float:
        """
        Send a PING and wait for the matching PONG.

        Returns the round-trip time in seconds.
        Raises ConnectionTimeout if no PONG is received within *timeout*.
        """
        if gen != self._generation:
            raise ClientShutdown("Stale connection")

        req_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[float] = loop.create_future()
        self._pending_pings[req_id] = fut

        ping_msg = build_message(MessageType.PING, request_id=req_id)
        sent_at = time.monotonic()

        try:
            await ws.send(ping_msg)
            self._stats.messages_sent += 1
            self._stats.bytes_sent += len(ping_msg.encode("utf-8"))

            received_at = await asyncio.wait_for(fut, timeout=timeout)
            return received_at - sent_at

        except asyncio.TimeoutError:
            raise ConnectionTimeout(f"PING response timed out ({timeout}s)")
        finally:
            self._pending_pings.pop(req_id, None)
            if not fut.done():
                fut.cancel()

    # ------------------------------------------------------------------
    # State transition
    # ------------------------------------------------------------------

    async def _transition(self, new_state: ConnectionState) -> None:
        """Change state and emit state_changed event."""
        old = self._state
        if old == new_state:
            return
        self._state = new_state
        logger.debug(
            "State %s → %s: client_id=%r",
            old.value,
            new_state.value,
            self._config.client_id,
        )
        await self._events.emit("state_changed", old=old, new=new_state)

    # ------------------------------------------------------------------
    # Cleanup helpers
    # ------------------------------------------------------------------

    def _cancel_pending_pings(self) -> None:
        """Cancel all pending PING futures (called on disconnect)."""
        for fut in list(self._pending_pings.values()):
            if not fut.done():
                fut.cancel()
        self._pending_pings.clear()

    async def _close_current_ws(self) -> None:
        """Close the current WebSocket if one is open."""
        ws = self._ws
        if ws is not None:
            self._ws = None
            await _safe_close(ws)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

async def _safe_close(ws: Any) -> None:
    """Close a WebSocket, swallowing all exceptions."""
    try:
        await ws.close()
    except Exception:
        pass
