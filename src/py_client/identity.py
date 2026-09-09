"""
identity.py — Client identity validation.

Rules mirror py_relay's auth.py exactly:
  - 1 to 64 characters
  - ASCII letters, digits, hyphen (-), underscore (_), dot (.)
  - Must be a non-empty str
"""
import re

from .exceptions import ConfigurationError

_CLIENT_ID_RE = re.compile(r"^[a-zA-Z0-9_\-.]+$")
_MAX_CLIENT_ID_LEN = 64


def validate_client_id(client_id: object) -> None:
    """
    Validate the client_id format.

    Raises ConfigurationError if the value is invalid.
    On success, returns None.
    """
    if not isinstance(client_id, str):
        raise ConfigurationError("client_id must be a string")
    if not client_id:
        raise ConfigurationError("client_id must not be empty")
    if len(client_id) > _MAX_CLIENT_ID_LEN:
        raise ConfigurationError(
            f"client_id must be {_MAX_CLIENT_ID_LEN} characters or fewer"
        )
    if not _CLIENT_ID_RE.match(client_id):
        raise ConfigurationError(
            "client_id contains invalid characters "
            "(allowed: a-z A-Z 0-9 _ - .)"
        )
