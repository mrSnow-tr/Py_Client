# py_client Configuration

## Precedence (highest → lowest)

1. Explicit Python constructor arguments
2. Environment variables (`ClientConfig.from_env()`)
3. TOML file (`ClientConfig.from_toml(path)`)
4. Built-in defaults

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PY_CLIENT_RELAY_URL` | Yes | — | WebSocket URL (`wss://…` or `ws://`) |
| `PY_CLIENT_CLIENT_ID` | Yes | — | Persistent client identity |
| `PY_CLIENT_SECRET` | Yes | — | Shared HMAC secret — never logged |
| `PY_CLIENT_CONNECT_TIMEOUT` | No | `10.0` | Seconds for TCP connect |
| `PY_CLIENT_AUTH_TIMEOUT` | No | `15.0` | Seconds for HELLO→AUTH_OK |
| `PY_CLIENT_HEARTBEAT_INTERVAL` | No | `20.0` | Seconds between client PINGs |
| `PY_CLIENT_HEARTBEAT_TIMEOUT` | No | `70.0` | Seconds of silence before reconnect |
| `PY_CLIENT_RECONNECT_INITIAL_DELAY` | No | `1.0` | First backoff in seconds |
| `PY_CLIENT_RECONNECT_MAX_DELAY` | No | `30.0` | Maximum backoff in seconds |
| `PY_CLIENT_RECONNECT_JITTER` | No | `2.0` | Max random jitter per attempt |
| `PY_CLIENT_MAX_RECONNECT_ATTEMPTS` | No | `0` | 0 = unlimited |
| `PY_CLIENT_MAX_MESSAGE_SIZE` | No | `65536` | Max incoming message bytes |
| `PY_CLIENT_ALLOW_INSECURE` | No | `false` | `1`/`true`/`yes` to allow `ws://` |
| `PY_CLIENT_SSL_CA_FILE` | No | (system) | Path to custom CA bundle |

## Python API

```python
from py_client import Client, ClientConfig
from py_client.config import SecretStr

config = ClientConfig(
    relay_url="wss://your-relay.onrender.com",
    client_id="my-machine",
    secret=SecretStr("your-auth-secret"),
    # Optional overrides:
    connect_timeout=10.0,
    auth_timeout=15.0,
    heartbeat_interval=20.0,
    heartbeat_timeout=70.0,
    reconnect_initial_delay=1.0,
    reconnect_max_delay=30.0,
    reconnect_jitter=2.0,
    max_reconnect_attempts=0,     # unlimited
    max_message_size=65536,
    allow_insecure=False,
    ssl_ca_file=None,
)
```

## TOML File

```toml
relay_url  = "wss://your-relay.onrender.com"
client_id  = "my-machine"
# secret — prefer $PY_CLIENT_SECRET instead of storing here

connect_timeout          = 10.0
auth_timeout             = 15.0
heartbeat_interval       = 20.0
heartbeat_timeout        = 70.0
reconnect_initial_delay  = 1.0
reconnect_max_delay      = 30.0
reconnect_jitter         = 2.0
max_reconnect_attempts   = 0
max_message_size         = 65536
allow_insecure           = false
```

Load with:

```python
config = ClientConfig.from_toml("py_client.toml")
```

## Security Notes

- `AUTH_SECRET` must be at least 32 bytes of random entropy.
- Generate one: `python -c "import secrets; print(secrets.token_hex(32))"`
- Never store the secret in a config file or commit it to version control.
- Use `$PY_CLIENT_SECRET` environment variable in production.
- TLS verification is always enabled for `wss://` connections.
- `allow_insecure=True` is for **local development only**.
