"""Unit tests for py_client.identity.validate_client_id."""
import pytest
from py_client.identity import validate_client_id
from py_client.exceptions import ConfigurationError


class TestValidateClientId:
    # ---- Valid cases ----

    def test_simple_alphanumeric(self):
        validate_client_id("client1")  # no exception

    def test_with_hyphen(self):
        validate_client_id("client-01")

    def test_with_underscore(self):
        validate_client_id("client_01")

    def test_with_dot(self):
        validate_client_id("client.host")

    def test_uppercase(self):
        validate_client_id("ClientABC")

    def test_exactly_64_chars(self):
        validate_client_id("a" * 64)

    def test_all_allowed_chars(self):
        validate_client_id("aZ0-_.")

    def test_single_char(self):
        validate_client_id("x")

    def test_numeric_only(self):
        validate_client_id("123456")

    # ---- Invalid cases ----

    def test_empty_string(self):
        with pytest.raises(ConfigurationError, match="empty"):
            validate_client_id("")

    def test_too_long(self):
        with pytest.raises(ConfigurationError, match="64"):
            validate_client_id("a" * 65)

    def test_space_not_allowed(self):
        with pytest.raises(ConfigurationError, match="invalid characters"):
            validate_client_id("client id")

    def test_exclamation_not_allowed(self):
        with pytest.raises(ConfigurationError, match="invalid characters"):
            validate_client_id("client!")

    def test_at_sign_not_allowed(self):
        with pytest.raises(ConfigurationError, match="invalid characters"):
            validate_client_id("client@host")

    def test_slash_not_allowed(self):
        with pytest.raises(ConfigurationError, match="invalid characters"):
            validate_client_id("path/to/client")

    def test_non_string_raises(self):
        with pytest.raises(ConfigurationError, match="string"):
            validate_client_id(42)  # type: ignore[arg-type]

    def test_none_raises(self):
        with pytest.raises(ConfigurationError, match="string"):
            validate_client_id(None)  # type: ignore[arg-type]
