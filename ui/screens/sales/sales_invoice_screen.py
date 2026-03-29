"""
Sales Invoice Screen — back-office sales that deduct from warehouse stock.

Flow:
  1. Customer (type to search / walk-in default)
  2. Date / Warehouse / Currency
  3. Barcode → lookup item → auto-fill price
  4. Qty / Price / Disc% / Total (Enter → add line)
  5. Save → deducts stock, creates SalesInvoice (source='manual')
"""
from datetime import date as _date

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QLabel, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFrame, QDoubleSpinBox, QSpinBox,
    QDateEdit, QMessageBox, QDialog, QListWidget,
    QListWidgetItem, QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal, QDate, QTimer
from PySide6.QtGui import QColor, QFont

from services.sales_invoice_service import SalesInvoiceService, SalesLineItem
from services.auth_service import AuthService


# ── Customer picker ────────────────────────────────────────────────────────────

class CustomerPickerDialog(QDialog):
    def __init__(self, query: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Customer")
        self.setMinimumSize(520, 400)
        self._chosen: dict | None = None

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        top = QHBoxLayout()
        self._search = QLineEdit(query)
        self._search.setPlaceholderText("Name or phone…")
        self._search.setFixedHeight(32)
        top.addWidget(self._search)
        search_btn = QPushButton("🔍  Search")
        search_btn.setFixedHeight(32)
        search_btn.clicked.connect(self._load)
        top.addWidget(search_btn)
        lay.addLayout(top)

        self._list = QListWidget()
        self._list.doubleClicked.connect(self._accept)
        lay.addWidget(self._list)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._search.textChanged.connect(lambda _: self._load())
        self._search.returnPressed.connect(self._load)
        self._load()

    def _load(self):
        customers = SalesInvoiceService.list_customers(self._search.text().strip())
        self._data = customers
        self._list.clear()
        for c in customers:
            it = QListWidgetItem(f"{c['name']}  —  {c['phone']}")
            it.setData(Qt.UserRole, c)
            self._list.addItem(it)
        if customers:
            self._list.setCurrentRow(0)

    def _accept(self):
        item = self._list.currentItem()
        if item:
            self._chosen = item.data(Qt.UserRole)
            self.accept()

    @property
    def chosen(self) -> dict | None:
        return self._chosen


# ── Item picker ────────────────────────────────────────────────────────────────

class ItemPickerDialog(QDialog):
    def __init__(self, query: str = "", warehouse_id: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Item Search  —  ↑↓ browse · Enter select")
        self.setMinimumSize(780, 480)
        self._warehouse_id = warehouse_id
        self._chosen: dict | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        top = QHBoxLayout()
        self._search = QLineEdit(query)
        self._search.setPlaceholderText("Type to filter…")
        self._search.setFixedHeight(34)
        top.addWidget(self._search)
        search_btn = QPushButton("🔍  Search")
        search_btn.setFixedHeight(34)
        search_btn.clicked.connect(self._load)
        top.addWidget(search_btn)
        lay.addLayout(top)

        hint = QLabel("Double-click or Enter to select.")
        hint.setStyleSheet("color:#888; font-size:11px;")
        lay.addWidget(hint)

        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["#", "Code", "Barcode", "Name", "Stock", "Price LBP"])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        for c in (0, 1, 2, 4, 5):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setStyleSheet(
            "QHeaderView::section{background:#1a3a5c;color:#fff;"
            "font-weight:700;border:none;padding:4px;}"
        )
        self._table.doubleClicked.connect(self._accept)
        lay.addWidget(self._table)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._rows: list[dict] = []
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._load)
        self._search.textChanged.connect(lambda _: self._timer.start())
        self._search.returnPressed.connect(self._load)
        self._load()
        self._table.setFocus()

    def _load(self):
        query = self._search.text().strip()
        self._rows = SalesInvoiceService.search_items(query, self._warehouse_id, limit=80)
        self._table.setRowCount(0)
        self._table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            vals = [
                str(i + 1),
                row["code"],
                row["barcode"],
                row["name"],
                f"{row['stock']:,.0f}",
                f"{row['price_lbp']:,.0f}",
            ]
            for col, val in enumerate(vals):
                cell = QTableWidgetItem(val)
                cell.setTextAlignment(Qt.AlignCenter if col != 3 else Qt.AlignLeft | Qt.AlignVCenter)
                if col == 4:
                    cell.setForeground(QColor("#c62828" if row["stock"] <= 0 else "#2e7d32"))
                self._table.setItem(i, col, cell)
        if self._rows:
            self._table.selectRow(0)

    def _accept(self):
        r = self._table.currentRow()
        if 0 <= r < len(self._rows):
            self._chosen = self._rows[r]
            self.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._table.hasFocus() or not self._search.hasFocus():
                self._accept()
                return
        if event.key() in (Qt.Key_Down, Qt.Key_Up):
            self._table.setFocus()
        super().keyPressEvent(event)

    @property
    def chosen(self) -> dict | None:
        return self._chosen


# ── Main screen ────────────────────────────────────────────────────────────────

class SalesInvoiceScreen(QWidget):
    back = Signal()

    COL_NUM  = 0
    COL_CODE = 1
    COL_BC   = 2
    COL_DESC = 3
    COL_QTY  = 4
    COL_PRC  = 5
    COL_DSC  = 6
    COL_TOT  = 7
    COL_DEL  = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._customer: dict | None = None   # {id, name, phone, balance}
        self._lines: list[dict] = []
        self._current_item: SalesLineItem | None = None
        self._editing_row: int = -1
        self._current_pack_qty = 1
        self._table_updating = False
        self._build_ui()
        self._load_defaults()

    # ── Build ──────────────────────────────────────────────────────────────────

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

    def _make_top_bar(self):
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background:#1b5e20;")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 12, 0)

        back_btn = QPushButton("←  Back")
        back_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.15);color:#fff;border:1px solid rgba(255,255,255,0.3);"
            "border-radius:4px;padding:4px 12px;font-size:12px;}"
            "QPushButton:hover{background:rgba(255,255,255,0.3);}"
        )
        back_btn.setFixedHeight(28)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self._confirm_back)
        lay.addWidget(back_btn)

        title = QLabel("Sales Invoice")
        title.setStyleSheet("color:#fff;font-size:16px;font-weight:700;margin-left:12px;")
        lay.addWidget(title)
        lay.addStretch()

        self._inv_no_label = QLabel("")
        self._inv_no_label.setStyleSheet(
            "color:#fff;font-size:14px;font-weight:700;"
            "background:rgba(255,255,255,0.1);border-radius:4px;padding:2px 12px;"
        )
        lay.addWidget(self._inv_no_label)
        return bar

    def _make_setup_row(self):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:#f0f4f8;border-bottom:1px solid #cdd5e0;}"
            " QLabel{color:#1a1a2e;}"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(10)

        # Customer
        lay.addWidget(QLabel("Customer:"))
        self._cust_input = QLineEdit()
        self._cust_input.setPlaceholderText("Type name…")
        self._cust_input.setFixedHeight(30)
        self._cust_input.setMinimumWidth(180)
        self._cust_input.returnPressed.connect(self._search_customer)
        lay.addWidget(self._cust_input)

        search_btn = QPushButton("🔍")
        search_btn.setFixedSize(30, 30)
        search_btn.setCursor(Qt.PointingHandCursor)
        search_btn.clicked.connect(self._search_customer)
        lay.addWidget(search_btn)

        self._cust_name_label = QLabel("Walk-In")
        self._cust_name_label.setStyleSheet(
            "color:#1a6cb5;font-weight:700;font-size:13px;min-width:140px;"
        )
        lay.addWidget(self._cust_name_label)

        lay.addSpacing(16)

        # Date
        lay.addWidget(QLabel("Date:"))
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setFixedHeight(30)
        self._date_edit.setFixedWidth(120)
        lay.addWidget(self._date_edit)

        lay.addSpacing(16)

        # Warehouse
        lay.addWidget(QLabel("Warehouse:"))
        self._wh_combo = QComboBox()
        self._wh_combo.setFixedHeight(30)
        self._wh_combo.setMinimumWidth(160)
        self._wh_combo.currentIndexChanged.connect(self._on_warehouse_changed)
        lay.addWidget(self._wh_combo)

        lay.addStretch()

        # Currency
        lay.addWidget(QLabel("Currency:"))
        self._cur_combo = QComboBox()
        self._cur_combo.setFixedHeight(30)
        self._cur_combo.addItems(["LBP", "USD"])
        lay.addWidget(self._cur_combo)

        # Payment
        lay.addSpacing(8)
        lay.addWidget(QLabel("Payment:"))
        self._pay_combo = QComboBox()
        self._pay_combo.setFixedHeight(30)
        self._pay_combo.addItems(["cash", "account", "card"])
        lay.addWidget(self._pay_combo)

        return frame

    def _make_entry_bar(self):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:#e8f0fb;border-bottom:2px solid #2e7d32;}"
            " QLabel{color:#1a1a2e;}"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(6)

        bc_lbl = QLabel("Barcode / Code:")
        bc_lbl.setStyleSheet("font-weight:600;")
        lay.addWidget(bc_lbl)
        self._bc_input = QLineEdit()
        self._bc_input.setPlaceholderText("Scan or type…  Ctrl+Enter = browse")
        self._bc_input.setFixedHeight(32)
        self._bc_input.setMinimumWidth(180)
        self._bc_input.setStyleSheet("font-size:13px;font-weight:600;")
        self._bc_input.installEventFilter(self)
        lay.addWidget(self._bc_input)

        self._item_desc_label = QLabel("")
        self._item_desc_label.setStyleSheet(
            "color:#1a3a5c;font-weight:600;min-width:160px;font-size:12px;"
        )
        lay.addWidget(self._item_desc_label)

        lay.addSpacing(8)

        # Box (always visible; disabled when pack_qty == 1)
        self._box_lbl = QLabel("Box:")
        self._box_lbl.setStyleSheet("font-weight:600;")
        lay.addWidget(self._box_lbl)
        self._box_spin = QSpinBox()
        self._box_spin.setRange(0, 99999)
        self._box_spin.setFixedHeight(32)
        self._box_spin.setFixedWidth(70)
        self._box_spin.valueChanged.connect(self._on_box_changed)
        self._box_spin.installEventFilter(self)
        lay.addWidget(self._box_spin)

        # Qty (Pcs)
        self._pcs_lbl = QLabel("Pcs:")
        self._pcs_lbl.setStyleSheet("font-weight:600;")
        lay.addWidget(self._pcs_lbl)
        self._qty_spin = QDoubleSpinBox()
        self._qty_spin.setRange(0, 999999)
        self._qty_spin.setDecimals(3)
        self._qty_spin.setFixedHeight(32)
        self._qty_spin.setFixedWidth(80)
        self._qty_spin.installEventFilter(self)
        lay.addWidget(self._qty_spin)

        # Price
        price_lbl = QLabel("Price:")
        price_lbl.setStyleSheet("font-weight:600;")
        lay.addWidget(price_lbl)
        self._price_spin = QDoubleSpinBox()
        self._price_spin.setRange(0, 999_999_999)
        self._price_spin.setDecimals(2)
        self._price_spin.setFixedHeight(32)
        self._price_spin.setFixedWidth(110)
        self._price_spin.installEventFilter(self)
        self._price_spin.valueChanged.connect(self._on_price_changed)
        lay.addWidget(self._price_spin)

        # Disc%
        disc_lbl = QLabel("Disc%:")
        disc_lbl.setStyleSheet("font-weight:600;")
        lay.addWidget(disc_lbl)
        self._disc_spin = QDoubleSpinBox()
        self._disc_spin.setRange(0, 100)
        self._disc_spin.setDecimals(2)
        self._disc_spin.setFixedHeight(32)
        self._disc_spin.setFixedWidth(70)
        self._disc_spin.installEventFilter(self)
        self._disc_spin.valueChanged.connect(self._on_price_changed)
        lay.addWidget(self._disc_spin)

        # Total
        tot_lbl = QLabel("Total:")
        tot_lbl.setStyleSheet("font-weight:700;color:#1a3a5c;")
        lay.addWidget(tot_lbl)
        self._total_spin = QDoubleSpinBox()
        self._total_spin.setRange(0, 999_999_999)
        self._total_spin.setDecimals(2)
        self._total_spin.setFixedHeight(32)
        self._total_spin.setFixedWidth(120)
        self._total_spin.setStyleSheet("font-weight:700;font-size:13px;")
        self._total_spin.installEventFilter(self)
        self._total_spin.valueChanged.connect(self._on_total_changed)
        lay.addWidget(self._total_spin)

        self._total_editing = False

        lay.addStretch()

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

        self._set_box_enabled(1)   # start disabled
        return frame

    def _set_box_enabled(self, pack_qty: int):
        enabled = pack_qty > 1
        self._box_spin.setEnabled(enabled)
        self._box_lbl.setStyleSheet(
            "font-weight:600;" if enabled else "font-weight:600;color:#aaa;"
        )
        self._pcs_lbl.setText(f"Pcs ({pack_qty}):" if enabled else "Pcs:")

    def _on_box_changed(self, val: int):
        if self._current_pack_qty > 1:
            self._qty_spin.blockSignals(True)
            self._qty_spin.setValue(val * self._current_pack_qty)
            self._qty_spin.blockSignals(False)
        self._recalc_total()

    def _make_table(self):
        self._table = QTableWidget()
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels([
            "#", "Code", "Barcode", "Description", "Qty", "Price", "Disc%", "Total", "",
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        self._table.doubleClicked.connect(self._on_row_double_clicked)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(self.COL_DESC, QHeaderView.Stretch)
        for col in (self.COL_NUM, self.COL_CODE, self.COL_BC):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        for col, w in (
            (self.COL_QTY, 72), (self.COL_PRC, 100),
            (self.COL_DSC, 60), (self.COL_TOT, 110), (self.COL_DEL, 30),
        ):
            hdr.setSectionResizeMode(col, QHeaderView.Fixed)
            self._table.setColumnWidth(col, w)
        self._table.verticalHeader().setDefaultSectionSize(32)
        hdr.setStyleSheet(
            "QHeaderView::section{background:#1b5e20;color:#fff;"
            "font-weight:700;border:none;padding:4px;}"
        )
        return self._table

    def _make_info_bar(self):
        frame = QFrame()
        frame.setFixedHeight(34)
        frame.setStyleSheet(
            "background:#1a3a5c;"
            "border-top:1px solid #0d2238;border-bottom:1px solid #0d2238;"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(0)

        def _lbl(text, bold=False, color="#cfe0f5", min_w=0):
            l = QLabel(text)
            s = f"color:{color};font-size:12px;"
            if bold: s += "font-weight:700;"
            if min_w: s += f"min-width:{min_w}px;"
            l.setStyleSheet(s)
            return l

        self._info_name_lbl = _lbl("—", bold=True, color="#fff", min_w=180)
        lay.addWidget(self._info_name_lbl)

        lay.addWidget(_lbl("   │  "))
        self._info_sub_lbl = _lbl("—", color="#cfe0f5", min_w=100)
        lay.addWidget(self._info_sub_lbl)

        lay.addWidget(_lbl("   │  "))
        self._info_stock_lbl = _lbl("—", color="#a5d6a7", min_w=90)
        lay.addWidget(self._info_stock_lbl)

        lay.addWidget(_lbl("   │  "))
        self._info_price_lbl = _lbl("—", color="#ffe082", min_w=110)
        lay.addWidget(self._info_price_lbl)

        lay.addWidget(_lbl("   │  "))
        self._info_cost_lbl = _lbl("—", color="#ef9a9a", min_w=90)
        lay.addWidget(self._info_cost_lbl)

        lay.addStretch()
        return frame

    def _update_info_bar(self, item: "SalesLineItem"):
        self._info_name_lbl.setText(item.description[:35])
        self._info_sub_lbl.setText(item.subgroup or "—")
        stock_color = "#c62828" if item.stock_units <= 0 else "#a5d6a7"
        self._info_stock_lbl.setStyleSheet(
            f"color:{stock_color};font-size:12px;min-width:90px;"
        )
        self._info_stock_lbl.setText(f"Stock: {item.stock_units:,.0f}")
        self._info_price_lbl.setText(f"Price: {item.price:,.2f}")
        self._info_cost_lbl.setText(f"Cost: {item.cost:,.2f}")

    def _clear_info_bar(self):
        for lbl in (self._info_name_lbl, self._info_sub_lbl,
                    self._info_stock_lbl, self._info_price_lbl, self._info_cost_lbl):
            lbl.setText("—")

    def _make_totals_bar(self):
        # Placeholder — totals are rendered inside _make_footer
        frame = QFrame()
        frame.setFixedHeight(0)
        return frame

    def _make_footer(self):
        frame = QFrame()
        frame.setStyleSheet("QFrame{background:#f0f4f8;border-top:2px solid #1a3a5c;} QLabel{color:#1a1a2e;}")
        outer = QHBoxLayout(frame)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(10)

        # ── Left: note + buttons ──────────────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(4)

        note_row = QHBoxLayout()
        note_row.setSpacing(6)
        note_lbl = QLabel("Note:")
        note_lbl.setStyleSheet("font-size:11px;")
        note_row.addWidget(note_lbl)
        self._notes_input = QLineEdit()
        self._notes_input.setPlaceholderText("Optional notes…")
        self._notes_input.setFixedHeight(24)
        self._notes_input.setMinimumWidth(200)
        self._notes_input.setStyleSheet("font-size:11px;")
        note_row.addWidget(self._notes_input)
        note_row.addStretch()
        left.addLayout(note_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        clear_btn = QPushButton("🗑  Delete All Items")
        clear_btn.setStyleSheet(
            "QPushButton{background:#757575;color:#fff;border:none;border-radius:4px;"
            "font-size:11px;font-weight:700;padding:0 12px;}"
            "QPushButton:hover{background:#424242;}"
        )
        clear_btn.setFixedHeight(30)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_all)
        btn_row.addWidget(clear_btn)

        self._print_btn = QPushButton("🖨  Print")
        self._print_btn.setStyleSheet(
            "QPushButton{background:#00695c;color:#fff;border:none;border-radius:4px;"
            "font-size:11px;font-weight:700;padding:0 12px;}"
            "QPushButton:hover{background:#004d40;}"
        )
        self._print_btn.setFixedHeight(30)
        self._print_btn.setCursor(Qt.PointingHandCursor)
        self._print_btn.clicked.connect(self._print_current)
        btn_row.addWidget(self._print_btn)

        self._save_btn = QPushButton("💾  Save Invoice")
        self._save_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;border:none;border-radius:6px;"
            "font-size:13px;font-weight:700;padding:0 18px;}"
            "QPushButton:hover{background:#1b5e20;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self._save_btn.setFixedHeight(34)
        self._save_btn.setCursor(Qt.PointingHandCursor)
        self._save_btn.clicked.connect(self._save_invoice)
        btn_row.addWidget(self._save_btn)
        btn_row.addStretch()
        left.addLayout(btn_row)

        outer.addLayout(left, 1)
        outer.addStretch()

        # ── Right: stacked totals ─────────────────────────────────────────────
        totals_frame = QFrame()
        totals_frame.setStyleSheet(
            "QFrame{background:#f8faff;border-left:3px solid #1a3a5c;border-radius:0;padding:0 8px;}"
        )
        tlay = QGridLayout(totals_frame)
        tlay.setContentsMargins(12, 6, 12, 6)
        tlay.setHorizontalSpacing(16)
        tlay.setVerticalSpacing(3)

        def stat_row(row_idx, label, big=False, color="#1a3a5c"):
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#555;font-size:12px;font-weight:500;")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val = QLabel("0.00")
            sz  = "16px" if big else "13px"
            wt  = "800"  if big else "700"
            val.setStyleSheet(f"font-weight:{wt};font-size:{sz};color:{color};min-width:110px;")
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tlay.addWidget(lbl, row_idx, 0)
            tlay.addWidget(val, row_idx, 1)
            return val

        self._lines_lbl      = stat_row(0, "Lines:")
        self._subtotal_lbl   = stat_row(1, "Sub-Total:")
        self._discount_lbl   = stat_row(2, "Discount:")
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#bbd0ee;")
        tlay.addWidget(sep, 3, 0, 1, 2)
        self._grand_lbl      = stat_row(4, "Grand Total:", big=True, color="#1a3a5c")

        outer.addWidget(totals_frame)
        return frame

    # ── Defaults ───────────────────────────────────────────────────────────────

    def _load_defaults(self):
        # Warehouses (load first so warehouse_id is available for invoice number)
        from services.daily_sales_service import DailySalesService
        warehouses = DailySalesService.get_warehouses()
        self._wh_combo.blockSignals(True)
        self._wh_combo.clear()
        for wh_id, wh_name in warehouses:
            self._wh_combo.addItem(wh_name, wh_id)
        self._wh_combo.blockSignals(False)

        # Invoice number based on selected warehouse
        wh_id = self._wh_combo.currentData() or ""
        inv_no = SalesInvoiceService.next_invoice_number(wh_id)
        self._inv_no_label.setText(inv_no)

        # Walk-in customer
        self._set_walk_in_customer()

    def _refresh_invoice_number(self):
        wh_id = self._wh_combo.currentData() or ""
        self._inv_no_label.setText(SalesInvoiceService.next_invoice_number(wh_id))

    def _set_walk_in_customer(self):
        from database.engine import get_session, init_db
        from database.models.parties import Customer
        from database.models.items import Warehouse
        init_db()
        session = get_session()
        try:
            wh_id = self._wh_combo.currentData() or ""
            c = None
            # Use warehouse default customer if set
            if wh_id:
                wh = session.query(Warehouse).filter_by(id=wh_id).first()
                if wh and wh.default_customer_id:
                    c = session.query(Customer).filter_by(id=wh.default_customer_id).first()
            # Fall back to global cash client
            if not c:
                c = session.query(Customer).filter_by(is_cash_client=True).first()
            if c:
                self._customer = {"id": c.id, "name": c.name, "phone": c.phone or "", "balance": c.balance}
            else:
                self._customer = None
        finally:
            session.close()
        self._cust_name_label.setText(
            self._customer["name"] if self._customer else "Walk-In"
        )

    def _on_warehouse_changed(self):
        # Refresh invoice number for newly selected warehouse
        self._refresh_invoice_number()
        # Clear item desc when warehouse changes so price re-lookup on next scan
        self._item_desc_label.setText("")
        self._clear_info_bar()
        self._current_item = None

    # ── Customer search ────────────────────────────────────────────────────────

    def _search_customer(self):
        query = self._cust_input.text().strip()
        dlg = CustomerPickerDialog(query, self)
        if dlg.exec() and dlg.chosen:
            c = dlg.chosen
            self._customer = c
            self._cust_name_label.setText(c["name"])
            self._cust_input.clear()
        self._bc_input.setFocus()

    # ── Barcode entry ──────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.KeyPress:
            key = event.key()
            mods = event.modifiers()

            # Enter in barcode field
            if obj is self._bc_input and key in (Qt.Key_Return, Qt.Key_Enter):
                if mods & Qt.ControlModifier:
                    self._open_item_picker()
                else:
                    self._on_barcode_entered()
                    # _fill_entry already moves focus to qty_spin on success
                    if not self._current_item:
                        # item not found — stay in barcode field
                        pass
                return True

            # Box → Pcs navigation
            if obj is self._box_spin and key in (Qt.Key_Return, Qt.Key_Enter):
                self._qty_spin.setFocus()
                self._qty_spin.selectAll()
                return True

            # Enter in entry spinboxes → advance focus
            spin_order = [
                self._qty_spin, self._price_spin,
                self._disc_spin, self._total_spin,
            ]
            if obj in spin_order and key in (Qt.Key_Return, Qt.Key_Enter):
                idx = spin_order.index(obj)
                if idx == len(spin_order) - 1:
                    self._add_line()
                else:
                    spin_order[idx + 1].setFocus()
                    if hasattr(spin_order[idx + 1], "selectAll"):
                        spin_order[idx + 1].selectAll()
                return True

        return super().eventFilter(obj, event)

    def _on_barcode_entered(self):
        query = self._bc_input.text().strip()
        if not query:
            return
        wh_id = self._wh_combo.currentData() or ""
        currency = self._cur_combo.currentText()
        item = SalesInvoiceService.lookup_item(query, wh_id, "barcode", currency)
        if not item:
            item = SalesInvoiceService.lookup_item(query, wh_id, "name", currency)
        if not item:
            self._item_desc_label.setText("Not found")
            self._item_desc_label.setStyleSheet("color:#c62828;font-weight:600;font-size:12px;")
            return
        self._fill_entry(item)

    def _open_item_picker(self):
        query = self._bc_input.text().strip()
        wh_id = self._wh_combo.currentData() or ""
        dlg = ItemPickerDialog(query, wh_id, self)
        if not dlg.exec() or not dlg.chosen:
            return
        row = dlg.chosen
        currency = self._cur_combo.currentText()
        item = SalesInvoiceService.lookup_item(row["barcode"] or row["item_id"], wh_id,
                                               "barcode" if row["barcode"] else "name", currency)
        if item:
            self._fill_entry(item)

    def _fill_entry(self, item: SalesLineItem):
        self._current_item = item
        self._current_pack_qty = item.pack_qty
        self._item_desc_label.setText(item.description)
        self._item_desc_label.setStyleSheet(
            "color:#1b5e20;font-weight:700;min-width:160px;font-size:12px;"
        )
        self._update_info_bar(item)
        self._box_spin.blockSignals(True)
        self._box_spin.setValue(0)
        self._box_spin.blockSignals(False)
        # For box items start qty at 0 (box entry drives pcs); for unit items use 1
        self._qty_spin.setValue(0.0 if item.pack_qty > 1 else item.qty)
        self._price_spin.setValue(item.price)
        self._disc_spin.setValue(0.0)
        self._recalc_total()
        self._set_box_enabled(item.pack_qty)
        if item.pack_qty > 1:
            QTimer.singleShot(0, lambda: (self._box_spin.setFocus(), self._box_spin.selectAll()))
        else:
            QTimer.singleShot(0, lambda: (self._qty_spin.setFocus(), self._qty_spin.selectAll()))

    # ── Entry calculation ──────────────────────────────────────────────────────

    def _on_price_changed(self):
        if not self._total_editing:
            self._recalc_total()

    def _on_total_changed(self, val: float):
        # When user edits total: back-calculate price
        if self._total_editing:
            return
        qty = self._qty_spin.value()
        disc = self._disc_spin.value()
        if qty > 0 and (1 - disc / 100) > 0:
            self._total_editing = True
            try:
                raw_price = val / qty / (1 - disc / 100)
                self._price_spin.setValue(round(raw_price, 2))
            finally:
                self._total_editing = False

    def _recalc_total(self):
        qty = self._qty_spin.value()
        price = self._price_spin.value()
        disc = self._disc_spin.value()
        total = qty * price * (1 - disc / 100)
        self._total_editing = True
        try:
            self._total_spin.setValue(round(total, 2))
        finally:
            self._total_editing = False

    # ── Add / edit line ────────────────────────────────────────────────────────

    def _add_line(self):
        if not self._current_item and self._editing_row < 0:
            QMessageBox.warning(self, "No Item", "Scan or search an item first.")
            return

        qty   = self._qty_spin.value()
        price = self._price_spin.value()
        disc  = self._disc_spin.value()
        total = self._total_spin.value()

        if qty <= 0:
            QMessageBox.warning(self, "Qty", "Quantity must be greater than 0.")
            return

        if self._editing_row >= 0:
            # Update existing row
            row = self._editing_row
            self._lines[row]["qty"]   = qty
            self._lines[row]["price"] = price
            self._lines[row]["disc"]  = disc
            self._lines[row]["total"] = total
            self._editing_row = -1
            self._add_btn.setText("✓  Add")
            self._cancel_edit_btn.hide()
        else:
            item = self._current_item
            self._lines.append({
                "item_id":  item.item_id,
                "code":     item.code,
                "barcode":  item.barcode,
                "desc":     item.description,
                "qty":      qty,
                "price":    price,
                "disc":     disc,
                "total":    total,
                "vat_pct":  item.vat_pct,
            })

        self._refresh_table()
        self._clear_entry()
        self._bc_input.setFocus()

    def _cancel_edit(self):
        self._editing_row = -1
        self._add_btn.setText("✓  Add")
        self._cancel_edit_btn.hide()
        self._clear_entry()
        self._bc_input.setFocus()

    def _clear_entry(self):
        self._bc_input.clear()
        self._item_desc_label.setText("")
        self._clear_info_bar()
        self._box_spin.blockSignals(True)
        self._box_spin.setValue(0)
        self._box_spin.blockSignals(False)
        self._set_box_enabled(1)
        self._qty_spin.setValue(0)
        self._price_spin.setValue(0)
        self._disc_spin.setValue(0)
        self._total_spin.setValue(0)
        self._current_item = None
        self._current_pack_qty = 1

    # ── Table ──────────────────────────────────────────────────────────────────

    def _refresh_table(self):
        self._table_updating = True
        self._table.setRowCount(len(self._lines))
        grand = 0.0
        for i, ln in enumerate(self._lines):
            grand += ln["total"]
            for col, (txt, align) in enumerate([
                (str(i + 1),                Qt.AlignCenter),
                (ln["code"],                Qt.AlignCenter),
                (ln["barcode"],             Qt.AlignCenter),
                (ln["desc"],                Qt.AlignLeft | Qt.AlignVCenter),
                (f"{ln['qty']:,.3f}",       Qt.AlignCenter),
                (f"{ln['price']:,.2f}",     Qt.AlignRight | Qt.AlignVCenter),
                (f"{ln['disc']:,.1f}%",     Qt.AlignCenter),
                (f"{ln['total']:,.2f}",     Qt.AlignRight | Qt.AlignVCenter),
            ]):
                cell = QTableWidgetItem(txt)
                cell.setTextAlignment(align)
                if col == self.COL_TOT:
                    cell.setFont(QFont("", -1, QFont.Bold))
                self._table.setItem(i, col, cell)

            # Delete button
            del_btn = QPushButton("✕")
            del_btn.setFixedSize(24, 24)
            del_btn.setStyleSheet(
                "QPushButton{background:#c62828;color:#fff;border:none;border-radius:3px;"
                "font-size:11px;font-weight:700;}"
                "QPushButton:hover{background:#8b0000;}"
            )
            del_btn.clicked.connect(lambda _, r=i: self._delete_line(r))
            self._table.setCellWidget(i, self.COL_DEL, del_btn)

        self._table_updating = False

        subtotal = sum(ln["qty"] * ln["price"] for ln in self._lines)
        discount = subtotal - grand
        currency = self._cur_combo.currentText()
        if currency == "LBP":
            fmt = lambda v: f"ل.ل {v:,.0f}"
        else:
            fmt = lambda v: f"${v:,.2f}"
        self._grand_lbl.setText(fmt(grand))
        self._subtotal_lbl.setText(fmt(subtotal))
        self._discount_lbl.setText(fmt(discount))
        self._lines_lbl.setText(f"{len(self._lines)} line{'s' if len(self._lines) != 1 else ''}")

    def _on_row_double_clicked(self, index):
        row = index.row()
        if 0 <= row < len(self._lines):
            ln = self._lines[row]
            # Re-fill entry bar for editing
            self._qty_spin.setValue(ln["qty"])
            self._price_spin.setValue(ln["price"])
            self._disc_spin.setValue(ln["disc"])
            self._recalc_total()
            self._item_desc_label.setText(ln["desc"])
            self._item_desc_label.setStyleSheet(
                "color:#e65100;font-weight:700;min-width:160px;font-size:12px;"
            )
            self._editing_row = row
            self._add_btn.setText("✓  Update")
            self._cancel_edit_btn.show()
            # Fake a current_item so _add_line doesn't bail
            self._current_item = SalesLineItem(
                item_id=ln["item_id"], code=ln["code"], barcode=ln["barcode"],
                description=ln["desc"], pack_qty=1, qty=ln["qty"],
                price=ln["price"], disc_pct=ln["disc"], vat_pct=ln["vat_pct"],
                total=ln["total"],
            )
            self._qty_spin.setFocus()
            self._qty_spin.selectAll()

    def _delete_line(self, row: int):
        if 0 <= row < len(self._lines):
            self._lines.pop(row)
            self._refresh_table()

    # ── Save ───────────────────────────────────────────────────────────────────

    def _save_invoice(self):
        if not self._lines:
            QMessageBox.warning(self, "Empty", "Add at least one line item.")
            return

        grand = sum(ln["total"] for ln in self._lines)
        currency = self._cur_combo.currentText()
        currency_sym = "ل.ل" if currency == "LBP" else "$"

        confirm = QMessageBox.question(
            self, "Confirm Save",
            f"Save invoice  {self._inv_no_label.text()}\n"
            f"{len(self._lines)} lines · Total: {currency_sym} {grand:,.0f}\n\n"
            f"This will deduct stock from the selected warehouse.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        user = AuthService.current_user()
        operator_id = user.id if user else ""
        wh_id = self._wh_combo.currentData() or ""
        inv_date = self._date_edit.date().toString("yyyy-MM-dd")
        payment = self._pay_combo.currentText()
        notes = self._notes_input.text().strip()
        customer_id = self._customer["id"] if self._customer else ""
        inv_number = self._inv_no_label.text()

        lines = [
            SalesLineItem(
                item_id=ln["item_id"],
                code=ln["code"],
                barcode=ln["barcode"],
                description=ln["desc"],
                pack_qty=1,
                qty=ln["qty"],
                price=ln["price"],
                disc_pct=ln["disc"],
                vat_pct=ln["vat_pct"],
                total=ln["total"],
            )
            for ln in self._lines
        ]

        ok, result = SalesInvoiceService.save_invoice(
            customer_id=customer_id,
            operator_id=operator_id,
            warehouse_id=wh_id,
            invoice_number=inv_number,
            invoice_date=inv_date,
            currency=currency,
            lines=lines,
            payment_mode=payment,
            notes=notes,
        )

        if ok:
            QMessageBox.information(
                self, "Saved",
                f"Invoice {inv_number} saved.\n"
                f"{len(lines)} items · {currency_sym} {grand:,.0f}",
            )
            self._lines.clear()
            self._refresh_table()
            self._notes_input.clear()
            # Refresh shown number for current warehouse
            self._refresh_invoice_number()
            self._bc_input.setFocus()
        else:
            QMessageBox.critical(self, "Error", f"Failed to save:\n{result}")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _clear_all(self):
        if self._lines:
            if QMessageBox.question(
                self, "Clear", "Clear all lines?", QMessageBox.Yes | QMessageBox.No
            ) != QMessageBox.Yes:
                return
        self._lines.clear()
        self._refresh_table()
        self._clear_entry()
        self._bc_input.setFocus()

    def _print_current(self):
        if not self._lines:
            QMessageBox.information(self, "Print", "No items to print.")
            return
        from ui.screens.sales.sales_invoice_list import _print_invoice
        cur = self._cur_combo.currentText()
        sym = "ل.ل" if cur == "LBP" else "$"
        wh_id = self._wh_combo.currentData() or ""
        wh_name = self._wh_combo.currentText()
        inv_data = {
            "invoice_number": self._inv_no_label.text(),
            "source": "manual",
            "customer_name": self._customer["name"] if self._customer else "Walk-In",
            "warehouse_name": wh_name,
            "warehouse_num": "",
            "cashier": "",
            "invoice_date": self._date_edit.date().toString("yyyy-MM-dd"),
            "currency": cur,
            "total": sum(ln["total"] for ln in self._lines),
            "subtotal": sum(ln["total"] for ln in self._lines),
            "discount_value": 0.0,
            "vat_value": 0.0,
            "payment_status": self._pay_combo.currentText(),
            "status": "draft",
            "notes": self._notes_input.text().strip(),
            "lines": [
                {
                    "item_name": ln["desc"],
                    "barcode": ln["barcode"],
                    "qty": ln["qty"],
                    "price": ln["price"],
                    "disc_pct": ln["disc"],
                    "total": ln["total"],
                    "warehouse_num": "",
                }
                for ln in self._lines
            ],
        }
        _print_invoice(inv_data, self)

    def load_for_edit(self, inv_data: dict):
        """Pre-load an existing invoice for editing (original already voided by caller)."""
        self._load_invoice_data(inv_data)

    def load_for_duplicate(self, inv_data: dict):
        """Pre-load an invoice as a duplicate (original untouched, new number assigned)."""
        self._load_invoice_data(inv_data)

    def _load_invoice_data(self, d: dict):
        """Populate header and lines from an invoice dict."""
        from services.item_service import ItemService

        # Warehouse
        wh_id = d.get("warehouse_id", "")
        for i in range(self._wh_combo.count()):
            if self._wh_combo.itemData(i) == wh_id:
                self._wh_combo.setCurrentIndex(i)
                break

        # Currency
        cur = d.get("currency", "LBP")
        idx = self._cur_combo.findText(cur)
        if idx >= 0:
            self._cur_combo.setCurrentIndex(idx)

        # Customer
        cust_id = d.get("customer_id", "")
        if cust_id:
            from database.engine import get_session, init_db
            from database.models.parties import Customer
            init_db()
            s = get_session()
            try:
                c = s.query(Customer).filter_by(id=cust_id).first()
                if c:
                    self._customer = {"id": c.id, "name": c.name, "phone": "", "balance": c.balance}
                    self._cust_name_label.setText(c.name)
            finally:
                s.close()

        # Notes
        self._notes_input.setText(d.get("notes", ""))

        # Lines
        self._lines.clear()
        for li in d.get("lines", []):
            self._lines.append({
                "item_id": li["item_id"],
                "code": "",
                "barcode": li.get("barcode", ""),
                "desc": li["item_name"],
                "qty": li["qty"],
                "price": li["price"],
                "disc": li.get("disc_pct", 0.0),
                "total": li["total"],
                "vat_pct": li.get("vat_pct", 0.0),
            })
        self._refresh_table()
        self._bc_input.setFocus()

    def _confirm_back(self):
        if self._lines:
            if QMessageBox.question(
                self, "Discard?", "Discard unsaved lines and go back?",
                QMessageBox.Yes | QMessageBox.No,
            ) != QMessageBox.Yes:
                return
        self.back.emit()
