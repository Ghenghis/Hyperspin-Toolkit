"""M22 — Real-time WebSocket event hub.

Provides a global event bus that broadcasts events to all connected WebSocket
clients. Any engine can push events (audit progress, scan updates, download
progress, errors) and the dashboard receives them in real time.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from core.logger import get_logger

log = get_logger("event_hub")


class EventHub:
    """Singleton event hub for real-time WebSocket push.

    Usage:
        hub = get_hub()
        hub.emit("scan.progress", {"system": "MAME", "pct": 45})

    Dashboard WebSocket clients receive JSON:
        {"event": "scan.progress", "data": {"system": "MAME", "pct": 45}, "ts": "..."}
    """

    def __init__(self):
        self._clients: set[Any] = set()  # WebSocket connections
        self._history: list[dict] = []   # Recent events ring buffer
        self._max_history = 200
        self._listeners: dict[str, list[Callable]] = {}  # In-process listeners

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def register(self, ws: Any) -> None:
        """Register a WebSocket client."""
        self._clients.add(ws)
        log.info("WS client connected (%d total)", len(self._clients))

    def unregister(self, ws: Any) -> None:
        """Unregister a WebSocket client."""
        self._clients.discard(ws)
        log.info("WS client disconnected (%d remaining)", len(self._clients))

    def on(self, event_type: str, callback: Callable) -> None:
        """Register an in-process listener for an event type."""
        self._listeners.setdefault(event_type, []).append(callback)

    def emit(self, event_type: str, data: Any = None) -> None:
        """Emit an event to all connected clients and in-process listeners.

        Safe to call from sync code — schedules async broadcast if loop is running.
        """
        payload = {
            "event": event_type,
            "data": data,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

        # Store in history
        self._history.append(payload)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Fire in-process listeners
        for cb in self._listeners.get(event_type, []):
            try:
                cb(payload)
            except Exception as exc:
                log.debug("Listener error for %s: %s", event_type, exc)

        # Also fire wildcard listeners
        for cb in self._listeners.get("*", []):
            try:
                cb(payload)
            except Exception:
                pass

        # Schedule async broadcast to WebSocket clients
        if self._clients:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._broadcast(payload))
            except RuntimeError:
                # No running event loop — skip WS broadcast (CLI context)
                pass

    async def _broadcast(self, payload: dict) -> None:
        """Send event JSON to all connected WebSocket clients."""
        msg = json.dumps(payload, default=str)
        dead: set = set()
        for ws in self._clients.copy():
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)

        for ws in dead:
            self._clients.discard(ws)

    def recent(self, limit: int = 50, event_type: str | None = None) -> list[dict]:
        """Return recent events from the ring buffer."""
        events = self._history
        if event_type:
            events = [e for e in events if e["event"] == event_type]
        return events[-limit:]

    def clear(self) -> None:
        """Clear event history."""
        self._history.clear()


# ── Singleton ────────────────────────────────────────────────────────

_hub: EventHub | None = None


def get_hub() -> EventHub:
    """Get or create the global event hub singleton."""
    global _hub
    if _hub is None:
        _hub = EventHub()
    return _hub
