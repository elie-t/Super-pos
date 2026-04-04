"""
Inventory Count screen — physical stock count / inventory invoice.

Layout:
  top bar    → dark blue, session #, Back
  setup row  → Warehouse combo, Date
  entry bar  → Barcode/Code, description, Box, Pcs, System Stock, Diff, Add
  table      → # | Code | Barcode | Name | System Qty | Counted Qty | Diff | Cost | ✏ | ✕
  info bar   → dark blue: item name | system stock | last cost
  footer     → Save (green) | Lock/Unlock | New | History | Notes
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QLineEdit, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDoubleSpinBox, QSpinBox, QDateEdit, QMessageBox,
    QDialog, QSplitter,
)
from PySide6.QtCore import Qt, Signal, QDate, QTimer
from PySide6.QtGui import QColor

from services.inventory_session_service import InventorySessionService
from services.auth_service import AuthService


class InventorySessionScreen(QWidget):
    back = Signal()

    COL_NUM     = 0
    COL_CODE    = 1
    COL_BC      = 2
    COL_NAME    = 3
    COL_SYS     = 4
    COL_CNT     = 5
    COL_DIFF    = 6
    COL_COST    = 7
    COL_EDIT    = 8
    COL_DEL     = 9

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines: list[dict] = []
        self._wh_id    = ""
        self._wh_name  = ""
        self._session_id: str | None = None
        self._current_item = None
        self._current_pack_qty = 1
        self._editing_row = -1
        self._table_updating = False
        self._build_ui()
        self._load_warehouses()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._make_top_bar())
        root.addWidget(self._make_setup_row())
        root.addWidget(self._make_entry_bar())
        root.addWidget(self._make_table(), stretch=1)
        root.addWidget(self._make_info_bar())
        root.addWidget(self._make_summary_bar())
        root.addWidget(self._make_footer())

    # ─ top bar ────────────────────────────────────────────────────────────────

    def _make_top_bar(self):
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background:#1a3a5c;")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(12)

        back_btn = QPushButton("←  Back")
        back_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.15);color:#fff;"
            "border:1px solid rgba(255,255,255,0.3);border-radius:4px;"
            "padding:4px 12px;font-size:12px;}"
            "QPushButton:hover{background:rgba(255,255,255,0.3);}"
        )
        back_btn.setFixedHeight(28)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.back.emit)
        lay.addWidget(back_btn)

        title = QLabel("Inventory Count")
        title.setStyleSheet("color:#fff;font-size:16px;font-weight:700;margin-left:12px;")
        lay.addWidget(title)
        lay.addStretch()

        no_lbl = QLabel("Session #")
        no_lbl.setStyleSheet("color:#a8c8e8;font-size:12px;")
        lay.addWidget(no_lbl)

        self._no_input = QLineEdit()
        self._no_input.setFixedHeight(28)
        self._no_input.setFixedWidth(130)
        self._no_input.setStyleSheet(
            "background:rgba(255,255,255,0.1);color:#fff;"
            "border:1px solid rgba(255,255,255,0.3);border-radius:4px;"
            "padding:0 8px;font-size:13px;font-weight:700;"
        )
        lay.addWidget(self._no_input)
        return bar

    # ─ setup row ──────────────────────────────────────────────────────────────

    def _make_setup_row(self):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:#f0f4f8;border-bottom:1px solid #cdd5e0;}"
            "QLabel{color:#1a1a2e;}"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(8)

        lay.addWidget(self._lbl("Warehouse:"))
        self._wh_combo = QComboBox()
        self._wh_combo.setFixedHeight(30)
        self._wh_combo.setMinimumWidth(180)
        self._wh_combo.currentIndexChanged.connect(self._on_wh_changed)
        lay.addWidget(self._wh_combo)

        lay.addSpacing(20)
        lay.addWidget(self._lbl("Date:"))
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setFixedHeight(30)
        self._date_edit.setFixedWidth(120)
        lay.addWidget(self._date_edit)

        lay.addStretch()
        return frame

    # ─ entry bar ──────────────────────────────────────────────────────────────

    def _make_entry_bar(self):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:#e8f0fb;border-bottom:2px solid #1a6cb5;}"
            "QLabel{color:#1a1a2e;}"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(6)

        bc_lbl = QLabel("Barcode / Code:")
        bc_lbl.setStyleSheet("font-weight:600;")
        lay.addWidget(bc_lbl)
        self._bc_input = QLineEdit()
        self._bc_input.setPlaceholderText("Scan or type…")
        self._bc_input.setFixedHeight(32)
        self._bc_input.setMinimumWidth(160)
        self._bc_input.setStyleSheet("font-size:13px;font-weight:600;")
        self._bc_input.returnPressed.connect(self._on_barcode_entered)
        lay.addWidget(self._bc_input)

        self._item_desc_label = QLabel("")
        self._item_desc_label.setStyleSheet(
            "color:#1a3a5c;font-weight:600;min-width:180px;font-size:12px;"
        )
        lay.addWidget(self._item_desc_label)

        lay.addSpacing(6)

        # Box spinner (disabled when pack_qty == 1)
        self._box_lbl = QLabel("Box:")
        self._box_lbl.setStyleSheet("font-weight:600;color:#1a3a5c;font-size:12px;")
        lay.addWidget(self._box_lbl)
        self._box_spin = QSpinBox()
        self._box_spin.setRange(0, 99999)
        self._box_spin.setFixedHeight(32)
        self._box_spin.setFixedWidth(70)
        self._box_spin.valueChanged.connect(self._on_box_changed)
        self._box_spin.installEventFilter(self)
        lay.addWidget(self._box_spin)

        self._pcs_lbl = QLabel("Pcs:")
        self._pcs_lbl.setStyleSheet("font-weight:600;color:#1a3a5c;font-size:12px;")
        lay.addWidget(self._pcs_lbl)
        self._pcs_spin = QDoubleSpinBox()
        self._pcs_spin.setRange(0, 999999)
        self._pcs_spin.setDecimals(3)
        self._pcs_spin.setFixedHeight(32)
        self._pcs_spin.setFixedWidth(90)
        self._pcs_spin.valueChanged.connect(self._on_pcs_changed)
        self._pcs_spin.installEventFilter(self)
        lay.addWidget(self._pcs_spin)

        lay.addSpacing(8)

        sys_lbl = QLabel("System:")
        sys_lbl.setStyleSheet("font-weight:600;color:#607d8b;font-size:12px;")
        lay.addWidget(sys_lbl)
        self._sys_qty_lbl = QLabel("—")
        self._sys_qty_lbl.setStyleSheet(
            "font-weight:700;color:#1a3a5c;font-size:13px;min-width:60px;"
        )
        lay.addWidget(self._sys_qty_lbl)

        diff_lbl = QLabel("Diff:")
        diff_lbl.setStyleSheet("font-weight:600;color:#607d8b;font-size:12px;")
        lay.addWidget(diff_lbl)
        self._diff_lbl = QLabel("—")
        self._diff_lbl.setStyleSheet(
            "font-weight:700;font-size:13px;min-width:60px;color:#607d8b;"
        )
        lay.addWidget(self._diff_lbl)

        self._add_btn = QPushButton("✓  Add")
        self._add_btn.setObjectName("primaryBtn")
        self._add_btn.setFixedHeight(32)
        self._add_btn.setFixedWidth(90)
        self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.clicked.connect(self._add_line)
        lay.addWidget(self._add_btn)

        self._cancel_edit_btn = QPushButton("✕  Cancel")
        self._cancel_edit_btn.setStyleSheet(
            "QPushButton{background:#757575;color:#fff;border:none;border-radius:4px;"
            "padding:4px 10px;font-size:12px;}"
            "QPushButton:hover{background:#424242;}"
        )
        self._cancel_edit_btn.setFixedHeight(32)
        self._cancel_edit_btn.setFixedWidth(90)
        self._cancel_edit_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_edit_btn.clicked.connect(self._cancel_edit)
        self._cancel_edit_btn.hide()
        lay.addWidget(self._cancel_edit_btn)

        self._set_box_enabled(1)
        return frame

    # ─ table ──────────────────────────────────────────────────────────────────

    def _make_table(self):
        self._table = QTableWidget()
        self._table.setColumnCount(10)
        self._table.setHorizontalHeaderLabels([
            "#", "Code", "Barcode", "Name",
            "System Qty", "Counted Qty", "Diff", "Cost",
            "", "",
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        self._table.itemSelectionChanged.connect(self._on_row_selected)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(self.COL_NAME, QHeaderView.Stretch)
        for col in (self.COL_NUM, self.COL_CODE, self.COL_BC):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        for col, w in (
            (self.COL_SYS, 90), (self.COL_CNT, 90), (self.COL_DIFF, 80), (self.COL_COST, 90),
        ):
            hdr.setSectionResizeMode(col, QHeaderView.Fixed)
            self._table.setColumnWidth(col, w)
        for col in (self.COL_EDIT, self.COL_DEL):
            hdr.setSectionResizeMode(col, QHeaderView.Fixed)
            self._table.setColumnWidth(col, 28)
        self._table.verticalHeader().setDefaultSectionSize(34)
        hdr.setStyleSheet(
            "QHeaderView::section{background:#1a3a5c;color:#fff;"
            "font-weight:700;border:none;padding:4px;}"
        )
        return self._table

    # ─ info bar ───────────────────────────────────────────────────────────────

    def _make_info_bar(self):
        frame = QFrame()
        frame.setFixedHeight(36)
        frame.setStyleSheet(
            "background:#1a3a5c;"
            "border-top:1px solid #0d2238;border-bottom:1px solid #0d2238;"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(0)

        def _lbl(text, bold=False, min_w=0, color="#cfe0f5"):
            l = QLabel(text)
            s = f"color:{color};font-size:12px;"
            if bold:
                s += "font-weight:700;"
            if min_w:
                s += f"min-width:{min_w}px;"
            l.setStyleSheet(s)
            return l

        lay.addWidget(_lbl("Item:", bold=True))
        self._info_name = _lbl("—", min_w=200, color="#ffffff")
        self._info_name.setStyleSheet(
            "color:#ffffff;font-size:12px;font-weight:700;min-width:200px;"
        )
        lay.addWidget(self._info_name)

        lay.addWidget(_lbl("   │  "))
        self._info_stock = _lbl("System Stock: —", color="#90caf9")
        self._info_stock.setStyleSheet(
            "color:#90caf9;font-size:12px;font-weight:700;min-width:140px;"
        )
        lay.addWidget(self._info_stock)

        lay.addWidget(_lbl("   │  "))
        self._info_cost = _lbl("—", min_w=100, color="#ef9a9a")
        lay.addWidget(self._info_cost)

        lay.addStretch()
        return frame

    # ─ summary bar ────────────────────────────────────────────────────────────

    def _make_summary_bar(self):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:#f0f4f8;border-top:1px solid #cdd5e0;}"
            "QLabel{color:#1a1a2e;}"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(16, 6, 16, 6)
        lay.setSpacing(24)

        def stat(label):
            l = QLabel(label)
            l.setStyleSheet("color:#555;font-size:12px;")
            v = QLabel("0")
            v.setStyleSheet("font-weight:700;font-size:13px;color:#1a3a5c;min-width:60px;")
            lay.addWidget(l)
            lay.addWidget(v)
            return v

        self._lines_lbl   = stat("Lines:")
        self._adj_in_lbl  = stat("Adj In:")
        self._adj_out_lbl = stat("Adj Out:")
        lay.addStretch()
        return frame

    # ─ footer ─────────────────────────────────────────────────────────────────

    def _make_footer(self):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:#e8f0fb;border-top:2px solid #1a6cb5;}"
            "QLabel{color:#1a1a2e;}"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        self._save_btn = QPushButton("💾  Save")
        self._save_btn.setFixedHeight(38)
        self._save_btn.setMinimumWidth(140)
        self._save_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;font-size:14px;font-weight:700;"
            "border-radius:4px;border:none;}"
            "QPushButton:hover{background:#1b5e20;}"
        )
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.clicked.connect(self._save_session)
        lay.addWidget(self._save_btn)

        self._lock_btn = QPushButton("🔒  Lock")
        self._lock_btn.setFixedHeight(38)
        self._lock_btn.setMinimumWidth(100)
        self._lock_btn.setStyleSheet(
            "QPushButton{background:#f57c00;color:#fff;border:none;"
            "border-radius:4px;font-size:13px;font-weight:600;padding:0 16px;}"
            "QPushButton:hover{background:#e65100;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self._lock_btn.setCursor(Qt.PointingHandCursor)
        self._lock_btn.setEnabled(False)
        self._lock_btn.clicked.connect(self._toggle_lock)
        lay.addWidget(self._lock_btn)

        new_btn = QPushButton("✚  New")
        new_btn.setFixedHeight(38)
        new_btn.setStyleSheet(
            "QPushButton{background:#1565c0;color:#fff;border:none;"
            "border-radius:4px;font-size:13px;font-weight:600;padding:0 16px;}"
            "QPushButton:hover{background:#0d47a1;}"
        )
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.clicked.connect(self._clear_all)
        lay.addWidget(new_btn)

        history_btn = QPushButton("History")
        history_btn.setFixedHeight(38)
        history_btn.setStyleSheet(
            "QPushButton{background:#455a64;color:#fff;border:none;"
            "border-radius:4px;font-size:13px;font-weight:600;padding:0 16px;}"
            "QPushButton:hover{background:#263238;}"
        )
        history_btn.clicked.connect(self._open_history)
        lay.addWidget(history_btn)

        self._delete_btn = QPushButton("🗑  Delete")
        self._delete_btn.setFixedHeight(38)
        self._delete_btn.setStyleSheet(
            "QPushButton{background:#c62828;color:#fff;border:none;"
            "border-radius:4px;font-size:13px;font-weight:600;padding:0 16px;}"
            "QPushButton:hover{background:#b71c1c;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self._delete_btn.setCursor(Qt.PointingHandCursor)
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._delete_session)
        lay.addWidget(self._delete_btn)

        collector_btn = QPushButton("📥  Fill from Data Collector")
        collector_btn.setFixedHeight(38)
        collector_btn.setStyleSheet(
            "QPushButton{background:#5c35a0;color:#fff;border:none;"
            "border-radius:4px;font-size:13px;font-weight:600;padding:0 12px;}"
            "QPushButton:hover{background:#4527a0;}"
        )
        collector_btn.setCursor(Qt.PointingHandCursor)
        collector_btn.clicked.connect(self._fill_from_collector)
        lay.addWidget(collector_btn)

        lay.addStretch()

        lay.addWidget(self._lbl("Notes:"))
        self._notes_input = QLineEdit()
        self._notes_input.setFixedHeight(30)
        self._notes_input.setMinimumWidth(200)
        lay.addWidget(self._notes_input)

        return frame

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _lbl(text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet("font-weight:600;color:#1a3a5c;font-size:12px;")
        return l

    def _set_box_enabled(self, pack_qty: int):
        enabled = pack_qty > 1
        self._box_spin.setEnabled(enabled)
        self._box_lbl.setStyleSheet(
            "font-weight:600;color:#1a3a5c;font-size:12px;" if enabled
            else "font-weight:600;color:#aaa;font-size:12px;"
        )
        self._pcs_lbl.setText(f"Pcs ({pack_qty}):" if enabled else "Pcs:")

    # ── Warehouses ────────────────────────────────────────────────────────────

    def _load_warehouses(self):
        from services.transfer_service import TransferService
        warehouses = TransferService.get_warehouses()   # (id, name, number)
        self._wh_combo.blockSignals(True)
        self._wh_combo.clear()
        for wh_id, wh_name, wh_num in warehouses:
            self._wh_combo.addItem(wh_name, (wh_id, wh_name))
        self._wh_combo.blockSignals(False)
        if warehouses:
            self._on_wh_changed()

    def _on_wh_changed(self):
        data = self._wh_combo.currentData()
        self._wh_id   = data[0] if data else ""
        self._wh_name = data[1] if data else ""
        self._refresh_session_number()
        # Refresh system stock column
        for line in self._lines:
            line["system_qty"] = self._get_current_stock(line["item_id"])
        if self._lines:
            self._refresh_table()

    def _refresh_session_number(self):
        if not self._session_id and self._wh_id:
            no = InventorySessionService.next_session_number(self._wh_id)
            self._no_input.setText(no)

    def _get_current_stock(self, item_id: str) -> float:
        from services.transfer_service import TransferService
        return TransferService.get_item_stock(item_id, self._wh_id)

    # ── Barcode / item lookup ─────────────────────────────────────────────────

    def _on_barcode_entered(self):
        query = self._bc_input.text().strip()
        if not query:
            return
        from services.purchase_service import PurchaseService
        item = (
            PurchaseService.lookup_item(query, "barcode")
            or PurchaseService.lookup_item(query, "code")
            or PurchaseService.lookup_item(query, "name")
        )
        if not item:
            self._item_desc_label.setText("⚠ Not found")
            self._item_desc_label.setStyleSheet("color:#c62828;font-weight:600;font-size:12px;")
            return

        # Duplicate check
        for idx, line in enumerate(self._lines):
            if line["item_id"] == item.item_id and idx != self._editing_row:
                ans = QMessageBox.question(
                    self, "Item Already Listed",
                    f"This item is already in line #{idx + 1}.\n\nAdd another line anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if ans != QMessageBox.Yes:
                    self._bc_input.clear()
                    self._bc_input.setFocus()
                    return
                break

        self._current_item = item
        self._current_pack_qty = item.pack_qty

        # Get current system stock for selected warehouse
        sys_qty = self._get_current_stock(item.item_id)

        self._item_desc_label.setText(item.description[:36])
        self._item_desc_label.setStyleSheet("color:#1a3a5c;font-weight:600;font-size:12px;")
        self._sys_qty_lbl.setText(f"{sys_qty:,.3f}")

        self._box_spin.blockSignals(True)
        self._box_spin.setValue(0)
        self._box_spin.blockSignals(False)
        self._pcs_spin.setValue(0.0 if item.pack_qty > 1 else 1.0)
        self._diff_lbl.setText("—")
        self._diff_lbl.setStyleSheet("font-weight:700;font-size:13px;min-width:60px;color:#607d8b;")

        # Info bar
        self._info_name.setText(item.description[:60])
        self._info_stock.setText(f"System Stock: {sys_qty:,.3f}")
        self._info_cost.setText(f"Last Cost: {getattr(item, 'last_cost', 0):,.4f}")

        self._set_box_enabled(item.pack_qty)
        if item.pack_qty > 1:
            QTimer.singleShot(0, lambda: (self._box_spin.setFocus(), self._box_spin.selectAll()))
        else:
            QTimer.singleShot(0, lambda: (self._pcs_spin.setFocus(), self._pcs_spin.selectAll()))

    def _on_box_changed(self, val: int):
        if self._current_pack_qty > 1:
            self._pcs_spin.blockSignals(True)
            self._pcs_spin.setValue(val * self._current_pack_qty)
            self._pcs_spin.blockSignals(False)
        self._update_diff_label()

    def _on_pcs_changed(self, _val):
        self._update_diff_label()

    def _update_diff_label(self):
        if not self._current_item:
            return
        try:
            sys_qty = float(self._sys_qty_lbl.text().replace(",", ""))
        except ValueError:
            return
        counted = self._pcs_spin.value()
        diff = counted - sys_qty
        if diff > 0:
            color = "#2e7d32"
            text = f"+{diff:,.3f}"
        elif diff < 0:
            color = "#c62828"
            text = f"{diff:,.3f}"
        else:
            color = "#607d8b"
            text = "0.000"
        self._diff_lbl.setText(text)
        self._diff_lbl.setStyleSheet(
            f"font-weight:700;font-size:13px;min-width:60px;color:{color};"
        )

    # ── Add / edit line ───────────────────────────────────────────────────────

    def _add_line(self):
        if not self._current_item:
            self._bc_input.setFocus()
            return
        if not self._wh_id:
            QMessageBox.warning(self, "Warehouse", "Please select a warehouse.")
            return
        counted_qty = self._pcs_spin.value()
        if counted_qty < 0:
            QMessageBox.warning(self, "Quantity", "Quantity cannot be negative.")
            return

        item = self._current_item
        try:
            sys_qty = float(self._sys_qty_lbl.text().replace(",", ""))
        except ValueError:
            sys_qty = self._get_current_stock(item.item_id)

        diff = counted_qty - sys_qty
        last_cost = getattr(item, "last_cost", 0.0)

        line = {
            "item_id":     item.item_id,
            "code":        item.code,
            "barcode":     item.barcode,
            "item_name":   item.description,
            "system_qty":  sys_qty,
            "counted_qty": counted_qty,
            "diff_qty":    diff,
            "unit_cost":   last_cost,
        }

        if self._editing_row >= 0:
            self._lines[self._editing_row] = line
        else:
            self._lines.append(line)

        self._refresh_table()
        self._refresh_summary()
        self._clear_entry()

    def _load_line_to_entry(self, row: int):
        if row < 0 or row >= len(self._lines):
            return
        self._editing_row = row
        line = self._lines[row]

        from services.purchase_service import PurchaseService
        item = (
            PurchaseService.lookup_item(line["barcode"], "barcode")
            or PurchaseService.lookup_item(line["code"], "code")
        )
        self._current_item = item
        self._current_pack_qty = item.pack_qty if item else 1

        self._bc_input.setText(line["barcode"] or line["code"])
        self._item_desc_label.setText(line["item_name"][:36])
        self._item_desc_label.setStyleSheet("color:#1a3a5c;font-weight:600;font-size:12px;")

        sys_qty = line["system_qty"]
        self._sys_qty_lbl.setText(f"{sys_qty:,.3f}")

        self._box_spin.blockSignals(True)
        self._box_spin.setValue(0)
        self._box_spin.blockSignals(False)
        self._pcs_spin.setValue(line["counted_qty"])

        self._set_box_enabled(self._current_pack_qty)

        self._add_btn.setText("✓  Update")
        self._add_btn.setStyleSheet(
            "QPushButton{background:#e65100;color:#fff;font-size:13px;font-weight:700;"
            "border:none;border-radius:4px;}"
            "QPushButton:hover{background:#bf360c;}"
        )
        self._cancel_edit_btn.show()
        self._pcs_spin.setFocus()
        self._pcs_spin.selectAll()

    def _cancel_edit(self):
        self._editing_row = -1
        self._clear_entry()

    def _clear_entry(self):
        self._current_item = None
        self._current_pack_qty = 1
        self._editing_row = -1
        self._bc_input.clear()
        self._item_desc_label.setText("")
        self._sys_qty_lbl.setText("—")
        self._diff_lbl.setText("—")
        self._diff_lbl.setStyleSheet(
            "font-weight:700;font-size:13px;min-width:60px;color:#607d8b;"
        )
        self._box_spin.blockSignals(True)
        self._box_spin.setValue(0)
        self._box_spin.blockSignals(False)
        self._pcs_spin.setValue(0)
        self._set_box_enabled(1)
        self._add_btn.setText("✓  Add")
        self._add_btn.setStyleSheet("")
        self._add_btn.setObjectName("primaryBtn")
        self._add_btn.style().unpolish(self._add_btn)
        self._add_btn.style().polish(self._add_btn)
        self._cancel_edit_btn.hide()
        self._bc_input.setFocus()

    # ── Table ─────────────────────────────────────────────────────────────────

    def _refresh_table(self):
        self._table_updating = True
        self._table.setRowCount(0)
        self._table.setRowCount(len(self._lines))

        for row, line in enumerate(self._lines):
            diff = line["diff_qty"]
            if diff > 0:
                diff_color = "#2e7d32"
                diff_text  = f"+{diff:,.3f}"
            elif diff < 0:
                diff_color = "#c62828"
                diff_text  = f"{diff:,.3f}"
            else:
                diff_color = "#607d8b"
                diff_text  = "0.000"

            cells = [
                (str(row + 1),                       Qt.AlignCenter,                  False),
                (line["code"],                       Qt.AlignLeft | Qt.AlignVCenter,  False),
                (line["barcode"],                    Qt.AlignLeft | Qt.AlignVCenter,  False),
                (line["item_name"],                  Qt.AlignLeft | Qt.AlignVCenter,  False),
                (f"{line['system_qty']:,.3f}",       Qt.AlignRight | Qt.AlignVCenter, False),
                (f"{line['counted_qty']:,.3f}",      Qt.AlignRight | Qt.AlignVCenter, False),
                (diff_text,                          Qt.AlignRight | Qt.AlignVCenter, False),
                (f"{line['unit_cost']:,.4f}",        Qt.AlignRight | Qt.AlignVCenter, False),
            ]
            for col, (val, align, _editable) in enumerate(cells):
                cell = QTableWidgetItem(val)
                cell.setTextAlignment(align)
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                if col == self.COL_DIFF:
                    cell.setForeground(QColor(diff_color))
                    if diff < 0:
                        cell.setBackground(QColor("#ffebee"))
                    elif diff > 0:
                        cell.setBackground(QColor("#e8f5e9"))
                self._table.setItem(row, col, cell)

            # Edit button
            edit_btn = QPushButton("✏")
            edit_btn.setToolTip("Edit line")
            edit_btn.setStyleSheet(
                "QPushButton{background:#e65100;color:#fff;border:none;border-radius:3px;}"
                "QPushButton:hover{background:#bf360c;}"
            )
            edit_btn.setFixedSize(24, 24)
            edit_btn.setCursor(Qt.PointingHandCursor)
            edit_btn.clicked.connect(lambda _, r=row: self._load_line_to_entry(r))
            self._table.setCellWidget(row, self.COL_EDIT, edit_btn)

            # Delete button
            del_btn = QPushButton("✕")
            del_btn.setToolTip("Remove line")
            del_btn.setStyleSheet(
                "QPushButton{background:#c62828;color:#fff;border:none;border-radius:3px;}"
                "QPushButton:hover{background:#8b0000;}"
            )
            del_btn.setFixedSize(24, 24)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.clicked.connect(lambda _, r=row: self._delete_line(r))
            self._table.setCellWidget(row, self.COL_DEL, del_btn)

        self._table_updating = False

    def _on_row_selected(self):
        if self._table_updating:
            return
        row = self._table.currentRow()
        if row < 0 or row >= len(self._lines):
            return
        line = self._lines[row]
        self._info_name.setText(line["item_name"][:60])
        sys_qty = line["system_qty"]
        self._info_stock.setText(f"System Stock: {sys_qty:,.3f}")
        self._info_cost.setText(f"Last Cost: {line['unit_cost']:,.4f}")

    def _delete_line(self, row: int):
        if 0 <= row < len(self._lines):
            self._lines.pop(row)
            self._refresh_table()
            self._refresh_summary()

    # ── Summary ───────────────────────────────────────────────────────────────

    def _refresh_summary(self):
        adj_in  = sum(l["diff_qty"] for l in self._lines if l["diff_qty"] > 0)
        adj_out = sum(l["diff_qty"] for l in self._lines if l["diff_qty"] < 0)
        self._lines_lbl.setText(str(len(self._lines)))
        self._adj_in_lbl.setText(f"+{adj_in:,.3f}")
        self._adj_out_lbl.setText(f"{adj_out:,.3f}")

    # ── eventFilter — Enter key navigation ────────────────────────────────────

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if obj is self._box_spin:
                    self._pcs_spin.setFocus()
                    self._pcs_spin.selectAll()
                    return True
                if obj is self._pcs_spin:
                    self._add_line()
                    return True
        return super().eventFilter(obj, event)

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save_session(self):
        if not self._lines and not self._session_id:
            QMessageBox.warning(self, "Empty", "No items to save.")
            return
        if not self._wh_id:
            QMessageBox.warning(self, "Warehouse", "Please select a warehouse.")
            return

        user  = AuthService.current_user()
        op_id = user.id if user else ""
        no    = self._no_input.text().strip()

        ok, result = InventorySessionService.save_session(
            session_id=self._session_id or "",
            warehouse_id=self._wh_id,
            operator_id=op_id,
            session_date=self._date_edit.date().toString("yyyy-MM-dd"),
            notes=self._notes_input.text().strip(),
            lines=[{
                "item_id":     l["item_id"],
                "item_name":   l["item_name"],
                "system_qty":  l["system_qty"],
                "counted_qty": l["counted_qty"],
                "unit_cost":   l["unit_cost"],
            } for l in self._lines],
            session_number=no,
        )

        if not ok:
            QMessageBox.critical(self, "Error", f"Save failed:\n{result}")
            return

        self._session_id = result
        self._lock_btn.setEnabled(True)
        self._lock_btn.setText("🔒  Lock")
        self._delete_btn.setEnabled(True)

        n = len(self._lines)
        QMessageBox.information(
            self, "Saved",
            f"Inventory session {no} saved — {n} item(s).\n"
            f"Stock adjustments applied."
        )

    # ── Lock / Unlock ─────────────────────────────────────────────────────────

    def _toggle_lock(self):
        if not self._session_id:
            return
        detail = InventorySessionService.get_session_detail(self._session_id)
        if not detail:
            return
        if detail["status"] == "locked":
            ok, msg = InventorySessionService.unlock_session(self._session_id)
            if ok:
                self._lock_btn.setText("🔒  Lock")
                self._set_locked(False)
            else:
                QMessageBox.critical(self, "Error", msg)
        else:
            ok, msg = InventorySessionService.lock_session(self._session_id)
            if ok:
                self._lock_btn.setText("🔓  Unlock")
                self._set_locked(True)
            else:
                QMessageBox.critical(self, "Error", msg)

    def _set_locked(self, locked: bool):
        self._save_btn.setEnabled(not locked)
        self._wh_combo.setEnabled(not locked)
        self._date_edit.setEnabled(not locked)
        self._bc_input.setEnabled(not locked)
        self._notes_input.setEnabled(not locked)

    # ── New / Clear ───────────────────────────────────────────────────────────

    def _clear_all(self):
        self._session_id = None
        self._lock_btn.setEnabled(False)
        self._lock_btn.setText("🔒  Lock")
        self._delete_btn.setEnabled(False)
        self._set_locked(False)
        self._lines.clear()
        self._refresh_table()
        self._refresh_summary()
        self._clear_entry()
        self._notes_input.clear()
        self._refresh_session_number()

    # ── Data collector import ──────────────────────────────────────────────────

    def _fill_from_collector(self):
        if not self._wh_id:
            QMessageBox.warning(self, "Warehouse", "Please select a warehouse first.")
            return
        from ui.widgets.data_collector_dialog import DataCollectorDialog
        dlg = DataCollectorDialog(self)
        if not dlg.exec():
            return
        added = skipped = 0
        for row in dlg.rows:
            item = row["item"]
            if not item:
                skipped += 1
                continue
            qty = row["qty"]
            sys_qty = self._get_current_stock(item.item_id)
            # Merge if already in list
            for line in self._lines:
                if line["item_id"] == item.item_id:
                    line["counted_qty"] += qty
                    line["diff_qty"] = line["counted_qty"] - line["system_qty"]
                    added += 1
                    break
            else:
                self._lines.append({
                    "item_id":     item.item_id,
                    "code":        item.code,
                    "barcode":     item.barcode,
                    "item_name":   item.description,
                    "system_qty":  sys_qty,
                    "counted_qty": qty,
                    "diff_qty":    qty - sys_qty,
                    "unit_cost":   getattr(item, "last_cost", 0.0),
                })
                added += 1
        self._refresh_table()
        self._refresh_summary()
        QMessageBox.information(
            self, "Imported",
            f"Imported {added} item(s)." +
            (f"\n{skipped} barcode(s) not found — skipped." if skipped else "")
        )

    # ── Delete ────────────────────────────────────────────────────────────────

    def _delete_session(self):
        if not self._session_id:
            return
        no = self._no_input.text().strip() or self._session_id[:8]
        ans = QMessageBox.question(
            self, "Delete Inventory Session",
            f"Delete inventory session {no}?\n\n"
            "All stock adjustments will be reversed and the session\n"
            "will be removed from all branches.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        from services.inventory_session_service import InventorySessionService
        ok, msg = InventorySessionService.delete_session(self._session_id)
        if not ok:
            QMessageBox.critical(self, "Error", f"Delete failed:\n{msg}")
            return
        QMessageBox.information(self, "Deleted", f"Session {no} deleted.")
        self._clear_all()

    # ── History ───────────────────────────────────────────────────────────────

    def _open_history(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Inventory Count History")
        dlg.resize(1100, 620)
        root = QVBoxLayout(dlg)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: sessions list ───────────────────────────────────────────────
        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(4)
        llay.addWidget(QLabel("All Sessions:"))

        list_tbl = QTableWidget()
        list_tbl.setColumnCount(5)
        list_tbl.setHorizontalHeaderLabels(["#", "Date", "Warehouse", "Items", "Status"])
        list_tbl.setAlternatingRowColors(True)
        list_tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        list_tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        list_tbl.verticalHeader().setVisible(False)
        list_tbl.setStyleSheet(
            "QHeaderView::section{background:#1a3a5c;color:#fff;"
            "font-weight:700;border:none;padding:5px;}"
        )
        lhdr = list_tbl.horizontalHeader()
        for i, m in enumerate([
            QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
            QHeaderView.Stretch,
            QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
        ]):
            lhdr.setSectionResizeMode(i, m)
        llay.addWidget(list_tbl)

        # ── Right: detail ─────────────────────────────────────────────────────
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(4)

        detail_header = QLabel("Select a session to view details")
        detail_header.setStyleSheet("font-weight:700;font-size:13px;color:#1a3a5c;")
        rlay.addWidget(detail_header)

        detail_tbl = QTableWidget()
        detail_tbl.setColumnCount(6)
        detail_tbl.setHorizontalHeaderLabels([
            "Code", "Name", "Barcode", "System Qty", "Counted Qty", "Diff"
        ])
        detail_tbl.setAlternatingRowColors(True)
        detail_tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        detail_tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        detail_tbl.verticalHeader().setVisible(False)
        detail_tbl.setStyleSheet(
            "QHeaderView::section{background:#37474f;color:#fff;"
            "font-weight:700;border:none;padding:5px;}"
        )
        dhdr = detail_tbl.horizontalHeader()
        dhdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in (0, 2, 3, 4, 5):
            dhdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        rlay.addWidget(detail_tbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        load_btn = QPushButton("✏  Open")
        load_btn.setStyleSheet(
            "QPushButton{background:#1565c0;color:#fff;font-size:12px;font-weight:700;"
            "border:none;border-radius:4px;padding:6px 16px;}"
            "QPushButton:hover{background:#0d47a1;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        load_btn.setEnabled(False)
        load_btn.setCursor(Qt.PointingHandCursor)
        btn_row.addWidget(load_btn)

        notes_lbl = QLabel("")
        notes_lbl.setStyleSheet("color:#555;font-size:11px;font-style:italic;")
        btn_row.addWidget(notes_lbl)
        btn_row.addStretch()
        rlay.addLayout(btn_row)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([380, 680])
        root.addWidget(splitter)

        # ── Populate list ─────────────────────────────────────────────────────
        session_rows = InventorySessionService.list_sessions(limit=500)
        list_tbl.setRowCount(len(session_rows))
        for r, d in enumerate(session_rows):
            for c, val in enumerate([
                d["number"], d["date"], d["warehouse"],
                str(d["item_count"]), d["status"],
            ]):
                it = QTableWidgetItem(val)
                it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                if c == 4:
                    it.setForeground(
                        QColor("#607d8b") if d["status"] == "locked"
                        else QColor("#2e7d32")
                    )
                list_tbl.setItem(r, c, it)

        # ── Row selection ─────────────────────────────────────────────────────
        def on_row_selected():
            sel = list_tbl.selectedItems()
            if not sel:
                return
            row = list_tbl.currentRow()
            if row < 0 or row >= len(session_rows):
                return
            d = session_rows[row]
            detail = InventorySessionService.get_session_detail(d["id"])
            if not detail:
                return

            status = detail["status"]
            detail_header.setText(
                f"Session {detail['number']}  ·  {detail['warehouse']}"
                f"  ·  {detail['date']}  ·  [{status.upper()}]"
            )
            notes_lbl.setText(f"Notes: {detail['notes']}" if detail.get("notes") else "")

            lines = detail["lines"]
            detail_tbl.setRowCount(len(lines))
            for r2, li in enumerate(lines):
                diff = li["diff_qty"]
                diff_text = (f"+{diff:,.3f}" if diff > 0 else f"{diff:,.3f}"
                             if diff < 0 else "0.000")
                for c2, val in enumerate([
                    li["code"], li["item_name"], li["barcode"],
                    f"{li['system_qty']:,.3f}", f"{li['counted_qty']:,.3f}", diff_text,
                ]):
                    it2 = QTableWidgetItem(str(val))
                    it2.setTextAlignment(
                        Qt.AlignRight | Qt.AlignVCenter if c2 in (3, 4, 5)
                        else Qt.AlignLeft | Qt.AlignVCenter
                    )
                    if c2 == 5:
                        it2.setForeground(
                            QColor("#2e7d32") if diff > 0
                            else QColor("#c62828") if diff < 0
                            else QColor("#607d8b")
                        )
                    detail_tbl.setItem(r2, c2, it2)

            load_btn.setEnabled(True)
            load_btn.setProperty("session_detail", detail)

        list_tbl.itemSelectionChanged.connect(on_row_selected)
        list_tbl.doubleClicked.connect(lambda _: on_row_selected())

        # ── Load for edit ──────────────────────────────────────────────────────
        def on_load():
            detail = load_btn.property("session_detail")
            if not detail:
                return
            dlg.accept()
            self._load_session(detail)

        load_btn.clicked.connect(on_load)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            "QPushButton{background:#607d8b;color:#fff;font-size:12px;font-weight:700;"
            "border:none;border-radius:4px;padding:6px 16px;}"
            "QPushButton:hover{background:#455a64;}"
        )
        close_btn.clicked.connect(dlg.accept)
        root.addWidget(close_btn, 0, Qt.AlignRight)

        dlg.exec()

    def _load_session(self, detail: dict):
        """Load an existing session into the screen."""
        self._clear_all()
        self._session_id = detail["id"]
        self._lock_btn.setEnabled(True)
        self._delete_btn.setEnabled(True)
        locked = detail["status"] == "locked"
        self._lock_btn.setText("🔓  Unlock" if locked else "🔒  Lock")
        self._set_locked(locked)

        # Set warehouse
        for i in range(self._wh_combo.count()):
            if self._wh_combo.itemData(i)[0] == detail["warehouse_id"]:
                self._wh_combo.setCurrentIndex(i)
                break

        self._no_input.setText(detail["number"])
        self._notes_input.setText(detail.get("notes", ""))

        # Set date
        if detail.get("date"):
            self._date_edit.setDate(QDate.fromString(detail["date"], "yyyy-MM-dd"))

        # Load lines
        for li in detail["lines"]:
            self._lines.append({
                "item_id":     li["item_id"],
                "code":        li["code"],
                "barcode":     li["barcode"],
                "item_name":   li["item_name"],
                "system_qty":  li["system_qty"],
                "counted_qty": li["counted_qty"],
                "diff_qty":    li["diff_qty"],
                "unit_cost":   li["unit_cost"],
            })

        self._refresh_table()
        self._refresh_summary()
