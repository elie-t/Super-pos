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


class SyncWorker(QThread):
    """Background thread that syncs with Supabase."""

    new_orders    = Signal(int)      # new online orders pulled
    sync_done     = Signal(int, int) # (synced, failed)
    items_updated = Signal(int)      # item master data changes pulled
    users_changed = Signal()         # user records added/updated/deactivated
    error         = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False

    def run(self):
        self._running = True
        while self._running:
            self._tick()
            # Sleep in small increments so stop() is responsive
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
            try:
                pull_sales_invoices()
            except Exception:
                pass

            # Pull item master data from Supabase
            try:
                count, _ = pull_master_items()
                if count > 0:
                    self.items_updated.emit(count)
            except Exception:
                pass

            # Pull stock movements from other branches (deducts their sales from local stock)
            try:
                pull_stock_movements()
            except Exception:
                pass

        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._running = False
        self.wait(3000)
