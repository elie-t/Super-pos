"""
Settings screen — system configuration and sync control.
"""
import uuid as _uuid_mod
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QProgressBar, QSizePolicy,
    QComboBox, QLineEdit, QFormLayout, QListWidget,
    QListWidgetItem, QDialog, QDialogButtonBox, QCheckBox,
    QSpinBox, QScrollArea, QFrame, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QThread


# ── Scale config editor dialog ────────────────────────────────────────────────

class _ScaleConfigDialog(QDialog):
    """Add or edit a single scale configuration."""

    def __init__(self, cfg: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scale Configuration")
        self.setMinimumWidth(380)
        self._cfg = dict(cfg) if cfg else {}
        self._build()
        self._load(self._cfg)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        self._name       = QLineEdit(); self._name.setPlaceholderText("e.g. Scale 1 — Produce")
        self._flag_len   = QSpinBox();  self._flag_len.setRange(1, 4);  self._flag_len.setValue(2)
        self._flag_val   = QLineEdit(); self._flag_val.setPlaceholderText("e.g. 27")
        self._code_len   = QSpinBox();  self._code_len.setRange(1, 6);  self._code_len.setValue(3)
        self._pay_len    = QSpinBox();  self._pay_len.setRange(1, 10);  self._pay_len.setValue(7)
        self._pay_type   = QComboBox(); self._pay_type.addItems(["price", "weight"])
        self._pay_dec    = QSpinBox();  self._pay_dec.setRange(0, 5);   self._pay_dec.setValue(0)
        self._has_chk    = QCheckBox("Scale adds its own checksum digit")
        self._code_pfx   = QLineEdit(); self._code_pfx.setPlaceholderText("e.g. 27  (prepended to PLU for item lookup)")
        self._enabled    = QCheckBox("Enabled");  self._enabled.setChecked(True)

        form.addRow("Name:",              self._name)
        form.addRow("Flag length:",        self._flag_len)
        form.addRow("Flag value:",         self._flag_val)
        form.addRow("Code (PLU) length:",  self._code_len)
        form.addRow("Payload length:",     self._pay_len)
        form.addRow("Payload type:",       self._pay_type)
        form.addRow("Payload decimals:",   self._pay_dec)
        form.addRow("Code prefix (DB):",   self._code_pfx)
        form.addRow("",                    self._has_chk)
        form.addRow("",                    self._enabled)

        lay.addLayout(form)

        # Live preview
        self._preview = QLabel()
        self._preview.setStyleSheet(
            "font-family:monospace; font-size:11px; color:#1a6cb5;"
            "background:#f0f4ff; border-radius:4px; padding:6px;"
        )
        self._preview.setWordWrap(True)
        lay.addWidget(self._preview)

        for w in (self._flag_len, self._code_len, self._pay_len, self._pay_dec, self._pay_type):
            if isinstance(w, QSpinBox):
                w.valueChanged.connect(self._refresh_preview)
            else:
                w.currentIndexChanged.connect(self._refresh_preview)
        self._flag_val.textChanged.connect(self._refresh_preview)
        self._has_chk.toggled.connect(self._refresh_preview)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._refresh_preview()

    def _refresh_preview(self):
        fl = self._flag_len.value()
        cl = self._code_len.value()
        pl = self._pay_len.value()
        ic = 1 if self._has_chk.isChecked() else 0
        total = fl + cl + pl + ic + 1
        pt = self._pay_type.currentText()
        pd = self._pay_dec.value()
        fv = self._flag_val.text() or "?"
        ex_code = "0" * cl
        ex_pay  = "0" * (pl - 1) + "1"   # small sample value
        ex_chk  = "X" * ic
        ex_ean  = "C"
        structure = f"{fv}{'N'*cl}{'P'*pl}{ex_chk}{ex_ean}"
        self._preview.setText(
            f"Structure ({total} digits):  {structure}\n"
            f"  flag({fl}) + PLU({cl}) + {pt}({pl})"
            + (f" + internal_chk(1)" if ic else "")
            + f" + EAN_check(1) = {total}\n"
            f"  Decimal places: {pd}  →  '{ex_pay}' = {int(ex_pay)/(10**pd) if pd else int(ex_pay)}"
        )

    def _load(self, cfg: dict):
        self._name.setText(cfg.get("name", ""))
        self._flag_len.setValue(int(cfg.get("flag_length", 2)))
        self._flag_val.setText(str(cfg.get("flag_value", "27")))
        self._code_len.setValue(int(cfg.get("code_length", 3)))
        self._pay_len.setValue(int(cfg.get("payload_length", 7)))
        idx = self._pay_type.findText(cfg.get("payload_type", "price"))
        if idx >= 0:
            self._pay_type.setCurrentIndex(idx)
        self._pay_dec.setValue(int(cfg.get("payload_decimals", 0)))
        self._has_chk.setChecked(bool(cfg.get("has_internal_checksum", False)))
        self._code_pfx.setText(str(cfg.get("code_prefix", cfg.get("flag_value", "27"))))
        self._enabled.setChecked(bool(cfg.get("enabled", True)))

    def _on_accept(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "Validation", "Name is required.")
            return
        if not self._flag_val.text().strip():
            QMessageBox.warning(self, "Validation", "Flag value is required.")
            return
        self.accept()

    def result_cfg(self) -> dict:
        return {
            "id":                   self._cfg.get("id") or str(_uuid_mod.uuid4())[:8],
            "name":                 self._name.text().strip(),
            "enabled":              self._enabled.isChecked(),
            "flag_length":          self._flag_len.value(),
            "flag_value":           self._flag_val.text().strip(),
            "code_length":          self._code_len.value(),
            "payload_length":       self._pay_len.value(),
            "payload_type":         self._pay_type.currentText(),
            "payload_decimals":     self._pay_dec.value(),
            "has_internal_checksum": self._has_chk.isChecked(),
            "code_prefix":          self._code_pfx.text().strip() or self._flag_val.text().strip(),
        }


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
            pull_sales_invoices, pull_warehouses, push_warehouses,
            pull_categories, pull_transfers,
            pull_inventory_sessions,
            push_categories,
            drain_sync_queue,
            pull_all_stock_levels,
        )
        from sync.push_all import push_all_online_items

        if not is_configured():
            self.finished.emit("Supabase not configured — check .env")
            return

        results = []

        self.progress.emit("Draining local sync queue…")
        synced, failed = drain_sync_queue()
        results.append(f"Queue: {synced} pushed, {failed} failed")

        # Pull items FIRST so stale local UUIDs are deactivated in products
        # before push_all_online_items runs — prevents duplicates on the app.
        from sync.service import _state_set
        _state_set("items_pull", "2000-01-01T00:00:00Z")
        _state_set("items_pull_last_id", "")

        self.progress.emit("Pulling item master data…")
        n, err = pull_master_items()
        results.append(f"Items pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pushing online catalog…")
        ok, fail, errs = push_all_online_items()
        results.append(f"Online catalog: {ok} items")

        self.progress.emit("Pulling customers…")
        n, err = pull_master_customers()
        results.append(f"Customers pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pulling users…")
        n, err = pull_users()
        results.append(f"Users pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pulling stock movements…")
        n, err = pull_stock_movements()
        results.append(f"Stock movements applied: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pulling warehouses…")
        push_warehouses()
        n, err = pull_warehouses()
        results.append(f"Warehouses pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Rebuilding stock levels from movements…")
        n, err = pull_all_stock_levels()
        results.append(f"Stock levels synced: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pulling suppliers…")
        n, err = pull_suppliers()
        results.append(f"Suppliers pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pulling sales invoices…")
        n, err = pull_sales_invoices()
        results.append(f"Sales invoices pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pulling purchase invoices…")
        n, err = pull_purchase_invoices()
        results.append(f"Purchase invoices pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pushing categories…")
        push_categories()

        self.progress.emit("Pulling categories…")
        n, err = pull_categories()
        results.append(f"Categories pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pulling transfers…")
        n, err = pull_transfers()
        results.append(f"Transfers pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.progress.emit("Pulling inventory sessions…")
        n, err = pull_inventory_sessions()
        results.append(f"Inventory sessions pulled: {n}" + (f" ⚠ {err}" if err else ""))

        self.finished.emit("\n".join(results))


class SettingsScreen(QWidget):
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:#fff;}"
            "QScrollBar:vertical{width:8px;background:#f0f4f8;border-radius:4px;}"
            "QScrollBar::handle:vertical{background:#bcd;border-radius:4px;}"
        )
        outer.addWidget(scroll)

        inner = QWidget()
        scroll.setWidget(inner)

        root = QVBoxLayout(inner)
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

        reconcile_btn = QPushButton("🔁  Reconcile Stock")
        reconcile_btn.setFixedHeight(38)
        reconcile_btn.setCursor(Qt.PointingHandCursor)
        reconcile_btn.setEnabled(configured)
        reconcile_btn.setStyleSheet(
            "QPushButton{background:#6a1b9a;color:#fff;border:none;"
            "border-radius:5px;font-size:13px;font-weight:700;padding:0 20px;}"
            "QPushButton:hover{background:#4a148c;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        reconcile_btn.clicked.connect(self._do_reconcile_stock)
        reconcile_btn.setToolTip(
            "Reset the stock-movements pull cursor and re-pull all movements.\n"
            "Use this when stock counts differ between branches."
        )
        btn_row.addWidget(reconcile_btn)
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

        # ── Stock History panel ────────────────────────────────────────────────
        stock_box = QGroupBox("Stock History")
        stock_box.setStyleSheet(
            "QGroupBox { font-weight:700; font-size:13px; padding-top:12px; }"
        )
        stock_lay = QVBoxLayout(stock_box)
        stock_lay.setSpacing(10)

        stock_desc = QLabel(
            "Set a stock start date to wipe all stock movements before that date\n"
            "on ALL branches. Opening balance will show 0 from that date forward.\n"
            "Current stock quantities are NOT affected — only the history is cleared."
        )
        stock_desc.setWordWrap(True)
        stock_desc.setStyleSheet("font-size:11px; color:#555;")
        stock_lay.addWidget(stock_desc)

        date_row = QHBoxLayout()
        date_row.setSpacing(10)
        from PySide6.QtWidgets import QDateEdit as _QDE
        from PySide6.QtCore import QDate as _QD
        date_row.addWidget(QLabel("Clear all movements before:"))
        self._stock_start_date = _QDE()
        self._stock_start_date.setCalendarPopup(True)
        self._stock_start_date.setDate(_QD.currentDate())
        self._stock_start_date.setDisplayFormat("dd/MM/yyyy")
        self._stock_start_date.setFixedHeight(30)
        self._stock_start_date.setFixedWidth(130)
        date_row.addWidget(self._stock_start_date)

        set_start_btn = QPushButton("🗑  Clear History Before This Date")
        set_start_btn.setFixedHeight(34)
        set_start_btn.setCursor(Qt.PointingHandCursor)
        set_start_btn.setStyleSheet(
            "QPushButton{background:#b71c1c;color:#fff;border:none;"
            "border-radius:5px;font-size:12px;font-weight:700;padding:0 16px;}"
            "QPushButton:hover{background:#7f0000;}"
        )
        set_start_btn.clicked.connect(self._do_set_stock_start)
        date_row.addWidget(set_start_btn)
        date_row.addStretch()
        stock_lay.addLayout(date_row)

        self._stock_start_status = QLabel("")
        self._stock_start_status.setStyleSheet("font-size:11px; color:#2e7d32;")
        stock_lay.addWidget(self._stock_start_status)

        root.addWidget(stock_box)

        # ── General / Currency panel ───────────────────────────────────────────
        general_box = QGroupBox("General Settings")
        general_box.setStyleSheet(
            "QGroupBox { font-weight:700; font-size:13px; padding-top:12px; }"
        )
        gen_lay = QVBoxLayout(general_box)
        gen_lay.setSpacing(10)

        gen_form = QFormLayout()
        gen_form.setSpacing(8)
        gen_form.setLabelAlignment(Qt.AlignRight)

        self._lbp_rate = QLineEdit()
        self._lbp_rate.setPlaceholderText("e.g. 89500")
        self._lbp_rate.setFixedWidth(140)
        gen_form.addRow("LBP Rate (LBP per 1 USD):", self._lbp_rate)
        gen_lay.addLayout(gen_form)

        save_gen_btn = QPushButton("💾  Save General Settings")
        save_gen_btn.setFixedHeight(32)
        save_gen_btn.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#fff;border:none;"
            "border-radius:4px;font-size:12px;font-weight:700;padding:0 16px;}"
            "QPushButton:hover{background:#1a6cb5;}"
        )
        save_gen_btn.clicked.connect(self._save_general_settings)
        gen_btn_row = QHBoxLayout()
        gen_btn_row.addWidget(save_gen_btn)
        gen_btn_row.addStretch()
        gen_lay.addLayout(gen_btn_row)

        self._gen_status_lbl = QLabel("")
        self._gen_status_lbl.setStyleSheet("font-size:11px; color:#2e7d32;")
        gen_lay.addWidget(self._gen_status_lbl)

        root.addWidget(general_box)
        self._load_general_settings()

        # ── Receipt Printer panel ──────────────────────────────────────────────
        printer_box = QGroupBox("Receipt Printer (ESC/POS)")
        printer_box.setStyleSheet(
            "QGroupBox { font-weight:700; font-size:13px; padding-top:12px; }"
        )
        pb_lay = QVBoxLayout(printer_box)
        pb_lay.setSpacing(10)

        # Connection type
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Connection:"))
        self._printer_type = QComboBox()
        self._printer_type.setFixedHeight(28)
        self._printer_type.addItem("— Not configured —", "")
        self._printer_type.addItem("USB  (auto-detect)",  "usb_auto")
        self._printer_type.addItem("USB  (manual VID:PID)", "usb_manual")
        self._printer_type.addItem("Network  (TCP/IP)",  "network")
        self._printer_type.addItem("Serial  (COM / ttyUSB)", "serial")
        self._printer_type.addItem("Windows printer name", "win_raw")
        self._printer_type.addItem("File / pipe",          "file")
        self._printer_type.addItem("Windows (system printer)", "windows_qt")
        type_row.addWidget(self._printer_type)
        type_row.addStretch()
        pb_lay.addLayout(type_row)

        # Detail fields
        self._printer_form = QFormLayout()
        self._printer_form.setSpacing(6)

        self._pe_host   = QLineEdit(); self._pe_host.setPlaceholderText("192.168.1.100")
        self._pe_port   = QLineEdit("9100"); self._pe_port.setFixedWidth(80)
        self._pe_vid    = QLineEdit(); self._pe_vid.setPlaceholderText("0x04b8")
        self._pe_pid    = QLineEdit(); self._pe_pid.setPlaceholderText("0x0e15")
        self._pe_serial = QLineEdit(); self._pe_serial.setPlaceholderText("/dev/ttyUSB0  or  COM3")
        self._pe_baud   = QLineEdit("9600"); self._pe_baud.setFixedWidth(80)
        self._pe_win    = QLineEdit(); self._pe_win.setPlaceholderText("printer name from Windows")
        self._pe_file   = QLineEdit(); self._pe_file.setPlaceholderText("/dev/usb/lp0")

        # Windows Qt system printer — combo populated from OS printer list
        from PySide6.QtPrintSupport import QPrinterInfo as _QPrinterInfo
        qt_row_widget = QWidget()
        qt_row_lay = QHBoxLayout(qt_row_widget)
        qt_row_lay.setContentsMargins(0, 0, 0, 0)
        qt_row_lay.setSpacing(6)
        self._pe_qt_printer = QComboBox()
        self._pe_qt_printer.setFixedHeight(26)
        for _info in _QPrinterInfo.availablePrinters():
            self._pe_qt_printer.addItem(_info.printerName())
        qt_row_lay.addWidget(self._pe_qt_printer)
        _refresh_btn = QPushButton("↺")
        _refresh_btn.setFixedSize(26, 26)
        _refresh_btn.setToolTip("Refresh printer list")
        _refresh_btn.clicked.connect(self._refresh_qt_printer_list)
        qt_row_lay.addWidget(_refresh_btn)
        qt_row_lay.addStretch()

        self._printer_form.addRow("IP Address:", self._pe_host)     # row 0
        self._printer_form.addRow("Port:", self._pe_port)           # row 1
        self._printer_form.addRow("USB Vendor ID:", self._pe_vid)   # row 2
        self._printer_form.addRow("USB Product ID:", self._pe_pid)  # row 3
        self._printer_form.addRow("Serial device:", self._pe_serial)# row 4
        self._printer_form.addRow("Baud rate:", self._pe_baud)      # row 5
        self._printer_form.addRow("Printer name:", self._pe_win)    # row 6
        self._printer_form.addRow("File / pipe:", self._pe_file)    # row 7
        self._printer_form.addRow("System printer:", qt_row_widget) # row 8
        pb_lay.addLayout(self._printer_form)

        # (type → list of row indices that should be visible for that type)
        self._printer_type_rows = {
            "network":    {0, 1},
            "usb_auto":   set(),
            "usb_manual": {2, 3},
            "serial":     {4, 5},
            "win_raw":    {6},
            "file":       {7},
            "windows_qt": {8},
        }

        self._printer_type.currentIndexChanged.connect(self._refresh_printer_fields)
        self._refresh_printer_fields()

        # Buttons
        btn_row2 = QHBoxLayout()
        save_printer_btn = QPushButton("💾  Save Printer Config")
        save_printer_btn.setFixedHeight(32)
        save_printer_btn.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#fff;border:none;"
            "border-radius:4px;font-size:12px;font-weight:700;padding:0 16px;}"
            "QPushButton:hover{background:#1a6cb5;}"
        )
        save_printer_btn.clicked.connect(self._save_printer_config)
        btn_row2.addWidget(save_printer_btn)

        test_printer_btn = QPushButton("🖨  Test Print")
        test_printer_btn.setFixedHeight(32)
        test_printer_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;border:none;"
            "border-radius:4px;font-size:12px;font-weight:700;padding:0 16px;}"
            "QPushButton:hover{background:#1b5e20;}"
        )
        test_printer_btn.clicked.connect(self._test_printer)
        btn_row2.addWidget(test_printer_btn)
        btn_row2.addStretch()
        pb_lay.addLayout(btn_row2)

        self._printer_status_lbl = QLabel("")
        self._printer_status_lbl.setStyleSheet("font-size:11px; color:#1a6cb5;")
        pb_lay.addWidget(self._printer_status_lbl)

        root.addWidget(printer_box)
        self._load_printer_config()

        # ── Scale Barcodes panel ───────────────────────────────────────────────
        scale_box = QGroupBox("Scale Barcodes")
        scale_box.setStyleSheet(
            "QGroupBox { font-weight:700; font-size:13px; padding-top:12px; }"
        )
        sb_lay = QVBoxLayout(scale_box)
        sb_lay.setSpacing(8)

        sb_desc = QLabel(
            "Configure how barcodes from pricing scales are decoded.\n"
            "Each scale can have different flag/code/payload lengths."
        )
        sb_desc.setStyleSheet("font-size:11px; color:#444;")
        sb_desc.setWordWrap(True)
        sb_lay.addWidget(sb_desc)

        self._scale_list = QListWidget()
        self._scale_list.setFixedHeight(110)
        self._scale_list.setStyleSheet("font-size:12px;")
        self._scale_list.itemDoubleClicked.connect(self._edit_scale)
        sb_lay.addWidget(self._scale_list)

        sc_btn_row = QHBoxLayout()
        add_sc_btn = QPushButton("➕  Add Scale")
        add_sc_btn.setFixedHeight(30)
        add_sc_btn.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#fff;border:none;"
            "border-radius:4px;font-size:12px;font-weight:700;padding:0 14px;}"
            "QPushButton:hover{background:#1a6cb5;}"
        )
        add_sc_btn.clicked.connect(self._add_scale)
        sc_btn_row.addWidget(add_sc_btn)

        edit_sc_btn = QPushButton("✏️  Edit")
        edit_sc_btn.setFixedHeight(30)
        edit_sc_btn.setStyleSheet(
            "QPushButton{background:#455a64;color:#fff;border:none;"
            "border-radius:4px;font-size:12px;font-weight:700;padding:0 14px;}"
            "QPushButton:hover{background:#607d8b;}"
        )
        edit_sc_btn.clicked.connect(self._edit_scale)
        sc_btn_row.addWidget(edit_sc_btn)

        del_sc_btn = QPushButton("🗑  Delete")
        del_sc_btn.setFixedHeight(30)
        del_sc_btn.setStyleSheet(
            "QPushButton{background:#c62828;color:#fff;border:none;"
            "border-radius:4px;font-size:12px;font-weight:700;padding:0 14px;}"
            "QPushButton:hover{background:#e53935;}"
        )
        del_sc_btn.clicked.connect(self._delete_scale)
        sc_btn_row.addWidget(del_sc_btn)
        sc_btn_row.addStretch()
        sb_lay.addLayout(sc_btn_row)

        self._scale_status = QLabel("")
        self._scale_status.setStyleSheet("font-size:11px; color:#2e7d32;")
        sb_lay.addWidget(self._scale_status)

        root.addWidget(scale_box)
        self._load_scale_list()

        root.addStretch()

        # Back button
        back_btn = QPushButton("← Back")
        back_btn.setObjectName("secondaryBtn")
        back_btn.setFixedWidth(100)
        back_btn.clicked.connect(self.back.emit)
        root.addWidget(back_btn, alignment=Qt.AlignLeft)

    def _load_general_settings(self):
        try:
            from database.engine import get_session, init_db
            from database.models.items import Setting
            init_db()
            session = get_session()
            try:
                s = session.get(Setting, "lbp_rate")
                self._lbp_rate.setText(s.value if s else "")
            finally:
                session.close()
        except Exception:
            pass

    def _save_general_settings(self):
        try:
            from database.engine import get_session, init_db
            from database.models.items import Setting
            init_db()
            session = get_session()
            try:
                val = self._lbp_rate.text().strip()
                s = session.get(Setting, "lbp_rate")
                if s:
                    s.value = val
                else:
                    session.add(Setting(key="lbp_rate", value=val))
                session.commit()
                self._gen_status_lbl.setText("✔  Saved.")
                self._gen_status_lbl.setStyleSheet("font-size:11px; color:#2e7d32;")
            finally:
                session.close()
        except Exception as exc:
            self._gen_status_lbl.setText(f"Error: {exc}")
            self._gen_status_lbl.setStyleSheet("font-size:11px; color:#c62828;")

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

    def _do_set_stock_start(self):
        from PySide6.QtWidgets import QMessageBox
        cutoff_qdate = self._stock_start_date.date()
        cutoff_str   = cutoff_qdate.toString("yyyy-MM-dd")
        cutoff_iso   = f"{cutoff_str}T00:00:00Z"

        ans = QMessageBox.question(
            self, "Clear Stock History",
            f"Delete ALL stock movements before  {cutoff_qdate.toString('dd/MM/yyyy')}  "
            f"from this device AND from Supabase (all branches)?\n\n"
            "Current stock quantities will NOT change.\n"
            "This cannot be undone.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return

        try:
            import requests as _req
            import sqlalchemy as _sa
            from database.engine import get_session, init_db
            from sync.service import _url, _headers, is_configured

            # 1. Delete from local stock_movements
            init_db()
            session = get_session()
            try:
                result = session.execute(
                    _sa.text("DELETE FROM stock_movements WHERE created_at < :cutoff"),
                    {"cutoff": cutoff_iso},
                )
                removed_local = result.rowcount
                # Also clean applied_central_movements for gone movements
                session.execute(_sa.text(
                    "DELETE FROM applied_central_movements "
                    "WHERE movement_id NOT IN (SELECT id FROM stock_movements)"
                ))
                session.commit()
            finally:
                session.close()

            # 2. Delete from Supabase (all branches see the same cut)
            removed_central = 0
            if is_configured():
                r = _req.delete(
                    f"{_url('stock_movements_central')}?created_at=lt.{cutoff_iso}",
                    headers=_headers(), timeout=30,
                )
                removed_central = 0 if r.status_code not in (200, 204) else -1

            msg = (
                f"Cleared {removed_local} local movements before {cutoff_str}.\n"
                f"Supabase central movements also deleted."
                if removed_central != 0 else
                f"Cleared {removed_local} local movements before {cutoff_str}.\n"
                "⚠ Supabase delete may have failed — check connection."
            )
            self._stock_start_status.setText(msg)
            self._stock_start_status.setStyleSheet("font-size:11px; color:#2e7d32;")

        except Exception as e:
            self._stock_start_status.setText(f"Error: {e}")
            self._stock_start_status.setStyleSheet("font-size:11px; color:#c62828;")

    def _do_reconcile_stock(self):
        """Full stock reconcile: clear applied-movements log, reset cursor,
        re-pull all movements from Supabase and re-apply from scratch."""
        from PySide6.QtWidgets import QMessageBox
        ans = QMessageBox.question(
            self, "Reconcile Stock",
            "This will:\n"
            "  1. Clear the applied-movements log\n"
            "  2. Reset the pull cursor to the beginning\n"
            "  3. Re-pull and re-apply ALL stock movements from Supabase\n\n"
            "Use this when stock counts differ between branches.\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        try:
            import sqlalchemy
            from database.engine import get_session, init_db
            from sync.service import _state_set
            init_db()
            session = get_session()
            try:
                # Wipe all local stock movements — sync will rebuild from invoices/transfers
                session.execute(sqlalchemy.text("DELETE FROM stock_movements"))
                session.execute(sqlalchemy.text("DELETE FROM applied_central_movements"))
                session.commit()
            finally:
                session.close()
            _state_set("movements_pull", "2000-01-01T00:00:00Z")
            _state_set("purchase_invoices_pull", "2000-01-01T00:00:00Z")
            _state_set("transfers_pull", "2000-01-01T00:00:00Z")
            self._sync_status.setText(
                "All stock movements cleared. Re-pulling from Supabase now…"
            )
            self._result_lbl.hide()
            self._do_force_sync()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Printer config helpers ─────────────────────────────────────────────────

    def _refresh_printer_fields(self):
        ptype = self._printer_type.currentData() or ""
        visible_rows = self._printer_type_rows.get(ptype, set())
        for row_idx in range(self._printer_form.rowCount()):
            self._printer_form.setRowVisible(row_idx, row_idx in visible_rows)

    def _load_printer_config(self):
        try:
            from database.engine import get_session, init_db
            from database.models.items import Setting
            init_db()
            session = get_session()
            try:
                def _get(key, default=""):
                    s = session.get(Setting, key)
                    return s.value if s else default
                ptype = _get("escpos_type", "")
                for i in range(self._printer_type.count()):
                    if self._printer_type.itemData(i) == ptype:
                        self._printer_type.setCurrentIndex(i)
                        break
                self._pe_host.setText(_get("escpos_host", ""))
                self._pe_port.setText(_get("escpos_port", "9100"))
                self._pe_vid.setText(_get("escpos_usb_vid", ""))
                self._pe_pid.setText(_get("escpos_usb_pid", ""))
                self._pe_serial.setText(_get("escpos_serial", ""))
                self._pe_baud.setText(_get("escpos_baud", "9600"))
                self._pe_win.setText(_get("escpos_win_printer", ""))
                self._pe_file.setText(_get("escpos_file", ""))
                qt_pname = _get("escpos_qt_printer", "")
                if qt_pname:
                    idx = self._pe_qt_printer.findText(qt_pname)
                    if idx >= 0:
                        self._pe_qt_printer.setCurrentIndex(idx)
            finally:
                session.close()
        except Exception:
            pass
        self._refresh_printer_fields()

    def _save_printer_config(self):
        try:
            from database.engine import get_session, init_db
            from database.models.items import Setting
            init_db()
            session = get_session()
            try:
                def _set(key, val):
                    s = session.get(Setting, key)
                    if s:
                        s.value = val
                    else:
                        session.add(Setting(key=key, value=val))
                _set("escpos_type",        self._printer_type.currentData() or "")
                _set("escpos_host",        self._pe_host.text().strip())
                _set("escpos_port",        self._pe_port.text().strip() or "9100")
                _set("escpos_usb_vid",     self._pe_vid.text().strip())
                _set("escpos_usb_pid",     self._pe_pid.text().strip())
                _set("escpos_serial",      self._pe_serial.text().strip())
                _set("escpos_baud",        self._pe_baud.text().strip() or "9600")
                _set("escpos_win_printer", self._pe_win.text().strip())
                _set("escpos_file",        self._pe_file.text().strip())
                _set("escpos_qt_printer",  self._pe_qt_printer.currentText())
                session.commit()
                self._printer_status_lbl.setText("✔  Printer config saved.")
                self._printer_status_lbl.setStyleSheet("font-size:11px; color:#2e7d32;")
            finally:
                session.close()
        except Exception as exc:
            self._printer_status_lbl.setText(f"Error: {exc}")
            self._printer_status_lbl.setStyleSheet("font-size:11px; color:#c62828;")

    def _refresh_qt_printer_list(self):
        from PySide6.QtPrintSupport import QPrinterInfo as _QPrinterInfo
        current = self._pe_qt_printer.currentText()
        self._pe_qt_printer.clear()
        for info in _QPrinterInfo.availablePrinters():
            self._pe_qt_printer.addItem(info.printerName())
        idx = self._pe_qt_printer.findText(current)
        if idx >= 0:
            self._pe_qt_printer.setCurrentIndex(idx)

    def _test_printer(self):
        self._printer_status_lbl.setText("Sending test print…")
        self._printer_status_lbl.setStyleSheet("font-size:11px; color:#1a6cb5;")
        try:
            from utils.receipt_printer import print_transfer_escpos
            ok, err = print_transfer_escpos(
                no="TEST",
                from_wh="Warehouse A",
                to_wh="Warehouse B",
                date_str="2026-01-01",
                lines=[
                    {"name": "Test Item One",  "qty": 5.0,  "total": 0.0},
                    {"name": "Test Item Two",  "qty": 10.0, "total": 0.0},
                ],
                currency="",
            )
            if ok:
                self._printer_status_lbl.setText("✔  Test print sent successfully.")
                self._printer_status_lbl.setStyleSheet("font-size:11px; color:#2e7d32;")
            else:
                self._printer_status_lbl.setText(f"✘  {err}")
                self._printer_status_lbl.setStyleSheet("font-size:11px; color:#c62828;")
        except Exception as exc:
            self._printer_status_lbl.setText(f"✘  {exc}")
            self._printer_status_lbl.setStyleSheet("font-size:11px; color:#c62828;")

    # ── Scale config helpers ───────────────────────────────────────────────────

    def _load_scale_list(self):
        """Refresh the scale list widget from the DB."""
        from utils.scale_barcode import load_scale_configs
        self._scale_list.clear()
        for cfg in load_scale_configs():
            enabled = cfg.get("enabled", True)
            fl = cfg.get("flag_length", 2)
            fv = cfg.get("flag_value", "?")
            cl = cfg.get("code_length", 3)
            pl = cfg.get("payload_length", 7)
            pt = cfg.get("payload_type", "price")
            label = (
                f"{'✔' if enabled else '✘'}  {cfg['name']}  "
                f"│  flag={fv}({fl})  PLU({cl})  {pt}({pl})"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, cfg)
            if not enabled:
                item.setForeground(Qt.gray)
            self._scale_list.addItem(item)

    def _add_scale(self):
        dlg = _ScaleConfigDialog(parent=self)
        if dlg.exec():
            from utils.scale_barcode import load_scale_configs, save_scale_configs
            configs = load_scale_configs()
            configs.append(dlg.result_cfg())
            save_scale_configs(configs)
            self._load_scale_list()
            self._scale_status.setText("✔  Scale configuration saved.")

    def _edit_scale(self):
        item = self._scale_list.currentItem()
        if not item:
            return
        cfg = item.data(Qt.UserRole)
        dlg = _ScaleConfigDialog(cfg=cfg, parent=self)
        if dlg.exec():
            from utils.scale_barcode import load_scale_configs, save_scale_configs
            configs = load_scale_configs()
            new_cfg = dlg.result_cfg()
            for i, c in enumerate(configs):
                if c.get("id") == cfg.get("id"):
                    configs[i] = new_cfg
                    break
            save_scale_configs(configs)
            self._load_scale_list()
            self._scale_status.setText("✔  Scale configuration updated.")

    def _delete_scale(self):
        item = self._scale_list.currentItem()
        if not item:
            return
        cfg = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "Delete Scale",
            f"Delete scale configuration '{cfg.get('name')}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        from utils.scale_barcode import load_scale_configs, save_scale_configs
        configs = [c for c in load_scale_configs() if c.get("id") != cfg.get("id")]
        save_scale_configs(configs)
        self._load_scale_list()
        self._scale_status.setText("Scale configuration deleted.")
