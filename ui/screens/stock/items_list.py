"""
Items List screen — searchable, filterable, paginated table of all items.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem,
    QLabel, QComboBox, QHeaderView, QAbstractItemView,
    QSpinBox,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont
from services.item_service import ItemService, ItemRow

PAGE_SIZE = 500   # rows per page


class ItemsListScreen(QWidget):
    open_item_requested = Signal(str)
    add_item_requested  = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[ItemRow] = []
        self._current_page  = 0
        self._total_count   = 0
        self._search_timer  = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(350)
        self._search_timer.timeout.connect(self._reset_and_load)
        self._build_ui()
        self._load_categories()
        self._load_items()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        # ── Title + count ─────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title = QLabel("Items List")
        title.setObjectName("sectionTitle")
        self._count_label = QLabel("")
        self._count_label.setStyleSheet(
            "background:#1a3a5c; color:#ffffff; border-radius:10px; "
            "padding:2px 12px; font-size:12px; font-weight:600;"
        )
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(self._count_label)
        root.addLayout(title_row)

        # ── Filter bar ────────────────────────────────────────────────────────
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        def _make_search(placeholder):
            box = QLineEdit()
            box.setObjectName("searchBox")
            box.setPlaceholderText(placeholder)
            box.setFixedHeight(34)
            box.textChanged.connect(self._search_timer.start)
            return box

        self._name_box    = _make_search("🔍 Name…")
        self._code_box    = _make_search("🔍 Code…")
        self._barcode_box = _make_search("🔍 Barcode…")

        filter_bar.addWidget(self._name_box,    3)
        filter_bar.addWidget(self._code_box,    2)
        filter_bar.addWidget(self._barcode_box, 2)

        self._cat_combo = QComboBox()
        self._cat_combo.setFixedHeight(34)
        self._cat_combo.setMinimumWidth(160)
        self._cat_combo.currentIndexChanged.connect(self._reset_and_load)
        filter_bar.addWidget(self._cat_combo, 2)

        self._active_combo = QComboBox()
        self._active_combo.setFixedHeight(34)
        self._active_combo.addItems(["All Items", "Active Only", "Inactive Only"])
        self._active_combo.currentIndexChanged.connect(self._reset_and_load)
        filter_bar.addWidget(self._active_combo)

        add_btn = QPushButton("+ New Item")
        add_btn.setObjectName("primaryBtn")
        add_btn.setFixedHeight(34)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self.add_item_requested.emit)
        filter_bar.addWidget(add_btn)

        root.addLayout(filter_bar)

        # ── Table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(9)
        self._table.setHorizontalHeaderLabels([
            "Code", "Barcode", "Name", "Category",
            "Cost", "Price", "Currency", "Stock", "Active",
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        self._table.setSortingEnabled(False)   # disabled — sorting 27k rows client-side is slow
        self._table.doubleClicked.connect(self._on_row_double_clicked)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        for col in (0, 1, 3, 4, 5, 6, 7, 8):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        root.addWidget(self._table)

        # ── Pagination bar ────────────────────────────────────────────────────
        pag_bar = QHBoxLayout()
        pag_bar.setSpacing(6)

        self._edit_btn = QPushButton("✏  Edit")
        self._edit_btn.setObjectName("secondaryBtn")
        self._edit_btn.setFixedHeight(30)
        self._edit_btn.clicked.connect(self._edit_selected)

        self._toggle_btn = QPushButton("Toggle Active")
        self._toggle_btn.setObjectName("warningBtn")
        self._toggle_btn.setFixedHeight(30)
        self._toggle_btn.clicked.connect(self._toggle_active)

        pag_bar.addWidget(self._edit_btn)
        pag_bar.addWidget(self._toggle_btn)
        pag_bar.addStretch()

        # Page info + navigation
        self._prev_btn = QPushButton("◀  Prev")
        self._prev_btn.setObjectName("secondaryBtn")
        self._prev_btn.setFixedHeight(30)
        self._prev_btn.setFixedWidth(80)
        self._prev_btn.clicked.connect(self._prev_page)

        self._page_label = QLabel("Page 1 of 1")
        self._page_label.setStyleSheet("font-size:12px; font-weight:600; color:#1a3a5c; padding:0 8px;")
        self._page_label.setAlignment(Qt.AlignCenter)

        self._next_btn = QPushButton("Next  ▶")
        self._next_btn.setObjectName("primaryBtn")
        self._next_btn.setFixedHeight(30)
        self._next_btn.setFixedWidth(80)
        self._next_btn.clicked.connect(self._next_page)

        self._page_size_combo = QComboBox()
        self._page_size_combo.addItems(["100", "250", "500", "1000", "All"])
        self._page_size_combo.setCurrentText("500")
        self._page_size_combo.setFixedHeight(30)
        self._page_size_combo.setFixedWidth(70)
        self._page_size_combo.currentTextChanged.connect(self._reset_and_load)

        pag_bar.addWidget(QLabel("Rows:"))
        pag_bar.addWidget(self._page_size_combo)
        pag_bar.addSpacing(16)
        pag_bar.addWidget(self._prev_btn)
        pag_bar.addWidget(self._page_label)
        pag_bar.addWidget(self._next_btn)

        root.addLayout(pag_bar)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_categories(self):
        self._cat_combo.blockSignals(True)
        self._cat_combo.clear()
        self._cat_combo.addItem("All Categories", "")
        for cat_id, cat_name, *_ in sorted(ItemService.get_categories(), key=lambda x: x[1]):
            self._cat_combo.addItem(cat_name, cat_id)
        self._cat_combo.blockSignals(False)

    def _reset_and_load(self):
        self._current_page = 0
        self._load_items()

    def _page_size(self) -> int:
        val = self._page_size_combo.currentText()
        if val == "All":
            return 99_999
        return int(val)

    def _load_items(self):
        name_q    = self._name_box.text().strip()
        code_q    = self._code_box.text().strip()
        barcode_q = self._barcode_box.text().strip()
        cat_id    = self._cat_combo.currentData() or ""
        active_idx = self._active_combo.currentIndex()
        ps        = self._page_size()
        offset    = self._current_page * ps

        items = ItemService.search_items(
            category_id=cat_id,
            active_only=(active_idx == 1),
            limit=ps,
            offset=offset,
            name_query=name_q,
            code_query=code_q,
            barcode_query=barcode_q,
        )

        if active_idx == 2:
            items = [i for i in items if not i.is_active]

        self._items = items
        self._total_count = ItemService.count_items(
            category_id=cat_id,
            name_query=name_q,
            code_query=code_q,
            barcode_query=barcode_q,
        )
        self._populate_table(items)
        self._update_pagination()

    def _populate_table(self, items: list[ItemRow]):
        self._table.setRowCount(0)
        self._table.setRowCount(len(items))

        inactive_bg   = QColor("#f5f5f5")
        inactive_fg   = QColor("#aaaaaa")

        for row, item in enumerate(items):
            vals = [
                item.code, item.barcode, item.name, item.category,
                f"{item.cost:.4f}", f"{item.price:.4f}",
                item.price_currency, "", "✔" if item.is_active else "✘",
            ]
            for col, val in enumerate(vals):
                cell = QTableWidgetItem(str(val))
                cell.setData(Qt.UserRole, item.id)

                if not item.is_active:
                    cell.setForeground(inactive_fg)
                    cell.setBackground(inactive_bg)

                if col in (4, 5):
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

                if col == 8:
                    cell.setTextAlignment(Qt.AlignCenter)
                    if item.is_active:
                        cell.setForeground(QColor("#2e7d32"))
                        cell.setFont(QFont("", -1, QFont.Bold))
                    else:
                        cell.setForeground(QColor("#c62828"))

                self._table.setItem(row, col, cell)

    def _update_pagination(self):
        ps         = self._page_size()
        total      = self._total_count
        total_pages = max(1, (total + ps - 1) // ps)
        showing_from = self._current_page * ps + 1
        showing_to   = min(showing_from + len(self._items) - 1, total)

        self._count_label.setText(
            f"  {showing_from:,} – {showing_to:,}  of  {total:,} items  "
        )
        self._page_label.setText(
            f"Page {self._current_page + 1} of {total_pages}"
        )
        self._prev_btn.setEnabled(self._current_page > 0)
        self._next_btn.setEnabled(showing_to < total)

    # ── Pagination actions ────────────────────────────────────────────────────

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._load_items()

    def _next_page(self):
        ps = self._page_size()
        if (self._current_page + 1) * ps < self._total_count:
            self._current_page += 1
            self._load_items()

    # ── Row actions ───────────────────────────────────────────────────────────

    def _on_row_double_clicked(self, index):
        item_id = self._table.item(index.row(), 0).data(Qt.UserRole)
        self.open_item_requested.emit(item_id)

    def _edit_selected(self):
        row = self._table.currentRow()
        if row < 0:
            return
        item_id = self._table.item(row, 0).data(Qt.UserRole)
        self.open_item_requested.emit(item_id)

    def _toggle_active(self):
        row = self._table.currentRow()
        if row < 0:
            return
        item_id = self._table.item(row, 0).data(Qt.UserRole)
        ok, _ = ItemService.toggle_active(item_id)
        if ok:
            self._load_items()

    def refresh(self):
        self._load_items()
