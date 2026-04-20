"""
PriceWatcher — listens to Supabase Realtime for item price changes.

When the main branch pushes updated prices to item_prices_central,
Supabase emits an INSERT/UPDATE event here.  The POS then triggers an
immediate pull so the cashier's prices are always current.

Same Phoenix protocol as OrderWatcher.
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

_RECONNECT_DELAY_MS = 10_000
_HEARTBEAT_MS       = 25_000


class PriceWatcher(QObject):
    """Watches Supabase Realtime for item_prices_central changes."""

    prices_changed = Signal()   # emitted on INSERT or UPDATE
    error          = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ws    = QWebSocket(parent=self)
        self._ref   = 0
        self._active = False

        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(_HEARTBEAT_MS)
        self._heartbeat_timer.timeout.connect(self._send_heartbeat)

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.setInterval(_RECONNECT_DELAY_MS)
        self._reconnect_timer.timeout.connect(self._connect)

        self._ws.connected.connect(self._on_connected)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.textMessageReceived.connect(self._on_message)
        self._ws.errorOccurred.connect(self._on_error)

    def start(self):
        if not _SUPABASE_URL or not _SUPABASE_KEY:
            return
        self._active = True
        self._connect()

    def stop(self):
        self._active = False
        self._heartbeat_timer.stop()
        self._reconnect_timer.stop()
        self._ws.close()

    def _connect(self):
        if not self._active:
            return
        base = _SUPABASE_URL.replace("https://", "wss://").replace("http://", "ws://")
        url  = f"{base}/realtime/v1/websocket?apikey={_SUPABASE_KEY}&vsn=1.0.0"
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
        self._send({
            "topic": "realtime:public:item_prices_central",
            "event": "phx_join",
            "payload": {
                "config": {
                    "postgres_changes": [
                        {"event": "INSERT", "schema": "public", "table": "item_prices_central"},
                        {"event": "UPDATE", "schema": "public", "table": "item_prices_central"},
                    ]
                }
            },
            "ref": self._next_ref(),
        })

    def _on_disconnected(self):
        self._heartbeat_timer.stop()
        if self._active:
            self._reconnect_timer.start()

    def _on_error(self, err):
        self.error.emit(f"PriceWatcher: {err}")

    def _on_message(self, raw: str):
        try:
            msg = json.loads(raw)
        except Exception:
            return

        event   = msg.get("event", "")
        payload = msg.get("payload", {})

        if event == "postgres_changes":
            data = payload.get("data", {})
            if data.get("type") in ("INSERT", "UPDATE"):
                self.prices_changed.emit()
            return

        if event in ("INSERT", "UPDATE"):
            self.prices_changed.emit()

    def _send_heartbeat(self):
        self._send({
            "topic": "phoenix",
            "event": "heartbeat",
            "payload": {},
            "ref":   self._next_ref(),
        })
