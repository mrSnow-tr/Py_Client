"""Unit tests for py_client.statistics.Statistics."""
import time
import pytest
from py_client.statistics import Statistics


class TestStatistics:
    def test_initial_counters_are_zero(self):
        s = Statistics()
        assert s.connection_attempts == 0
        assert s.successful_connections == 0
        assert s.reconnect_count == 0
        assert s.authentication_failures == 0
        assert s.protocol_errors == 0
        assert s.messages_sent == 0
        assert s.messages_received == 0
        assert s.bytes_sent == 0
        assert s.bytes_received == 0

    def test_initial_timestamps_are_none(self):
        s = Statistics()
        assert s.last_connected is None
        assert s.last_disconnected is None

    def test_no_latency_initially(self):
        s = Statistics()
        assert s.average_latency_ms is None
        assert s.min_latency_ms is None
        assert s.max_latency_ms is None

    def test_counters_are_mutable(self):
        s = Statistics()
        s.connection_attempts += 1
        s.messages_sent += 5
        assert s.connection_attempts == 1
        assert s.messages_sent == 5

    def test_record_latency_single(self):
        s = Statistics()
        s.record_latency(0.05)  # 50 ms
        assert s.average_latency_ms == pytest.approx(50.0)
        assert s.min_latency_ms == pytest.approx(50.0)
        assert s.max_latency_ms == pytest.approx(50.0)

    def test_record_latency_average(self):
        s = Statistics()
        s.record_latency(0.01)   # 10 ms
        s.record_latency(0.03)   # 30 ms
        assert s.average_latency_ms == pytest.approx(20.0)

    def test_record_latency_min_max(self):
        s = Statistics()
        s.record_latency(0.01)
        s.record_latency(0.10)
        s.record_latency(0.05)
        assert s.min_latency_ms == pytest.approx(10.0)
        assert s.max_latency_ms == pytest.approx(100.0)

    def test_latency_rolling_window_100(self):
        s = Statistics()
        # Fill 150 samples; window should keep only last 100.
        for i in range(150):
            s.record_latency(float(i) / 1000.0)
        # The 100 retained samples are 50..149 ms.
        assert len(s._latency_samples) == 100
        # min should be sample 50 (0.050s = 50 ms)
        assert s.min_latency_ms == pytest.approx(50.0)
        # max should be sample 149 (0.149s = 149 ms)
        assert s.max_latency_ms == pytest.approx(149.0)

    def test_uptime_increases(self):
        s = Statistics()
        t0 = s.uptime
        time.sleep(0.01)
        t1 = s.uptime
        assert t1 > t0

    def test_repr_has_no_secrets(self):
        s = Statistics()
        s.successful_connections = 3
        r = repr(s)
        assert "connections=3" in r
        # Make sure no accidental secret field leaks
        assert "secret" not in r.lower()
        assert "password" not in r.lower()

    def test_timestamps_settable(self):
        s = Statistics()
        now = time.monotonic()
        s.last_connected = now
        s.last_disconnected = now + 1.0
        assert s.last_connected == now
        assert s.last_disconnected == now + 1.0
