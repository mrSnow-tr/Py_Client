"""Unit tests for py_client.state.ConnectionState."""
from py_client.state import ConnectionState


class TestConnectionState:
    def test_all_expected_states_exist(self):
        expected = {
            "stopped", "connecting", "authenticating",
            "connected", "reconnecting", "disconnecting", "failed",
        }
        actual = {s.value for s in ConnectionState}
        assert expected == actual

    def test_terminal_states(self):
        assert ConnectionState.STOPPED.value == "stopped"
        assert ConnectionState.FAILED.value == "failed"

    def test_enum_members_are_unique(self):
        values = [s.value for s in ConnectionState]
        assert len(values) == len(set(values))

    def test_enum_comparison(self):
        assert ConnectionState.CONNECTED == ConnectionState.CONNECTED
        assert ConnectionState.CONNECTED != ConnectionState.STOPPED
