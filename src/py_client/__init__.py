"""
py_client — Production-grade WebSocket relay client for py_relay.

Quick start
-----------
::

    import asyncio
    from py_client import Client, ClientConfig
    from py_client.config import SecretStr

    async def main():
        config = ClientConfig(
            relay_url="wss://your-relay.example.com",
            client_id="client-001",
            secret=SecretStr("your-auth-secret"),
        )
        client = Client(config)
        await client.start()
        await client.wait_until_connected(timeout=30)
        try:
            await asyncio.Event().wait()
        finally:
            await client.stop()

    asyncio.run(main())
"""
from .client import Client, ClientStatus, __version__
from .config import ClientConfig, SecretStr
from .exceptions import (
    AuthenticationError,
    ClientShutdown,
    ConfigurationError,
    ConnectionTimeout,
    InvalidStateError,
    ProtocolError,
    PyClientError,
    ServerUnavailable,
    TransportError,
)
from .session import SessionInfo
from .state import ConnectionState
from .statistics import Statistics

__all__ = [
    # Core API
    "Client",
    "ClientConfig",
    "ClientStatus",
    "SecretStr",
    "SessionInfo",
    "ConnectionState",
    "Statistics",
    # Exceptions
    "PyClientError",
    "ConfigurationError",
    "AuthenticationError",
    "ConnectionTimeout",
    "ServerUnavailable",
    "TransportError",
    "ProtocolError",
    "InvalidStateError",
    "ClientShutdown",
    # Version
    "__version__",
]
