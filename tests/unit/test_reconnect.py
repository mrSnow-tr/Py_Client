"""Unit tests for py_client.reconnect.ReconnectPolicy."""
import pytest
from py_client.config import ClientConfig, SecretStr
from py_client.reconnect import ReconnectPolicy


def _config(**overrides) -> ClientConfig:
    defaults = dict(
        relay_url="wss://relay.example.com",
        client_id="test-client",
        secret=SecretStr("secret"),
        reconnect_initial_delay=1.0,
        reconnect_max_delay=30.0,
        reconnect_jitter=0.0,   # deterministic in tests
        max_reconnect_attempts=0,
    )
    defaults.update(overrides)
    return ClientConfig(**defaults)


class TestReconnectPolicy:
    def test_initial_attempt_is_zero(self):
        policy = ReconnectPolicy(_config())
        assert policy.attempt == 0

    def test_should_not_give_up_unlimited(self):
        policy = ReconnectPolicy(_config(max_reconnect_attempts=0))
        for _ in range(100):
            policy.next_delay()
        assert not policy.should_give_up()

    def test_should_give_up_after_max(self):
        policy = ReconnectPolicy(_config(max_reconnect_attempts=3))
        assert not policy.should_give_up()
        policy.next_delay()
        assert not policy.should_give_up()
        policy.next_delay()
        assert not policy.should_give_up()
        policy.next_delay()
        assert policy.should_give_up()

    def test_reset_clears_attempt_counter(self):
        policy = ReconnectPolicy(_config(max_reconnect_attempts=3))
        policy.next_delay()
        policy.next_delay()
        policy.next_delay()
        assert policy.should_give_up()
        policy.reset()
        assert policy.attempt == 0
        assert not policy.should_give_up()

    def test_exponential_backoff_sequence(self):
        policy = ReconnectPolicy(
            _config(
                reconnect_initial_delay=1.0,
                reconnect_max_delay=60.0,
                reconnect_jitter=0.0,
            )
        )
        delays = [policy.next_delay() for _ in range(6)]
        # 1, 2, 4, 8, 16, 32
        assert delays[0] == pytest.approx(1.0)
        assert delays[1] == pytest.approx(2.0)
        assert delays[2] == pytest.approx(4.0)
        assert delays[3] == pytest.approx(8.0)
        assert delays[4] == pytest.approx(16.0)
        assert delays[5] == pytest.approx(32.0)

    def test_max_delay_cap(self):
        policy = ReconnectPolicy(
            _config(
                reconnect_initial_delay=1.0,
                reconnect_max_delay=30.0,
                reconnect_jitter=0.0,
            )
        )
        # Exhaust backoff past cap
        for _ in range(10):
            delay = policy.next_delay()
        assert delay == pytest.approx(30.0)

    def test_jitter_adds_randomness(self):
        """With jitter, two successive calls should differ (statistically)."""
        policy = ReconnectPolicy(
            _config(
                reconnect_initial_delay=1.0,
                reconnect_max_delay=1.0,
                reconnect_jitter=2.0,
                max_reconnect_attempts=0,
            )
        )
        delays = {policy.next_delay() for _ in range(20)}
        policy.reset()
        # Extremely unlikely all 20 calls return the exact same value.
        assert len(delays) > 1

    def test_delay_at_least_initial(self):
        policy = ReconnectPolicy(
            _config(
                reconnect_initial_delay=2.0,
                reconnect_max_delay=30.0,
                reconnect_jitter=0.0,
            )
        )
        delay = policy.next_delay()
        assert delay >= 2.0

    def test_attempt_increments_each_call(self):
        policy = ReconnectPolicy(_config())
        for expected in range(1, 6):
            policy.next_delay()
            assert policy.attempt == expected
