"""
exceptions.py — Exception hierarchy for py_client.

All py_client exceptions inherit from PyClientError so callers can
catch the entire hierarchy with a single ``except PyClientError``.
"""


class PyClientError(Exception):
    """Base class for all py_client exceptions."""


class ConfigurationError(PyClientError):
    """Raised when the ClientConfig is invalid."""


class AuthenticationError(PyClientError):
    """Raised when the relay rejects the client's credentials."""


class ConnectionTimeout(PyClientError):
    """Raised when a connect or auth step exceeds its deadline."""


class ServerUnavailable(PyClientError):
    """Raised when the relay host cannot be reached (DNS / TCP failure)."""


class TransportError(PyClientError):
    """Raised when the WebSocket layer encounters an unexpected error."""


class ProtocolError(PyClientError):
    """Raised when a message violates the relay protocol."""


class InvalidStateError(PyClientError):
    """Raised when an operation is invalid in the current connection state."""


class ClientShutdown(PyClientError):
    """Internal sentinel raised to break the connection loop during shutdown."""
