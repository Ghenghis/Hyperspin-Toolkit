"""Tests for M22 — WebSocket Event Hub."""
import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engines.event_hub import EventHub, get_hub


class TestEventHub(unittest.TestCase):
    def setUp(self):
        self.hub = EventHub()

    def test_emit_stores_history(self):
        self.hub.emit("test.event", {"key": "value"})
        history = self.hub.recent()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["event"], "test.event")
        self.assertEqual(history[0]["data"]["key"], "value")
        self.assertIn("ts", history[0])

    def test_history_limit(self):
        self.hub._max_history = 5
        for i in range(10):
            self.hub.emit("test", {"i": i})
        self.assertEqual(len(self.hub.recent(limit=100)), 5)

    def test_recent_filter_by_type(self):
        self.hub.emit("a.event", {"x": 1})
        self.hub.emit("b.event", {"x": 2})
        self.hub.emit("a.event", {"x": 3})
        a_events = self.hub.recent(event_type="a.event")
        self.assertEqual(len(a_events), 2)
        b_events = self.hub.recent(event_type="b.event")
        self.assertEqual(len(b_events), 1)

    def test_clear(self):
        self.hub.emit("test", {})
        self.hub.clear()
        self.assertEqual(len(self.hub.recent()), 0)

    def test_register_unregister(self):
        ws = MagicMock()
        self.hub.register(ws)
        self.assertEqual(self.hub.client_count, 1)
        self.hub.unregister(ws)
        self.assertEqual(self.hub.client_count, 0)

    def test_unregister_unknown(self):
        ws = MagicMock()
        self.hub.unregister(ws)  # Should not raise
        self.assertEqual(self.hub.client_count, 0)

    def test_in_process_listener(self):
        received = []
        self.hub.on("scan.done", lambda e: received.append(e))
        self.hub.emit("scan.done", {"total": 5})
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["data"]["total"], 5)

    def test_wildcard_listener(self):
        received = []
        self.hub.on("*", lambda e: received.append(e))
        self.hub.emit("any.event", {"a": 1})
        self.hub.emit("other.event", {"b": 2})
        self.assertEqual(len(received), 2)

    def test_listener_error_does_not_crash(self):
        def bad_listener(e):
            raise ValueError("boom")
        self.hub.on("test", bad_listener)
        self.hub.emit("test", {})  # Should not raise
        self.assertEqual(len(self.hub.recent()), 1)


class TestEventHubAsync(unittest.TestCase):
    def test_broadcast_to_clients(self):
        hub = EventHub()
        ws1 = MagicMock()
        ws1.send_text = AsyncMock()
        ws2 = MagicMock()
        ws2.send_text = AsyncMock()
        hub.register(ws1)
        hub.register(ws2)

        payload = {"event": "test", "data": {}, "ts": "now"}
        asyncio.run(hub._broadcast(payload))

        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

        msg = json.loads(ws1.send_text.call_args[0][0])
        self.assertEqual(msg["event"], "test")

    def test_broadcast_removes_dead_clients(self):
        hub = EventHub()
        ws_good = MagicMock()
        ws_good.send_text = AsyncMock()
        ws_dead = MagicMock()
        ws_dead.send_text = AsyncMock(side_effect=Exception("disconnected"))

        hub.register(ws_good)
        hub.register(ws_dead)
        self.assertEqual(hub.client_count, 2)

        payload = {"event": "test", "data": {}, "ts": "now"}
        asyncio.run(hub._broadcast(payload))

        self.assertEqual(hub.client_count, 1)
        self.assertIn(ws_good, hub._clients)


class TestGetHub(unittest.TestCase):
    def test_singleton(self):
        # Reset singleton for test
        import engines.event_hub as eh
        eh._hub = None
        h1 = get_hub()
        h2 = get_hub()
        self.assertIs(h1, h2)


if __name__ == "__main__":
    unittest.main()
