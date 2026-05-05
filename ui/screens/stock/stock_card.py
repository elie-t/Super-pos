"""Stock Card — detailed movement history for a selected item."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QComboBox, QFrame, QSizePolicy,
    QDateEdit,
)
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QColor, QFont
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog

from services.stock_card_service import StockCardService
from services.item_service import ItemService


# ── column indices ──────────────────────────────────────────────────────────
COL_DATE    = 0
COL_TYPE    = 1
COL_INV     = 2
COL_QTY     = 3
COL_PRICE   = 4
COL_DISC    = 5
COL_TOTAL   = 6
COL_WH      = 7
COL_PARTY   = 8
COL_CASHIER = 9
COL_BALANCE = 10
COL_VIEW    = 11

HEADERS = ["Date", "Type", "Invoice #", "Qty", "Price", "Disc%",
           "Total", "Warehouse", "Customer / Supplier", "Cashier", "Balance", ""]

IN_COLOR  = QColor("#e8f5e9")
OUT_COLOR = QColor("#ffebee")
OPN_COLOR = QColor("#bbdefb")   # opening row (light blue)


class _StatCard(QFrame):
    """Small summary stat card for the footer bar."""
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "QFrame{background:#f5f7fa;border:1px solid #d0d8e8;border-radius:6px;padding:4px 8px;}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)
        self._lbl = QLabel(label)
        self._lbl.setStyleSheet("font-size:10px; color:#5a6070; font-weight:600;")
        self._val = QLabel("—")
        self._val.setStyleSheet("font-size:14px; font-weight:700; color:#1a3a5c;")
        layout.addWidget(self._lbl)
        layout.addWidget(self._val)

    def set_value(self, text: str):
        self._val.setText(text)


class StockCardScreen(QWidget):
    back = Signal()

    def __init__(self, item_id: str = "", parent=None):
        super().__init__(parent)
        self._item: dict | None = None   # {id, code, name, barcode}
        self._build_ui()
        if item_id:
            self._load_by_id(item_id)

    # ── UI construction ─────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # ── Title bar ───────────────────────────────────────────────────────
        top = QHBoxLayout()
        title = QLabel("Stock Card")
        title.setObjectName("sectionTitle")
        back_btn = QPushButton("← Back")
        back_btn.setObjectName("secondaryBtn")
        back_btn.setFixedHeight(32)
        back_btn.clicked.connect(self.back.emit)
        top.addWidget(back_btn)
        top.addWidget(title)
        top.addStretch()
        root.addLayout(top)

        # ── Filter panel ────────────────────────────────────────────────────
        filter_frame = QFrame()
        filter_frame.setFrameShape(QFrame.StyledPanel)
        filter_frame.setStyleSheet(
            "QFrame{background:#f0f4fa;border:1px solid #c8d8ec;border-radius:6px;}"
        )
        ff = QVBoxLayout(filter_frame)
        ff.setContentsMargins(12, 10, 12, 10)
        ff.setSpacing(8)

        # Row 1 — item search
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        row1.addWidget(QLabel("Barcode:"))
        self._bc_edit = QLineEdit()
        self._bc_edit.setPlaceholderText("Scan or type barcode…")
        self._bc_edit.setFixedHeight(30)
        self._bc_edit.setFixedWidth(180)
        self._bc_edit.returnPressed.connect(lambda: self._find_item(self._bc_edit.text()))
        row1.addWidget(self._bc_edit)

        row1.addWidget(QLabel("Code:"))
        self._code_edit = QLineEdit()
        self._code_edit.setPlaceholderText("Item code")
        self._code_edit.setFixedHeight(30)
        self._code_edit.setFixedWidth(120)
        self._code_edit.returnPressed.connect(lambda: self._find_item(self._code_edit.text()))
        row1.addWidget(self._code_edit)

        row1.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Item name  (Ctrl+Enter = list)")
        self._name_edit.setFixedHeight(30)
        self._name_edit.setFixedWidth(220)
        self._name_edit.returnPressed.connect(lambda: self._find_item(self._name_edit.text()))
        self._name_edit.installEventFilter(self)
        row1.addWidget(self._name_edit)

        find_btn = QPushButton("🔍 Find")
        find_btn.setObjectName("primaryBtn")
        find_btn.setFixedHeight(30)
        find_btn.setFixedWidth(80)
        find_btn.clicked.connect(self._find_from_inputs)
        row1.addWidget(find_btn)

        self._found_lbl = QLabel("")
        self._found_lbl.setStyleSheet("font-weight:700; color:#1a6cb5; font-size:13px;")
        row1.addWidget(self._found_lbl)
        row1.addStretch()
        ff.addLayout(row1)

        # Row 2 — date range, warehouse, category, action buttons
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        row2.addWidget(QLabel("From:"))
        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate().addMonths(-1))
        self._date_from.setFixedHeight(30)
        self._date_from.setMinimumWidth(110)
        self._date_from.setDisplayFormat("dd/MM/yyyy")
        row2.addWidget(self._date_from)

        row2.addWidget(QLabel("To:"))
        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setFixedHeight(30)
        self._date_to.setMinimumWidth(110)
        self._date_to.setDisplayFormat("dd/MM/yyyy")
        row2.addWidget(self._date_to)

        row2.addWidget(QLabel("Warehouse:"))
        self._wh_combo = QComboBox()
        self._wh_combo.setFixedHeight(30)
        self._wh_combo.setMinimumWidth(140)
        self._populate_warehouses()
        row2.addWidget(self._wh_combo)

        row2.addWidget(QLabel("Category:"))
        self._cat_combo = QComboBox()
        self._cat_combo.setFixedHeight(30)
        self._cat_combo.setMinimumWidth(140)
        self._populate_categories()
        row2.addWidget(self._cat_combo)

        row2.addStretch()

        gen_btn = QPushButton("▶  Generate")
        gen_btn.setObjectName("successBtn")
        gen_btn.setFixedHeight(32)
        gen_btn.setFixedWidth(110)
        gen_btn.clicked.connect(self._generate)
        row2.addWidget(gen_btn)

        print_btn = QPushButton("🖨 Print")
        print_btn.setObjectName("secondaryBtn")
        print_btn.setFixedHeight(32)
        print_btn.setFixedWidth(90)
        print_btn.clicked.connect(self._print_card)
        row2.addWidget(print_btn)

        ff.addLayout(row2)
        root.addWidget(filter_frame)

        # ── Item info bar ────────────────────────────────────────────────────
        self._item_bar = QLabel("")
        self._item_bar.setStyleSheet(
            "background:#e3f2fd;border:1px solid #90caf9;border-radius:4px;"
            "padding:6px 14px;font-size:13px;"
        )
        self._item_bar.hide()
        root.addWidget(self._item_bar)

        # ── Table ────────────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(len(HEADERS))
        self._table.setHorizontalHeaderLabels(HEADERS)
        self._table.setAlternatingRowColors(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        self._table.setStyleSheet("QTableWidget{font-size:12px;}")

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(COL_DATE,    QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_TYPE,    QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_INV,     QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_QTY,     QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_PRICE,   QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_DISC,    QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_TOTAL,   QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_WH,      QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_PARTY,   QHeaderView.Stretch)
        hdr.setSectionResizeMode(COL_CASHIER, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_BALANCE, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(COL_VIEW,    QHeaderView.Fixed)
        self._table.setColumnWidth(COL_VIEW, 60)
        root.addWidget(self._table)

        # ── Summary footer ────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setSpacing(10)
        self._sc_opening_qty   = _StatCard("Opening Qty")
        self._sc_opening_val   = _StatCard("Opening Value")
        self._sc_in_qty        = _StatCard("Stock In")
        self._sc_in_val        = _StatCard("Value In")
        self._sc_out_qty       = _StatCard("Stock Out")
        self._sc_out_val       = _StatCard("Value Out")
        self._sc_current       = _StatCard("Current Stock")

        for sc in (self._sc_opening_qty, self._sc_opening_val,
                   self._sc_in_qty, self._sc_in_val,
                   self._sc_out_qty, self._sc_out_val,
                   self._sc_current):
            sc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            footer.addWidget(sc)

        root.addLayout(footer)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _populate_warehouses(self):
        self._wh_combo.clear()
        self._wh_combo.addItem("All Warehouses", "")
        for wh_id, wh_name, _is_def, _num, _cust in ItemService.get_warehouses():
            self._wh_combo.addItem(wh_name, wh_id)

    def _populate_categories(self):
        self._cat_combo.clear()
        self._cat_combo.addItem("All Categories", "")
        for cat_id, cat_name, *_ in ItemService.get_categories():
            self._cat_combo.addItem(cat_name, cat_id)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self._name_edit and event.type() == QEvent.Type.KeyPress:
            if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self._find_item_list(self._name_edit.text())
                return True
        return super().eventFilter(obj, event)

    def _find_item_list(self, query: str):
        """Search by name and show a picker if multiple results."""
        if not query.strip():
            return
        results = ItemService.search_items(query=query.strip(), limit=100)
        if not results:
            self._found_lbl.setText("✘  No items found")
            self._found_lbl.setStyleSheet("font-weight:700; color:#c62828; font-size:13px;")
            return
        if len(results) == 1:
            self._apply_item(results[0].id, results[0].code, results[0].name, results[0].barcode or "")
            return
        self._show_picker(results)

    def _show_picker(self, results):
        from PySide6.QtWidgets import QDialog, QListWidget, QListWidgetItem, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Select Item")
        dlg.resize(560, 400)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(f"{len(results)} matches — select one:"))

        filter_box = QLineEdit()
        filter_box.setPlaceholderText("Filter…")
        filter_box.setFixedHeight(30)
        layout.addWidget(filter_box)

        lst = QListWidget()
        all_items = []
        for item in results:
            text = f"[{item.code}]  {item.name}"
            li = QListWidgetItem(text)
            li.setData(Qt.UserRole, (item.id, item.code, item.name, item.barcode or ""))
            lst.addItem(li)
            all_items.append((text.lower(), li.data(Qt.UserRole), text))
        lst.setCurrentRow(0)
        layout.addWidget(lst, 1)

        def _filter(text):
            lst.clear()
            for low, data, display in all_items:
                if text.lower() in low:
                    li = QListWidgetItem(display)
                    li.setData(Qt.UserRole, data)
                    lst.addItem(li)
            if lst.count():
                lst.setCurrentRow(0)

        filter_box.textChanged.connect(_filter)

        # Arrow keys in the filter box move the list selection
        def _filter_key(event):
            from PySide6.QtCore import QEvent
            from PySide6.QtGui import QKeyEvent
            key = event.key()
            if key == Qt.Key.Key_Down:
                row = lst.currentRow()
                if row < lst.count() - 1:
                    lst.setCurrentRow(row + 1)
                return True
            elif key == Qt.Key.Key_Up:
                row = lst.currentRow()
                if row > 0:
                    lst.setCurrentRow(row - 1)
                return True
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                dlg.accept()
                return True
            return False

        original_key_press = filter_box.keyPressEvent
        def _patched_key_press(event):
            if not _filter_key(event):
                original_key_press(event)
        filter_box.keyPressEvent = _patched_key_press

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        lst.doubleClicked.connect(lambda: dlg.accept())

        filter_box.setFocus()
        if dlg.exec() == QDialog.Accepted and lst.currentItem():
            item_id, code, name, barcode = lst.currentItem().data(Qt.UserRole)
            self._apply_item(item_id, code, name, barcode)

    def _apply_item(self, item_id: str, code: str, name: str, barcode: str):
        self._item = {"id": item_id, "code": code, "name": name, "barcode": barcode}
        self._bc_edit.setText(barcode)
        self._code_edit.setText(code)
        self._name_edit.setText(name)
        self._found_lbl.setText(f"✔  {code} — {name}")
        self._found_lbl.setStyleSheet("font-weight:700; color:#2e7d32; font-size:13px;")

    def _find_from_inputs(self):
        q = (self._bc_edit.text().strip() or
             self._code_edit.text().strip() or
             self._name_edit.text().strip())
        if q:
            self._find_item(q)

    def _find_item(self, query: str):
        if not query:
            return
        result = StockCardService.find_item(query)
        if result:
            self._apply_item(result["id"], result["code"], result["name"], result["barcode"])
        else:
            self._item = None
            self._found_lbl.setText("✘  Item not found — try Ctrl+Enter to search by name")
            self._found_lbl.setStyleSheet("font-weight:700; color:#c62828; font-size:13px;")

    def _load_by_id(self, item_id: str):
        from services.item_service import ItemService
        detail = ItemService.get_item_detail(item_id)
        if detail:
            self._item = {"id": detail.id, "code": detail.code,
                          "name": detail.name, "barcode": ""}
            self._code_edit.setText(detail.code)
            self._name_edit.setText(detail.name)
            self._found_lbl.setText(f"✔  {detail.code} — {detail.name}")
            self._found_lbl.setStyleSheet("font-weight:700; color:#2e7d32; font-size:13px;")
            self._generate()

    # ── Generate ─────────────────────────────────────────────────────────────

    def _generate(self):
        if not self._item:
            self._found_lbl.setText("Select an item first.")
            self._found_lbl.setStyleSheet("font-weight:700; color:#c62828;")
            return

        date_from = self._date_from.date().toString("yyyy-MM-dd")
        date_to   = self._date_to.date().toString("yyyy-MM-dd")
        wh_id     = self._wh_combo.currentData() or ""

        data = StockCardService.get_stock_card(
            self._item["id"], date_from, date_to, wh_id
        )
        self._data = data
        self._populate_table(data)
        self._populate_footer(data)
        self._update_item_bar(data)

    def _update_item_bar(self, data: dict):
        item = self._item
        stock_str = f"{data['current_stock']:,.2f}".rstrip("0").rstrip(".")
        self._item_bar.setText(
            f"<b>[{item['code']}]  {item['name']}</b>"
            f"    Current Stock: <b>{stock_str}</b> units"
        )
        self._item_bar.show()

    def _populate_table(self, data: dict):
        mvs = data["movements"]

        # +1 for the opening balance row
        self._table.setRowCount(len(mvs) + 1)

        # Opening row
        oqty = data["opening_qty"]
        self._set_row(0, {
            "date": "Opening Balance", "trans": "", "invoice_no": "",
            "qty": None, "price": None, "disc_pct": None, "total": None,
            "warehouse": "", "party": "", "cashier": "",
            "running_stock": oqty, "movement_type": "opening",
            "ref_type": "", "ref_id": "", "inv_found": False,
        }, color=OPN_COLOR, bold=True)

        for i, mv in enumerate(mvs):
            qty = mv["qty"]
            color = IN_COLOR if qty >= 0 else OUT_COLOR
            self._set_row(i + 1, mv, color=color)

    def _set_row(self, row: int, mv: dict, color: QColor, bold: bool = False):
        qty     = mv["qty"]
        price   = mv["price"]
        disc    = mv["disc_pct"]
        total   = mv["total"]
        balance = mv["running_stock"]

        def cell(text: str, align=Qt.AlignLeft | Qt.AlignVCenter) -> QTableWidgetItem:
            it = QTableWidgetItem(str(text) if text is not None else "")
            it.setBackground(color)
            it.setTextAlignment(align)
            if bold:
                f = it.font(); f.setBold(True); it.setFont(f)
            return it

        right = Qt.AlignRight | Qt.AlignVCenter

        self._table.setItem(row, COL_DATE,    cell(mv["date"]))
        self._table.setItem(row, COL_TYPE,    cell(mv["trans"]))
        self._table.setItem(row, COL_INV,     cell(mv["invoice_no"]))

        # Qty
        qty_cell = cell(f"{qty:+.2f}" if qty is not None else "", right)
        if qty is not None:
            qty_cell.setForeground(QColor("#2e7d32") if qty >= 0 else QColor("#c62828"))
        self._table.setItem(row, COL_QTY, qty_cell)

        self._table.setItem(row, COL_PRICE, cell(
            f"{price:,.2f}" if price else "", right))
        self._table.setItem(row, COL_DISC,  cell(
            f"{disc:.1f}%" if disc else "", right))
        self._table.setItem(row, COL_TOTAL, cell(
            f"{total:,.2f}" if total else "", right))
        self._table.setItem(row, COL_WH,      cell(mv["warehouse"]))
        self._table.setItem(row, COL_PARTY,   cell(mv["party"]))
        self._table.setItem(row, COL_CASHIER, cell(mv["cashier"]))

        # Running balance
        bal_cell = cell(f"{balance:,.2f}" if balance is not None else "", right)
        bal_cell.setForeground(QColor("#1a6cb5"))
        f = bal_cell.font(); f.setBold(True); bal_cell.setFont(f)
        self._table.setItem(row, COL_BALANCE, bal_cell)

        # View button — only for rows that have a reference
        ref_type = mv.get("ref_type", "")
        ref_id   = mv.get("ref_id", "")
        if ref_type and ref_id and mv.get("movement_type") != "opening":
            btn = QPushButton("View")
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                "QPushButton{background:#1a3a5c;color:#fff;border:none;"
                "border-radius:3px;font-size:11px;font-weight:700;}"
                "QPushButton:hover{background:#1a6cb5;}"
            )
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, rt=ref_type, rid=ref_id: self._open_reference(rt, rid))
            self._table.setCellWidget(row, COL_VIEW, btn)
        else:
            self._table.setItem(row, COL_VIEW, cell(""))

    def _populate_footer(self, data: dict):
        self._sc_opening_qty.set_value(f"{data['opening_qty']:,.2f}")
        self._sc_opening_val.set_value(f"{data['opening_value']:,.2f}")
        self._sc_in_qty.set_value(f"{data['stock_in']:,.2f}")
        self._sc_in_val.set_value(f"{data['value_in']:,.2f}")
        self._sc_out_qty.set_value(f"{data['stock_out']:,.2f}")
        self._sc_out_val.set_value(f"{data['value_out']:,.2f}")
        self._sc_current.set_value(f"{data['current_stock']:,.2f}")

    # ── View reference ────────────────────────────────────────────────────────

    def _open_reference(self, ref_type: str, ref_id: str):
        if ref_type == "sales_invoice":
            self._open_sales_invoice(ref_id)
        elif ref_type == "purchase_invoice":
            self._open_purchase_invoice(ref_id)
        elif ref_type == "transfer":
            self._open_transfer(ref_id)
        elif ref_type == "inventory":
            self._open_inventory(ref_id)

    def _open_sales_invoice(self, inv_id: str):
        from services.sales_invoice_service import SalesInvoiceService
        from ui.screens.sales.sales_invoice_list import InvoiceDetailDialog
        inv_data = SalesInvoiceService.get_invoice(inv_id)
        if inv_data:
            InvoiceDetailDialog(inv_data, self).exec()
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Not Found",
                                    "Invoice not found in local database.\n"
                                    "It may not have synced to this device yet.")

    def _open_purchase_invoice(self, inv_id: str):
        from database.engine import get_session, init_db
        from database.models.invoices import PurchaseInvoice, PurchaseInvoiceItem
        from database.models.parties import Supplier
        from database.models.users import User
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout
        init_db()
        session = get_session()
        try:
            inv = session.query(PurchaseInvoice).filter_by(id=inv_id).first()
            if not inv:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Not Found", "Purchase invoice not found in local database.")
                return
            sup = session.query(Supplier).filter_by(id=inv.supplier_id).first()
            op  = session.query(User).filter_by(id=inv.operator_id).first()
            items = session.query(PurchaseInvoiceItem).filter_by(invoice_id=inv_id).all()

            dlg = QDialog(self)
            dlg.setWindowTitle(f"Purchase Invoice  {inv.invoice_number}")
            dlg.setMinimumSize(700, 400)
            lay = QVBoxLayout(dlg)

            info = QLabel(
                f"<b>Invoice #:</b> {inv.invoice_number} &nbsp;&nbsp; "
                f"<b>Date:</b> {inv.invoice_date} &nbsp;&nbsp; "
                f"<b>Supplier:</b> {sup.name if sup else '—'} &nbsp;&nbsp; "
                f"<b>Operator:</b> {op.full_name if op else '—'} &nbsp;&nbsp; "
                f"<b>Total:</b> {inv.total:,.2f}"
            )
            info.setStyleSheet("padding:8px;font-size:12px;background:#f0f4f8;border-bottom:1px solid #ccc;")
            info.setWordWrap(True)
            lay.addWidget(info)

            tbl = QTableWidget(len(items), 5)
            tbl.setHorizontalHeaderLabels(["Item", "Qty", "Cost", "Disc%", "Total"])
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.verticalHeader().setVisible(False)
            tbl.setEditTriggers(QTableWidget.NoEditTriggers)
            for r, it in enumerate(items):
                tbl.setItem(r, 0, QTableWidgetItem(it.item_name or ""))
                tbl.setItem(r, 1, QTableWidgetItem(f"{it.quantity:,.3f}"))
                tbl.setItem(r, 2, QTableWidgetItem(f"{it.unit_cost:,.2f}"))
                tbl.setItem(r, 3, QTableWidgetItem(f"{(it.discount_pct or 0):.1f}%"))
                tbl.setItem(r, 4, QTableWidgetItem(f"{(it.line_total or 0):,.2f}"))
            lay.addWidget(tbl, 1)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dlg.accept)
            bl = QHBoxLayout()
            bl.addStretch()
            bl.addWidget(close_btn)
            lay.addLayout(bl)
            dlg.exec()
        finally:
            session.close()

    def _open_transfer(self, transfer_id: str):
        from database.engine import get_session, init_db
        from database.models.stock import WarehouseTransfer, WarehouseTransferItem
        from database.models.items import Warehouse
        from database.models.users import User
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout
        init_db()
        session = get_session()
        try:
            t = session.query(WarehouseTransfer).filter_by(id=transfer_id).first()
            if not t:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Not Found", "Transfer not found in local database.")
                return
            src = session.query(Warehouse).filter_by(id=t.from_warehouse_id).first()
            dst = session.query(Warehouse).filter_by(id=t.to_warehouse_id).first()
            op  = session.query(User).filter_by(id=t.operator_id).first()
            items = session.query(WarehouseTransferItem).filter_by(transfer_id=transfer_id).all()

            dlg = QDialog(self)
            dlg.setWindowTitle(f"Transfer  {t.transfer_number or transfer_id[:8]}")
            dlg.setMinimumSize(600, 350)
            lay = QVBoxLayout(dlg)

            info = QLabel(
                f"<b>Transfer #:</b> {t.transfer_number or '—'} &nbsp;&nbsp; "
                f"<b>Date:</b> {str(t.created_at)[:10] if t.created_at else '—'} &nbsp;&nbsp; "
                f"<b>From:</b> {src.name if src else '—'} &nbsp;&nbsp; "
                f"<b>To:</b> {dst.name if dst else '—'} &nbsp;&nbsp; "
                f"<b>Operator:</b> {op.full_name if op else '—'}"
            )
            info.setStyleSheet("padding:8px;font-size:12px;background:#f0f4f8;border-bottom:1px solid #ccc;")
            info.setWordWrap(True)
            lay.addWidget(info)

            tbl = QTableWidget(len(items), 3)
            tbl.setHorizontalHeaderLabels(["Item", "Qty", "Unit Cost"])
            tbl.horizontalHeader().setStretchLastSection(True)
            tbl.verticalHeader().setVisible(False)
            tbl.setEditTriggers(QTableWidget.NoEditTriggers)
            for r, it in enumerate(items):
                tbl.setItem(r, 0, QTableWidgetItem(it.item_name or ""))
                tbl.setItem(r, 1, QTableWidgetItem(f"{it.quantity:,.3f}"))
                tbl.setItem(r, 2, QTableWidgetItem(f"{(it.unit_cost or 0):,.2f}"))
            lay.addWidget(tbl, 1)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dlg.accept)
            bl = QHBoxLayout()
            bl.addStretch()
            bl.addWidget(close_btn)
            lay.addLayout(bl)
            dlg.exec()
        finally:
            session.close()

    def _open_inventory(self, session_id: str):
        from PySide6.QtWidgets import QMessageBox
        try:
            from database.engine import get_session, init_db
            from database.models.inventory import InventorySession
            init_db()
            s = get_session()
            inv = s.query(InventorySession).filter_by(id=session_id).first()
            s.close()
            if inv:
                QMessageBox.information(self, "Inventory Session",
                                        f"Session #: {inv.session_number or session_id[:8]}\n"
                                        f"Date: {str(inv.created_at)[:10] if inv.created_at else '—'}\n"
                                        f"Status: {inv.status or '—'}")
            else:
                QMessageBox.information(self, "Not Found", "Inventory session not found in local database.")
        except Exception as e:
            QMessageBox.information(self, "Not Found", f"Could not load inventory session:\n{e}")

    # ── Print ─────────────────────────────────────────────────────────────────

    def _print_card(self):
        if not self._item or not hasattr(self, "_data"):
            return
        data  = self._data
        item  = self._item
        mvs   = data["movements"]

        date_from = self._date_from.date().toString("dd/MM/yyyy")
        date_to   = self._date_to.date().toString("dd/MM/yyyy")

        rows_html = ""
        # Opening row
        rows_html += (
            f"<tr style='background:#fff9c4;font-weight:bold;'>"
            f"<td>Opening Balance</td><td colspan='9'></td>"
            f"<td align='right'>{data['opening_qty']:,.2f}</td></tr>"
        )
        for mv in mvs:
            bg      = "#e8f5e9" if mv["qty"] >= 0 else "#ffebee"
            qty_s   = "{:+.2f}".format(mv["qty"])
            price_s = "{:,.2f}".format(mv["price"]) if mv["price"] else ""
            disc_s  = "{:.1f}%".format(mv["disc_pct"]) if mv["disc_pct"] else ""
            total_s = "{:,.2f}".format(mv["total"]) if mv["total"] else ""
            bal_s   = "{:,.2f}".format(mv["running_stock"])
            rows_html += (
                "<tr style='background:{};'>".format(bg) +
                "<td>{}</td>".format(mv["date"]) +
                "<td>{}</td>".format(mv["trans"]) +
                "<td>{}</td>".format(mv["invoice_no"]) +
                "<td align='right'>{}</td>".format(qty_s) +
                "<td align='right'>{}</td>".format(price_s) +
                "<td align='right'>{}</td>".format(disc_s) +
                "<td align='right'>{}</td>".format(total_s) +
                "<td>{}</td>".format(mv["warehouse"]) +
                "<td>{}</td>".format(mv["party"]) +
                "<td>{}</td>".format(mv["cashier"]) +
                "<td align='right'><b>{}</b></td>".format(bal_s) +
                "</tr>"
            )

        html = f"""
        <html><body style='font-family:Arial;font-size:11px;'>
        <h2 style='text-align:center;'>Stock Card</h2>
        <p><b>Item:</b> [{item['code']}] {item['name']} &nbsp;&nbsp;
           <b>Period:</b> {date_from} → {date_to}</p>
        <table border='1' cellspacing='0' cellpadding='4' width='100%'>
          <thead style='background:#1a3a5c;color:white;'>
            <tr>
              <th>Date</th><th>Type</th><th>Invoice</th><th>Qty</th>
              <th>Price</th><th>Disc%</th><th>Total</th>
              <th>Warehouse</th><th>Party</th><th>Cashier</th><th>Balance</th>
            </tr>
          </thead>
          <tbody>{rows_html}</tbody>
        </table>
        <br/>
        <table border='0' cellspacing='4' cellpadding='4'>
          <tr>
            <td><b>Opening Qty:</b> {data['opening_qty']:,.2f}</td>
            <td><b>Stock In:</b> {data['stock_in']:,.2f}</td>
            <td><b>Value In:</b> {data['value_in']:,.2f}</td>
            <td><b>Stock Out:</b> {data['stock_out']:,.2f}</td>
            <td><b>Value Out:</b> {data['value_out']:,.2f}</td>
            <td><b>Current Stock:</b> {data['current_stock']:,.2f}</td>
          </tr>
        </table>
        </body></html>
        """

        from PySide6.QtGui import QTextDocument
        doc = QTextDocument()
        doc.setHtml(html)

        printer = QPrinter(QPrinter.HighResolution)
        preview = QPrintPreviewDialog(printer, self)
        preview.paintRequested.connect(doc.print_)
        preview.exec()
