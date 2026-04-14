"""
Sync Worker — runs in a background QThread.

Responsibilities:
  - Pull item/price master data from Supabase once per hour (SYNC_INTERVAL_SEC)
  - Drain the local sync_queue when explicitly triggered (shift-end)

Online order notifications are handled separately by OrderWatcher (websocket).
Sales invoice push happens at shift-end via trigger_drain().
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from config import SYNC_INTERVAL_SEC


_instance: "SyncWorker | None" = None


def get_sync_worker() -> "SyncWorker | None":
    return _instance


class SyncWorker(QThread):
    """Background thread: hourly item pull + on-demand queue drain."""

    sync_done       = Signal(int, int)  # (synced, failed) — after drain
    items_updated   = Signal(int)       # item master data changes pulled
    users_changed   = Signal()          # user records added/updated/deactivated
    error           = Signal(str)

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

    # ── Thread main loop ──────────────────────────────────────────────────────

    def run(self):
        self._running    = True
        ticks_since_pull = SYNC_INTERVAL_SEC  # pull immediately on first start

        while self._running:
            # Drain if requested (shift-end push)
            if self._drain_pending:
                self._drain_pending = False
                self._do_drain()

            # Hourly item pull
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
