"""
diagnostics.py — Local network diagnostics for py_client.

Provides lightweight information about the local host and relay endpoint.
Does NOT query any third-party IP-detection services.
Does NOT claim detected local addresses are public Internet addresses.
"""
import socket
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass(frozen=True)
class LocalDiagnostics:
    """
    Snapshot of local network information.

    Attributes
    ----------
    hostname
        The local machine's hostname.
    local_addresses
        Non-loopback IPv4/IPv6 addresses bound on this host.  May be
        private (RFC 1918) addresses — not necessarily routable.
    relay_host
        Hostname extracted from the relay URL.
    relay_port
        Port extracted from the relay URL (None if default).
    """

    hostname: str
    local_addresses: list[str] = field(default_factory=list)
    relay_host: str = ""
    relay_port: int | None = None


def get_local_diagnostics(relay_url: str) -> LocalDiagnostics:
    """
    Collect lightweight local network information.

    Parameters
    ----------
    relay_url:
        The relay WebSocket URL (e.g. ``wss://relay.example.com``).

    Returns
    -------
    LocalDiagnostics snapshot.  Never raises — returns partial data on error.
    """
    # Hostname
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"

    # Local addresses — exclude loopback
    local_addresses: list[str] = []
    try:
        infos = socket.getaddrinfo(hostname, None)
        seen: set[str] = set()
        for info in infos:
            addr = info[4][0]
            if addr in seen:
                continue
            seen.add(addr)
            # Skip loopback
            if addr.startswith("127.") or addr == "::1":
                continue
            local_addresses.append(addr)
    except Exception:
        pass

    # Relay host / port
    relay_host = ""
    relay_port: int | None = None
    try:
        parsed = urlparse(relay_url)
        relay_host = parsed.hostname or ""
        relay_port = parsed.port  # None when using the scheme default
    except Exception:
        pass

    return LocalDiagnostics(
        hostname=hostname,
        local_addresses=local_addresses,
        relay_host=relay_host,
        relay_port=relay_port,
    )
