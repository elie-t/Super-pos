"""
Warehouse Transfer — invoice-style screen for moving stock between warehouses.

Layout mirrors Purchase Invoice:
  top bar   → dark blue, editable transfer #, Back btn
  setup row → From warehouse, To warehouse, Date, Price Type, Currency
  entry bar → Barcode, item desc, Qty, Price, Disc%, Total, Add / Cancel
  table     → # | Code | BC | Name | Qty | Price | Disc% | Total | From Stock | To Stock | ✏ | H | ✕
  info bar  → dark blue: item name | From wh stock | To wh stock | prices
  totals    → Lines, Sub-Total, Discount, Grand Total
  footer    → Confirm Transfer, Clear All, History, Notes
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QLineEdit, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QDoubleSpinBox, QSpinBox, QDateEdit, QMessageBox, QDialog,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QDate, QTimer
from PySide6.QtGui import QColor

from services.transfer_service import TransferService
from services.auth_service import AuthService


# ── Post-confirm dialog ────────────────────────────────────────────────────────

class PostTransferDialog(QDialog):
    def __init__(self, transfer_no: str, line_count: int, total: float,
                 currency: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Transfer Confirmed")
        self.setFixedSize(500, 165)
        self.choice = None   # "done" | "print" | "new"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(18)

        msg = QLabel(
            f"✓  Transfer  <b>{transfer_no}</b>  confirmed — "
            f"{line_count} lines · Total: <b>{total:,.2f} {currency}</b>"
        )
        msg.setStyleSheet("font-size:14px; color:#1a3a5c;")
        msg.setAlignment(Qt.AlignCenter)
        lay.addWidget(msg)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        for label, bg, hover, key in [
            ("✓  Done",    "#607d8b", "#455a64", "done"),
            ("🖨  Print",  "#1a6cb5", "#1a3a5c", "print"),
            ("✚  New",    "#2e7d32", "#1b5e20", "new"),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(44)
            btn.setStyleSheet(
                f"QPushButton{{background:{bg};color:#fff;font-size:13px;font-weight:700;"
                f"border:none;border-radius:6px;}}"
                f"QPushButton:hover{{background:{hover};}}"
            )
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=key: self._pick(k))
            btn_row.addWidget(btn)
        lay.addLayout(btn_row)

    def _pick(self, choice: str):
        self.choice = choice
        self.accept()


# ── Main screen ───────────────────────────────────────────────────────────────

class WarehouseTransferScreen(QWidget):
    back = Signal()

    COL_NUM  = 0
    COL_CODE = 1
    COL_BC   = 2
    COL_NAME = 3
    COL_QTY  = 4
    COL_PRC  = 5
    COL_DSC  = 6
    COL_TOT  = 7
    COL_SRC  = 8
    COL_DST  = 9
    COL_EDIT = 10
    COL_HIST = 11
    COL_DEL  = 12

    _EDITABLE_COLS = {4, 5, 6, 7}   # qty, price, disc, total

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines: list[dict] = []
        self._from_wh_id   = ""
        self._to_wh_id     = ""
        self._from_wh_name = ""
        self._to_wh_name   = ""
        self._transfer_no  = ""
        self._current_transfer_id = None   # None = new, str = editing existing
        self._current_item    = None   # PurchaseLineItem from purchase_service
        self._current_pack_qty = 1
        self._editing_row  = -1
        self._table_updating  = False
        self._total_editing   = False
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
        root.addWidget(self._make_totals_bar())
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

        title = QLabel("Warehouse Transfer")
        title.setStyleSheet("color:#fff;font-size:16px;font-weight:700;margin-left:12px;")
        lay.addWidget(title)
        lay.addStretch()

        no_lbl = QLabel("Transfer #")
        no_lbl.setStyleSheet("color:#a8c8e8;font-size:12px;")
        lay.addWidget(no_lbl)

        self._no_input = QLineEdit()
        self._no_input.setFixedHeight(28)
        self._no_input.setFixedWidth(120)
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

        lay.addWidget(self._lbl("From:"))
        self._from_combo = QComboBox()
        self._from_combo.setFixedHeight(30)
        self._from_combo.setMinimumWidth(160)
        self._from_combo.currentIndexChanged.connect(self._on_from_changed)
        lay.addWidget(self._from_combo)

        arrow = QLabel("→")
        arrow.setStyleSheet("font-size:16px;font-weight:700;color:#1a3a5c;")
        lay.addWidget(arrow)

        lay.addWidget(self._lbl("To:"))
        self._to_combo = QComboBox()
        self._to_combo.setFixedHeight(30)
        self._to_combo.setMinimumWidth(160)
        self._to_combo.currentIndexChanged.connect(self._on_to_changed)
        lay.addWidget(self._to_combo)

        lay.addSpacing(16)
        lay.addWidget(self._lbl("Date:"))
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setFixedHeight(30)
        self._date_edit.setFixedWidth(120)
        lay.addWidget(self._date_edit)

        lay.addStretch()

        lay.addWidget(self._lbl("Price:"))
        self._price_type_combo = QComboBox()
        self._price_type_combo.setFixedHeight(30)
        self._price_type_combo.setMinimumWidth(120)
        self._price_type_combo.addItem("Cost Price",  "cost")
        self._price_type_combo.addItem("Retail",       "retail")
        self._price_type_combo.addItem("Wholesale",    "wholesale")
        self._price_type_combo.addItem("Semi-W/Sale",  "semi_wholesale")
        lay.addWidget(self._price_type_combo)

        lay.addSpacing(8)
        lay.addWidget(self._lbl("Currency:"))
        self._cur_combo = QComboBox()
        self._cur_combo.setFixedHeight(30)
        self._cur_combo.addItems(["USD", "LBP"])
        lay.addWidget(self._cur_combo)
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

        # Box (always visible; disabled when pack_qty == 1)
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
        self._qty_spin = QDoubleSpinBox()
        self._qty_spin.setRange(0, 999999)
        self._qty_spin.setDecimals(3)
        self._qty_spin.setFixedHeight(32)
        self._qty_spin.setFixedWidth(80)
        self._qty_spin.installEventFilter(self)
        lay.addWidget(self._qty_spin)

        lay.addWidget(self._lbl("Price:"))
        self._price_spin = QDoubleSpinBox()
        self._price_spin.setRange(0, 999999999)
        self._price_spin.setDecimals(4)
        self._price_spin.setFixedHeight(32)
        self._price_spin.setFixedWidth(100)
        self._price_spin.installEventFilter(self)
        lay.addWidget(self._price_spin)

        lay.addWidget(self._lbl("Disc%:"))
        self._disc_spin = QDoubleSpinBox()
        self._disc_spin.setRange(0, 100)
        self._disc_spin.setDecimals(2)
        self._disc_spin.setFixedHeight(32)
        self._disc_spin.setFixedWidth(70)
        self._disc_spin.installEventFilter(self)
        lay.addWidget(self._disc_spin)

        tot_lbl = QLabel("Total:")
        tot_lbl.setStyleSheet("font-weight:700;color:#1a3a5c;")
        lay.addWidget(tot_lbl)
        self._total_spin = QDoubleSpinBox()
        self._total_spin.setRange(0, 999999999)
        self._total_spin.setDecimals(2)
        self._total_spin.setFixedHeight(32)
        self._total_spin.setFixedWidth(110)
        self._total_spin.setStyleSheet("font-weight:700;font-size:13px;")
        self._total_spin.installEventFilter(self)
        self._total_spin.valueChanged.connect(self._on_total_changed)
        lay.addWidget(self._total_spin)

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
        self._table.setColumnCount(13)
        self._table.setHorizontalHeaderLabels([
            "#", "Code", "Barcode", "Name",
            "Qty", "Price", "Disc%", "Total",
            "From Stock", "To Stock",
            "", "H", "",
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked
        )
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        self._table.itemChanged.connect(self._on_cell_edited)
        self._table.itemSelectionChanged.connect(self._on_row_selected)
        self._table_updating = False
        self._table.setStyleSheet(
            "QTableWidget QLineEdit{"
            "  color:#1a3a5c;background:#ffffff;"
            "  border:2px solid #1a6cb5;"
            "  font-size:14px;font-weight:700;"
            "  min-height:28px;padding:0 4px;"
            "}"
        )
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(self.COL_NAME, QHeaderView.Stretch)
        for col in (self.COL_NUM, self.COL_CODE, self.COL_BC):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        for col, w in (
            (self.COL_QTY, 72), (self.COL_PRC, 92), (self.COL_DSC, 58),
            (self.COL_TOT, 90), (self.COL_SRC, 82), (self.COL_DST, 82),
        ):
            hdr.setSectionResizeMode(col, QHeaderView.Fixed)
            self._table.setColumnWidth(col, w)
        for col in (self.COL_EDIT, self.COL_HIST, self.COL_DEL):
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
        self._info_name = _lbl("—", min_w=180, color="#ffffff")
        self._info_name.setStyleSheet(
            "color:#ffffff;font-size:12px;font-weight:700;min-width:180px;"
        )
        lay.addWidget(self._info_name)

        lay.addWidget(_lbl("   │  "))
        self._info_sub = _lbl("—", min_w=90, color="#cfe0f5")
        lay.addWidget(self._info_sub)

        lay.addWidget(_lbl("   │  "))
        self._info_src = _lbl("From: —", color="#90caf9")
        self._info_src.setStyleSheet(
            "color:#90caf9;font-size:12px;font-weight:700;min-width:110px;"
        )
        lay.addWidget(self._info_src)

        lay.addWidget(_lbl("   │  "))
        self._info_dst = _lbl("To: —", color="#a5d6a7")
        self._info_dst.setStyleSheet(
            "color:#a5d6a7;font-size:12px;font-weight:700;min-width:110px;"
        )
        lay.addWidget(self._info_dst)

        lay.addWidget(_lbl("   │  "))
        self._info_cost = _lbl("—", min_w=90, color="#ef9a9a")
        lay.addWidget(self._info_cost)

        lay.addWidget(_lbl("   │  "))
        self._info_prices: list[QLabel] = []
        for _ in range(3):
            pl = _lbl("", min_w=90)
            self._info_prices.append(pl)
            lay.addWidget(pl)

        lay.addStretch()
        return frame

    # ─ totals bar ─────────────────────────────────────────────────────────────

    def _make_totals_bar(self):
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
            v = QLabel("0.00")
            v.setStyleSheet("font-weight:700;font-size:13px;color:#1a3a5c;min-width:90px;")
            lay.addWidget(l)
            lay.addWidget(v)
            return v

        self._lines_count_lbl = stat("Lines:")
        self._subtotal_lbl    = stat("Sub-Total:")
        self._disc_lbl        = stat("Discount:")
        self._grand_total_lbl = stat("Grand Total:")
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
        self._save_btn.clicked.connect(self._save_transfer)
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

        lay.addStretch()

        lay.addWidget(self._lbl("Notes:"))
        self._notes_input = QLineEdit()
        self._notes_input.setFixedHeight(30)
        self._notes_input.setMinimumWidth(200)
        lay.addWidget(self._notes_input)

        return frame

    # ── Box / Pcs helpers ─────────────────────────────────────────────────────

    def _set_box_enabled(self, pack_qty: int):
        enabled = pack_qty > 1
        self._box_spin.setEnabled(enabled)
        self._box_lbl.setStyleSheet(
            "font-weight:600;color:#1a3a5c;font-size:12px;" if enabled
            else "font-weight:600;color:#aaa;font-size:12px;"
        )
        self._pcs_lbl.setText(f"Pcs ({pack_qty}):" if enabled else "Pcs:")

    def _on_box_changed(self, val: int):
        if self._current_pack_qty > 1:
            self._qty_spin.blockSignals(True)
            self._qty_spin.setValue(val * self._current_pack_qty)
            self._qty_spin.blockSignals(False)
        self._recalc_total()

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _lbl(text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet("font-weight:600;color:#1a3a5c;font-size:12px;")
        return l

    # ── Warehouses ────────────────────────────────────────────────────────────

    def _load_warehouses(self):
        warehouses = TransferService.get_warehouses()   # (id, name, number)
        self._from_combo.blockSignals(True)
        self._to_combo.blockSignals(True)
        self._from_combo.clear()
        self._to_combo.clear()

        from_idx = 0
        to_idx   = 1 if len(warehouses) > 1 else 0

        for i, (wh_id, wh_name, wh_num) in enumerate(warehouses):
            self._from_combo.addItem(wh_name, (wh_id, wh_name))
            self._to_combo.addItem(wh_name, (wh_id, wh_name))
            if wh_num == 0:
                from_idx = i
            if wh_num == 1:
                to_idx = i

        self._from_combo.setCurrentIndex(from_idx)
        self._to_combo.setCurrentIndex(to_idx)
        self._from_combo.blockSignals(False)
        self._to_combo.blockSignals(False)
        self._on_from_changed()
        self._on_to_changed()

    def _on_from_changed(self):
        data = self._from_combo.currentData()
        self._from_wh_id   = data[0] if data else ""
        self._from_wh_name = data[1] if data else ""
        self._refresh_transfer_number()
        self._refresh_stock_column()

    def _on_to_changed(self):
        data = self._to_combo.currentData()
        self._to_wh_id   = data[0] if data else ""
        self._to_wh_name = data[1] if data else ""
        self._refresh_stock_column()

    def _refresh_transfer_number(self):
        if self._from_wh_id:
            no = TransferService.next_transfer_number(self._from_wh_id)
        else:
            no = "T—"
        self._transfer_no = no
        self._no_input.setText(no)

    # ── Item entry ─────────────────────────────────────────────────────────────

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

        self._current_item     = item
        self._current_pack_qty = item.pack_qty
        self._item_desc_label.setText(item.description[:36])
        self._item_desc_label.setStyleSheet(
            "color:#1a3a5c;font-weight:600;font-size:12px;"
        )

        price = self._price_for_item(item)
        self._block_total(True)
        self._box_spin.blockSignals(True)
        self._box_spin.setValue(0)
        self._box_spin.blockSignals(False)
        # For box items wait for box input; for unit items default to 1
        self._qty_spin.setValue(0.0 if item.pack_qty > 1 else 1.0)
        self._price_spin.setValue(price)
        self._disc_spin.setValue(0.0)
        self._total_spin.setValue(0.0)
        self._block_total(False)

        # Update info bar with current item details
        src = TransferService.get_item_stock(item.item_id, self._from_wh_id)
        dst = TransferService.get_item_stock(item.item_id, self._to_wh_id)
        self._info_name.setText(item.description[:50])
        self._info_sub.setText(getattr(item, "subgroup", "") or "—")
        self._info_src.setText(f"{self._from_wh_name}: {src:,.3f}")
        self._info_dst.setText(f"{self._to_wh_name}: {dst:,.3f}")
        self._info_cost.setText(f"Cost: {getattr(item, 'last_cost', 0):,.4f}")
        type_map = {"retail": "Retail", "wholesale": "W/Sale", "semi_wholesale": "Semi-W"}
        for lbl in self._info_prices:
            lbl.setText("")
        for i, (pt, amt, cur) in enumerate(getattr(item, "sales_prices", [])[:3]):
            self._info_prices[i].setText(f"{type_map.get(pt, pt.capitalize())}: {amt:,.4f} {cur}   ")

        self._set_box_enabled(item.pack_qty)
        if item.pack_qty > 1:
            QTimer.singleShot(0, lambda: (self._box_spin.setFocus(), self._box_spin.selectAll()))
        else:
            QTimer.singleShot(0, lambda: (self._qty_spin.setFocus(), self._qty_spin.selectAll()))

    def _price_for_item(self, item) -> float:
        """Return the price matching the selected price type and currency."""
        ptype = self._price_type_combo.currentData() or "cost"
        cur   = self._cur_combo.currentText()
        if ptype == "cost":
            return item.last_cost
        # Try exact type + currency match first
        for pt, amt, pcur in getattr(item, "sales_prices", []):
            if pt == ptype and pcur == cur:
                return amt
        # Fallback: any currency for that type
        for pt, amt, pcur in getattr(item, "sales_prices", []):
            if pt == ptype:
                return amt
        return item.last_cost

    # ── Recalc / back-calc ────────────────────────────────────────────────────

    def _recalc_total(self):
        qty   = self._qty_spin.value()
        price = self._price_spin.value()
        disc  = self._disc_spin.value()
        self._block_total(True)
        self._total_spin.setValue(round(qty * price * (1 - disc / 100), 2))
        self._block_total(False)

    def _on_total_changed(self, val):
        if self._total_editing:
            return
        qty  = self._qty_spin.value()
        disc = self._disc_spin.value()
        denom = qty * (1 - disc / 100)
        if denom > 0:
            self._price_spin.blockSignals(True)
            self._price_spin.setValue(round(val / denom, 4))
            self._price_spin.blockSignals(False)

    def _block_total(self, block: bool):
        self._total_editing = block
        self._total_spin.blockSignals(block)

    # ── Add / edit line ───────────────────────────────────────────────────────

    def _add_line(self):
        if not self._current_item:
            self._bc_input.setFocus()
            return
        qty = self._qty_spin.value()
        if qty <= 0:
            QMessageBox.warning(self, "Quantity", "Please enter a quantity.")
            self._qty_spin.setFocus()
            return

        item = self._current_item
        src  = TransferService.get_item_stock(item.item_id, self._from_wh_id)
        dst  = TransferService.get_item_stock(item.item_id, self._to_wh_id)

        line = {
            "item_id":     item.item_id,
            "code":        item.code,
            "barcode":     item.barcode,
            "name":        item.description,
            "pack_qty":    item.pack_qty,
            "subgroup":    getattr(item, "subgroup", ""),
            "last_cost":   getattr(item, "last_cost", 0.0),
            "qty":         qty,
            "price":       self._price_spin.value(),
            "disc":        self._disc_spin.value(),
            "total":       self._total_spin.value(),
            "src_stock":   src,
            "dst_stock":   dst,
            "sales_prices": getattr(item, "sales_prices", []),
        }

        if self._editing_row >= 0:
            self._lines[self._editing_row] = line
        else:
            self._lines.append(line)

        self._refresh_table()
        self._refresh_totals()
        self._clear_entry()

    def _load_line_to_entry(self, row: int):
        """Load an existing line back into the entry bar for editing."""
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

        self._bc_input.setText(line["barcode"] or line["code"])
        self._item_desc_label.setText(line["name"][:36])
        self._item_desc_label.setStyleSheet(
            "color:#1a3a5c;font-weight:600;font-size:12px;"
        )
        self._block_total(True)
        self._qty_spin.setValue(line["qty"])
        self._price_spin.setValue(line["price"])
        self._disc_spin.setValue(line["disc"])
        self._total_spin.setValue(line["total"])
        self._block_total(False)

        self._add_btn.setText("✓  Update")
        self._add_btn.setStyleSheet(
            "QPushButton{background:#e65100;color:#fff;font-size:13px;font-weight:700;"
            "border:none;border-radius:4px;}"
            "QPushButton:hover{background:#bf360c;}"
        )
        self._cancel_edit_btn.show()
        self._qty_spin.setFocus()
        self._qty_spin.selectAll()

    def _cancel_edit(self):
        self._editing_row = -1
        self._clear_entry()

    def _clear_entry(self):
        self._current_item     = None
        self._current_pack_qty = 1
        self._editing_row      = -1
        self._bc_input.clear()
        self._item_desc_label.setText("")
        self._box_spin.blockSignals(True)
        self._box_spin.setValue(0)
        self._box_spin.blockSignals(False)
        self._set_box_enabled(1)
        self._block_total(True)
        self._qty_spin.setValue(0)
        self._price_spin.setValue(0)
        self._disc_spin.setValue(0)
        self._total_spin.setValue(0)
        self._block_total(False)
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
            src = line.get("src_stock", 0.0)
            dst = line.get("dst_stock", 0.0)
            qty = line["qty"]

            cells = [
                (str(row + 1),           Qt.AlignCenter,                   False),
                (line["code"],           Qt.AlignLeft | Qt.AlignVCenter,   False),
                (line["barcode"],        Qt.AlignLeft | Qt.AlignVCenter,   False),
                (line["name"],           Qt.AlignLeft | Qt.AlignVCenter,   False),
                (f"{qty:.3f}",           Qt.AlignRight | Qt.AlignVCenter,  True),
                (f"{line['price']:.4f}", Qt.AlignRight | Qt.AlignVCenter,  True),
                (f"{line['disc']:.2f}",  Qt.AlignCenter,                   True),
                (f"{line['total']:.2f}", Qt.AlignRight | Qt.AlignVCenter,  True),
                (f"{src:,.2f}",          Qt.AlignRight | Qt.AlignVCenter,  False),
                (f"{dst:,.2f}",          Qt.AlignRight | Qt.AlignVCenter,  False),
            ]
            for col, (val, align, editable) in enumerate(cells):
                cell = QTableWidgetItem(val)
                cell.setTextAlignment(align)
                if editable:
                    cell.setFlags(cell.flags() | Qt.ItemIsEditable)
                else:
                    cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                # Colour source stock red when insufficient
                if col == self.COL_SRC:
                    color = "#2e7d32" if src >= qty else "#c62828"
                    cell.setForeground(QColor(color))
                    if src < qty:
                        cell.setBackground(QColor("#ffebee"))
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

            # Stock-card (H) button
            h_btn = QPushButton("H")
            h_btn.setToolTip("Stock card for this item")
            h_btn.setStyleSheet(
                "QPushButton{background:#1565c0;color:#fff;border:none;border-radius:3px;"
                "font-size:10px;font-weight:700;}"
                "QPushButton:hover{background:#0d47a1;}"
            )
            h_btn.setFixedSize(24, 24)
            h_btn.setCursor(Qt.PointingHandCursor)
            bc = line["barcode"]
            h_btn.clicked.connect(
                lambda _, b=bc, iid=line["item_id"]: self._open_stock_card(iid, b)
            )
            self._table.setCellWidget(row, self.COL_HIST, h_btn)

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

    def _on_cell_edited(self, cell):
        if self._table_updating:
            return
        row = cell.row()
        col = cell.column()
        if row < 0 or row >= len(self._lines) or col not in self._EDITABLE_COLS:
            return
        try:
            val = float(cell.text().replace(",", "").replace("%", "").strip())
        except ValueError:
            return
        line = self._lines[row]
        if col == self.COL_QTY:
            line["qty"] = val
        elif col == self.COL_PRC:
            line["price"] = val
        elif col == self.COL_DSC:
            line["disc"] = val
        elif col == self.COL_TOT:
            denom = line["qty"] * (1 - line["disc"] / 100)
            if denom > 0:
                line["price"] = round(val / denom, 4)
            line["total"] = val
            self._refresh_table()
            self._refresh_totals()
            return
        line["total"] = round(
            line["qty"] * line["price"] * (1 - line["disc"] / 100), 2
        )
        self._refresh_table()
        self._refresh_totals()

    def _on_row_selected(self):
        if self._table_updating:
            return
        row = self._table.currentRow()
        if row < 0 or row >= len(self._lines):
            self._clear_info_bar()
            return
        line = self._lines[row]
        src  = TransferService.get_item_stock(line["item_id"], self._from_wh_id)
        dst  = TransferService.get_item_stock(line["item_id"], self._to_wh_id)

        self._info_name.setText(line["name"][:50])
        self._info_sub.setText(line.get("subgroup", "") or "—")
        self._info_src.setText(f"{self._from_wh_name}: {src:,.3f}")
        self._info_dst.setText(f"{self._to_wh_name}: {dst:,.3f}")
        self._info_cost.setText(f"Cost: {line.get('last_cost', 0):,.4f}")

        type_map = {
            "retail": "Retail", "wholesale": "W/Sale",
            "semi_wholesale": "Semi-W", "cost": "Cost",
        }
        for lbl in self._info_prices:
            lbl.setText("")
        for i, (pt, amt, cur) in enumerate(line.get("sales_prices", [])[:3]):
            kind = type_map.get(pt, pt.capitalize())
            self._info_prices[i].setText(f"{kind}: {amt:,.4f} {cur}   ")

    def _clear_info_bar(self):
        self._info_name.setText("—")
        self._info_sub.setText("—")
        self._info_src.setText(f"{self._from_wh_name}: —")
        self._info_dst.setText(f"{self._to_wh_name}: —")
        self._info_cost.setText("—")
        for lbl in self._info_prices:
            lbl.setText("")

    def _delete_line(self, row: int):
        if 0 <= row < len(self._lines):
            self._lines.pop(row)
            self._refresh_table()
            self._refresh_totals()

    def _open_stock_card(self, item_id: str, barcode: str):
        try:
            from ui.screens.stock.stock_card import StockCardScreen
            dlg = QDialog(self)
            dlg.setWindowTitle("Stock Card")
            dlg.resize(1100, 700)
            from PySide6.QtWidgets import QVBoxLayout as _VL
            lay = _VL(dlg)
            lay.setContentsMargins(0, 0, 0, 0)
            sc = StockCardScreen()
            lay.addWidget(sc)
            # Pre-fill barcode and trigger search
            sc._bc_edit.setText(barcode or "")
            if barcode:
                sc._find_item(barcode)
            dlg.exec()
        except Exception as exc:
            QMessageBox.information(self, "Stock Card", str(exc))

    def _refresh_stock_column(self):
        for line in self._lines:
            line["src_stock"] = TransferService.get_item_stock(
                line["item_id"], self._from_wh_id
            )
            line["dst_stock"] = TransferService.get_item_stock(
                line["item_id"], self._to_wh_id
            )
        if self._lines:
            self._refresh_table()
        self._clear_info_bar()

    # ── Totals ────────────────────────────────────────────────────────────────

    def _refresh_totals(self):
        subtotal = disc_val = 0.0
        for line in self._lines:
            gross    = line["qty"] * line["price"]
            d        = gross * line["disc"] / 100
            subtotal += gross
            disc_val += d
        grand = subtotal - disc_val
        self._lines_count_lbl.setText(str(len(self._lines)))
        self._subtotal_lbl.setText(f"{subtotal:,.2f}")
        self._disc_lbl.setText(f"{disc_val:,.2f}")
        self._grand_total_lbl.setText(f"{grand:,.2f}")

    # ── eventFilter — Enter key navigation ────────────────────────────────────

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if obj is self._box_spin:
                    self._qty_spin.setFocus()
                    self._qty_spin.selectAll()
                    return True
                if obj is self._qty_spin:
                    self._recalc_total()
                    self._price_spin.setFocus()
                    self._price_spin.selectAll()
                    return True
                if obj is self._price_spin:
                    self._recalc_total()
                    self._disc_spin.setFocus()
                    self._disc_spin.selectAll()
                    return True
                if obj is self._disc_spin:
                    self._recalc_total()
                    self._total_spin.setFocus()
                    self._total_spin.selectAll()
                    return True
                if obj is self._total_spin:
                    self._add_line()
                    return True
        return super().eventFilter(obj, event)

    # ── Confirm ───────────────────────────────────────────────────────────────

    def _save_transfer(self):
        if not self._lines:
            QMessageBox.warning(self, "Empty", "No items to transfer.")
            return
        if not self._from_wh_id or not self._to_wh_id:
            QMessageBox.warning(self, "Warehouse", "Select source and destination warehouses.")
            return
        if self._from_wh_id == self._to_wh_id:
            QMessageBox.warning(self, "Warehouse",
                                "Source and destination must be different.")
            return

        short = [l for l in self._lines if l.get("src_stock", 0) < l["qty"]]
        if short:
            names = ", ".join(l["name"][:20] for l in short[:3])
            if QMessageBox.question(
                self, "Insufficient Stock",
                f"Some items have less stock than requested:\n{names}\n\nProceed anyway?",
                QMessageBox.Yes | QMessageBox.No,
            ) == QMessageBox.No:
                return

        user  = AuthService.current_user()
        op_id = user.id if user else ""
        no    = self._no_input.text().strip() or self._transfer_no

        ok, result = TransferService.save_transfer(
            from_warehouse_id=self._from_wh_id,
            to_warehouse_id=self._to_wh_id,
            operator_id=op_id,
            transfer_date=self._date_edit.date().toString("yyyy-MM-dd"),
            notes=self._notes_input.text().strip(),
            lines=[{
                "item_id":   l["item_id"],
                "item_name": l["name"],
                "barcode":   l["barcode"],
                "qty":       l["qty"],
                "unit_cost": l["price"],
            } for l in self._lines],
            transfer_number=no,
            transfer_id=self._current_transfer_id or "",
        )

        if not ok:
            QMessageBox.critical(self, "Error", f"Transfer failed:\n{result}")
            return

        self._current_transfer_id = result
        self._lock_btn.setEnabled(True)
        self._lock_btn.setText("🔒  Lock")

        total   = sum(l["total"] for l in self._lines)
        n_lines = len(self._lines)
        currency = self._cur_combo.currentText()
        saved_lines = list(self._lines)

        dlg = PostTransferDialog(
            transfer_no=no, line_count=n_lines, total=total,
            currency=currency, parent=self,
        )
        dlg.exec()

        if dlg.choice == "print":
            self._print_transfer(no, saved_lines, currency)
        # "new", "done", or closed → start fresh
        self._clear_all()

    # ── Print ─────────────────────────────────────────────────────────────────

    def _print_transfer(self, no: str, lines: list, currency: str):
        try:
            from PySide6.QtPrintSupport import QPrintPreviewDialog, QPrinter
            from PySide6.QtGui import QTextDocument
            printer = QPrinter(QPrinter.HighResolution)
            dlg     = QPrintPreviewDialog(printer, self)

            date_str = self._date_edit.date().toString("dd/MM/yyyy")
            rows_html = "".join(
                f"<tr>"
                f"<td style='text-align:center'>{i+1}</td>"
                f"<td>{l['code']}</td>"
                f"<td>{l['name']}</td>"
                f"<td style='text-align:right'>{l['qty']:.3f}</td>"
                f"<td style='text-align:right'>{l['price']:.4f}</td>"
                f"<td style='text-align:center'>{l['disc']:.2f}%</td>"
                f"<td style='text-align:right'>{l['total']:.2f}</td>"
                f"</tr>"
                for i, l in enumerate(lines)
            )
            total = sum(l["total"] for l in lines)
            html = (
                "<html><body style='font-family:Arial;font-size:12px;'>"
                f"<h2 style='text-align:center'>Warehouse Transfer — {no}</h2>"
                f"<p style='text-align:center'>{self._from_wh_name} → "
                f"{self._to_wh_name} &nbsp;&nbsp; Date: {date_str}</p>"
                "<table border='1' cellpadding='4' cellspacing='0' width='100%' "
                "style='border-collapse:collapse'>"
                "<tr style='background:#1a3a5c;color:#fff'>"
                "<th>#</th><th>Code</th><th>Name</th>"
                "<th>Qty</th><th>Price</th><th>Disc%</th><th>Total</th>"
                "</tr>"
                f"{rows_html}"
                "</table>"
                f"<p style='text-align:right;font-size:14px;font-weight:bold'>"
                f"Grand Total: {total:,.2f} {currency}</p>"
                "</body></html>"
            )

            def render(p):
                doc = QTextDocument()
                doc.setHtml(html)
                doc.print_(p)

            dlg.paintRequested.connect(render)
            dlg.exec()
        except Exception as exc:
            QMessageBox.warning(self, "Print", f"Print error: {exc}")

    # ── Clear all ─────────────────────────────────────────────────────────────

    def _toggle_lock(self):
        if not self._current_transfer_id:
            return
        detail = TransferService.get_transfer_detail(self._current_transfer_id)
        if not detail:
            return
        if detail["status"] == "locked":
            ok, msg = TransferService.unlock_transfer(self._current_transfer_id)
            if ok:
                self._lock_btn.setText("🔒  Lock")
                self._set_locked(False)
            else:
                QMessageBox.critical(self, "Error", msg)
        else:
            ok, msg = TransferService.lock_transfer(self._current_transfer_id)
            if ok:
                self._lock_btn.setText("🔓  Unlock")
                self._set_locked(True)
            else:
                QMessageBox.critical(self, "Error", msg)

    def _set_locked(self, locked: bool):
        """Enable/disable all input widgets based on lock state."""
        self._save_btn.setEnabled(not locked)
        self._from_combo.setEnabled(not locked)
        self._to_combo.setEnabled(not locked)
        self._date_edit.setEnabled(not locked)
        self._bc_input.setEnabled(not locked)
        self._notes_input.setEnabled(not locked)
        self._price_type_combo.setEnabled(not locked)
        self._cur_combo.setEnabled(not locked)

    def _clear_all(self):
        self._current_transfer_id = None
        self._lock_btn.setEnabled(False)
        self._lock_btn.setText("🔒  Lock")
        self._set_locked(False)
        self._lines.clear()
        self._refresh_table()
        self._refresh_totals()
        self._clear_entry()
        self._refresh_transfer_number()
        self._notes_input.clear()

    # ── History ───────────────────────────────────────────────────────────────

    def _open_history(self):
        from PySide6.QtWidgets import QVBoxLayout as _VL, QHBoxLayout as _HL, QSplitter
        dlg = QDialog(self)
        dlg.setWindowTitle("Transfer History")
        dlg.resize(1100, 620)
        root = _VL(dlg)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: transfers list ──────────────────────────────────────────────
        left = QWidget()
        llay = _VL(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(4)

        llay.addWidget(QLabel("All Transfers:"))

        list_tbl = QTableWidget()
        list_tbl.setColumnCount(6)
        list_tbl.setHorizontalHeaderLabels(["#", "Date", "From", "To", "Items", "Status"])
        list_tbl.setAlternatingRowColors(True)
        list_tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        list_tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        list_tbl.verticalHeader().setVisible(False)
        list_tbl.setStyleSheet(
            "QHeaderView::section{background:#1a3a5c;color:#fff;"
            "font-weight:700;border:none;padding:5px;}"
        )
        hdr = list_tbl.horizontalHeader()
        for i, m in enumerate([
            QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
            QHeaderView.Stretch, QHeaderView.Stretch,
            QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
        ]):
            hdr.setSectionResizeMode(i, m)
        llay.addWidget(list_tbl)

        # ── Right: detail view ────────────────────────────────────────────────
        right = QWidget()
        rlay = _VL(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(4)

        detail_header = QLabel("Select a transfer to view details")
        detail_header.setStyleSheet("font-weight:700;font-size:13px;color:#1a3a5c;")
        rlay.addWidget(detail_header)

        detail_tbl = QTableWidget()
        detail_tbl.setColumnCount(5)
        detail_tbl.setHorizontalHeaderLabels(["Code", "Name", "Barcode", "Qty", "Unit Cost"])
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
        for i in (0, 2, 3, 4):
            dhdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        rlay.addWidget(detail_tbl)

        # Action buttons
        btn_row = _HL()
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
        transfer_rows = TransferService.list_transfers(limit=500)
        list_tbl.setRowCount(len(transfer_rows))
        for r, d in enumerate(transfer_rows):
            for c, val in enumerate([
                d["number"], d["date"], d["from_wh"], d["to_wh"],
                str(d["item_count"]), d["status"],
            ]):
                it = QTableWidgetItem(val)
                it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                if c == 5:
                    it.setForeground(
                        QColor("#607d8b") if d["status"] == "locked"
                        else QColor("#2e7d32")
                    )
                list_tbl.setItem(r, c, it)

        # ── Row selection → show detail ────────────────────────────────────────
        def on_row_selected():
            sel = list_tbl.selectedItems()
            if not sel:
                return
            row = list_tbl.currentRow()
            if row < 0 or row >= len(transfer_rows):
                return
            d = transfer_rows[row]
            detail = TransferService.get_transfer_detail(d["id"])
            if not detail:
                return

            status = detail["status"]
            detail_header.setText(
                f"Transfer {detail['number']}  ·  {detail['from_wh']} → {detail['to_wh']}"
                f"  ·  {detail['date']}  ·  [{status.upper()}]"
            )
            notes_lbl.setText(f"Notes: {detail['notes']}" if detail["notes"] else "")

            lines = detail["lines"]
            detail_tbl.setRowCount(len(lines))
            for r2, li in enumerate(lines):
                for c2, val in enumerate([
                    li["code"], li["item_name"], li["barcode"],
                    f"{li['qty']:,.2f}", f"{li['unit_cost']:,.4f}",
                ]):
                    it2 = QTableWidgetItem(val)
                    it2.setTextAlignment(
                        Qt.AlignRight | Qt.AlignVCenter if c2 in (3, 4)
                        else Qt.AlignLeft | Qt.AlignVCenter
                    )
                    detail_tbl.setItem(r2, c2, it2)

            load_btn.setEnabled(True)
            load_btn.setProperty("transfer_detail", detail)

        list_tbl.itemSelectionChanged.connect(on_row_selected)
        list_tbl.doubleClicked.connect(lambda _: on_row_selected())

        # ── Load for edit ──────────────────────────────────────────────────────
        def on_load():
            detail = load_btn.property("transfer_detail")
            if not detail:
                return
            dlg.accept()
            self._load_transfer(detail)

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

    def _load_transfer(self, detail: dict):
        """Load an existing transfer into the screen for viewing/editing."""
        self._clear_all()
        self._current_transfer_id = detail["id"]
        self._lock_btn.setEnabled(True)
        locked = detail["status"] == "locked"
        self._lock_btn.setText("🔓  Unlock" if locked else "🔒  Lock")
        self._set_locked(locked)

        # Set warehouses
        for i in range(self._from_combo.count()):
            if self._from_combo.itemData(i)[0] == detail["from_wh_id"]:
                self._from_combo.setCurrentIndex(i)
                break
        for i in range(self._to_combo.count()):
            if self._to_combo.itemData(i)[0] == detail["to_wh_id"]:
                self._to_combo.setCurrentIndex(i)
                break

        self._notes_input.setText(detail.get("notes", ""))

        # Load lines
        for li in detail["lines"]:
            stock_src = TransferService.get_item_stock(li["item_id"], detail["from_wh_id"])
            stock_dst = TransferService.get_item_stock(li["item_id"], detail["to_wh_id"])
            self._lines.append({
                "item_id":   li["item_id"],
                "code":      li["code"],
                "barcode":   li["barcode"],
                "name":      li["item_name"],
                "pack_qty":  1,
                "subgroup":  "",
                "last_cost": li["unit_cost"],
                "qty":       li["qty"],
                "price":     li["unit_cost"],
                "disc":      0.0,
                "total":     li["qty"] * li["unit_cost"],
                "src_stock": stock_src,
                "dst_stock": stock_dst,
                "sales_prices": [],
            })

        self._refresh_table()
        self._refresh_totals()
