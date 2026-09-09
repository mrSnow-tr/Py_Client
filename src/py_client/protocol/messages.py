"""
protocol/messages.py — Message type constants and the parsed Message type.

Message types mirror py_relay's protocol.py exactly.
Only V1 types are listed; reserved future types are noted but not used.
"""
from dataclasses import dataclass, field
from typing import Any

# Protocol version enforced on every message.
PROTOCOL_VERSION: int = 1


class MessageType:
    """
    String constants for all V1 protocol message types.

    Directions noted as: S→C (server-to-client), C→S (client-to-server),
    or ↔ (either direction).
    """

    # V1 — implemented
    HELLO         = "hello"           # S→C  opens handshake, carries nonce
    AUTH          = "auth"            # C→S  authentication request
    AUTH_OK       = "auth_ok"         # S→C  authentication accepted
    AUTH_FAILED   = "auth_failed"     # S→C  authentication rejected
    HEARTBEAT     = "heartbeat"       # ↔    keep-alive probe
    HEARTBEAT_ACK = "heartbeat_ack"   # ↔    heartbeat acknowledgement
    PING          = "ping"            # ↔    connectivity / latency check
    PONG          = "pong"            # ↔    ping response
    DISCONNECT    = "disconnect"      # ↔    graceful close notification
    ERROR         = "error"           # S→C  protocol or server error

    # Reserved — not implemented in V1
    SESSION_RESUME = "session_resume"
    CLIENT_INFO    = "client_info"
    PEER_LIST      = "peer_list"
    CONNECT_PEER   = "connect_peer"
    DATA           = "data"
    ROUTE          = "route"


@dataclass
class Message:
    """A parsed, validated protocol message."""

    version: int
    msg_type: str
    request_id: str | None
    payload: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"Message(version={self.version}, "
            f"type={self.msg_type!r}, "
            f"request_id={self.request_id!r})"
        )
