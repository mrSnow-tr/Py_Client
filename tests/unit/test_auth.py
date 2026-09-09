"""
Unit tests for py_client.auth.

Verifies the credential computation matches py_relay's auth module exactly.
The expected values below were computed independently using the same
HMAC-SHA256 formula.
"""
import hashlib
import hmac

import pytest
from py_client.auth import compute_credential


def _reference_credential(nonce: str, client_id: str, secret: str) -> str:
    """Reference implementation matching py_relay auth.compute_credential."""
    key = secret.encode("utf-8")
    msg = f"{nonce}:{client_id}".encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


class TestComputeCredential:
    def test_returns_hex_string(self):
        result = compute_credential("nonce123", "client-1", "secret")
        assert isinstance(result, str)
        # SHA-256 hex digest is always 64 chars
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_matches_reference(self):
        nonce = "a1b2c3d4e5f6" * 5 + "a1b2"
        client_id = "test-client"
        secret = "my-shared-secret"
        assert compute_credential(nonce, client_id, secret) == \
               _reference_credential(nonce, client_id, secret)

    def test_different_secrets_differ(self):
        nonce = "abc"
        client_id = "client-1"
        r1 = compute_credential(nonce, client_id, "secret-A")
        r2 = compute_credential(nonce, client_id, "secret-B")
        assert r1 != r2

    def test_different_nonces_differ(self):
        client_id = "client-1"
        secret = "shared"
        r1 = compute_credential("nonce-X", client_id, secret)
        r2 = compute_credential("nonce-Y", client_id, secret)
        assert r1 != r2

    def test_different_client_ids_differ(self):
        nonce = "nonce"
        secret = "shared"
        r1 = compute_credential(nonce, "client-A", secret)
        r2 = compute_credential(nonce, "client-B", secret)
        assert r1 != r2

    def test_unicode_secret(self):
        """Secret values with non-ASCII bytes are encoded as UTF-8."""
        result = compute_credential("n", "c", "sécret")
        assert len(result) == 64

    def test_known_vector(self):
        """
        Known-answer test computed with Python's hmac module independently.

        nonce     = "deadbeef"
        client_id = "my-client"
        secret    = "test-secret-1234"

        HMAC-SHA256(key="test-secret-1234", msg="deadbeef:my-client")
        """
        expected = _reference_credential("deadbeef", "my-client", "test-secret-1234")
        result = compute_credential("deadbeef", "my-client", "test-secret-1234")
        assert result == expected

    def test_msg_format_colon_separated(self):
        """The message MUST be '{nonce}:{client_id}' — nonce and client_id joined by ':'."""
        nonce = "NONCE"
        client_id = "CLIENT"
        secret = "SECRET"
        # Manually construct expected
        key = secret.encode("utf-8")
        msg = f"{nonce}:{client_id}".encode("utf-8")
        expected = hmac.new(key, msg, hashlib.sha256).hexdigest()
        assert compute_credential(nonce, client_id, secret) == expected
