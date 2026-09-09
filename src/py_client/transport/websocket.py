"""
transport/websocket.py — WebSocket connection factory for py_client.

Responsibilities
----------------
- Build the correct SSL context (TLS enabled by default for wss://).
- Apply size limits and disable the websockets library's built-in ping
  (py_client manages its own PING/PONG via the relay protocol).
- Wrap the connect coroutine in a timeout.
- Let OSError and asyncio.TimeoutError propagate so the caller can
  classify them as ServerUnavailable / ConnectionTimeout respectively.

TLS policy
----------
TLS verification is ALWAYS enabled for wss:// URLs.
ssl.CERT_NONE and hostname-verification disabling are never used.
ws:// is only permitted when allow_insecure=True (local dev only).
"""
import asyncio
import ssl
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import ClientConfig


async def create_websocket_connection(config: "ClientConfig") -> Any:
    """
    Open and return an authenticated WebSocket connection to the relay.

    Parameters
    ----------
    config:
        A validated ClientConfig.

    Returns
    -------
    A ``websockets.WebSocketClientProtocol`` ready to send/receive.

    Raises
    ------
    asyncio.TimeoutError
        If the connection cannot be established within config.connect_timeout.
    OSError
        If the TCP connection is refused or DNS resolution fails.
    websockets.exceptions.WebSocketException
        For WebSocket-level protocol errors during the opening handshake.
    """
    ssl_ctx: ssl.SSLContext | None = None
    if config.relay_url.startswith("wss://"):
        ssl_ctx = ssl.create_default_context()
        if config.ssl_ca_file:
            ssl_ctx.load_verify_locations(config.ssl_ca_file)
        # TLS verification stays enabled — never use CERT_NONE.

    import websockets  # noqa: PLC0415 — imported lazily to allow stdlib-only tests

    async def _connect() -> Any:
        return await websockets.connect(
            config.relay_url,
            ssl=ssl_ctx,
            max_size=config.max_message_size,
            # Disable the websockets library's built-in ping; py_client
            # sends PING via the relay protocol for latency measurement.
            ping_interval=None,
            ping_timeout=None,
        )

    return await asyncio.wait_for(
        _connect(),
        timeout=config.connect_timeout,
    )
