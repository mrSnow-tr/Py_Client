"""Unit tests for py_client.events.EventBus."""
import asyncio
import pytest
from py_client.events import EventBus


class TestEventBus:
    @pytest.mark.asyncio
    async def test_sync_handler_called(self):
        bus = EventBus()
        results = []
        bus.on("test", lambda x: results.append(x))
        await bus.emit("test", x=42)
        assert results == [42]

    @pytest.mark.asyncio
    async def test_async_handler_called(self):
        bus = EventBus()
        results = []

        async def handler(x):
            results.append(x)

        bus.on("test", handler)
        await bus.emit("test", x=99)
        assert results == [99]

    @pytest.mark.asyncio
    async def test_multiple_handlers_called_in_order(self):
        bus = EventBus()
        order = []
        bus.on("ev", lambda: order.append(1))
        bus.on("ev", lambda: order.append(2))
        bus.on("ev", lambda: order.append(3))
        await bus.emit("ev")
        assert order == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_emit_unknown_event_is_silent(self):
        bus = EventBus()
        await bus.emit("no-such-event")  # no exception

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_propagate(self):
        bus = EventBus()
        bus.on("ev", lambda: (_ for _ in ()).throw(RuntimeError("oops")))
        await bus.emit("ev")  # should not raise

    @pytest.mark.asyncio
    async def test_async_handler_exception_does_not_propagate(self):
        bus = EventBus()

        async def bad_handler():
            raise ValueError("async oops")

        bus.on("ev", bad_handler)
        await bus.emit("ev")  # should not raise

    @pytest.mark.asyncio
    async def test_subsequent_handlers_run_after_exception(self):
        bus = EventBus()
        results = []

        def bad():
            raise RuntimeError("fail")

        bus.on("ev", bad)
        bus.on("ev", lambda: results.append("ok"))
        await bus.emit("ev")
        assert "ok" in results

    @pytest.mark.asyncio
    async def test_off_removes_handler(self):
        bus = EventBus()
        results = []
        handler = lambda: results.append(1)
        bus.on("ev", handler)
        bus.off("ev", handler)
        await bus.emit("ev")
        assert results == []

    @pytest.mark.asyncio
    async def test_off_nonexistent_handler_is_silent(self):
        bus = EventBus()
        bus.off("no-event", lambda: None)  # no exception

    @pytest.mark.asyncio
    async def test_clear_specific_event(self):
        bus = EventBus()
        results = []
        bus.on("a", lambda: results.append("a"))
        bus.on("b", lambda: results.append("b"))
        bus.clear("a")
        await bus.emit("a")
        await bus.emit("b")
        assert "a" not in results
        assert "b" in results

    @pytest.mark.asyncio
    async def test_clear_all_events(self):
        bus = EventBus()
        results = []
        bus.on("a", lambda: results.append("a"))
        bus.on("b", lambda: results.append("b"))
        bus.clear()
        await bus.emit("a")
        await bus.emit("b")
        assert results == []

    @pytest.mark.asyncio
    async def test_kwargs_passed_to_handler(self):
        bus = EventBus()
        received = {}

        def handler(old, new):
            received["old"] = old
            received["new"] = new

        bus.on("state_changed", handler)
        await bus.emit("state_changed", old="stopped", new="connecting")
        assert received == {"old": "stopped", "new": "connecting"}
