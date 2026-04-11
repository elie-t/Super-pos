"""
Sync Worker — runs in a background QThread.
Every SYNC_INTERVAL_SEC seconds:
  1. Drains the local sync_queue → pushes to Supabase
  2. Pulls new online orders from Supabase
  3. Emits signals so the POS UI can react (new order badge, etc.)
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal, QTimer
from config import SYNC_INTERVAL_SEC


_instance: "SyncWorker | None" = None


def get_sync_worker() -> "SyncWorker | None":
    return _instance


class SyncWorker(QThread):
    """Background thread that syncs with Supabase."""

    new_orders      = Signal(int)      # new online orders pulled
    sync_done       = Signal(int, int) # (synced, failed)
    items_updated   = Signal(int)      # item master data changes pulled
    invoices_pulled = Signal(int)      # branch invoices pulled
    users_changed   = Signal()         # user records added/updated/deactivated
    error           = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._paused  = False
        global _instance
        _instance = self

    def pause(self):
        """Pause sync ticks (e.g. during long DB operations like import)."""
        self._paused = True

    def resume(self):
        """Resume sync ticks."""
        self._paused = False

    def run(self):
        self._running = True
        while self._running:
            if not self._paused:
                self._tick()
            # Sleep in small increments so stop()/pause() are responsive
            for _ in range(SYNC_INTERVAL_SEC * 10):
                if not self._running:
                    break
                self.msleep(100)

    def _tick(self):
        from sync.service import (
            drain_sync_queue, pull_new_orders,
            pull_sales_invoices, pull_master_items,
            pull_stock_movements, is_configured,
        )
        if not is_configured():
            return
        from datetime import datetime as _dt
        _log_path = __import__('pathlib').Path(__file__).parent.parent / "data" / "sync.log"
        def _log(msg):
            try:
                with open(_log_path, "a") as _f:
                    _f.write(f"{_dt.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
            except Exception:
                pass
        try:
            # Push queued local changes (item saves, invoices, etc.)
            synced, failed = drain_sync_queue()
            if synced or failed:
                self.sync_done.emit(synced, failed)

            # Pull new online orders
            count, err = pull_new_orders()
            if err:
                self.error.emit(f"Order pull: {err}")
            elif count > 0:
                self.new_orders.emit(count)

            # Pull sales invoices from other branches
            pulled, err = pull_sales_invoices()
            if err:
                self.error.emit(f"Invoice pull: {err}")
                _log(f"[ERROR] invoice pull: {err}")
            elif pulled > 0:
                self.invoices_pulled.emit(pulled)
                _log(f"[OK] pulled {pulled} branch invoice(s)")

            # Pull item master data from Supabase
            count, err = pull_master_items()
            if err:
                self.error.emit(f"Items pull: {err}")
            elif count > 0:
                self.items_updated.emit(count)

            # Pull stock movements from other branches
            _, err = pull_stock_movements()
            if err:
                self.error.emit(f"Movements pull: {err}")

        except Exception as e:
            self.error.emit(str(e))
            _log(f"[EXCEPTION] {e}")

    def stop(self):
        self._running = False
        self.wait(3000)
