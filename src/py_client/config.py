"""
config.py — Strongly-typed, immutable configuration for py_client.

Secret handling
---------------
``ClientConfig.secret`` is wrapped in ``SecretStr`` whose ``__repr__`` and
``__str__`` return ``'***'``.  The actual value is only accessible via
``secret.get_secret_value()``.  This prevents accidental exposure through
logging, f-strings, or print statements.

Loading precedence (highest → lowest)
--------------------------------------
1. Explicit Python constructor arguments
2. Real OS environment variables
3. Project-root ``.env`` file  (auto-discovered; loaded via python-dotenv)
4. Built-in safe defaults

The ``.env`` file is loaded automatically the first time ``ClientConfig()``
or ``ClientConfig.from_env()`` is called.  OS environment variables are
**never** overridden by ``.env`` values — the file only fills gaps.

No-argument construction
------------------------
``ClientConfig()`` with no arguments is fully equivalent to
``ClientConfig.from_env()``: it discovers and loads the project-root
``.env``, then reads every field from the resulting environment.

Calling with explicit arguments (e.g. ``ClientConfig(relay_url=…)``) skips
the auto-load entirely; the provided values plus built-in defaults are used.

Environment variables
---------------------
PY_CLIENT_RELAY_URL
PY_CLIENT_CLIENT_ID
PY_CLIENT_SECRET              ← never echoed
PY_CLIENT_CONNECT_TIMEOUT
PY_CLIENT_AUTH_TIMEOUT
PY_CLIENT_HEARTBEAT_INTERVAL
PY_CLIENT_HEARTBEAT_TIMEOUT
PY_CLIENT_RECONNECT_INITIAL_DELAY
PY_CLIENT_RECONNECT_MAX_DELAY
PY_CLIENT_RECONNECT_JITTER
PY_CLIENT_MAX_RECONNECT_ATTEMPTS   (0 = unlimited)
PY_CLIENT_MAX_MESSAGE_SIZE
PY_CLIENT_ALLOW_INSECURE           (1/true/yes → ws:// allowed)
PY_CLIENT_SSL_CA_FILE
"""
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .exceptions import ConfigurationError
from .identity import validate_client_id

_DEFAULT_MAX_MESSAGE_SIZE = 64 * 1024  # 64 KiB — matches py_relay default


# ---------------------------------------------------------------------------
# .env auto-discovery and loading
# ---------------------------------------------------------------------------

def _find_project_root() -> Path | None:
    """
    Walk upward from this source file looking for ``pyproject.toml``.

    Returns the directory that contains ``pyproject.toml``, or ``None`` when
    the project root cannot be determined (e.g. the package is installed as a
    wheel in site-packages, where no ``.env`` file is expected).
    """
    try:
        candidate = Path(__file__).resolve().parent
        for _ in range(6):
            if (candidate / "pyproject.toml").is_file():
                return candidate
            parent = candidate.parent
            if parent == candidate:  # hit filesystem root
                break
            candidate = parent
    except Exception:
        pass
    return None


_dotenv_loaded: bool = False


def _load_dotenv_once() -> None:
    """
    Load ``<project-root>/.env`` into ``os.environ`` exactly once per process.

    Uses ``python-dotenv`` with ``override=False`` so that real OS environment
    variables are **never** overridden by ``.env`` entries.  Silently skips when:

    * ``python-dotenv`` is not installed.
    * No ``.env`` file exists at the project root.
    * The project root cannot be determined (installed wheel).

    Subsequent calls are cheap no-ops (guarded by a module-level flag).
    """
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    _dotenv_loaded = True

    root = _find_project_root()
    if root is None:
        return
    env_file = root / ".env"
    if not env_file.is_file():
        return

    try:
        from dotenv import load_dotenv  # python-dotenv
        load_dotenv(env_file, override=False)  # OS env always wins
    except ImportError:
        # python-dotenv not installed — .env will not be loaded.
        # Install it: pip install python-dotenv
        pass


# ---------------------------------------------------------------------------
# Internal env-var reader (shared by from_env() and __post_init__)
# ---------------------------------------------------------------------------

def _read_env_vars() -> dict:
    """
    Read all ``PY_CLIENT_*`` environment variables and return a dict suitable
    for ``ClientConfig(**…)`` construction.

    Assumes the caller has already invoked ``_load_dotenv_once()``.

    Raises ``ConfigurationError`` for missing required variables or
    malformed numeric values.
    """
    relay_url = os.environ.get("PY_CLIENT_RELAY_URL", "")
    client_id = os.environ.get("PY_CLIENT_CLIENT_ID", "")
    secret_val = os.environ.get("PY_CLIENT_SECRET", "")

    if not relay_url:
        raise ConfigurationError(
            "PY_CLIENT_RELAY_URL environment variable is required"
        )
    if not client_id:
        raise ConfigurationError(
            "PY_CLIENT_CLIENT_ID environment variable is required"
        )
    if not secret_val:
        raise ConfigurationError(
            "PY_CLIENT_SECRET environment variable is required"
        )

    def _bool(name: str, default: str = "false") -> bool:
        return os.environ.get(name, default).lower() in ("1", "true", "yes")

    def _float(name: str, default: float) -> float:
        try:
            return float(os.environ.get(name, str(default)))
        except ValueError:
            raise ConfigurationError(
                f"Environment variable {name} must be a number"
            )

    def _int(name: str, default: int) -> int:
        try:
            return int(os.environ.get(name, str(default)))
        except ValueError:
            raise ConfigurationError(
                f"Environment variable {name} must be an integer"
            )

    return dict(
        relay_url=relay_url,
        client_id=client_id,
        secret=SecretStr(secret_val),
        connect_timeout=_float("PY_CLIENT_CONNECT_TIMEOUT", 10.0),
        auth_timeout=_float("PY_CLIENT_AUTH_TIMEOUT", 15.0),
        heartbeat_interval=_float("PY_CLIENT_HEARTBEAT_INTERVAL", 20.0),
        heartbeat_timeout=_float("PY_CLIENT_HEARTBEAT_TIMEOUT", 70.0),
        reconnect_initial_delay=_float("PY_CLIENT_RECONNECT_INITIAL_DELAY", 1.0),
        reconnect_max_delay=_float("PY_CLIENT_RECONNECT_MAX_DELAY", 30.0),
        reconnect_jitter=_float("PY_CLIENT_RECONNECT_JITTER", 2.0),
        max_reconnect_attempts=_int("PY_CLIENT_MAX_RECONNECT_ATTEMPTS", 0),
        max_message_size=_int(
            "PY_CLIENT_MAX_MESSAGE_SIZE", _DEFAULT_MAX_MESSAGE_SIZE
        ),
        allow_insecure=_bool("PY_CLIENT_ALLOW_INSECURE"),
        ssl_ca_file=os.environ.get("PY_CLIENT_SSL_CA_FILE") or None,
    )


# ---------------------------------------------------------------------------
# SecretStr
# ---------------------------------------------------------------------------

class SecretStr:
    """
    A string wrapper that prevents accidental logging of secrets.

    Use ``secret.get_secret_value()`` to access the raw value.
    The value never appears in ``repr()``, ``str()``, ``format()``, or logs.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError(
                f"SecretStr requires a str, got {type(value).__name__}"
            )
        self._value = value

    def get_secret_value(self) -> str:
        """Return the raw secret value."""
        return self._value

    def __repr__(self) -> str:
        return "SecretStr('***')"

    def __str__(self) -> str:
        return "***"

    def __format__(self, spec: str) -> str:
        return "***"

    def __bool__(self) -> bool:
        return bool(self._value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SecretStr):
            return self._value == other._value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._value)


# ---------------------------------------------------------------------------
# ClientConfig
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClientConfig:
    """
    Immutable configuration snapshot for one Client instance.

    No-argument construction
    ------------------------
    ``ClientConfig()`` with no arguments is fully equivalent to
    ``ClientConfig.from_env()``: it discovers the project-root ``.env`` file,
    loads it (without overriding real OS environment variables), and reads
    every field from the resulting environment.

    Explicit-argument construction (existing behaviour, unchanged)
    -------------------------------------------------------------
    When any of ``relay_url``, ``client_id``, or ``secret`` is provided, the
    auto-load path is skipped entirely.  The supplied values are used as-is
    and unspecified optional fields fall back to their built-in defaults.

    Attributes
    ----------
    relay_url
        WebSocket URL of the relay.  Must start with ``wss://`` in
        production.  ``ws://`` is allowed only when ``allow_insecure=True``
        (local development only).
    client_id
        Persistent logical identity (1–64 ASCII alphanumeric / - / _ / .).
    secret
        Shared HMAC secret.  Stored as SecretStr — never logged.
    connect_timeout
        Seconds to wait for the TCP/WebSocket connection to open.
    auth_timeout
        Seconds to wait for the full HELLO→AUTH→AUTH_OK handshake.
    heartbeat_interval
        Seconds between client-initiated PING messages.
    heartbeat_timeout
        Seconds of silence from the server before declaring the connection
        dead and triggering a reconnect.
    reconnect_initial_delay
        Seconds before the first reconnect attempt.
    reconnect_max_delay
        Maximum seconds between reconnect attempts (backoff cap).
    reconnect_jitter
        Maximum random jitter added to each backoff delay.
    max_reconnect_attempts
        Hard cap on total reconnect attempts.  ``0`` means unlimited.
    max_message_size
        Maximum allowed incoming message size in bytes.
    allow_insecure
        Allow ``ws://`` URLs.  For local development only.
    ssl_ca_file
        Path to a custom CA certificate bundle.  ``None`` uses the system
        default.
    """

    # Required fields default to empty so that ClientConfig() works as a
    # zero-argument factory.  __post_init__ detects this and loads from env.
    relay_url: str = ""
    client_id: str = ""
    secret: SecretStr = field(default_factory=lambda: SecretStr(""))

    # Optional fields — safe built-in defaults
    connect_timeout: float = 10.0
    auth_timeout: float = 15.0
    heartbeat_interval: float = 20.0
    heartbeat_timeout: float = 70.0
    reconnect_initial_delay: float = 1.0
    reconnect_max_delay: float = 30.0
    reconnect_jitter: float = 2.0
    max_reconnect_attempts: int = 0
    max_message_size: int = _DEFAULT_MAX_MESSAGE_SIZE
    allow_insecure: bool = False
    ssl_ca_file: str | None = None

    # ------------------------------------------------------------------
    # Auto-load from environment on no-arg construction
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        """
        Populate all fields from the environment when called with no required
        arguments.

        The trigger is: all three required fields (``relay_url``,
        ``client_id``, ``secret``) are at their empty defaults.  When that is
        true, the project-root ``.env`` is loaded (OS env vars are not
        overridden), then every field is resolved from ``os.environ``.

        When any required field is explicitly provided, the method returns
        immediately — no environment reads occur, no ``.env`` is touched.
        """
        if self.relay_url or self.client_id or self.secret.get_secret_value():
            # At least one required field was explicitly supplied — skip auto-load.
            return

        # All three required fields are empty → no-arg (or explicit-empty)
        # construction.  Load .env into os.environ (override=False keeps OS
        # env vars intact), then read every field from os.environ.
        _load_dotenv_once()
        fields = _read_env_vars()
        for attr, value in fields.items():
            object.__setattr__(self, attr, value)

    # ------------------------------------------------------------------
    # repr — secret is never included
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"ClientConfig("
            f"relay_url={self.relay_url!r}, "
            f"client_id={self.client_id!r}, "
            f"secret=***)"
        )

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "ClientConfig":
        """
        Build a ``ClientConfig`` entirely from environment variables.

        Discovers and loads the project-root ``.env`` file first (OS env vars
        are never overridden), then reads all ``PY_CLIENT_*`` variables.

        Raises ``ConfigurationError`` if required variables are absent.
        """
        _load_dotenv_once()
        return cls(**_read_env_vars())

    @classmethod
    def from_toml(cls, path: str | Path) -> "ClientConfig":
        """
        Load a ``ClientConfig`` from a TOML file.

        The ``secret`` key may be omitted from the file and supplied via the
        ``PY_CLIENT_SECRET`` environment variable instead — recommended so
        secrets are not stored in config files.
        """
        path = Path(path)
        try:
            with open(path, "rb") as fh:
                data = tomllib.load(fh)
        except FileNotFoundError:
            raise ConfigurationError(f"Config file not found: {path}")
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError(
                f"Invalid TOML in {path}: {exc}"
            ) from exc

        relay_url = data.get("relay_url", "")
        client_id = data.get("client_id", "")
        # Prefer env var for the secret so it is not stored on disk
        secret_val = data.get(
            "secret", os.environ.get("PY_CLIENT_SECRET", "")
        )

        if not relay_url:
            raise ConfigurationError(
                f"relay_url is required in config file {path}"
            )
        if not client_id:
            raise ConfigurationError(
                f"client_id is required in config file {path}"
            )
        if not secret_val:
            raise ConfigurationError(
                "secret must be provided in the config file or via "
                "PY_CLIENT_SECRET environment variable"
            )

        return cls(
            relay_url=relay_url,
            client_id=client_id,
            secret=SecretStr(secret_val),
            connect_timeout=float(data.get("connect_timeout", 10.0)),
            auth_timeout=float(data.get("auth_timeout", 15.0)),
            heartbeat_interval=float(data.get("heartbeat_interval", 20.0)),
            heartbeat_timeout=float(data.get("heartbeat_timeout", 70.0)),
            reconnect_initial_delay=float(
                data.get("reconnect_initial_delay", 1.0)
            ),
            reconnect_max_delay=float(data.get("reconnect_max_delay", 30.0)),
            reconnect_jitter=float(data.get("reconnect_jitter", 2.0)),
            max_reconnect_attempts=int(data.get("max_reconnect_attempts", 0)),
            max_message_size=int(
                data.get("max_message_size", _DEFAULT_MAX_MESSAGE_SIZE)
            ),
            allow_insecure=bool(data.get("allow_insecure", False)),
            ssl_ca_file=data.get("ssl_ca_file"),
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_config(config: ClientConfig) -> None:
    """
    Validate a ``ClientConfig``, raising ``ConfigurationError`` on any problem.

    Called automatically by ``Client.__init__()``.
    """
    if not config.relay_url:
        raise ConfigurationError("relay_url must not be empty")

    if not config.relay_url.startswith(("wss://", "ws://")):
        raise ConfigurationError(
            f"relay_url must start with wss:// or ws://, "
            f"got: {config.relay_url!r}"
        )

    if config.relay_url.startswith("ws://") and not config.allow_insecure:
        raise ConfigurationError(
            "Insecure ws:// URLs are disabled by default.  Use wss:// for "
            "production, or set allow_insecure=True for local development."
        )

    validate_client_id(config.client_id)

    if not config.secret or not config.secret.get_secret_value():
        raise ConfigurationError("secret must not be empty")

    if config.connect_timeout <= 0:
        raise ConfigurationError("connect_timeout must be positive")

    if config.auth_timeout <= 0:
        raise ConfigurationError("auth_timeout must be positive")

    if config.heartbeat_interval <= 0:
        raise ConfigurationError("heartbeat_interval must be positive")

    if config.heartbeat_timeout <= 0:
        raise ConfigurationError("heartbeat_timeout must be positive")

    if config.reconnect_initial_delay < 0:
        raise ConfigurationError("reconnect_initial_delay must be >= 0")

    if config.reconnect_max_delay < config.reconnect_initial_delay:
        raise ConfigurationError(
            "reconnect_max_delay must be >= reconnect_initial_delay"
        )

    if config.reconnect_jitter < 0:
        raise ConfigurationError("reconnect_jitter must be >= 0")

    if config.max_reconnect_attempts < 0:
        raise ConfigurationError(
            "max_reconnect_attempts must be >= 0 (0 means unlimited)"
        )

    if config.max_message_size <= 0:
        raise ConfigurationError("max_message_size must be positive")

    if config.ssl_ca_file is not None:
        if not os.path.isfile(config.ssl_ca_file):
            raise ConfigurationError(
                f"ssl_ca_file not found: {config.ssl_ca_file}"
            )


# ---------------------------------------------------------------------------
# Load .env at import time so CLI argparse defaults (which call
# os.environ.get() inside _build_parser()) also benefit from the file.
# ---------------------------------------------------------------------------
_load_dotenv_once()
