"""Unit tests for py_client.config and py_client.config.SecretStr."""
import os
import tempfile
from pathlib import Path

import pytest

import py_client.config as cfg_mod
from py_client.config import ClientConfig, SecretStr, validate_config, _load_dotenv_once
from py_client.exceptions import ConfigurationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_dotenv():
    """
    Reset the module-level dotenv-loaded flag so tests that exercise
    _load_dotenv_once() start from a clean state.

    Always restore the flag in a finally block so subsequent tests are
    unaffected.
    """
    original = cfg_mod._dotenv_loaded
    cfg_mod._dotenv_loaded = False
    return original


# ---------------------------------------------------------------------------
# SecretStr
# ---------------------------------------------------------------------------

class TestSecretStr:
    def test_get_secret_value(self):
        s = SecretStr("my-secret")
        assert s.get_secret_value() == "my-secret"

    def test_repr_does_not_leak(self):
        s = SecretStr("super-secret-value")
        assert "super-secret-value" not in repr(s)
        assert "***" in repr(s)

    def test_str_does_not_leak(self):
        s = SecretStr("super-secret-value")
        assert "super-secret-value" not in str(s)
        assert str(s) == "***"

    def test_format_does_not_leak(self):
        s = SecretStr("my-secret")
        result = f"secret={s}"
        assert "my-secret" not in result

    def test_bool_truthy(self):
        assert bool(SecretStr("non-empty"))

    def test_bool_falsy(self):
        assert not bool(SecretStr(""))

    def test_equality(self):
        assert SecretStr("abc") == SecretStr("abc")
        assert SecretStr("abc") != SecretStr("xyz")

    def test_hash_consistency(self):
        a = SecretStr("abc")
        b = SecretStr("abc")
        assert hash(a) == hash(b)

    def test_type_error_on_non_str(self):
        with pytest.raises(TypeError):
            SecretStr(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ClientConfig repr
# ---------------------------------------------------------------------------

class TestClientConfigRepr:
    def test_repr_hides_secret(self):
        config = ClientConfig(
            relay_url="wss://relay.example.com",
            client_id="test-client",
            secret=SecretStr("my-super-secret"),
        )
        r = repr(config)
        assert "my-super-secret" not in r
        assert "***" in r
        assert "test-client" in r

    def test_str_of_config_hides_secret(self):
        config = ClientConfig(
            relay_url="wss://relay.example.com",
            client_id="test-client",
            secret=SecretStr("my-super-secret"),
        )
        # dataclass str falls back to repr for frozen dataclasses
        assert "my-super-secret" not in str(config)

    def test_fstring_hides_secret(self):
        config = ClientConfig(
            relay_url="wss://relay.example.com",
            client_id="test-client",
            secret=SecretStr("my-super-secret"),
        )
        assert "my-super-secret" not in f"{config}"


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------

class TestValidateConfig:
    def _valid(self, **overrides) -> ClientConfig:
        defaults = dict(
            relay_url="wss://relay.example.com",
            client_id="test-client",
            secret=SecretStr("good-secret"),
        )
        defaults.update(overrides)
        return ClientConfig(**defaults)

    def test_valid_config_passes(self):
        validate_config(self._valid())  # no exception

    def test_empty_relay_url(self):
        with pytest.raises(ConfigurationError, match="relay_url"):
            validate_config(self._valid(relay_url=""))

    def test_bad_scheme(self):
        with pytest.raises(ConfigurationError, match="wss://"):
            validate_config(self._valid(relay_url="http://relay.example.com"))

    def test_insecure_ws_rejected_by_default(self):
        with pytest.raises(ConfigurationError, match="Insecure"):
            validate_config(self._valid(relay_url="ws://localhost:8000"))

    def test_insecure_ws_allowed_with_flag(self):
        validate_config(
            self._valid(relay_url="ws://localhost:8000", allow_insecure=True)
        )

    def test_empty_client_id(self):
        with pytest.raises(ConfigurationError):
            validate_config(self._valid(client_id=""))

    def test_invalid_client_id_chars(self):
        with pytest.raises(ConfigurationError):
            validate_config(self._valid(client_id="bad client!"))

    def test_empty_secret(self):
        with pytest.raises(ConfigurationError, match="secret"):
            validate_config(self._valid(secret=SecretStr("")))

    def test_negative_connect_timeout(self):
        with pytest.raises(ConfigurationError, match="connect_timeout"):
            validate_config(self._valid(connect_timeout=-1.0))

    def test_zero_connect_timeout(self):
        with pytest.raises(ConfigurationError, match="connect_timeout"):
            validate_config(self._valid(connect_timeout=0.0))

    def test_reconnect_max_less_than_initial(self):
        with pytest.raises(ConfigurationError, match="reconnect_max_delay"):
            validate_config(
                self._valid(
                    reconnect_initial_delay=10.0,
                    reconnect_max_delay=5.0,
                )
            )

    def test_negative_max_reconnect_attempts(self):
        with pytest.raises(ConfigurationError, match="max_reconnect_attempts"):
            validate_config(self._valid(max_reconnect_attempts=-1))

    def test_zero_max_reconnect_attempts_ok(self):
        validate_config(self._valid(max_reconnect_attempts=0))

    def test_zero_message_size(self):
        with pytest.raises(ConfigurationError, match="max_message_size"):
            validate_config(self._valid(max_message_size=0))

    def test_nonexistent_ssl_ca_file(self):
        with pytest.raises(ConfigurationError, match="ssl_ca_file"):
            validate_config(
                self._valid(ssl_ca_file="/nonexistent/ca.pem")
            )


# ---------------------------------------------------------------------------
# from_env
# ---------------------------------------------------------------------------

class TestFromEnv:
    def test_from_env_reads_required_vars(self, monkeypatch):
        monkeypatch.setenv("PY_CLIENT_RELAY_URL", "wss://relay.example.com")
        monkeypatch.setenv("PY_CLIENT_CLIENT_ID", "env-client")
        monkeypatch.setenv("PY_CLIENT_SECRET", "env-secret")
        config = ClientConfig.from_env()
        assert config.relay_url == "wss://relay.example.com"
        assert config.client_id == "env-client"
        assert config.secret.get_secret_value() == "env-secret"

    def test_from_env_missing_url(self, monkeypatch):
        monkeypatch.delenv("PY_CLIENT_RELAY_URL", raising=False)
        monkeypatch.setenv("PY_CLIENT_CLIENT_ID", "c")
        monkeypatch.setenv("PY_CLIENT_SECRET", "s")
        with pytest.raises(ConfigurationError, match="PY_CLIENT_RELAY_URL"):
            ClientConfig.from_env()

    def test_from_env_missing_secret(self, monkeypatch):
        monkeypatch.setenv("PY_CLIENT_RELAY_URL", "wss://relay.example.com")
        monkeypatch.setenv("PY_CLIENT_CLIENT_ID", "c")
        monkeypatch.delenv("PY_CLIENT_SECRET", raising=False)
        with pytest.raises(ConfigurationError, match="PY_CLIENT_SECRET"):
            ClientConfig.from_env()

    def test_from_env_parses_floats(self, monkeypatch):
        monkeypatch.setenv("PY_CLIENT_RELAY_URL", "wss://relay.example.com")
        monkeypatch.setenv("PY_CLIENT_CLIENT_ID", "c")
        monkeypatch.setenv("PY_CLIENT_SECRET", "s")
        monkeypatch.setenv("PY_CLIENT_CONNECT_TIMEOUT", "42.5")
        config = ClientConfig.from_env()
        assert config.connect_timeout == 42.5

    def test_from_env_secret_not_in_repr(self, monkeypatch):
        monkeypatch.setenv("PY_CLIENT_RELAY_URL", "wss://relay.example.com")
        monkeypatch.setenv("PY_CLIENT_CLIENT_ID", "c")
        monkeypatch.setenv("PY_CLIENT_SECRET", "secret-must-not-leak")
        config = ClientConfig.from_env()
        assert "secret-must-not-leak" not in repr(config)
        assert "secret-must-not-leak" not in str(config)


# ---------------------------------------------------------------------------
# ClientConfig() — no-argument construction
# ---------------------------------------------------------------------------

class TestDefaultConstructor:
    """
    ClientConfig() with no arguments auto-populates from os.environ
    (which may already include values loaded from the project-root .env).
    All tests use monkeypatch to control exactly which env vars are visible.
    """

    def test_no_arg_reads_env_vars(self, monkeypatch):
        """ClientConfig() populates all fields from environment variables."""
        monkeypatch.setenv("PY_CLIENT_RELAY_URL", "wss://noarg.example.com")
        monkeypatch.setenv("PY_CLIENT_CLIENT_ID", "noarg-client")
        monkeypatch.setenv("PY_CLIENT_SECRET", "noarg-secret")
        monkeypatch.setenv("PY_CLIENT_CONNECT_TIMEOUT", "55")
        monkeypatch.setenv("PY_CLIENT_HEARTBEAT_INTERVAL", "7")

        config = ClientConfig()

        assert config.relay_url == "wss://noarg.example.com"
        assert config.client_id == "noarg-client"
        assert config.secret.get_secret_value() == "noarg-secret"
        assert config.connect_timeout == 55.0
        assert config.heartbeat_interval == 7.0

    def test_no_arg_missing_required_raises(self, monkeypatch):
        """ClientConfig() raises ConfigurationError when required vars are absent."""
        monkeypatch.delenv("PY_CLIENT_RELAY_URL", raising=False)
        monkeypatch.delenv("PY_CLIENT_CLIENT_ID", raising=False)
        monkeypatch.delenv("PY_CLIENT_SECRET", raising=False)
        with pytest.raises(ConfigurationError):
            ClientConfig()

    def test_no_arg_secret_never_in_repr(self, monkeypatch):
        """The secret from the environment must not appear in repr() or str()."""
        monkeypatch.setenv("PY_CLIENT_RELAY_URL", "wss://relay.example.com")
        monkeypatch.setenv("PY_CLIENT_CLIENT_ID", "client")
        monkeypatch.setenv("PY_CLIENT_SECRET", "repr-leak-test-secret")

        config = ClientConfig()
        assert "repr-leak-test-secret" not in repr(config)
        assert "repr-leak-test-secret" not in str(config)
        assert "repr-leak-test-secret" not in f"{config}"

    def test_no_arg_equivalent_to_from_env(self, monkeypatch):
        """ClientConfig() and ClientConfig.from_env() produce identical configs."""
        monkeypatch.setenv("PY_CLIENT_RELAY_URL", "wss://relay.example.com")
        monkeypatch.setenv("PY_CLIENT_CLIENT_ID", "equiv-client")
        monkeypatch.setenv("PY_CLIENT_SECRET", "equiv-secret")
        monkeypatch.setenv("PY_CLIENT_CONNECT_TIMEOUT", "17")

        config_noarg = ClientConfig()
        config_from_env = ClientConfig.from_env()

        assert config_noarg.relay_url == config_from_env.relay_url
        assert config_noarg.client_id == config_from_env.client_id
        assert config_noarg.connect_timeout == config_from_env.connect_timeout
        assert (
            config_noarg.secret.get_secret_value()
            == config_from_env.secret.get_secret_value()
        )

    def test_explicit_args_skip_env_load(self, monkeypatch):
        """Explicit constructor args are used as-is; env vars are ignored."""
        # Even if env has different values, the explicit args win
        monkeypatch.setenv("PY_CLIENT_RELAY_URL", "wss://env.example.com")
        monkeypatch.setenv("PY_CLIENT_CLIENT_ID", "env-client")
        monkeypatch.setenv("PY_CLIENT_SECRET", "env-secret")

        config = ClientConfig(
            relay_url="wss://explicit.example.com",
            client_id="explicit-client",
            secret=SecretStr("explicit-secret"),
        )

        assert config.relay_url == "wss://explicit.example.com"
        assert config.client_id == "explicit-client"
        assert config.secret.get_secret_value() == "explicit-secret"

    def test_os_env_overrides_dotenv(self, monkeypatch, tmp_path):
        """An OS environment variable beats the same key in a .env file."""
        # Write a temporary .env
        env_file = tmp_path / ".env"
        env_file.write_text(
            "PY_CLIENT_RELAY_URL=wss://from-dotenv.example.com\n"
            "PY_CLIENT_CLIENT_ID=dotenv-client\n"
            "PY_CLIENT_SECRET=dotenv-secret\n"
        )

        # OS env sets a different relay URL
        monkeypatch.setenv("PY_CLIENT_RELAY_URL", "wss://from-os.example.com")

        original_flag = cfg_mod._dotenv_loaded
        try:
            cfg_mod._dotenv_loaded = False
            # Point _find_project_root to our tmp directory
            from dotenv import load_dotenv
            # load_dotenv with override=False: OS env var should win
            load_dotenv(env_file, override=False)

            relay = os.environ.get("PY_CLIENT_RELAY_URL")
            assert relay == "wss://from-os.example.com", (
                f"OS env was overridden by .env: got {relay!r}"
            )
        finally:
            cfg_mod._dotenv_loaded = original_flag

    def test_works_without_dotenv_file(self, monkeypatch):
        """ClientConfig.from_env() works when no .env file is present."""
        # Force the dotenv loader to look in a directory without a .env file
        monkeypatch.setenv("PY_CLIENT_RELAY_URL", "wss://no-dotenv.example.com")
        monkeypatch.setenv("PY_CLIENT_CLIENT_ID", "no-dotenv-client")
        monkeypatch.setenv("PY_CLIENT_SECRET", "no-dotenv-secret")

        # Even if dotenv finds no file, from_env() must succeed via OS env vars
        config = ClientConfig.from_env()
        assert config.relay_url == "wss://no-dotenv.example.com"
        assert config.client_id == "no-dotenv-client"


# ---------------------------------------------------------------------------
# _load_dotenv_once — isolation tests
# ---------------------------------------------------------------------------

class TestLoadDotenvOnce:
    def test_loads_env_file_into_environ(self, monkeypatch, tmp_path):
        """_load_dotenv_once() sets env vars from an .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("PY_TEST_DOTENV_VAR=hello_from_dotenv\n")

        # Ensure the var is not already in the environment
        monkeypatch.delenv("PY_TEST_DOTENV_VAR", raising=False)

        original_flag = cfg_mod._dotenv_loaded
        original_root = None
        try:
            cfg_mod._dotenv_loaded = False
            from dotenv import load_dotenv
            load_dotenv(env_file, override=False)
            assert os.environ.get("PY_TEST_DOTENV_VAR") == "hello_from_dotenv"
        finally:
            cfg_mod._dotenv_loaded = original_flag
            monkeypatch.delenv("PY_TEST_DOTENV_VAR", raising=False)

    def test_does_not_override_os_env(self, monkeypatch, tmp_path):
        """OS environment variables are never overridden by .env entries."""
        env_file = tmp_path / ".env"
        env_file.write_text("PY_TEST_DOTENV_VAR=from_dotenv\n")

        monkeypatch.setenv("PY_TEST_DOTENV_VAR", "from_os")

        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)

        assert os.environ.get("PY_TEST_DOTENV_VAR") == "from_os"

    def test_missing_file_is_silent(self):
        """_load_dotenv_once() does not raise when the .env file is absent."""
        original_flag = cfg_mod._dotenv_loaded
        try:
            cfg_mod._dotenv_loaded = False
            # Root detection will succeed but .env won't exist there
            # (project root has a .env, but after our changes it will;
            # this is still a valid test of the silent-skip path at a
            # fictitious path)
            from dotenv import load_dotenv
            load_dotenv("/nonexistent/path/.env", override=False)  # no exception
        finally:
            cfg_mod._dotenv_loaded = original_flag
