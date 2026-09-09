"""
Protocol codec tests — parse_message and build_message.

All tests use the actual py_relay wire format.
"""
import json
import pytest
from py_client.protocol.codec import build_message, parse_message, new_request_id
from py_client.protocol.messages import MessageType, PROTOCOL_VERSION
from py_client.exceptions import ProtocolError


MAX = 65536  # default max_message_size


def _raw(**fields) -> str:
    """Build a raw JSON message string from field overrides."""
    base = {"version": PROTOCOL_VERSION, "type": "ping", "payload": {}}
    base.update(fields)
    return json.dumps(base)


class TestParseMessage:
    # ---- Valid messages ----

    def test_minimal_valid_message(self):
        raw = json.dumps({"version": 1, "type": "ping", "payload": {}})
        msg = parse_message(raw, MAX)
        assert msg.version == 1
        assert msg.msg_type == "ping"
        assert msg.request_id is None
        assert msg.payload == {}

    def test_with_request_id(self):
        raw = json.dumps({
            "version": 1, "type": "ping",
            "request_id": "abc-123", "payload": {}
        })
        msg = parse_message(raw, MAX)
        assert msg.request_id == "abc-123"

    def test_with_payload_data(self):
        raw = json.dumps({
            "version": 1, "type": "hello",
            "payload": {"nonce": "abc", "relay": "py_relay"}
        })
        msg = parse_message(raw, MAX)
        assert msg.payload["nonce"] == "abc"
        assert msg.payload["relay"] == "py_relay"

    def test_bytes_input_decoded(self):
        raw = json.dumps({"version": 1, "type": "ping", "payload": {}})
        msg = parse_message(raw.encode("utf-8"), MAX)
        assert msg.msg_type == "ping"

    def test_missing_payload_defaults_to_empty_dict(self):
        raw = json.dumps({"version": 1, "type": "ping"})
        msg = parse_message(raw, MAX)
        assert msg.payload == {}

    def test_all_v1_types_parsed(self):
        for msg_type in [
            MessageType.HELLO, MessageType.AUTH, MessageType.AUTH_OK,
            MessageType.AUTH_FAILED, MessageType.HEARTBEAT,
            MessageType.HEARTBEAT_ACK, MessageType.PING, MessageType.PONG,
            MessageType.DISCONNECT, MessageType.ERROR,
        ]:
            raw = json.dumps({"version": 1, "type": msg_type, "payload": {}})
            msg = parse_message(raw, MAX)
            assert msg.msg_type == msg_type

    # ---- Error cases ----

    def test_invalid_json(self):
        with pytest.raises(ProtocolError, match="Invalid JSON"):
            parse_message("not json", MAX)

    def test_json_array_rejected(self):
        with pytest.raises(ProtocolError, match="JSON object"):
            parse_message("[1, 2, 3]", MAX)

    def test_missing_version(self):
        with pytest.raises(ProtocolError, match="version"):
            parse_message(json.dumps({"type": "ping", "payload": {}}), MAX)

    def test_non_integer_version(self):
        with pytest.raises(ProtocolError, match="version"):
            parse_message(_raw(version="1"), MAX)

    def test_wrong_version(self):
        with pytest.raises(ProtocolError, match="Unsupported"):
            parse_message(_raw(version=99), MAX)

    def test_missing_type(self):
        with pytest.raises(ProtocolError, match="type"):
            parse_message(json.dumps({"version": 1, "payload": {}}), MAX)

    def test_empty_type(self):
        with pytest.raises(ProtocolError, match="type"):
            parse_message(_raw(type=""), MAX)

    def test_non_string_type(self):
        with pytest.raises(ProtocolError, match="type"):
            parse_message(_raw(type=42), MAX)

    def test_non_string_request_id(self):
        with pytest.raises(ProtocolError, match="request_id"):
            parse_message(_raw(request_id=123), MAX)

    def test_non_object_payload(self):
        with pytest.raises(ProtocolError, match="payload"):
            parse_message(_raw(payload=[1, 2, 3]), MAX)

    def test_message_too_large(self):
        raw = json.dumps({"version": 1, "type": "ping", "payload": {}})
        with pytest.raises(ProtocolError, match="size"):
            parse_message(raw, max_size=5)

    def test_non_utf8_bytes(self):
        with pytest.raises(ProtocolError, match="UTF-8"):
            parse_message(b"\xff\xfe invalid", MAX)


class TestBuildMessage:
    def test_minimal_message(self):
        raw = build_message("ping")
        data = json.loads(raw)
        assert data["version"] == PROTOCOL_VERSION
        assert data["type"] == "ping"
        assert data["payload"] == {}
        assert "request_id" not in data

    def test_with_payload(self):
        raw = build_message("auth", payload={"client_id": "c1", "credential": "cred"})
        data = json.loads(raw)
        assert data["payload"]["client_id"] == "c1"

    def test_with_request_id(self):
        raw = build_message("ping", request_id="req-42")
        data = json.loads(raw)
        assert data["request_id"] == "req-42"

    def test_compact_json(self):
        raw = build_message("ping")
        assert " " not in raw  # no spaces → compact JSON

    def test_round_trip(self):
        """build → parse → same values."""
        built = build_message(
            "hello",
            payload={"nonce": "abc123", "relay": "test"},
            request_id="r1",
        )
        msg = parse_message(built, MAX)
        assert msg.msg_type == "hello"
        assert msg.request_id == "r1"
        assert msg.payload["nonce"] == "abc123"

    def test_none_payload_becomes_empty_dict(self):
        raw = build_message("ping", payload=None)
        data = json.loads(raw)
        assert data["payload"] == {}


class TestNewRequestId:
    def test_returns_string(self):
        assert isinstance(new_request_id(), str)

    def test_unique_per_call(self):
        ids = {new_request_id() for _ in range(100)}
        assert len(ids) == 100
