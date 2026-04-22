"""
Stock module hub — 12-tile landing screen matching the reference software layout.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QFrame,
)
from PySide6.QtCore import Qt, Signal


STOCK_TOOLS = [
    # Row 1
    ("Items List",                "items_list"),
    ("Item Maintenance",          "item_maintenance"),
    ("Categories",                "categories"),
    ("Sub Categories",            "subcategories"),
    ("Brands",                    "brands"),
    ("Stock Card",                "stock_card"),
    # Row 2
    ("Change Selling Prices",     "change_prices"),
    ("Inventory Invoice",         "inventory_invoice"),
    ("Items Transfer\nFrom W to W", "warehouse_transfer"),
    ("Warehouse Table",           "warehouse_table"),
    ("Item Types",                "item_types"),
    ("Item Classifications",      "item_classifications"),
    # Row 3
    ("Import Items\nfrom Excel",  "import_items"),
    ("Old Inventory",             "old_inventory"),
]


class StockHub(QWidget):
    tool_requested = Signal(str)   # emits tool key

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        # Title
        title = QLabel("Stock")
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #1a3a5c;")
        root.addWidget(title)

        # Tile grid — 6 columns × 2 rows
        grid = QGridLayout()
        grid.setSpacing(8)

        for i, (label, key) in enumerate(STOCK_TOOLS):
            btn = QPushButton(label)
            btn.setFixedSize(190, 80)
            btn.setCursor(Qt.PointingHandCursor)
            if key == "warehouse_transfer":
                btn.setStyleSheet("""
                    QPushButton {
                        font-size: 13px; font-weight: 700;
                        text-align: center;
                        background: #1a6cb5; color: #ffffff;
                        border: 2px solid #0d47a1;
                        border-radius: 6px;
                    }
                    QPushButton:hover { background: #0d47a1; }
                    QPushButton:pressed { background: #082c6b; }
                """)
            else:
                btn.setObjectName("hubTile")
                btn.setStyleSheet("""
                    QPushButton#hubTile {
                        font-size: 13px;
                        font-weight: 600;
                        text-align: center;
                    }
                """)
            btn.clicked.connect(lambda checked=False, k=key: self.tool_requested.emit(k))
            row, col = divmod(i, 6)
            grid.addWidget(btn, row, col)

        root.addLayout(grid)
        root.addStretch()
