# py_relay Compatibility — py_client V1

This document describes the exact protocol that `py_client` implements to
communicate with `py_relay`.  It is derived from the live py_relay source
code, not from aspirational specifications.

---

## Transport

| Property | Value |
|----------|-------|
| Protocol | WebSocket (RFC 6455) |
| Endpoint | `/` (all other paths return 404) |
| TLS | `wss://` in production; `ws://` permitted with `allow_insecure=True` |
| Max message size | 65 536 bytes (64 KiB) by default; configurable |

---

## Wire Format

Every message is a compact UTF-8 JSON object:

```json
{
    "version":    1,
    "type":       "<message_type>",
    "request_id": "<uuid>",
    "payload":    {}
}
```

- `version` (integer, required) — must be `1`.
- `type` (string, required) — one of the types below.
- `request_id` (string, optional) — used to correlate requests and responses.
- `payload` (object, optional) — defaults to `{}`.

---

## Message Types — SUPPORTED NOW

| Type | Direction | Purpose |
|------|-----------|---------|
| `hello` | Server → Client | Opens handshake; carries `relay`, `version`, `nonce` |
| `auth` | Client → Server | Authentication request |
| `auth_ok` | Server → Client | Authentication accepted; carries `session_id` |
| `auth_failed` | Server → Client | Authentication rejected; carries `reason` |
| `heartbeat` | Server → Client | One-way keep-alive from relay |
| `ping` | Client → Server | Connectivity / latency probe |
| `pong` | Server → Client | Response to client PING |
| `disconnect` | Either direction | Graceful close notification |
| `error` | Server → Client | Protocol or server error |

### Not currently used by this client

| Type | Notes |
|------|-------|
| `heartbeat_ack` | The relay sends HEARTBEAT as a one-way probe and does not handle HEARTBEAT_ACK from clients.  Sending one causes the relay to return an ERROR. |

---

## Authentication Handshake

```
Client                                   Relay
  |                                         |
  |<───── HELLO { relay, version, nonce } ──|
  |                                         |
  |──── AUTH { client_id, credential } ────►|
  |                                         |  credential =
  |                                         |  HMAC-SHA256(
  |                                         |    key = AUTH_SECRET,
  |                                         |    msg = "{nonce}:{client_id}"
  |                                         |  ).hexdigest()
  |                                         |
  |<───── AUTH_OK { session_id } ───────────|
       OR AUTH_FAILED { reason } + close
```

### HELLO payload

```json
{
    "relay":   "py_relay",
    "version": 1,
    "nonce":   "<64-hex-chars>"
}
```

### AUTH payload

```json
{
    "client_id":  "my-client-001",
    "credential": "<64-hex-chars-hmac-sha256>"
}
```

### AUTH_OK payload

```json
{
    "session_id": "<uuid>"
}
```

### AUTH_FAILED payload

```json
{
    "reason": "Invalid credential"
}
```

---

## client_id Format

| Rule | Value |
|------|-------|
| Type | Non-empty string |
| Max length | 64 characters |
| Allowed characters | `a-z`, `A-Z`, `0-9`, `-`, `_`, `.` |

---

## Heartbeat

The relay sends `heartbeat` to all authenticated clients every
`HEARTBEAT_INTERVAL` seconds (default: 25 s).

**Client behaviour:**  The client does NOT send `heartbeat_ack` in response
(the relay's dispatcher rejects `heartbeat_ack` from clients with an ERROR).
Instead, the client sends `ping` messages periodically to measure latency and
to reset the relay's `CLIENT_TIMEOUT` counter.

---

## PING / PONG (Latency Measurement)

The client sends `ping` and the relay responds with `pong`:

```json
// Client sends
{ "version": 1, "type": "ping", "request_id": "<uuid>", "payload": {} }

// Relay responds
{ "version": 1, "type": "pong", "request_id": "<uuid>", "payload": {} }
```

Round-trip time is measured between send and receive.

---

## DISCONNECT

Either party may send `disconnect`:

```json
{ "version": 1, "type": "disconnect", "payload": { "reason": "..." } }
```

The connection is expected to close shortly after.

---

## ERROR

The relay sends `error` on protocol violations:

```json
{ "version": 1, "type": "error", "payload": { "reason": "..." } }
```

---

## Connection Lifecycle

```
WebSocket open
      │
      ▼
Receive HELLO (nonce)
      │
      ▼
Send AUTH (client_id + HMAC credential)
      │
      ├── AUTH_FAILED ──► connection closed
      │
      ▼
Receive AUTH_OK (session_id)
      │
      ▼
┌─────────────────────────────┐
│  Normal operation           │
│  Receive HEARTBEAT (no ACK) │
│  Send PING → receive PONG   │
│  Receive DISCONNECT         │
└─────────────────────────────┘
      │
      ▼
DISCONNECT / close
```

---

## Reconnect Behaviour

If a client reconnects with the same `client_id`:

1. The relay detects the existing session.
2. The old session receives `DISCONNECT` and its WebSocket is closed.
3. The new session is registered as the authoritative session.

---

## FUTURE / NOT IMPLEMENTED

The following are described in py_relay's roadmap but are **not available in V1**:

| Feature | Status |
|---------|--------|
| Session resumption | Not implemented — new session on every reconnect |
| Client-to-client data routing | Not implemented |
| Virtual IP allocation | Not implemented |
| Peer discovery (`peer_list`) | Reserved type only |
| Direct P2P / hole-punching | Not implemented |
| TUN/TAP integration | Not implemented |
| Multi-relay clustering | Not implemented |
| NAT traversal (STUN/TURN/ICE) | Not implemented |

---

## Health Endpoint

The relay exposes an HTTP endpoint (not WebSocket):

```
GET /health
→ 200 OK
→ { "status": "ok", "relay": "py_relay", "uptime": 3724, "clients": 2 }
```

No authentication required.  Used by Render for liveness checks.

---

*Document version: 1.0 — matches py_relay V1*
