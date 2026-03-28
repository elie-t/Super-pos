"""
Settings screen — system configuration and sync control.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QProgressBar, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QThread


class _SyncAllWorker(QThread):
    """Runs full push+pull in background so UI stays responsive."""
    progress = Signal(str)   # status message
    finished = Signal(str)   # final summary

    def run(self):
        from sync.service import (
            is_configured,
            push_stock_movements_for_invoice,
            pull_master_items, pull_master_customers,
            pull_stock_movements, pull_users,
            pull_purchase_invoices, pull_suppliers,
            pull_sales_invoices, drain_sync_queue,
        )
        from sync.push_all import push_all_online_items

        if not is_configured():
            self.finished.emit("Supabase not configured — check .env")
            return

        results = []

        self.progress.emit("Draining local sync queue…")
        synced, failed = drain_sync_queue()
        results.append(f"Queue: {synced} pushed, {failed} failed")

        self.progress.emit("Pushing online catalog…")
        ok, fail, errs = push_all_online_items()
        results.append(f"Online catalog: {ok} items")

        self.progress.emit("Pulling item master data…")
        n, err = pull_master_items()
        results.append(f"Items pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pulling customers…")
        n, err = pull_master_customers()
        results.append(f"Customers pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pulling users…")
        n, err = pull_users()
        results.append(f"Users pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pulling stock movements…")
        n, err = pull_stock_movements()
        results.append(f"Stock movements applied: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pulling suppliers…")
        n, err = pull_suppliers()
        results.append(f"Suppliers pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pulling sales invoices…")
        n, err = pull_sales_invoices()
        results.append(f"Sales invoices pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pulling purchase invoices…")
        n, err = pull_purchase_invoices()
        results.append(f"Purchase invoices pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.finished.emit("\n".join(results))


class SettingsScreen(QWidget):
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 30, 40, 30)
        root.setSpacing(24)

        # Title
        title = QLabel("⚙️  Settings")
        title.setStyleSheet("font-size:22px; font-weight:700; color:#1a3a5c;")
        root.addWidget(title)

        # ── Sync panel ────────────────────────────────────────────────────────
        from sync.service import is_configured, BRANCH_ID
        sync_box = QGroupBox("Multi-Branch Sync")
        sync_box.setStyleSheet(
            "QGroupBox { font-weight:700; font-size:13px; padding-top:12px; }"
        )
        sync_layout = QVBoxLayout(sync_box)
        sync_layout.setSpacing(12)

        # Branch info
        branch_lbl = QLabel(f"This branch ID:  {BRANCH_ID}")
        branch_lbl.setStyleSheet("font-size:11px; color:#555; font-family:monospace;")
        sync_layout.addWidget(branch_lbl)

        configured = is_configured()
        status_lbl = QLabel(
            "✔  Supabase connected" if configured else "✘  Supabase not configured — check .env"
        )
        status_lbl.setStyleSheet(
            f"font-size:12px; font-weight:600; color:{'#2e7d32' if configured else '#c62828'};"
        )
        sync_layout.addWidget(status_lbl)

        sync_layout.addSpacing(4)

        # Description
        desc = QLabel(
            "Force sync pushes all local changes to Supabase and pulls the latest\n"
            "items, prices, users, customers and stock movements from all branches."
        )
        desc.setStyleSheet("font-size:11px; color:#444;")
        desc.setWordWrap(True)
        sync_layout.addWidget(desc)

        # Progress bar + status
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)   # indeterminate
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.hide()
        sync_layout.addWidget(self._progress_bar)

        self._sync_status = QLabel("")
        self._sync_status.setStyleSheet("font-size:11px; color:#1a6cb5;")
        self._sync_status.setWordWrap(True)
        sync_layout.addWidget(self._sync_status)

        # Buttons row
        btn_row = QHBoxLayout()

        self._sync_btn = QPushButton("🔄  Force Push / Pull Now")
        self._sync_btn.setFixedHeight(38)
        self._sync_btn.setCursor(Qt.PointingHandCursor)
        self._sync_btn.setEnabled(configured)
        self._sync_btn.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#fff;border:none;"
            "border-radius:5px;font-size:13px;font-weight:700;padding:0 20px;}"
            "QPushButton:hover{background:#1a6cb5;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self._sync_btn.clicked.connect(self._do_force_sync)
        btn_row.addWidget(self._sync_btn)
        btn_row.addStretch()
        sync_layout.addLayout(btn_row)

        # Result area
        self._result_lbl = QLabel("")
        self._result_lbl.setStyleSheet(
            "font-size:11px; color:#2e7d32; font-family:monospace; "
            "background:#f0f8f0; border-radius:4px; padding:8px;"
        )
        self._result_lbl.setWordWrap(True)
        self._result_lbl.hide()
        sync_layout.addWidget(self._result_lbl)

        root.addWidget(sync_box)
        root.addStretch()

        # Back button
        back_btn = QPushButton("← Back")
        back_btn.setObjectName("secondaryBtn")
        back_btn.setFixedWidth(100)
        back_btn.clicked.connect(self.back.emit)
        root.addWidget(back_btn, alignment=Qt.AlignLeft)

    def _do_force_sync(self):
        self._sync_btn.setEnabled(False)
        self._sync_btn.setText("Syncing…")
        self._progress_bar.show()
        self._result_lbl.hide()
        self._sync_status.setText("Starting sync…")

        self._worker = _SyncAllWorker(self)
        self._worker.progress.connect(self._sync_status.setText)
        self._worker.finished.connect(self._on_sync_done)
        self._worker.start()

    def _on_sync_done(self, summary: str):
        self._progress_bar.hide()
        self._sync_btn.setEnabled(True)
        self._sync_btn.setText("🔄  Force Push / Pull Now")
        self._sync_status.setText("Sync complete.")
        self._result_lbl.setText(summary)
        self._result_lbl.show()

        # Refresh login screen if users were pulled
        try:
            top = self.window()
            if hasattr(top, "refresh_login"):
                top.refresh_login()
        except Exception:
            pass
