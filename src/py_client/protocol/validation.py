"""
protocol/validation.py — Field-level validation helpers for parsed messages.

Used by the connection manager to extract and validate specific fields
from message payloads without scattering validation logic everywhere.
"""
from typing import Any

from ..exceptions import ProtocolError
from .messages import Message


def require_str_field(message: Message, field: str) -> str:
    """
    Extract a required string field from a message payload.

    Raises ProtocolError if the field is missing, None, or not a str.
    """
    value = message.payload.get(field)
    if not isinstance(value, str) or not value:
        raise ProtocolError(
            f"Message {message.msg_type!r} missing required string field {field!r}"
        )
    return value


def optional_str_field(message: Message, field: str, default: str = "") -> str:
    """
    Extract an optional string field from a message payload.

    Returns *default* if the field is absent or not a string.
    """
    value = message.payload.get(field)
    if isinstance(value, str):
        return value
    return default


def optional_int_field(
    message: Message, field: str, default: int | None = None
) -> int | None:
    """
    Extract an optional integer field from a message payload.

    Returns *default* if the field is absent or not an integer.
    """
    value = message.payload.get(field)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def require_payload_field(message: Message, field: str) -> Any:
    """
    Extract a required field from the payload (any type).

    Raises ProtocolError if the field is absent (None).
    """
    value = message.payload.get(field)
    if value is None:
        raise ProtocolError(
            f"Message {message.msg_type!r} missing required field {field!r}"
        )
    return value
