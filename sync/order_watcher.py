"""
OrderWatcher — listens to Supabase Realtime for new online orders.

Uses QWebSocket (PySide6.QtWebSockets, included in PySide6-Addons) to maintain
a persistent connection to the Supabase Realtime endpoint.

When an INSERT arrives on the 'orders' table, emits new_order so the caller
can run pull_new_orders() in a background thread.

Supabase Realtime Phoenix protocol:
  - Connect: wss://<ref>.supabase.co/realtime/v1/websocket?apikey=<key>&vsn=1.0.0
  - Join:    send phx_join to topic realtime:public:orders
  - Heartbeat every 30s to keep connection alive
  - On postgres_changes INSERT event → emit new_order
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from PySide6.QtCore import QObject, QTimer, Signal, QUrl
from PySide6.QtWebSockets import QWebSocket

load_dotenv()

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

_RECONNECT_DELAY_MS = 5_000   # retry after 5s on disconnect
_HEARTBEAT_MS       = 25_000  # Supabase expects < 30s


class OrderWatcher(QObject):
    """Watches Supabase Realtime for new orders and emits new_order."""

    new_order = Signal()   # emitted on INSERT into orders table
    error     = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ws           = QWebSocket(parent=self)
        self._ref          = 0       # Phoenix message ref counter
        self._joined       = False
        self._active       = False

        self._heartbeat_timer  = QTimer(self)
        self._heartbeat_timer.setInterval(_HEARTBEAT_MS)
        self._heartbeat_timer.timeout.connect(self._send_heartbeat)

        self._reconnect_timer  = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.setInterval(_RECONNECT_DELAY_MS)
        self._reconnect_timer.timeout.connect(self._connect)

        self._ws.connected.connect(self._on_connected)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.textMessageReceived.connect(self._on_message)
        self._ws.errorOccurred.connect(self._on_error)

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Open websocket connection. Call once after app start."""
        if not _SUPABASE_URL or not _SUPABASE_KEY:
            return
        self._active = True
        self._connect()

    def stop(self):
        """Close connection cleanly."""
        self._active = False
        self._heartbeat_timer.stop()
        self._reconnect_timer.stop()
        self._ws.close()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _connect(self):
        if not self._active:
            return
        # Convert https:// → wss:// and http:// → ws://
        base = _SUPABASE_URL.replace("https://", "wss://").replace("http://", "ws://")
        url  = f"{base}/realtime/v1/websocket?apikey={_SUPABASE_KEY}&vsn=1.0.0"
        self._joined = False
        self._ws.open(QUrl(url))

    def _next_ref(self) -> str:
        self._ref += 1
        return str(self._ref)

    def _send(self, payload: dict):
        try:
            self._ws.sendTextMessage(json.dumps(payload))
        except Exception:
            pass

    def _on_connected(self):
        self._heartbeat_timer.start()
        # Subscribe to INSERT events on the orders table
        self._send({
            "topic": "realtime:public:orders",
            "event": "phx_join",
            "payload": {
                "config": {
                    "postgres_changes": [
                        {"event": "INSERT", "schema": "public", "table": "orders"}
                    ]
                }
            },
            "ref": self._next_ref(),
        })

    def _on_disconnected(self):
        self._heartbeat_timer.stop()
        self._joined = False
        if self._active:
            self._reconnect_timer.start()

    def _on_error(self, err):
        self.error.emit(f"OrderWatcher: {err}")
        # _on_disconnected will fire after error and handle reconnect

    def _on_message(self, raw: str):
        try:
            msg = json.loads(raw)
        except Exception:
            return

        event   = msg.get("event", "")
        payload = msg.get("payload", {})

        if event == "phx_reply" and payload.get("status") == "ok":
            self._joined = True
            return

        # Realtime v2 wraps the change inside payload.data
        if event == "postgres_changes":
            data = payload.get("data", {})
            if data.get("type") == "INSERT":
                self.new_order.emit()
            return

        # Realtime v1 sends the change directly in payload
        if event == "INSERT":
            self.new_order.emit()

    def _send_heartbeat(self):
        self._send({
            "topic": "phoenix",
            "event": "heartbeat",
            "payload": {},
            "ref":   self._next_ref(),
        })
