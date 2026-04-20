"""
Sync Worker — runs in a background QThread.

Responsibilities:
  - Pull item/price master data from Supabase once per hour (SYNC_INTERVAL_SEC)
  - Pull sales invoices from other branches every 15 minutes (INVOICE_PULL_SEC)
  - Drain the local sync_queue when explicitly triggered (shift-end)
  - Also pull invoices immediately after a drain (catches same-day shifts)

Online order notifications are handled separately by OrderWatcher (websocket).
Sales invoice push happens at shift-end via trigger_drain().
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from config import SYNC_INTERVAL_SEC

INVOICE_PULL_SEC = 900   # pull other branches' invoices every 15 minutes
DRAIN_INTERVAL_SEC = 600  # push queued changes (prices, items) every 10 minutes

_instance: "SyncWorker | None" = None


def get_sync_worker() -> "SyncWorker | None":
    return _instance


class SyncWorker(QThread):
    """Background thread: hourly item pull + 15-min invoice pull + on-demand drain."""

    sync_done          = Signal(int, int)  # (synced, failed) — after drain
    items_updated      = Signal(int)       # item master data changes pulled
    invoices_received  = Signal(int)       # new invoices pulled from other branches
    users_changed      = Signal()          # user records added/updated/deactivated
    prices_refreshed   = Signal(int)       # emitted after a remote-triggered price pull
    error              = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running       = False
        self._drain_pending = False
        global _instance
        _instance = self

    # ── Public API ────────────────────────────────────────────────────────────

    def trigger_drain(self):
        """
        Request a sync_queue drain on the next loop iteration.
        Call this after end-of-shift to push pending invoices/movements.
        """
        self._drain_pending = True

    def trigger_items_pull(self):
        """
        Pull item/price master data immediately (called by PriceWatcher on
        remote price change).  Runs in a plain daemon thread so it never
        blocks the Qt main thread or the SyncWorker loop.
        """
        import threading

        def _pull():
            from sync.service import pull_master_items, is_configured
            if not is_configured():
                return
            try:
                count, _ = pull_master_items()
                if count > 0:
                    self.prices_refreshed.emit(count)
            except Exception:
                pass

        threading.Thread(target=_pull, daemon=True).start()

    # ── Thread main loop ──────────────────────────────────────────────────────

    def run(self):
        self._running         = True
        ticks_since_pull      = SYNC_INTERVAL_SEC   # pull items immediately on first start
        ticks_since_inv_pull  = INVOICE_PULL_SEC     # pull invoices immediately on first start
        ticks_since_drain     = DRAIN_INTERVAL_SEC   # drain queue immediately on first start

        while self._running:
            # Drain if requested (shift-end push), then pull invoices right after
            if self._drain_pending:
                self._drain_pending = False
                self._do_drain()
                self._do_invoice_pull()          # pick up other branches' shifts immediately
                ticks_since_inv_pull = 0
                ticks_since_drain    = 0

            # 10-minute periodic drain — pushes price/item changes without waiting for shift-end
            ticks_since_drain += 1
            if ticks_since_drain >= DRAIN_INTERVAL_SEC:
                ticks_since_drain = 0
                self._do_drain()

            # 15-minute invoice pull from other branches
            ticks_since_inv_pull += 1
            if ticks_since_inv_pull >= INVOICE_PULL_SEC:
                ticks_since_inv_pull = 0
                self._do_invoice_pull()

            # Hourly item/price master pull
            ticks_since_pull += 1
            if ticks_since_pull >= SYNC_INTERVAL_SEC:
                ticks_since_pull = 0
                self._do_items_pull()

            # Sleep in 1-second increments so stop()/trigger_drain() are responsive
            for _ in range(10):
                if not self._running:
                    break
                if self._drain_pending:
                    break
                self.msleep(100)

    # ── Internal operations ───────────────────────────────────────────────────

    def _do_drain(self):
        """Push all pending sync_queue rows to Supabase."""
        from sync.service import drain_sync_queue, is_configured
        if not is_configured():
            return
        try:
            synced, failed = drain_sync_queue()
            self.sync_done.emit(synced, failed)
        except Exception as e:
            self.error.emit(str(e))

    def _do_invoice_pull(self):
        """Pull sales invoices from other branches (runs every 15 min + after drain)."""
        from sync.service import pull_sales_invoices, is_configured
        if not is_configured():
            return
        try:
            from datetime import datetime as _dt
            from pathlib import Path as _Path
            _log_path = _Path(__file__).parent.parent / "data" / "sync.log"

            pulled, err = pull_sales_invoices()
            if err:
                self.error.emit(f"Invoice pull: {err}")
                try:
                    with open(_log_path, "a") as f:
                        f.write(f"{_dt.now().strftime('%Y-%m-%d %H:%M:%S')} [ERROR] invoice pull: {err}\n")
                except Exception:
                    pass
            elif pulled > 0:
                self.invoices_received.emit(pulled)
                try:
                    with open(_log_path, "a") as f:
                        f.write(f"{_dt.now().strftime('%Y-%m-%d %H:%M:%S')} [INFO] invoice pull: {pulled} new invoice(s)\n")
                except Exception:
                    pass
        except Exception as e:
            self.error.emit(str(e))

    def _do_items_pull(self):
        """Pull item master data + user changes from Supabase."""
        from sync.service import pull_master_items, is_configured
        if not is_configured():
            return
        try:
            from datetime import datetime as _dt
            from pathlib import Path as _Path
            _log_path = _Path(__file__).parent.parent / "data" / "sync.log"

            count, err = pull_master_items()
            if err:
                self.error.emit(f"Items pull: {err}")
                try:
                    with open(_log_path, "a") as f:
                        f.write(f"{_dt.now().strftime('%Y-%m-%d %H:%M:%S')} [ERROR] items pull: {err}\n")
                except Exception:
                    pass
            elif count > 0:
                self.items_updated.emit(count)
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._running = False
        self.wait(3000)
