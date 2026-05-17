"""
SuperPOS — entry point.
"""
import sys
from database.engine import init_db
from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtGui import QKeyEvent


def _disable_windows_touch_keyboard():
    """
    Disable the Windows touch keyboard auto-invoke via registry.
    Safe no-op on non-Windows platforms or if registry access fails.
    """
    try:
        import winreg
        key_path = r"SOFTWARE\Microsoft\TabletTip\1.7"
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path,
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "EnableDesktopModeAutoInvoke", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
    except Exception:
        pass


class _NumpadEnterFilter(QObject):
    """Maps numpad Enter (Key_Enter) → regular Enter (Key_Return) app-wide."""
    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.KeyPress and
                event.key() == Qt.Key.Key_Enter):
            new_event = QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_Return,
                event.modifiers(),
                event.text(),
            )
            from PySide6.QtWidgets import QApplication
            QApplication.sendEvent(obj, new_event)
            return True
        return False


class _VirtualKBSuppressor(QObject):
    """
    Block the Windows touch keyboard from opening on non-text widgets.

    Intercepts RequestSoftwareInputPanel (the event that triggers the VKB)
    and consumes it for anything that isn't a real text input.
    Also hides the input method on FocusIn as a secondary guard.
    """
    _TEXT_TYPES = None

    @staticmethod
    def _text_types():
        if _VirtualKBSuppressor._TEXT_TYPES is None:
            from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit
            _VirtualKBSuppressor._TEXT_TYPES = (QLineEdit, QTextEdit, QPlainTextEdit)
        return _VirtualKBSuppressor._TEXT_TYPES

    def eventFilter(self, obj, event):
        et = event.type()
        # Block virtual keyboard request for non-text widgets
        if et == QEvent.Type.RequestSoftwareInputPanel:
            if not isinstance(obj, self._text_types()):
                return True  # consume — keyboard must not open
        # Also hide on focus change as belt-and-suspenders
        if et == QEvent.Type.FocusIn:
            if not isinstance(obj, self._text_types()):
                from PySide6.QtGui import QGuiApplication
                QGuiApplication.inputMethod().hide()
        return False


def main():
    import logging, os
    _log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(_log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.FileHandler(
            os.path.join(_log_dir, "superpos.log"), encoding="utf-8"
        )],
    )
    _disable_windows_touch_keyboard()
    init_db()

    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    _enter_filter = _NumpadEnterFilter(app)
    app.installEventFilter(_enter_filter)
    _kb_suppressor = _VirtualKBSuppressor(app)
    app.installEventFilter(_kb_suppressor)
    app.setApplicationName("TannouryMarket")

    window = MainWindow()
    window.showMaximized()
    window.setWindowState(window.windowState() | __import__('PySide6.QtCore', fromlist=['Qt']).Qt.WindowMaximized)

    # Background sync (only if Supabase is configured)
    from sync.service import is_configured
    if is_configured():
        # ── Hourly item/price pull ────────────────────────────────────────────
        from sync.worker import SyncWorker
        _sync_worker = SyncWorker(app)
        def _on_sync_done(s, f):
            if f:
                window.statusBar().showMessage(f"  ⚠ Sync: {s} pushed, {f} failed", 10000)
            # suppress silent success — no message when everything is clean
        _sync_worker.sync_done.connect(_on_sync_done)
        _sync_worker.items_updated.connect(
            lambda n: window.statusBar().showMessage(f"  ✔ {n} item(s) updated from main", 6000)
        )
        _sync_worker.invoices_received.connect(
            lambda n: window.statusBar().showMessage(
                f"  ⬇ {n} new shift invoice{'s' if n != 1 else ''} received from branches", 8000)
        )
        _sync_worker.error.connect(
            lambda e: window.statusBar().showMessage(f"  ⚠ Sync error: {e}", 10000)
        )
        _sync_worker.start()
        app.aboutToQuit.connect(_sync_worker.stop)

        # ── Instant order notifications via Supabase Realtime ─────────────────
        try:
            from sync.order_watcher import OrderWatcher
            import threading

            _order_watcher = OrderWatcher(app)

            def _on_new_order():
                """Pull the new order in a background thread, then notify."""
                def _pull():
                    from sync.service import pull_new_orders
                    count, _ = pull_new_orders()
                    if count > 0:
                        window.statusBar().showMessage(
                            f"  🛒 {count} new online order(s) received!", 10000)
                threading.Thread(target=_pull, daemon=True).start()

            _order_watcher.new_order.connect(_on_new_order)
            _order_watcher.start()
            app.aboutToQuit.connect(_order_watcher.stop)
        except Exception:
            pass   # QtWebSockets not available — orders still pulled at shift-end

        # ── Instant price update notifications via Supabase Realtime ──────────
        try:
            from sync.price_watcher import PriceWatcher

            _price_watcher = PriceWatcher(app)
            _price_watcher.prices_changed.connect(_sync_worker.trigger_items_pull)
            _sync_worker.prices_refreshed.connect(
                lambda n: window.statusBar().showMessage(
                    f"  💰 Prices updated ({n} item(s) refreshed)", 8000)
            )
            _price_watcher.start()
            app.aboutToQuit.connect(_price_watcher.stop)
        except Exception:
            pass   # QtWebSockets not available — prices still pulled hourly

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
