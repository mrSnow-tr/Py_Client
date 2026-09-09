"""
cli/main.py — Command-line interface for py_client.

Commands
--------
py-client run       Connect to a relay and display a live dashboard.
py-client version   Print the py_client version and exit.
py-client check     Validate configuration and exit (no connection made).

Environment variables (``py-client run``)
-----------------------------------------
PY_CLIENT_RELAY_URL     Required
PY_CLIENT_CLIENT_ID     Required
PY_CLIENT_SECRET        Required
PY_CLIENT_ALLOW_INSECURE  1/true/yes to permit ws://

All settings can alternatively be passed as CLI flags (see --help).

This module only owns the event loop (``asyncio.run``).
All networking is delegated to the Client library.
"""
import argparse
import asyncio
import logging
import os
import signal
import sys

from py_client import Client, __version__
from py_client.cli.dashboard import render_dashboard
from py_client.config import ClientConfig, SecretStr, validate_config
from py_client.diagnostics import get_local_diagnostics
from py_client.exceptions import ConfigurationError, PyClientError


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="py-client",
        description="py_client — WebSocket relay client for py_relay",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- run ----
    run_p = sub.add_parser(
        "run",
        help="Connect to a relay and display a live status dashboard.",
    )
    run_p.add_argument(
        "--url",
        dest="relay_url",
        default=os.environ.get("PY_CLIENT_RELAY_URL", ""),
        help="Relay WebSocket URL (default: $PY_CLIENT_RELAY_URL)",
    )
    run_p.add_argument(
        "--client-id",
        default=os.environ.get("PY_CLIENT_CLIENT_ID", ""),
        help="Client identity (default: $PY_CLIENT_CLIENT_ID)",
    )
    run_p.add_argument(
        "--secret",
        default="",
        help=(
            "AUTH_SECRET value.  "
            "Prefer $PY_CLIENT_SECRET to avoid shell history exposure."
        ),
    )
    run_p.add_argument(
        "--allow-insecure",
        action="store_true",
        default=os.environ.get("PY_CLIENT_ALLOW_INSECURE", "").lower()
        in ("1", "true", "yes"),
        help="Allow ws:// (insecure) connections.  Dev use only.",
    )
    run_p.add_argument(
        "--log-level",
        default=os.environ.get("PY_CLIENT_LOG_LEVEL", "WARNING").upper(),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: WARNING)",
    )
    run_p.add_argument(
        "--refresh",
        type=float,
        default=2.0,
        metavar="SECONDS",
        help="Dashboard refresh interval in seconds (default: 2)",
    )

    # ---- check ----
    check_p = sub.add_parser(
        "check",
        help="Validate configuration and exit without connecting.",
    )
    check_p.add_argument(
        "--url",
        dest="relay_url",
        default=os.environ.get("PY_CLIENT_RELAY_URL", ""),
        help="Relay WebSocket URL",
    )
    check_p.add_argument(
        "--client-id",
        default=os.environ.get("PY_CLIENT_CLIENT_ID", ""),
        help="Client identity",
    )
    check_p.add_argument(
        "--secret",
        default="",
        help="AUTH_SECRET value.",
    )
    check_p.add_argument(
        "--allow-insecure",
        action="store_true",
        default=False,
        help="Allow ws:// connections.",
    )

    # ---- version ----
    sub.add_parser("version", help="Print version and exit.")

    return parser


# ---------------------------------------------------------------------------
# Subcommand: version
# ---------------------------------------------------------------------------

def _cmd_version() -> None:
    print(f"py_client {__version__}")


# ---------------------------------------------------------------------------
# Subcommand: check
# ---------------------------------------------------------------------------

def _cmd_check(args: argparse.Namespace) -> int:
    secret_val = (
        args.secret
        or os.environ.get("PY_CLIENT_SECRET", "")
    )
    try:
        config = ClientConfig(
            relay_url=args.relay_url,
            client_id=args.client_id,
            secret=SecretStr(secret_val) if secret_val else SecretStr(""),
            allow_insecure=args.allow_insecure,
        )
        validate_config(config)
        print(
            f"✓ Configuration OK\n"
            f"  relay_url  : {config.relay_url}\n"
            f"  client_id  : {config.client_id}\n"
            f"  secret     : ***"
        )
        return 0
    except ConfigurationError as exc:
        print(f"✗ Configuration error: {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------

async def _run_client(args: argparse.Namespace) -> None:
    secret_val = args.secret or os.environ.get("PY_CLIENT_SECRET", "")
    if not secret_val:
        print(
            "Error: AUTH_SECRET is required.  "
            "Set $PY_CLIENT_SECRET or pass --secret.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        config = ClientConfig(
            relay_url=args.relay_url,
            client_id=args.client_id,
            secret=SecretStr(secret_val),
            allow_insecure=args.allow_insecure,
        )
        validate_config(config)
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    diag = get_local_diagnostics(config.relay_url)
    client = Client(config)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _request_shutdown() -> None:
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except (NotImplementedError, RuntimeError):
            pass  # Windows

    await client.start()

    try:
        while not stop_event.is_set():
            render_dashboard(client.status, diag, clear=True)
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=args.refresh
                )
            except asyncio.TimeoutError:
                pass
    except KeyboardInterrupt:
        pass
    finally:
        await client.stop()
        print("\nStopped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Synchronous entry point called by the ``py-client`` script."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "version":
        _cmd_version()
        return

    if args.command == "check":
        sys.exit(_cmd_check(args))

    if args.command == "run":
        log_level = getattr(args, "log_level", "WARNING")
        logging.basicConfig(
            level=getattr(logging, log_level, logging.WARNING),
            format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
        )
        try:
            asyncio.run(_run_client(args))
        except KeyboardInterrupt:
            pass
        sys.exit(0)
