# Pi_Client

**Production-grade asyncio WebSocket relay client** for [Py_Relay](https://github.com/mrSnow-tr/Py_Relay).

> This repository contains the **client half** of the system.  
> The matching server-side component lives in the companion repository: **[Py_Relay](https://github.com/mrSnow-tr/Py_Relay)**.

Clients behind NAT / private networks open **outbound** WebSocket connections to a Py_Relay instance.  
Pi_Client (package name `py_client`) manages the complete connection lifecycle:

- HMAC-SHA256 challenge-response authentication
- Keep-alive heartbeats
- Automatic reconnection with exponential backoff + jitter
- Clean shutdown
- Rich status / statistics / event API
- Optional live CLI dashboard

---

## Architecture

```
User Application / CLI
        │
        ▼
┌──────────────────┐
│     Client       │  ← public API
└────────┬─────────┘
         │
┌────────┴─────────────────────────┐
│      ConnectionManager           │  ← state machine
│  STOPPED → CONNECTING →          │
│  AUTHENTICATING → CONNECTED      │
│  → RECONNECTING → …              │
└────────┬─────────────────────────┘
         │
┌────────┴────────┐      wss://
│    transport    │ ──────────────►  Py_Relay
│   (websocket)   │
└─────────────────┘
```

---

## Requirements

- **Python 3.11+**
- Runtime dependencies (see `requirements.txt`):
  - `websockets >= 10.0, < 12.0`
  - `python-dotenv >= 1.0`

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/mrSnow-tr/Pi_Client.git
cd Pi_Client
```

### 2. (Recommended) Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\activate           # Windows
```

### 3. Install dependencies

**Option A – using `requirements.txt` (simple)**

```bash
pip install -r requirements.txt
```

**Option B – editable install (recommended for development)**

```bash
pip install -e .
# or with test extras:
pip install -e ".[dev]"
```

**Option C – development extras only**

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

After installation the CLI entry-point `py-client` becomes available.

---

## Quick Start (Library)

```python
import asyncio
from py_client import Client, ClientConfig
from py_client.config import SecretStr

async def main():
    config = ClientConfig(
        relay_url="wss://your-relay.example.com",   # use wss:// in production
        client_id="client-001",
        secret=SecretStr("your-shared-auth-secret"),
        # allow_insecure=True,   # only for local ws:// development
    )

    client = Client(config)

    @client.on("connected")
    async def on_connected(client_id, session_id, relay_name):
        print(f"✓ Connected  session={session_id}")

    @client.on("disconnected")
    async def on_disconnected(session_id, reason):
        print(f"✗ Disconnected  reason={reason}")

    await client.start()
    await client.wait_until_connected(timeout=30)

    try:
        await asyncio.Event().wait()          # run until Ctrl-C
    finally:
        await client.stop()

asyncio.run(main())
```

A ready-to-run local example is provided in `example.py`.

---

## Configuration

| Parameter                  | Default   | Description                                      |
|----------------------------|-----------|--------------------------------------------------|
| `relay_url`                | —         | Required. Prefer `wss://…` in production         |
| `client_id`                | —         | Required. 1–64 chars (`[a-zA-Z0-9._-]`)          |
| `secret`                   | —         | Required. Shared HMAC secret (`SecretStr`)       |
| `connect_timeout`          | `
... 
