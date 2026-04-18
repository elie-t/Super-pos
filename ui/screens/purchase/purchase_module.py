"""Purchase module container — routes between sub-screens."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QDialog, QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFrame, QLineEdit, QMessageBox,
    QComboBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from ui.screens.purchase.purchase_hub import PurchaseHub
from ui.screens.purchase.purchase_invoice import PurchaseInvoiceScreen
from services.purchase_service import PurchaseService


# ── New / Edit choice dialog ───────────────────────────────────────────────────

class InvoiceChoiceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Purchase Invoice")
        self.setFixedSize(320, 160)
        self.choice = None   # "new" | "edit"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        lbl = QLabel("What would you like to do?")
        lbl.setStyleSheet("font-size:14px; font-weight:600; color:#1a3a5c;")
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)

        new_btn = QPushButton("➕  New Invoice")
        new_btn.setFixedHeight(44)
        new_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;font-size:14px;font-weight:700;"
            "border:none;border-radius:6px;}"
            "QPushButton:hover{background:#1b5e20;}"
        )
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.clicked.connect(lambda: self._pick("new"))
        btn_row.addWidget(new_btn)

        edit_btn = QPushButton("📋  Edit Invoice")
        edit_btn.setFixedHeight(44)
        edit_btn.setStyleSheet(
            "QPushButton{background:#1a6cb5;color:#fff;font-size:14px;font-weight:700;"
            "border:none;border-radius:6px;}"
            "QPushButton:hover{background:#1a3a5c;}"
        )
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self._pick("edit"))
        btn_row.addWidget(edit_btn)

        lay.addLayout(btn_row)

    def _pick(self, choice: str):
        self.choice = choice
        self.accept()


# ── Invoice list screen (Edit mode) ───────────────────────────────────────────

class PurchaseInvoiceListScreen(QWidget):
    invoice_selected = Signal(str)   # emits invoice id
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._load()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background:#1a3a5c;")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(12, 0, 12, 0)
        back_btn = QPushButton("←  Back")
        back_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.15);color:#fff;border:1px solid rgba(255,255,255,0.3);"
            "border-radius:4px;padding:4px 12px;font-size:12px;}"
            "QPushButton:hover{background:rgba(255,255,255,0.3);}"
        )
        back_btn.setFixedHeight(28)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.back.emit)
        bar_lay.addWidget(back_btn)
        title = QLabel("Purchase Invoices")
        title.setStyleSheet("color:#fff;font-size:15px;font-weight:700;margin-left:12px;")
        bar_lay.addWidget(title)
        bar_lay.addStretch()

        # Invoice number jump-to field inside the top bar
        inv_lbl = QLabel("Invoice #:")
        inv_lbl.setStyleSheet("color:#cfe0f5; font-size:12px;")
        bar_lay.addWidget(inv_lbl)
        self._inv_no_input = QLineEdit()
        self._inv_no_input.setPlaceholderText("Enter number…")
        self._inv_no_input.setFixedHeight(28)
        self._inv_no_input.setFixedWidth(140)
        self._inv_no_input.setStyleSheet(
            "background:rgba(255,255,255,0.1); color:#fff; border:1px solid rgba(255,255,255,0.3);"
            "border-radius:4px; padding:0 6px; font-size:12px;"
        )
        self._inv_no_input.returnPressed.connect(self._jump_to_invoice)
        bar_lay.addWidget(self._inv_no_input)

        go_btn = QPushButton("Open")
        go_btn.setFixedHeight(28)
        go_btn.setFixedWidth(52)
        go_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.15);color:#fff;border:1px solid rgba(255,255,255,0.3);"
            "border-radius:4px;font-size:12px;}"
            "QPushButton:hover{background:rgba(255,255,255,0.3);}"
        )
        go_btn.clicked.connect(self._jump_to_invoice)
        bar_lay.addWidget(go_btn)
        bar_lay.addSpacing(16)

        sup_lbl = QLabel("Supplier:")
        sup_lbl.setStyleSheet("color:#cfe0f5; font-size:12px;")
        bar_lay.addWidget(sup_lbl)
        self._supplier_filter = QComboBox()
        self._supplier_filter.setFixedHeight(28)
        self._supplier_filter.setFixedWidth(200)
        self._supplier_filter.setStyleSheet(
            "QComboBox{background:rgba(255,255,255,0.1);color:#fff;"
            "border:1px solid rgba(255,255,255,0.3);border-radius:4px;"
            "padding:0 6px;font-size:12px;}"
            "QComboBox::drop-down{border:none;}"
            "QComboBox QAbstractItemView{background:#1a3a5c;color:#fff;"
            "selection-background-color:#1a6cb5;}"
        )
        self._supplier_filter.currentIndexChanged.connect(self._apply_filter)
        bar_lay.addWidget(self._supplier_filter)
        bar_lay.addSpacing(8)

        root.addWidget(bar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "#", "Invoice No", "Date", "Supplier", "Lines", "Total", "Status"
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(28)
        self._table.setShowGrid(True)
        self._table.doubleClicked.connect(self._on_double_click)
        self._table.setSortingEnabled(True)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        for c in (0, 1, 2, 4, 5, 6):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setStyleSheet(
            "QHeaderView::section{"
            "  background:#1a3a5c; color:#fff; font-weight:700;"
            "  border:none; padding:4px;"
            "}"
            "QHeaderView::section:hover{ background:#1a6cb5; }"
            "QHeaderView::down-arrow{ image:none; }"
            "QHeaderView::up-arrow{ image:none; }"
        )
        root.addWidget(self._table, stretch=1)

        # Footer
        hint = QFrame()
        hint.setStyleSheet("background:#f0f4f8;border-top:1px solid #cdd5e0;")
        hint_lay = QHBoxLayout(hint)
        hint_lay.setContentsMargins(16, 6, 16, 6)
        hint_lay.setSpacing(8)
        hint_lay.addWidget(QLabel("Double-click to open.  Select row to pay/unpay."))

        self._pay_btn = QPushButton("💰  Mark as Paid")
        self._pay_btn.setFixedHeight(30)
        self._pay_btn.setEnabled(False)
        self._pay_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;border:none;border-radius:4px;"
            "font-size:12px;font-weight:700;padding:0 14px;}"
            "QPushButton:hover{background:#1b5e20;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self._pay_btn.setCursor(Qt.PointingHandCursor)
        self._pay_btn.clicked.connect(self._mark_paid)
        hint_lay.addWidget(self._pay_btn)

        self._unpay_btn = QPushButton("✖  Mark as Unpaid")
        self._unpay_btn.setFixedHeight(30)
        self._unpay_btn.setEnabled(False)
        self._unpay_btn.setStyleSheet(
            "QPushButton{background:#c62828;color:#fff;border:none;border-radius:4px;"
            "font-size:12px;font-weight:700;padding:0 14px;}"
            "QPushButton:hover{background:#a01010;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self._unpay_btn.setCursor(Qt.PointingHandCursor)
        self._unpay_btn.clicked.connect(self._mark_unpaid)
        hint_lay.addWidget(self._unpay_btn)

        self._del_btn = QPushButton("🗑  Delete")
        self._del_btn.setFixedHeight(30)
        self._del_btn.setEnabled(False)
        self._del_btn.setStyleSheet(
            "QPushButton{background:#6a1010;color:#fff;border:none;border-radius:4px;"
            "font-size:12px;font-weight:700;padding:0 14px;}"
            "QPushButton:hover{background:#a01010;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self._del_btn.setCursor(Qt.PointingHandCursor)
        self._del_btn.clicked.connect(self._delete_invoice)
        hint_lay.addWidget(self._del_btn)

        hint_lay.addStretch()
        root.addWidget(hint)

        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def _load(self):
        self._table.setSortingEnabled(False)   # disable while populating
        rows = PurchaseService.list_invoices(limit=300)
        self._rows = rows
        self._table.setRowCount(0)
        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            paid_color = QColor("#2e7d32") if r["payment_status"] == "paid" else QColor("#c62828")
            for col, (val, align, numeric) in enumerate([
                (str(i + 1),                             Qt.AlignCenter,              False),
                (r["invoice_number"],                    Qt.AlignLeft | Qt.AlignVCenter, False),
                (r["date"],                              Qt.AlignCenter,              False),
                (r["supplier"],                          Qt.AlignLeft | Qt.AlignVCenter, False),
                (str(r["lines"]),                        Qt.AlignCenter,              True),
                (f"{r['total']:,.2f} {r['currency']}",  Qt.AlignRight | Qt.AlignVCenter, True),
                (r["payment_status"].upper(),            Qt.AlignCenter,              False),
            ]):
                cell = QTableWidgetItem(val)
                cell.setTextAlignment(align)
                if numeric:
                    # store raw numeric so sorting works correctly
                    cell.setData(Qt.UserRole, r["total"] if col == 5 else r["lines"])
                if col == 6:
                    cell.setForeground(paid_color)
                    cell.setFont(QFont("", -1, QFont.Bold))
                self._table.setItem(i, col, cell)
        self._table.setSortingEnabled(True)

        # Populate supplier filter — preserve current selection if possible
        current_sup = self._supplier_filter.currentText()
        self._supplier_filter.blockSignals(True)
        self._supplier_filter.clear()
        self._supplier_filter.addItem("All Suppliers")
        suppliers = sorted({r["supplier"] for r in rows if r["supplier"]})
        for s in suppliers:
            self._supplier_filter.addItem(s)
        idx = self._supplier_filter.findText(current_sup)
        self._supplier_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self._supplier_filter.blockSignals(False)
        self._apply_filter()

    def _apply_filter(self):
        """Show/hide rows based on selected supplier."""
        selected = self._supplier_filter.currentText()
        for row in range(self._table.rowCount()):
            if selected == "All Suppliers":
                self._table.setRowHidden(row, False)
            else:
                cell = self._table.item(row, 3)   # Supplier column
                self._table.setRowHidden(row, cell is None or cell.text() != selected)

    def _on_double_click(self, index):
        self._open_row(index.row())

    def _open_row(self, visual_row: int):
        """Open the invoice at the given visual row (respects current sort order)."""
        item = self._table.item(visual_row, 1)   # Invoice No column
        if not item:
            return
        inv_no = item.text()
        match = next((r for r in self._rows if r["invoice_number"] == inv_no), None)
        if match:
            self.invoice_selected.emit(match["id"])

    def _jump_to_invoice(self):
        """Find invoice by number typed in the top bar and open it."""
        query = self._inv_no_input.text().strip().upper()
        if not query:
            return
        # Try exact match first, then prefix
        match = next((r for r in self._rows if r["invoice_number"].upper() == query), None)
        if not match:
            match = next((r for r in self._rows if r["invoice_number"].upper().startswith(query)), None)
        if match:
            self.invoice_selected.emit(match["id"])
        else:
            QMessageBox.warning(self.parent(), "Not Found",
                                f"No invoice found matching '{query}'.")

    def _on_selection_changed(self):
        row = self._table.currentRow()
        if row < 0:
            self._pay_btn.setEnabled(False)
            self._unpay_btn.setEnabled(False)
            self._del_btn.setEnabled(False)
            return
        item = self._table.item(row, 1)
        if not item:
            return
        inv_no = item.text()
        match = next((r for r in self._rows if r["invoice_number"] == inv_no), None)
        if match:
            paid = match["payment_status"] == "paid"
            self._pay_btn.setEnabled(not paid)
            self._unpay_btn.setEnabled(paid)
            self._del_btn.setEnabled(True)

    def _mark_paid(self):
        self._set_payment_status("paid")

    def _mark_unpaid(self):
        self._set_payment_status("unpaid")

    def _set_payment_status(self, status: str):
        row = self._table.currentRow()
        if row < 0:
            return
        inv_no = self._table.item(row, 1).text()
        match = next((r for r in self._rows if r["invoice_number"] == inv_no), None)
        if not match:
            return
        if status == "paid":
            ok, err = PurchaseService.mark_paid(match["id"])
        else:
            ok, err = PurchaseService.mark_unpaid(match["id"])
        if ok:
            self._load()
            # Re-select the same invoice
            for r in range(self._table.rowCount()):
                if self._table.item(r, 1) and self._table.item(r, 1).text() == inv_no:
                    self._table.selectRow(r)
                    break
        else:
            QMessageBox.warning(self.parent(), "Error", err)

    def _delete_invoice(self):
        row = self._table.currentRow()
        if row < 0:
            return
        inv_no = self._table.item(row, 1).text()
        match = next((r for r in self._rows if r["invoice_number"] == inv_no), None)
        if not match:
            return
        reply = QMessageBox.question(
            self, "Delete Invoice",
            f"Delete invoice {inv_no}?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        ok, err = PurchaseService.delete_invoice(match["id"])
        if ok:
            self._load()
        else:
            QMessageBox.warning(self, "Error", err)

    def refresh(self):
        self._load()


# ── Module ─────────────────────────────────────────────────────────────────────

class PurchaseModule(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self._hub = PurchaseHub()
        self._hub.tool_requested.connect(self._open_tool)
        self._stack.addWidget(self._hub)
        self._screens: dict[str, QWidget] = {}

    def _open_tool(self, key: str):
        if key == "purchase_invoice":
            self._choose_invoice_mode()
        elif key == "suppliers_list":
            self._open_suppliers()
        elif key == "delivery_invoices":
            self._open_delivery_invoices()
        else:
            self._show_placeholder(key)

    # ── Invoice mode choice ───────────────────────────────────────────────────

    def _choose_invoice_mode(self):
        dlg = InvoiceChoiceDialog(self)
        if dlg.exec() and dlg.choice:
            if dlg.choice == "new":
                self._open_new_invoice()
            else:
                self._open_invoice_list()

    def _open_new_invoice(self):
        screen = PurchaseInvoiceScreen()
        screen.back.connect(self._go_hub)
        screen.edit_item_requested.connect(self._open_item_maintenance)
        self._stack.addWidget(screen)
        self._stack.setCurrentWidget(screen)
        # keep reference so we can return to it from item maintenance
        self._active_invoice = screen

    def _open_invoice_list(self):
        key = "invoice_list"
        if key not in self._screens:
            screen = PurchaseInvoiceListScreen()
            screen.back.connect(self._go_hub)
            screen.invoice_selected.connect(self._open_existing_invoice)
            self._screens[key] = screen
            self._stack.addWidget(screen)
        else:
            self._screens[key].refresh()
        self._stack.setCurrentWidget(self._screens[key])

    def _open_existing_invoice(self, invoice_id: str):
        """Open an existing invoice, loading all its data."""
        screen = PurchaseInvoiceScreen()
        screen.back.connect(self._go_hub)
        screen.deleted.connect(self._open_invoice_list)
        screen.edit_item_requested.connect(self._open_item_maintenance)
        self._stack.addWidget(screen)
        self._stack.setCurrentWidget(screen)
        self._active_invoice = screen
        screen.load_invoice(invoice_id)

    # ── Item maintenance overlay ──────────────────────────────────────────────

    def _open_item_maintenance(self, item_id: str, supplier_id: str = ""):
        from ui.screens.stock.item_maintenance import ItemMaintenanceScreen
        self._new_item_id = None   # reset; set on save
        screen = ItemMaintenanceScreen(item_id=item_id, supplier_id=supplier_id)
        screen.back.connect(lambda: self._close_item_maintenance(None))
        screen.saved.connect(self._close_item_maintenance)
        self._stack.addWidget(screen)
        self._stack.setCurrentWidget(screen)
        self._item_maintenance_screen = screen

    def _close_item_maintenance(self, saved_item_id: str | None = None):
        screen = getattr(self, "_item_maintenance_screen", None)
        if screen:
            prev = getattr(self, "_active_invoice", None) or self._hub
            self._stack.setCurrentWidget(prev)
            self._stack.removeWidget(screen)
            screen.deleteLater()
            self._item_maintenance_screen = None

        # If a new item was just saved, pre-fill the barcode field with its code
        # so Ctrl+Enter immediately finds it at the top of the picker
        if saved_item_id:
            inv = getattr(self, "_active_invoice", None)
            if inv and hasattr(inv, "_bc_input"):
                try:
                    from database.engine import get_session, init_db
                    from database.models.items import Item
                    init_db()
                    db = get_session()
                    try:
                        item = db.get(Item, saved_item_id)
                        code = item.code if item else ""
                    finally:
                        db.close()
                    if code:
                        inv._bc_input.setText(code)
                except Exception:
                    pass
                inv._bc_input.setFocus()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _open_suppliers(self):
        key = "suppliers_list"
        if key not in self._screens:
            from ui.screens.purchase.supplier_list import SupplierListScreen
            screen = SupplierListScreen()
            screen.back.connect(self._go_hub)
            self._screens[key] = screen
            self._stack.addWidget(screen)
        self._stack.setCurrentWidget(self._screens[key])

    def _open_delivery_invoices(self):
        key = "delivery_invoices"
        if key not in self._screens:
            from ui.screens.purchase.delivery_screen import DeliveryInvoicesScreen
            screen = DeliveryInvoicesScreen()
            screen.back.connect(self._go_hub)
            screen.invoice_selected.connect(self._open_existing_invoice)
            self._screens[key] = screen
            self._stack.addWidget(screen)
        else:
            self._screens[key].refresh()
        self._stack.setCurrentWidget(self._screens[key])

    def _show_placeholder(self, key: str):
        from PySide6.QtWidgets import QLabel
        w = QWidget()
        vl = QVBoxLayout(w)
        back = QPushButton("← Back")
        back.setObjectName("secondaryBtn")
        back.setFixedWidth(100)
        back.clicked.connect(self._go_hub)
        lbl = QLabel(f"{key.replace('_', ' ').title()} — coming soon")
        lbl.setStyleSheet("font-size:18px; color:#888; margin:40px;")
        vl.addWidget(back)
        vl.addWidget(lbl)
        self._stack.addWidget(w)
        self._stack.setCurrentWidget(w)

    def _go_hub(self):
        self._stack.setCurrentWidget(self._hub)
