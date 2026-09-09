"""
protocol/codec.py — Message serialisation and deserialisation.

All JSON construction and parsing for the relay protocol lives here.
No other module should build or decode raw protocol bytes.

Wire format (UTF-8 JSON)
------------------------
{
    "version":    1,
    "type":       "<message_type>",
    "request_id": "<uuid>",   // optional
    "payload":    {}          // always an object
}
"""
import json
import uuid
from typing import Any

from ..exceptions import ProtocolError
from .messages import Message, PROTOCOL_VERSION


def parse_message(raw: str | bytes, max_size: int) -> Message:
    """
    Parse and validate a raw string or bytes as a protocol message.

    Parameters
    ----------
    raw:
        UTF-8 text (or bytes that will be decoded) from the WebSocket.
    max_size:
        Maximum allowed byte length.  Messages larger than this are
        rejected even if they are valid JSON.

    Returns
    -------
    A validated Message instance.

    Raises
    ------
    ProtocolError
        For any validation failure: bad encoding, bad JSON, wrong version,
        missing fields, wrong field types, or size excess.
    """
    # Decode bytes
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("Message is not valid UTF-8") from exc

    # Size guard
    byte_len = len(raw.encode("utf-8"))
    if byte_len > max_size:
        raise ProtocolError(
            f"Message exceeds size limit ({byte_len} > {max_size} bytes)"
        )

    # JSON decode
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ProtocolError("Message must be a JSON object")

    # version
    version = data.get("version")
    if version is None:
        raise ProtocolError("Missing required field 'version'")
    if not isinstance(version, int):
        raise ProtocolError("Field 'version' must be an integer")
    if version != PROTOCOL_VERSION:
        raise ProtocolError(
            f"Unsupported protocol version {version}; "
            f"this client requires version {PROTOCOL_VERSION}"
        )

    # type
    msg_type = data.get("type")
    if msg_type is None:
        raise ProtocolError("Missing required field 'type'")
    if not isinstance(msg_type, str) or not msg_type:
        raise ProtocolError("Field 'type' must be a non-empty string")

    # request_id (optional)
    request_id = data.get("request_id")
    if request_id is not None and not isinstance(request_id, str):
        raise ProtocolError("Field 'request_id' must be a string when present")

    # payload (optional; defaults to empty object)
    payload = data.get("payload", {})
    if not isinstance(payload, dict):
        raise ProtocolError("Field 'payload' must be a JSON object")

    return Message(
        version=version,
        msg_type=msg_type,
        request_id=request_id,
        payload=payload,
    )


def build_message(
    msg_type: str,
    payload: dict[str, Any] | None = None,
    request_id: str | None = None,
    version: int = PROTOCOL_VERSION,
) -> str:
    """
    Serialise a protocol message to a compact UTF-8 JSON string.

    Parameters
    ----------
    msg_type:   One of the MessageType constants.
    payload:    Optional dict for the payload object.  Defaults to {}.
    request_id: Optional correlation identifier.
    version:    Protocol version (defaults to PROTOCOL_VERSION).

    Returns
    -------
    Compact JSON string ready to transmit over a WebSocket.
    """
    data: dict[str, Any] = {"version": version, "type": msg_type}
    if request_id is not None:
        data["request_id"] = request_id
    data["payload"] = payload if payload is not None else {}
    return json.dumps(data, separators=(",", ":"))


def new_request_id() -> str:
    """Generate a unique, opaque request correlation identifier."""
    return str(uuid.uuid4())
