"""
example.py — Minimal py_client usage example.

Run against a local py_relay:

    export AUTH_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
    export PORT=8000
    # In one terminal:
    python /path/to/py_relay/app.py
    # In another:
    python example.py
"""
import asyncio
import logging

from py_client import Client, ClientConfig
from py_client.config import SecretStr
from py_client.state import ConnectionState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)


async def main() -> None:
    config = ClientConfig(
        relay_url="ws://127.0.0.1:8000",   # use wss:// in production
        client_id="example-client",
        secret=SecretStr("replace-with-your-auth-secret"),
        allow_insecure=True,               # for local ws:// only
        heartbeat_interval=10.0,
    )

    client = Client(config)

    # Register event handlers
    async def on_connected(client_id: str, session_id: str, relay_name: str) -> None:
        print(f"✓ Connected  client_id={client_id}  session_id={session_id}")

    async def on_disconnected(session_id: str | None, reason: str) -> None:
        print(f"✗ Disconnected  reason={reason!r}")

    async def on_reconnecting(attempt: int, delay: float) -> None:
        print(f"↺ Reconnecting  attempt={attempt}  delay={delay:.1f}s")

    async def on_error(reason: str, exc: Exception | None) -> None:
        print(f"! Error  reason={reason!r}")

    client.on("connected",    on_connected)
    client.on("disconnected", on_disconnected)
    client.on("reconnecting", on_reconnecting)
    client.on("error",        on_error)

    print(f"Connecting to {config.relay_url} as {config.client_id!r}...")
    await client.start()

    try:
        await client.wait_until_connected(timeout=15.0)
    except Exception as exc:
        print(f"Failed to connect: {exc}")
        await client.stop()
        return

    print(f"Session: {client.session}")
    print("Running... press Ctrl-C to stop.\n")

    try:
        # Keep running until interrupted
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        print("\nShutting down...")
        await client.stop()
        stats = client.statistics
        print(
            f"Final stats: "
            f"connections={stats.successful_connections} "
            f"reconnects={stats.reconnect_count} "
            f"msgs_sent={stats.messages_sent} "
            f"msgs_recv={stats.messages_received}"
        )


if __name__ == "__main__":
    asyncio.run(main())
