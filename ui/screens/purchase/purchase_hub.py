"""Purchase module hub — 13-tile landing screen."""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QPushButton, QLabel
from PySide6.QtCore import Qt, Signal

PURCHASE_TOOLS = [
    # Row 1
    ("Suppliers List",              "suppliers_list"),
    ("Purchase\nInvoice",           "purchase_invoice"),
    ("Payment",                     "payment"),
    ("Refund Purchase\nInvoice",    "refund_invoice"),
    ("Statement Of\nAccount",       "statement"),
    ("Suppliers Position\nBetween", "position"),
    # Row 2
    ("Credit Note",                 "credit_note"),
    ("Debit Note",                  "debit_note"),
    ("Create\nSalesmen",            "salesmen"),
    ("Clients &\nSuppliers\nClassification", "classification"),
    ("Purchase\nOrder",             "purchase_order"),
    ("Merge\nSuppliers",            "merge_suppliers"),
    # Row 3
    ("Calculate\nSalesman\nCommission", "salesman_commission"),
    ("Delivery\nInvoices",             "delivery_invoices"),
]


class PurchaseHub(QWidget):
    tool_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        title = QLabel("Purchase")
        title.setStyleSheet("font-size:16px; font-weight:700; color:#1a3a5c;")
        root.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setContentsMargins(0, 0, 0, 0)

        for i, (label, key) in enumerate(PURCHASE_TOOLS):
            btn = QPushButton(label)
            btn.setFixedSize(160, 80)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 13px; font-weight: 600;
                    text-align: center;
                    background: #ffffff; color: #1a3a5c;
                    border: 1px solid #c5ccd6;
                    border-radius: 8px;
                }
                QPushButton:hover { background: #e8f0fb; border-color: #1a6cb5; }
                QPushButton:pressed { background: #d0e4f7; }
            """)
            btn.clicked.connect(lambda checked=False, k=key: self.tool_requested.emit(k))
            row, col = divmod(i, 6)
            grid.addWidget(btn, row, col)

        root.addLayout(grid)
        root.addStretch()
