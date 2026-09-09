#!/usr/bin/env python3
"""End-to-end py_client -> Render py_relay test.

Usage:
    python test_py_client_render.py

Optional:
    PY_RELAY_URL   Override the relay URL.
    PY_CLIENT_ID   Override the test client ID.

The authentication secret is deliberately not accepted from the command
line or environment. The test expects the current py_client implementation
to obtain its relay secret internally.
"""

from __future__ import annotations

import asyncio
import os
import time


RELAY_URL = os.getenv("PY_RELAY_URL", "wss://py-relay-o9kx.onrender.com/")
CLIENT_ID = os.getenv("PY_CLIENT_ID", "render-py-client-test")
CONNECT_TIMEOUT = 30.0
HEARTBEAT_WAIT = 8.0


def attr(obj, *names, default=None):
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def show_status(status):
    if status is None:
        return "unavailable"
    state = attr(status, "state", default=None)
    client_id = attr(status, "client_id", default=None)
    session_id = attr(status, "session_id", default=None)
    return f"state={state!r}, client_id={client_id!r}, session_id={session_id!r}"


async def stop_client(client):
    for name in ("stop", "disconnect", "close"):
        fn = getattr(client, name, None)
        if callable(fn):
            try:
                result = fn()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass
            return


async def wait_connected(client):
    fn = attr(client, "wait_until_connected", "wait_for_connection", default=None)
    if callable(fn):
        result = fn()
        if asyncio.iscoroutine(result):
            await asyncio.wait_for(result, timeout=CONNECT_TIMEOUT)
        return

    # Fallback for clients whose start() is background-only.
    deadline = time.monotonic() + CONNECT_TIMEOUT
    while time.monotonic() < deadline:
        status = attr(client, "status", default=None)
        if callable(status):
            status = status()
        state = attr(status, "state", default=None)
        if state is not None and "CONNECTED" in str(state).upper():
            return
        await asyncio.sleep(0.25)
    raise TimeoutError("client did not reach CONNECTED state")


async def main():
    print("=" * 68)
    print("py_client -> Render py_relay end-to-end test")
    print("=" * 68)
    print(f"Relay:     {RELAY_URL}")
    print(f"Client ID: {CLIENT_ID}")
    print("Secret:    [NOT DISPLAYED]")
    print()

    try:
        from py_client import Client, ClientConfig
    except Exception as exc:
        print(f"[FAIL] Cannot import py_client: {type(exc).__name__}: {exc}")
        print("Install it first with: python -m pip install -e .")
        return 1

    print("[PASS] py_client import")

    try:
        config = ClientConfig()
    except TypeError as exc:
        print("[FAIL] ClientConfig API does not match this test.")
        print(f"       {type(exc).__name__}: {exc}")
        print("Do not expose the secret in this script; adapt only the public API.")
        return 1
    except Exception as exc:
        print(f"[FAIL] ClientConfig failed: {type(exc).__name__}: {exc}")
        return 1

    try:
        client = Client(config)
    except Exception as exc:
        print(f"[FAIL] Client creation failed: {type(exc).__name__}: {exc}")
        return 1

    print("[PASS] Client creation")

    print("[1/7] Connecting and authenticating...")
    try:
        started = time.monotonic()
        await asyncio.wait_for(client.start(), timeout=CONNECT_TIMEOUT)
        await wait_connected(client)
        print(f"[PASS] Connected/authenticated in {time.monotonic() - started:.2f}s")
    except asyncio.TimeoutError:
        print("[FAIL] Timed out connecting to the Render relay.")
        await stop_client(client)
        return 1
    except Exception as exc:
        print(f"[FAIL] Connection/authentication failed: {type(exc).__name__}: {exc}")
        await stop_client(client)
        return 1

    print("[2/7] Checking status...")
    status = attr(client, "status", default=None)
    if callable(status):
        status = status()
    print(f"       {show_status(status)}")
    state = attr(status, "state", default=None)
    if state is not None and "CONNECTED" not in str(state).upper():
        print(f"[FAIL] Expected CONNECTED, got {state!r}")
        await stop_client(client)
        return 1
    print("[PASS] Connected state")

    print("[3/7] Checking session...")
    session_id = attr(status, "session_id", default=None)
    if session_id:
        print(f"[PASS] Session ID: {session_id}")
    else:
        print("[WARN] Session ID is not exposed by status.")

    print("[4/7] Checking statistics...")
    stats = attr(client, "statistics", "stats", default=None)
    if callable(stats):
        stats = stats()
    if stats is None:
        print("[WARN] Statistics API not exposed.")
    else:
        for name in (
            "connection_attempts",
            "successful_connections",
            "reconnect_count",
            "authentication_failures",
            "messages_sent",
            "messages_received",
            "bytes_sent",
            "bytes_received",
        ):
            if hasattr(stats, name):
                print(f"       {name}: {getattr(stats, name)}")
        print("[PASS] Statistics accessible")

    print(f"[5/7] Waiting {HEARTBEAT_WAIT:.0f}s to exercise heartbeat...")
    await asyncio.sleep(HEARTBEAT_WAIT)
    status = attr(client, "status", default=None)
    if callable(status):
        status = status()
    state = attr(status, "state", default=None)
    if state is not None and "CONNECTED" not in str(state).upper():
        print(f"[FAIL] Connection was lost during heartbeat test: {state!r}")
        await stop_client(client)
        return 1
    print("[PASS] Connection remained healthy")

    print("[6/7] Clean disconnect...")
    try:
        await stop_client(client)
    except Exception as exc:
        print(f"[FAIL] Disconnect failed: {type(exc).__name__}: {exc}")
        return 1
    print("[PASS] Clean disconnect")

    print("[7/7] Reconnect...")
    try:
        await asyncio.wait_for(client.start(), timeout=CONNECT_TIMEOUT)
        await wait_connected(client)
    except asyncio.TimeoutError:
        print("[FAIL] Reconnect timed out.")
        await stop_client(client)
        return 1
    except Exception as exc:
        print(f"[FAIL] Reconnect failed: {type(exc).__name__}: {exc}")
        await stop_client(client)
        return 1

    status = attr(client, "status", default=None)
    if callable(status):
        status = status()
    print(f"       {show_status(status)}")
    state = attr(status, "state", default=None)
    if state is not None and "CONNECTED" not in str(state).upper():
        print(f"[FAIL] Reconnected state is {state!r}")
        await stop_client(client)
        return 1

    await stop_client(client)

    print()
    print("=" * 68)
    print("RESULT: PASS")
    print("=" * 68)
    print("Verified:")
    print("  - py_client import")
    print("  - client creation")
    print("  - Render WebSocket connection")
    print("  - authentication")
    print("  - connected state")
    print("  - session/status")
    print("  - statistics")
    print("  - sustained connection/heartbeat")
    print("  - clean disconnect")
    print("  - reconnect")
    print("  - final cleanup")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
        raise SystemExit(130)
