"""
Touch Mode Panel for POS screen.

Two-level grid:
  Level 0 — Category tiles (categories flagged show_on_touch)
  Level 1 — Item tiles for the selected category

Emits:
  item_selected(dict)  — dict with item_id, code, name, price, currency
  exit_requested()     — user pressed Back from the category page
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, Signal

# Rotating palette — one colour per category/item slot
_TILE_COLORS = [
    "#c0392b", "#2980b9", "#27ae60", "#8e44ad", "#d35400",
    "#16a085", "#2c3e50", "#e67e22", "#1abc9c", "#e74c3c",
    "#f39c12", "#3498db", "#7f8c8d", "#6c3483", "#117a65",
    "#a04000", "#1a5276", "#196f3d", "#515a5a", "#922b21",
]

COLS = 3   # tiles per row


def _tile_btn(label: str, sub: str, color: str, size: int = 80) -> QPushButton:
    """Create a coloured square tile button."""
    b = QPushButton()
    b.setFixedSize(size, size)
    b.setCursor(Qt.PointingHandCursor)
    text = f"<div style='text-align:center;font-size:11px;font-weight:700;color:#fff;" \
           f"line-height:1.2;'>{label}</div>"
    if sub:
        text += f"<div style='text-align:center;font-size:9px;color:#ddd;" \
                f"margin-top:2px;'>{sub}</div>"
    b.setText("")
    # Use a QLabel overlay approach via stylesheet + text
    b.setStyleSheet(
        f"QPushButton{{background:{color};border-radius:6px;border:none;}}"
        f"QPushButton:hover{{background:{color}cc;}}"
        f"QPushButton:pressed{{background:{color}99;}}"
    )
    # Embed HTML-like text via rich text on a child label
    lbl = QLabel(text, b)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("background:transparent;border:none;")
    lbl.setGeometry(2, 2, size - 4, size - 4)
    lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
    return b


class TouchPanel(QWidget):
    item_selected  = Signal(dict)   # {item_id, code, name, price, currency}
    exit_requested = Signal()       # back pressed from category page

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ──────────────────────────────────────────────────────────
        self._top_bar = QFrame()
        self._top_bar.setFixedHeight(36)
        self._top_bar.setStyleSheet("background:#1a3a5c;")
        tb_lay = QHBoxLayout(self._top_bar)
        tb_lay.setContentsMargins(6, 0, 6, 0)
        tb_lay.setSpacing(6)

        self._back_btn = QPushButton("← Back")
        self._back_btn.setFixedHeight(26)
        self._back_btn.setStyleSheet(
            "QPushButton{background:#455a64;color:#fff;border:none;"
            "border-radius:4px;font-size:11px;font-weight:700;padding:0 10px;}"
            "QPushButton:hover{background:#607d8b;}"
        )
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.clicked.connect(self._on_back)
        tb_lay.addWidget(self._back_btn)

        self._title_lbl = QLabel("Touch Mode")
        self._title_lbl.setStyleSheet("color:#fff;font-size:12px;font-weight:700;")
        tb_lay.addWidget(self._title_lbl)
        tb_lay.addStretch()

        root.addWidget(self._top_bar)

        # ── Scroll area for the grid ──────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:#f0f4f8;}"
            "QScrollBar:vertical{width:6px;background:#e0e8f0;border-radius:3px;}"
            "QScrollBar::handle:vertical{background:#9ab;border-radius:3px;}"
        )
        root.addWidget(scroll)

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background:#f0f4f8;")
        scroll.setWidget(self._grid_widget)

        self._grid_lay = QGridLayout(self._grid_widget)
        self._grid_lay.setContentsMargins(8, 8, 8, 8)
        self._grid_lay.setSpacing(6)

        # State
        self._mode = "categories"   # "categories" | "items"
        self._current_cat_id = ""

    def refresh(self):
        """Reload category grid and show it."""
        self._load_categories()

    def _clear_grid(self):
        while self._grid_lay.count():
            item = self._grid_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _load_categories(self):
        from services.item_service import ItemService
        self._clear_grid()
        self._mode = "categories"
        self._title_lbl.setText("Touch Mode — Select Category")

        cats = ItemService.get_touch_categories()
        if not cats:
            lbl = QLabel("No categories marked for touch mode.\nGo to Stock → Categories and enable 'Show on Touch Screen'.")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color:#888;font-size:11px;padding:20px;")
            self._grid_lay.addWidget(lbl, 0, 0, 1, COLS)
            return

        for idx, cat in enumerate(cats):
            color = _TILE_COLORS[idx % len(_TILE_COLORS)]
            btn   = _tile_btn(cat["name"], "", color)
            btn.clicked.connect(
                lambda _checked=False, c=cat: self._open_category(c["id"], c["name"])
            )
            row, col = divmod(idx, COLS)
            self._grid_lay.addWidget(btn, row, col)

    def _open_category(self, cat_id: str, cat_name: str):
        from services.item_service import ItemService
        self._clear_grid()
        self._mode = "items"
        self._current_cat_id = cat_id
        self._title_lbl.setText(cat_name)

        items = ItemService.get_touch_items(cat_id)
        if not items:
            lbl = QLabel("No active items in this category.")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color:#888;font-size:11px;padding:20px;")
            self._grid_lay.addWidget(lbl, 0, 0, 1, COLS)
            return

        for idx, it in enumerate(items):
            if it["currency"] == "LBP":
                price_str = f"{it['price']:,.0f} L"
            else:
                price_str = f"$ {it['price']:,.2f}"
            color = _TILE_COLORS[idx % len(_TILE_COLORS)]
            btn   = _tile_btn(it["name"], price_str, color)
            btn.clicked.connect(
                lambda _checked=False, i=it: self.item_selected.emit(i)
            )
            row, col = divmod(idx, COLS)
            self._grid_lay.addWidget(btn, row, col)

    def _on_back(self):
        if self._mode == "items":
            self._load_categories()
        else:
            self.exit_requested.emit()
