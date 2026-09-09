"""
state.py — Connection state machine for py_client.

Valid states and their meanings
--------------------------------
STOPPED         Client not running; initial state and after stop().
CONNECTING      Attempting to open the WebSocket connection.
AUTHENTICATING  WebSocket open; running the HELLO → AUTH → AUTH_OK handshake.
CONNECTED       Fully authenticated; message loop active.
RECONNECTING    Waiting (with backoff) before the next connection attempt.
DISCONNECTING   stop() called; sending DISCONNECT and tearing down.
FAILED          Terminal: too many auth failures or max retries exceeded.

Allowed transitions
-------------------
STOPPED       → CONNECTING                 (start())
CONNECTING    → AUTHENTICATING             (WebSocket opened)
CONNECTING    → RECONNECTING               (connection failed)
CONNECTING    → DISCONNECTING              (stop() called)
AUTHENTICATING→ CONNECTED                 (AUTH_OK received)
AUTHENTICATING→ RECONNECTING              (auth failed, retrying)
AUTHENTICATING→ DISCONNECTING             (stop() called)
AUTHENTICATING→ FAILED                    (too many auth failures)
CONNECTED     → RECONNECTING              (connection lost)
CONNECTED     → DISCONNECTING             (stop() called)
RECONNECTING  → CONNECTING                (backoff elapsed)
RECONNECTING  → DISCONNECTING             (stop() called)
RECONNECTING  → FAILED                    (max retries exceeded)
DISCONNECTING → STOPPED                   (teardown complete)
FAILED        → CONNECTING                (start() after FAILED)
"""
from enum import Enum


class ConnectionState(Enum):
    STOPPED = "stopped"
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DISCONNECTING = "disconnecting"
    FAILED = "failed"
