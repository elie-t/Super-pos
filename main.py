"""
SuperPOS — entry point.
"""
import sys
from database.engine import init_db
from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtGui import QKeyEvent


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


def main():
    init_db()

    from PySide6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    app = QApplication(sys.argv)
    _enter_filter = _NumpadEnterFilter(app)
    app.installEventFilter(_enter_filter)
    app.setApplicationName("TannouryMarket")

    window = MainWindow()
    window.showMaximized()
    window.setWindowState(window.windowState() | __import__('PySide6.QtCore', fromlist=['Qt']).Qt.WindowMaximized)

    # Start background sync worker (only if Supabase is configured)
    from sync.service import is_configured
    if is_configured():
        from sync.worker import SyncWorker
        _sync_worker = SyncWorker(app)
        _sync_worker.new_orders.connect(
            lambda n: window.statusBar().showMessage(f"  {n} new online order(s) received!", 8000)
        )
        _sync_worker.sync_done.connect(
            lambda s, f: window.statusBar().showMessage(f"  Sync: {s} pushed" + (f", {f} failed" if f else ""), 5000)
        )
        _sync_worker.error.connect(
            lambda e: window.statusBar().showMessage(f"  ⚠ Sync error: {e}", 10000)
        )
        _sync_worker.invoices_pulled.connect(
            lambda n: window.statusBar().showMessage(f"  ✔ {n} branch invoice(s) synced", 8000)
        )
        _sync_worker.users_changed.connect(window.refresh_login)
        _sync_worker.start()
        app.aboutToQuit.connect(_sync_worker.stop)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
