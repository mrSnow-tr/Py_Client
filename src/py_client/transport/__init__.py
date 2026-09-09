"""py_client transport package."""

__all__ = ["create_websocket_connection"]


def __getattr__(name: str):  # type: ignore[return]
    if name == "create_websocket_connection":
        from .websocket import create_websocket_connection
        return create_websocket_connection
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
