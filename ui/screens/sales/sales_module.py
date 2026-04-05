"""Sales module container — routes between sub-screens."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QDialog, QPushButton, QLabel, QLineEdit,
)
from PySide6.QtCore import Qt, Signal

from ui.screens.sales.sales_hub import SalesHub
from ui.screens.sales.sales_invoice_screen import SalesInvoiceScreen
from ui.screens.sales.sales_invoice_list import SalesInvoiceListScreen
from ui.screens.sales.customer_screen import CustomerScreen
from ui.screens.sales.shift_invoices_screen import ShiftInvoicesScreen


class SalesModule(QWidget):
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self._hub = SalesHub()
        self._hub.tool_requested.connect(self._open_tool)
        self._stack.addWidget(self._hub)
        self._screens: dict[str, QWidget] = {}

    def _open_tool(self, key: str):
        if key == "sales_invoice":
            self._choose_invoice_mode()
        elif key == "shift_invoices":
            self._open_shift_invoices()
        elif key == "customers":
            self._open_customers()
        else:
            self._show_placeholder(key)

    def _open_shift_invoices(self):
        key = "shift_invoices"
        if key not in self._screens:
            screen = ShiftInvoicesScreen()
            screen.back.connect(self._go_hub)
            self._screens[key] = screen
            self._stack.addWidget(screen)
        screen = self._screens[key]
        screen.refresh()
        self._stack.setCurrentWidget(screen)

    def _open_customers(self):
        key = "customers"
        if key not in self._screens:
            screen = CustomerScreen()
            screen.back.connect(self._go_hub)
            self._screens[key] = screen
            self._stack.addWidget(screen)
        self._stack.setCurrentWidget(self._screens[key])

    # ── Sales invoice ──────────────────────────────────────────────────────────

    def _choose_invoice_mode(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Sales Invoice")
        dlg.setFixedSize(360, 210)
        dlg.choice = None
        dlg.search_number = ""

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        lbl = QLabel("What would you like to do?")
        lbl.setStyleSheet("font-size:14px; font-weight:600; color:#1a3a5c;")
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)

        # Invoice number search box
        search_row = QHBoxLayout()
        search_lbl = QLabel("Invoice #:")
        search_lbl.setStyleSheet("color:#444; font-size:12px;")
        search_row.addWidget(search_lbl)
        inv_search = QLineEdit()
        inv_search.setPlaceholderText("Enter invoice number to open…")
        inv_search.setFixedHeight(30)
        inv_search.setStyleSheet(
            "QLineEdit{border:1px solid #b0c4de;border-radius:4px;padding:0 6px;font-size:13px;}"
        )
        search_row.addWidget(inv_search)
        lay.addLayout(search_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        for label, bg, hover, choice in [
            ("➕  New Invoice", "#2e7d32", "#1b5e20", "new"),
            ("📋  View List",  "#1a6cb5", "#1a3a5c", "list"),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(44)
            btn.setStyleSheet(
                f"QPushButton{{background:{bg};color:#fff;font-size:13px;font-weight:700;"
                f"border:none;border-radius:6px;}}"
                f"QPushButton:hover{{background:{hover};}}"
            )
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda checked=False, c=choice, d=dlg, e=inv_search: (
                    setattr(d, 'choice', c),
                    setattr(d, 'search_number', e.text().strip()),
                    d.accept(),
                )
            )
            btn_row.addWidget(btn)

        lay.addLayout(btn_row)

        # Also trigger search on Enter in the search box
        inv_search.returnPressed.connect(
            lambda: (
                setattr(dlg, 'choice', 'list'),
                setattr(dlg, 'search_number', inv_search.text().strip()),
                dlg.accept(),
            )
        )

        if dlg.exec() and dlg.choice:
            if dlg.choice == "new":
                self._open_new_invoice()
            else:
                self._open_invoice_list(search_number=dlg.search_number)

    def _open_new_invoice(self):
        screen = SalesInvoiceScreen()
        screen.back.connect(self._go_hub)
        self._stack.addWidget(screen)
        self._stack.setCurrentWidget(screen)

    def _open_invoice_list(self, search_number: str = ""):
        key = "invoice_list"
        if key not in self._screens:
            screen = SalesInvoiceListScreen()
            screen.back.connect(self._go_hub)
            screen.edit_requested.connect(self._on_edit_invoice)
            screen.duplicate_requested.connect(self._on_duplicate_invoice)
            self._screens[key] = screen
            self._stack.addWidget(screen)
        screen = self._screens[key]
        screen.refresh()
        if search_number:
            screen.set_search(search_number)
        self._stack.setCurrentWidget(screen)

    def _open_loaded_invoice(self, inv_data: dict, mode: str):
        screen = SalesInvoiceScreen()
        screen.back.connect(self._go_hub)
        self._stack.addWidget(screen)
        self._stack.setCurrentWidget(screen)
        if mode == "edit":
            screen.load_for_edit(inv_data)
        else:
            screen.load_for_duplicate(inv_data)

    def _on_edit_invoice(self, inv_data: dict):
        self._open_loaded_invoice(inv_data, "edit")

    def _on_duplicate_invoice(self, inv_data: dict):
        self._open_loaded_invoice(inv_data, "duplicate")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _show_placeholder(self, key: str):
        w = QWidget()
        vl = QVBoxLayout(w)
        btn = QPushButton("← Back")
        btn.setObjectName("secondaryBtn")
        btn.setFixedWidth(100)
        btn.clicked.connect(self._go_hub)
        lbl = QLabel(f"{key.replace('_', ' ').title()} — coming soon")
        lbl.setStyleSheet("font-size:18px; color:#888; margin:40px;")
        vl.addWidget(btn)
        vl.addWidget(lbl)
        self._stack.addWidget(w)
        self._stack.setCurrentWidget(w)

    def _go_hub(self):
        self._stack.setCurrentWidget(self._hub)

    def refresh(self):
        """Called after End of Shift — refresh the list if open."""
        key = "invoice_list"
        if key in self._screens:
            self._screens[key].refresh()
