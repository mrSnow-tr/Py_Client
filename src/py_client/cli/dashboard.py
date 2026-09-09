"""
cli/dashboard.py — Terminal status dashboard for py_client.

Renders a live-updating status panel to stdout using ANSI escape codes.
Falls back to plain periodic prints if ANSI is not supported.
"""
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import ClientStatus
    from ..diagnostics import LocalDiagnostics


_BOLD  = "\033[1m"
_RESET = "\033[0m"
_CLEAR = "\033[2J\033[H"


def _supports_ansi() -> bool:
    """Return True when stdout appears to support ANSI escape codes."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def render_dashboard(
    status: "ClientStatus",
    diag: "LocalDiagnostics",
    *,
    clear: bool = True,
) -> None:
    """
    Print the dashboard to stdout.

    Parameters
    ----------
    status:
        Current client status snapshot.
    diag:
        Local network diagnostics snapshot.
    clear:
        If True and the terminal supports ANSI, clear the screen first.
    """
    lines: list[str] = []
    ansi = _supports_ansi()

    if clear and ansi:
        lines.append(_CLEAR)

    def _h(text: str) -> str:
        return f"{_BOLD}{text}{_RESET}" if ansi else text

    lines.append(_h("py_client"))
    lines.append("─" * 50)
    lines.append("")

    # Connection state
    state_val = status.state.value.upper()
    lines.append(f"  State:            {state_val}")
    lines.append(f"  Relay:            {status.relay_url}")
    lines.append(f"  Client ID:        {status.client_id}")

    if status.session_id:
        lines.append(f"  Session ID:       {status.session_id}")
    else:
        lines.append(f"  Session ID:       —")

    if status.relay_name:
        lines.append(f"  Relay name:       {status.relay_name}")

    lines.append("")

    # Local network
    lines.append(_h("  Network"))
    lines.append(f"  Hostname:         {diag.hostname}")
    if diag.local_addresses:
        lines.append("  Local IPs:")
        for addr in diag.local_addresses:
            lines.append(f"    {addr}")
    else:
        lines.append("  Local IPs:        (none detected)")
    lines.append(f"  Relay host:       {diag.relay_host}")
    lines.append("")

    # Timing
    lines.append(_h("  Timing"))
    uptime_s = int(status.uptime)
    h, rem = divmod(uptime_s, 3600)
    m, s   = divmod(rem, 60)
    lines.append(f"  Uptime:           {h:02d}:{m:02d}:{s:02d}")
    lines.append(f"  Connected for:    {status.connected_duration_str()}")
    lines.append(f"  Last activity:    {status.last_activity_str()}")
    lines.append("")

    # Statistics
    lines.append(_h("  Statistics"))
    lines.append(f"  Reconnects:       {status.reconnect_attempts}")
    lines.append(f"  Auth failures:    {status.auth_failures}")
    lines.append(f"  Latency:          {status.latency_str()}")
    lines.append(f"  Messages sent:    {status.messages_sent}")
    lines.append(f"  Messages recv:    {status.messages_received}")
    lines.append(f"  Bytes sent:       {status.bytes_sent_str()}")
    lines.append(f"  Bytes recv:       {status.bytes_received_str()}")
    lines.append("")

    # Last error
    err = status.last_error or "none"
    lines.append(f"  Last error:       {err}")
    lines.append("")
    lines.append(f"  [Updated {time.strftime('%H:%M:%S')}]  Ctrl-C to stop")

    print("\n".join(lines), flush=True)
