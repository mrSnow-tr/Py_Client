# py_client Architecture

## Overview

```
┌─────────────────────────────────────────────────────┐
│                    User Application                  │
│                                                      │
│  from py_client import Client, ClientConfig          │
│  client = Client(config)                             │
│  await client.start()                                │
└────────────────────────┬────────────────────────────┘
                         │
                    ┌────┴────┐
                    │ Client  │  (thin façade, public API)
                    └────┬────┘
                         │ owns
          ┌──────────────┼──────────────┐
          │              │              │
     ┌────┴────┐  ┌──────┴──────┐  ┌───┴────┐
     │Statistics│  │ConnectionMgr│  │EventBus│
     └──────────┘  └──────┬──────┘  └────────┘
                          │ owns
               ┌──────────┼──────────┐
               │          │          │
        ┌──────┴──┐  ┌────┴────┐  ┌─┴──────────┐
        │Reconnect│  │Heartbeat│  │transport/  │
        │Policy   │  │Monitor  │  │websocket.py│
        └─────────┘  └─────────┘  └─────┬──────┘
                                         │
                                    ┌────┴────┐
                                    │websockets│
                                    │library   │
                                    └─────┬────┘
                                          │  wss://
                                    ┌─────┴─────┐
                                    │ py_relay  │
                                    └───────────┘
```

## Key Modules

| Module | Responsibility |
|--------|---------------|
| `client.py` | Public API (`Client`, `ClientStatus`) |
| `connection.py` | Full connection lifecycle state machine |
| `config.py` | Immutable configuration + `SecretStr` |
| `auth.py` | HMAC-SHA256 credential computation |
| `state.py` | `ConnectionState` enum |
| `session.py` | Immutable `SessionInfo` per connection |
| `heartbeat.py` | `HeartbeatMonitor` — tracks server activity |
| `reconnect.py` | Exponential backoff with jitter |
| `events.py` | Async-safe pub/sub event bus |
| `statistics.py` | In-memory runtime counters |
| `diagnostics.py` | Local network information |
| `protocol/codec.py` | `parse_message` / `build_message` |
| `protocol/messages.py` | `Message` dataclass + `MessageType` constants |
| `transport/websocket.py` | WebSocket connection factory (TLS, timeouts) |
| `cli/main.py` | `py-client run / version / check` |
| `cli/dashboard.py` | Terminal status dashboard |

## Connection State Machine

```
STOPPED ──start()──► CONNECTING ──ws open──► AUTHENTICATING ──AUTH_OK──► CONNECTED
   ▲                     │                        │                          │
   │                     │ fail                   │ fail                     │ loss
   │                     ▼                        ▼                          ▼
   └──────── STOPPED ◄── DISCONNECTING ◄────────────────────────────── RECONNECTING
             FAILED ◄── (too many auth failures or max retries exceeded)
```

## Generation IDs

Each connection attempt increments `_generation`.  Background tasks
(heartbeat, message dispatch) capture their generation at launch and
check it before mutating state.  This prevents stale connections from
overwriting a newer connection's session.

## Secret Handling

`AUTH_SECRET` is wrapped in `SecretStr`, whose `__repr__`, `__str__`,
and `__format__` return `***`.  The real value is only accessible via
`get_secret_value()` and is used solely to compute the HMAC credential.
It is never logged, serialised, or transmitted.
