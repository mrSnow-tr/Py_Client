"""
auth.py — Authentication credential computation for py_client.

Implements the client side of py_relay's HMAC-SHA256 challenge-response
authentication.

Protocol
--------
1. Server sends HELLO { nonce: "<64-hex>" }
2. Client computes credential = HMAC-SHA256(key=AUTH_SECRET, msg="{nonce}:{client_id}")
3. Client sends AUTH { client_id: "...", credential: "<hex>" }
4. Server verifies; responds AUTH_OK or AUTH_FAILED

The AUTH_SECRET is never transmitted — only the HMAC digest is sent.
The nonce is unique per connection, preventing credential replay.
"""
import hashlib
import hmac
import secrets


def generate_nonce() -> str:
    """Generate a 64-character hex nonce (for testing; the server normally generates it)."""
    return secrets.token_hex(32)


def compute_credential(nonce: str, client_id: str, secret: str) -> str:
    """
    Compute the HMAC-SHA256 credential expected by py_relay.

    Parameters
    ----------
    nonce:     The challenge string received in HELLO.
    client_id: The persistent logical identity of this client.
    secret:    The raw AUTH_SECRET value (never logged or transmitted).

    Returns
    -------
    Lowercase hex string of the HMAC-SHA256 digest.

    This must match py_relay's ``auth.compute_credential`` exactly:
        key = AUTH_SECRET.encode("utf-8")
        msg = f"{nonce}:{client_id}".encode("utf-8")
        return hmac.new(key, msg, hashlib.sha256).hexdigest()
    """
    key = secret.encode("utf-8")
    msg = f"{nonce}:{client_id}".encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()
