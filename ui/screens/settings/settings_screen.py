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
            pull_sales_invoices, pull_warehouses,
            pull_categories, pull_transfers,
            pull_inventory_sessions,
            push_categories,
            drain_sync_queue,
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

        self.progress.emit("Pulling warehouses…")
        n, err = pull_warehouses()
        results.append(f"Warehouses pulled: {n}" + (f" ⚠ {err}" if err else ""))

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
        type_row.addWidget(self._printer_type)
        type_row.addStretch()
        pb_lay.addLayout(type_row)

        # Detail fields
        form = QFormLayout()
        form.setSpacing(6)

        self._pe_host   = QLineEdit(); self._pe_host.setPlaceholderText("192.168.1.100")
        self._pe_port   = QLineEdit("9100"); self._pe_port.setFixedWidth(80)
        self._pe_vid    = QLineEdit(); self._pe_vid.setPlaceholderText("0x04b8")
        self._pe_pid    = QLineEdit(); self._pe_pid.setPlaceholderText("0x0e15")
        self._pe_serial = QLineEdit(); self._pe_serial.setPlaceholderText("/dev/ttyUSB0  or  COM3")
        self._pe_baud   = QLineEdit("9600"); self._pe_baud.setFixedWidth(80)
        self._pe_win    = QLineEdit(); self._pe_win.setPlaceholderText("printer name from Windows")
        self._pe_file   = QLineEdit(); self._pe_file.setPlaceholderText("/dev/usb/lp0")

        form.addRow("IP Address:", self._pe_host)
        form.addRow("Port:", self._pe_port)
        form.addRow("USB Vendor ID:", self._pe_vid)
        form.addRow("USB Product ID:", self._pe_pid)
        form.addRow("Serial device:", self._pe_serial)
        form.addRow("Baud rate:", self._pe_baud)
        form.addRow("Printer name:", self._pe_win)
        form.addRow("File / pipe:", self._pe_file)
        pb_lay.addLayout(form)

        self._printer_detail_rows = [
            ("network",    [self._pe_host, self._pe_port]),
            ("usb_manual", [self._pe_vid,  self._pe_pid]),
            ("serial",     [self._pe_serial, self._pe_baud]),
            ("win_raw",    [self._pe_win]),
            ("file",       [self._pe_file]),
        ]
        # Map each widget to its form row widget (label + field)
        self._all_printer_fields = [
            self._pe_host, self._pe_port,
            self._pe_vid,  self._pe_pid,
            self._pe_serial, self._pe_baud,
            self._pe_win,  self._pe_file,
        ]

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

    # ── Printer config helpers ─────────────────────────────────────────────────

    def _refresh_printer_fields(self):
        ptype = self._printer_type.currentData() or ""
        visible_fields = set()
        for typ, fields in self._printer_detail_rows:
            if typ == ptype:
                visible_fields.update(id(f) for f in fields)
        for f in self._all_printer_fields:
            f.setVisible(id(f) in visible_fields)

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
                session.commit()
                self._printer_status_lbl.setText("✔  Printer config saved.")
                self._printer_status_lbl.setStyleSheet("font-size:11px; color:#2e7d32;")
            finally:
                session.close()
        except Exception as exc:
            self._printer_status_lbl.setText(f"Error: {exc}")
            self._printer_status_lbl.setStyleSheet("font-size:11px; color:#c62828;")

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
