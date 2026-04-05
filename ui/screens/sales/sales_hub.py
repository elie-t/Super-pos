"""Sales module hub — landing screen with tile navigation."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QPushButton, QLabel
from PySide6.QtCore import Qt, Signal

SALES_TOOLS = [
    ("Sales\nInvoice",         "sales_invoice"),
    ("Shift\nInvoices",        "shift_invoices"),
    ("Customers",              "customers"),
    ("Customer\nStatement",    "customer_statement"),
    ("Payment\nReceipt",       "payment_receipt"),
]


class SalesHub(QWidget):
    tool_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        title = QLabel("Sales")
        title.setStyleSheet("font-size:16px; font-weight:700; color:#1a3a5c;")
        root.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(8)

        for i, (label, key) in enumerate(SALES_TOOLS):
            btn = QPushButton(label)
            btn.setObjectName("hubTile")
            btn.setFixedSize(190, 80)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=key: self.tool_requested.emit(k))
            row, col = divmod(i, 6)
            grid.addWidget(btn, row, col)

        root.addLayout(grid)
        root.addStretch()
