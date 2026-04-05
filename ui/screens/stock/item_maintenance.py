"""
Item Maintenance — matches the layout of the reference software item card.

Layout:
  ┌─────────────────────────────────────────────────────────────┬──────────────┐
  │  [Scan Barcode Btn]   $ = 89000          Edit / New Item   │  Notes       │
  │  Code | Reference                        Cost panel        │  Date info   │
  │  Description                             Supplier          ├──────────────┤
  │  Alt Description                         Image area        │  Delete      │
  │  Category / Family / Brand                                 │  Search      │
  │                                                            │  Stock Card  │
  │                                                            │  Save        │
  │                                                            │  Close       │
  ├─────────────────────────────────────────────────────────────┴──────────────┤
  │  Barcode entry | Qty: Opening / In / Out / Stock Units / Stock Pack       │
  │  Currency row + price grid (barcode × Individual/Retail/Wholesale/...)    │
  └─────────────────────────────────────────────────────────────────────────┘
"""
import uuid
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox,
    QPushButton, QLabel, QGroupBox, QFormLayout,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSplitter, QTextEdit,
    QRadioButton, QButtonGroup, QFrame, QSizePolicy,
    QMessageBox, QCheckBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import QFileDialog
from services.item_service import ItemService, ItemDetail
from database.models.base import new_uuid

# Price columns in the grid
PRICE_TYPES = ["Individual", "Retail", "Whole Sale", "Semi-Wholesale"]


class ItemMaintenanceScreen(QWidget):
    saved  = Signal(str)
    back   = Signal()

    def __init__(self, item_id: str = "", parent=None):
        super().__init__(parent)
        self._item_id = item_id or new_uuid()
        self._is_new  = not item_id
        self._detail: ItemDetail | None = None
        self._photo_url: str = ""
        self._lbp_rate = self._get_lbp_rate()
        self._build_ui()
        if item_id:
            self._load_item(item_id)

    # ─────────────────────────────────────────────────────────────────────────
    # UI Construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Lookup bar (always visible at top) ───────────────────────────────
        root.addWidget(self._build_lookup_bar())

        # ── Item card (hidden until an item is loaded or New is clicked) ──────
        self._card_widget = QWidget()
        card_layout = QVBoxLayout(self._card_widget)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Top section
        top_widget = QWidget()
        top_widget.setStyleSheet("background:#ffffff; border-bottom:1px solid #c0ccd8;")
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(10, 8, 10, 8)
        top_layout.setSpacing(10)
        top_layout.addWidget(self._build_left_panel(),   4)
        top_layout.addWidget(self._build_middle_panel(), 3)
        top_layout.addWidget(self._build_right_panel(),  1)
        card_layout.addWidget(top_widget)

        # Bottom section
        bottom_widget = QWidget()
        bottom_widget.setStyleSheet("background:#f8f9fa;")
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(10, 6, 10, 6)
        bottom_layout.setSpacing(6)
        bottom_layout.addLayout(self._build_barcode_stock_row())
        bottom_layout.addWidget(self._build_price_grid())
        card_layout.addWidget(bottom_widget, 1)

        root.addWidget(self._card_widget, 1)

        # Hide card until item is loaded
        if self._is_new:
            self._card_widget.hide()



    # ── Lookup bar ────────────────────────────────────────────────────────────

    def _build_lookup_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(
            "background:#1a3a5c; border-bottom:2px solid #0f2540;"
        )
        bar.setFixedHeight(52)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        title_lbl = QLabel("Item Maintenance")
        title_lbl.setStyleSheet("color:#ffffff; font-size:15px; font-weight:700;")
        layout.addWidget(title_lbl)

        layout.addSpacing(20)

        lbl = QLabel("Enter Code / Barcode:")
        lbl.setStyleSheet("color:#a8c8e8; font-size:12px;")
        layout.addWidget(lbl)

        self._lookup_input = QLineEdit()
        self._lookup_input.setPlaceholderText("Scan barcode or type item code / name…")
        self._lookup_input.setFixedHeight(34)
        self._lookup_input.setMinimumWidth(300)
        self._lookup_input.setStyleSheet(
            "background:#ffffff; border:1px solid #4a7aac; border-radius:4px; "
            "padding:4px 10px; font-size:13px;"
        )
        self._lookup_input.returnPressed.connect(self._lookup_item)
        self._lookup_input.installEventFilter(self)
        layout.addWidget(self._lookup_input, 2)

        load_btn = QPushButton("Load Item")
        load_btn.setFixedHeight(34)
        load_btn.setFixedWidth(100)
        load_btn.setCursor(Qt.PointingHandCursor)
        load_btn.setStyleSheet(
            "QPushButton { background:#1565c0; color:#ffffff; border:none; border-radius:4px; "
            "font-weight:700; font-size:13px; }"
            "QPushButton:hover { background:#1976d2; }"
        )
        load_btn.clicked.connect(self._lookup_item)
        layout.addWidget(load_btn)

        new_btn = QPushButton("+ New Item")
        new_btn.setFixedHeight(34)
        new_btn.setFixedWidth(100)
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.setStyleSheet(
            "QPushButton { background:#2e7d32; color:#ffffff; border:none; border-radius:4px; "
            "font-weight:700; font-size:13px; }"
            "QPushButton:hover { background:#388e3c; }"
        )
        new_btn.clicked.connect(self._start_new_item)
        layout.addWidget(new_btn)

        layout.addStretch()

        back_btn = QPushButton("← Back")
        back_btn.setFixedHeight(34)
        back_btn.setStyleSheet(
            "QPushButton { background:rgba(255,255,255,0.1); color:#ffffff; border:1px solid rgba(255,255,255,0.25); "
            "border-radius:4px; padding:4px 12px; font-size:12px; }"
            "QPushButton:hover { background:rgba(255,255,255,0.25); }"
        )
        back_btn.clicked.connect(self.back.emit)
        layout.addWidget(back_btn)

        return bar

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        if obj is self._lookup_input and event.type() == QEvent.Type.KeyPress:
            if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self._lookup_item(force_list=True)
                return True
        return super().eventFilter(obj, event)

    def _lookup_item(self, force_list: bool = False):
        """Search by barcode, code, or name and load if found."""
        query = self._lookup_input.text().strip()
        if not query:
            self._lookup_input.setFocus()
            return

        limit = 100 if force_list else 5
        results = ItemService.search_items(query=query, limit=limit)
        if not results:
            self._lookup_status("✘  No item found for: " + query, error=True)
            return

        if len(results) == 1 and not force_list:
            self._load_item(results[0].id)
            self._lookup_status(f"✔  Loaded: [{results[0].code}]  {results[0].name}", error=False)
        else:
            # Multiple matches or forced list — show picker
            self._show_picker(results)

    def _show_picker(self, results):
        """Dialog to pick from multiple matches, with inline filter."""
        from PySide6.QtWidgets import QDialog, QListWidget, QListWidgetItem, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Select Item")
        dlg.resize(560, 400)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(f"Found {len(results)} matches — select one:"))

        filter_box = QLineEdit()
        filter_box.setPlaceholderText("Filter list…")
        filter_box.setFixedHeight(30)
        layout.addWidget(filter_box)

        lst = QListWidget()
        all_items = []
        for item in results:
            text = f"[{item.code}]  {item.name}  —  {item.barcode}"
            li = QListWidgetItem(text)
            li.setData(Qt.UserRole, item.id)
            lst.addItem(li)
            all_items.append((text.lower(), item.id, text))
        lst.setCurrentRow(0)
        layout.addWidget(lst, 1)

        def _filter(text):
            lst.clear()
            for low, iid, display in all_items:
                if text.lower() in low:
                    li = QListWidgetItem(display)
                    li.setData(Qt.UserRole, iid)
                    lst.addItem(li)
            if lst.count():
                lst.setCurrentRow(0)

        filter_box.textChanged.connect(_filter)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        lst.doubleClicked.connect(lambda: dlg.accept())
        filter_box.returnPressed.connect(lambda: dlg.accept())

        if dlg.exec() == QDialog.Accepted and lst.currentItem():
            item_id = lst.currentItem().data(Qt.UserRole)
            self._load_item(item_id)

    def _lookup_status(self, msg: str, error: bool = False):
        color = "#c62828" if error else "#2e7d32"
        self._lookup_input.setStyleSheet(
            f"background:#ffffff; border:2px solid {color}; border-radius:4px; "
            f"padding:4px 10px; font-size:13px;"
        )

    def _start_new_item(self):
        """Clear all fields and show card for new item entry."""
        self._item_id = new_uuid()
        self._is_new  = True
        self._detail  = None
        self._clear_fields()
        self._card_widget.show()
        self._code_edit.setFocus()
        # Reset lookup bar style
        self._lookup_input.clear()
        self._lookup_input.setStyleSheet(
            "background:#ffffff; border:1px solid #4a7aac; border-radius:4px; "
            "padding:4px 10px; font-size:13px;"
        )

    def _clear_fields(self):
        self._code_edit.clear()
        self._ref_edit.clear()
        self._name_edit.clear()
        self._altdesc_edit.clear()
        self._notes_edit.clear()
        self._brut_cost.setValue(0)
        self._discount_spin.setValue(0)
        self._vat_spin.setValue(11.0)
        self._price_table.setRowCount(0)
        self._date_created_lbl.setText("Created: —")
        self._date_modified_lbl.setText("Modified: —")

    # ── Left panel: code / name / category ───────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Scan barcode button
        self._scan_btn = QPushButton("🔍  Click This Button To Scan Your Barcode")
        self._scan_btn.setStyleSheet(
            "QPushButton { background:#ffffff; border:2px solid #1a3a5c; border-radius:4px; "
            "font-size:13px; font-weight:600; color:#1a3a5c; padding:8px; }"
            "QPushButton:hover { background:#e8f0fa; }"
        )
        self._scan_btn.setFixedHeight(38)
        self._scan_btn.clicked.connect(lambda: self._lookup_input.setFocus())
        layout.addWidget(self._scan_btn)

        # Code + Reference row
        code_row = QHBoxLayout()
        code_row.addWidget(QLabel("Product Code:"))
        self._code_edit = QLineEdit()
        self._code_edit.setFixedWidth(130)
        self._code_edit.setPlaceholderText("Code")
        code_row.addWidget(self._code_edit)
        code_row.addWidget(QLabel("Reference:"))
        self._ref_edit = QLineEdit()
        self._ref_edit.setFixedWidth(120)
        code_row.addWidget(self._ref_edit)
        code_row.addStretch()
        layout.addLayout(code_row)

        # Description
        desc_lbl = QLabel("Product Description :")
        desc_lbl.setStyleSheet("color:#c62828; font-weight:700; font-size:13px;")
        layout.addWidget(desc_lbl)

        self._name_edit = QLineEdit()
        self._name_edit.setStyleSheet(
            "font-size:14px; font-weight:600; border:1px solid #1a6cb5; "
            "border-radius:3px; padding:6px;"
        )
        layout.addWidget(self._name_edit)

        # Alt description
        layout.addWidget(QLabel("Alternate Description :"))
        self._altdesc_edit = QTextEdit()
        self._altdesc_edit.setFixedHeight(48)
        layout.addWidget(self._altdesc_edit)

        # Category / Family / Brand
        self._cat_combo    = self._combo_row(layout, "Category :")
        self._family_combo = self._combo_row(layout, "Family :", red=True)
        self._brand_combo  = self._combo_row(layout, "Brand :")

        layout.addStretch()
        return w

    def _combo_row(self, layout, label: str, red: bool = False) -> QComboBox:
        row = QHBoxLayout()
        lbl = QLabel(label)
        if red:
            lbl.setStyleSheet("color:#c62828; font-weight:700;")
        lbl.setFixedWidth(80)
        combo = QComboBox()
        combo.setMinimumWidth(180)
        add_btn = QPushButton("+")
        add_btn.setObjectName("secondaryBtn")
        add_btn.setFixedSize(26, 26)
        row.addWidget(lbl)
        row.addWidget(combo, 1)
        row.addWidget(add_btn)
        row.addStretch()
        layout.addLayout(row)
        return combo

    # ── Middle panel: rate / cost / supplier / image ──────────────────────────

    def _build_middle_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        # LBP rate
        rate_row = QHBoxLayout()
        rate_lbl = QLabel(f"$ = {self._lbp_rate:,}")
        rate_lbl.setStyleSheet("color:#c62828; font-size:14px; font-weight:700;")
        title_lbl = QLabel("Edit Item" if not self._is_new else "New Item")
        title_lbl.setStyleSheet("color:#e65100; font-size:22px; font-weight:700;")
        rate_row.addWidget(rate_lbl)
        rate_row.addStretch()
        rate_row.addWidget(title_lbl)
        layout.addLayout(rate_row)

        # Last updated item (info box)
        self._last_updated = QLabel("Last Updated Item\n—")
        self._last_updated.setStyleSheet(
            "color:#c62828; font-size:11px; background:#fff8f8; "
            "border:1px solid #f0c0c0; border-radius:3px; padding:4px 8px;"
        )
        layout.addWidget(self._last_updated)

        # Cost panel
        cost_grp = QGroupBox("Cost")
        cost_form = QGridLayout(cost_grp)
        cost_form.setSpacing(4)

        cost_form.addWidget(QLabel("Brut Cost:"), 0, 0)
        self._brut_cost = QDoubleSpinBox()
        self._brut_cost.setRange(0, 9999999); self._brut_cost.setDecimals(4)
        self._brut_cost.valueChanged.connect(self._recalc_margins)
        cost_form.addWidget(self._brut_cost, 0, 1)

        cost_form.addWidget(QLabel("Discount:"), 0, 2)
        self._discount_spin = QDoubleSpinBox()
        self._discount_spin.setRange(0, 100); self._discount_spin.setSuffix("%")
        self._discount_spin.valueChanged.connect(self._recalc_margins)
        cost_form.addWidget(self._discount_spin, 0, 3)

        cost_form.addWidget(QLabel("Net Cost:"), 1, 0)
        self._net_cost_lbl = QLabel("0.0000")
        self._net_cost_lbl.setStyleSheet("font-weight:600;")
        cost_form.addWidget(self._net_cost_lbl, 1, 1)

        cost_form.addWidget(QLabel("Avg Cost:"), 1, 2)
        self._avg_cost_lbl = QLabel("0.0000")
        self._avg_cost_lbl.setStyleSheet("font-weight:600;")
        cost_form.addWidget(self._avg_cost_lbl, 1, 3)

        cost_form.addWidget(QLabel("VAT%:"), 2, 0)
        self._vat_spin = QDoubleSpinBox()
        self._vat_spin.setRange(0, 100); self._vat_spin.setSuffix("%")
        self._vat_spin.setValue(11.0); self._vat_spin.setFixedWidth(80)
        cost_form.addWidget(self._vat_spin, 2, 1)

        self._cost_currency = QComboBox()
        self._cost_currency.addItems(["USD", "LBP"])
        self._cost_currency.setFixedWidth(70)
        cost_form.addWidget(QLabel("Currency:"), 2, 2)
        cost_form.addWidget(self._cost_currency, 2, 3)

        layout.addWidget(cost_grp)

        # Supplier row
        sup_row = QHBoxLayout()
        sup_row.addWidget(QLabel("Supplier:"))
        add_sup_btn = QPushButton("Add")
        add_sup_btn.setObjectName("secondaryBtn")
        add_sup_btn.setFixedSize(40, 24)
        self._supplier_lbl = QLabel("—")
        self._supplier_lbl.setStyleSheet("color:#1a6cb5; text-decoration:underline; cursor:pointer;")
        self._supplier_combo = QComboBox()
        self._supplier_combo.setMinimumWidth(160)
        sup_row.addWidget(add_sup_btn)
        sup_row.addWidget(self._supplier_combo, 1)
        layout.addLayout(sup_row)

        # Item photo (Browse → upload to Supabase Storage)
        img_frame = QFrame()
        img_frame.setStyleSheet(
            "background:#f8f8f8; border:1px solid #c0ccd8; border-radius:3px;"
        )
        img_frame.setFixedHeight(100)
        img_layout = QVBoxLayout(img_frame)
        img_layout.setContentsMargins(4, 4, 4, 4)
        self._img_preview = QLabel("[ No Image ]")
        self._img_preview.setAlignment(Qt.AlignCenter)
        self._img_preview.setStyleSheet("color:#aaaaaa;")
        self._img_preview.setScaledContents(False)
        img_layout.addWidget(self._img_preview)
        layout.addWidget(img_frame)

        # URL input row
        url_row = QHBoxLayout()
        self._photo_url_edit = QLineEdit()
        self._photo_url_edit.setPlaceholderText("Paste image URL…")
        self._photo_url_edit.setFixedHeight(24)
        self._photo_url_edit.setStyleSheet("font-size:10px;")
        self._photo_url_edit.editingFinished.connect(self._refresh_photo_preview)
        url_set_btn = QPushButton("Set")
        url_set_btn.setObjectName("secondaryBtn")
        url_set_btn.setFixedSize(36, 24)
        url_set_btn.clicked.connect(self._set_photo_from_url)
        url_row.addWidget(self._photo_url_edit, 1)
        url_row.addWidget(url_set_btn)
        layout.addLayout(url_row)

        img_btn_row = QHBoxLayout()
        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.setFixedHeight(26)
        browse_btn.clicked.connect(self._browse_photo)
        self._clear_photo_btn = QPushButton("Clear")
        self._clear_photo_btn.setObjectName("secondaryBtn")
        self._clear_photo_btn.setFixedHeight(26)
        self._clear_photo_btn.clicked.connect(self._clear_photo)
        img_btn_row.addWidget(browse_btn)
        img_btn_row.addWidget(self._clear_photo_btn)
        layout.addLayout(img_btn_row)

        layout.addStretch()
        return w

    # ── Right panel: notes / dates / action buttons ───────────────────────────

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#f0f4f8; border-left:1px solid #c0ccd8;")
        w.setMinimumWidth(130)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(3)

        notes_lbl = QLabel("Notes:")
        notes_lbl.setStyleSheet("font-weight:600; font-size:11px;")
        layout.addWidget(notes_lbl)

        self._notes_edit = QTextEdit()
        self._notes_edit.setFixedHeight(36)
        layout.addWidget(self._notes_edit)

        self._date_created_lbl = QLabel("Created: —")
        self._date_created_lbl.setStyleSheet("color:#c62828; font-size:10px;")
        layout.addWidget(self._date_created_lbl)

        self._date_modified_lbl = QLabel("Modified: —")
        self._date_modified_lbl.setStyleSheet("color:#c62828; font-size:10px;")
        layout.addWidget(self._date_modified_lbl)

        layout.addSpacing(2)

        # Online flags
        online_lbl = QLabel("Online Shop:")
        online_lbl.setStyleSheet("font-weight:600; font-size:10px;")
        layout.addWidget(online_lbl)

        self._chk_online = QCheckBox("Active Online")
        self._chk_online.setStyleSheet("font-size:10px;")
        layout.addWidget(self._chk_online)

        self._chk_featured = QCheckBox("Featured")
        self._chk_featured.setStyleSheet("font-size:10px;")
        layout.addWidget(self._chk_featured)

        self._chk_touch = QCheckBox("Touch Screen")
        self._chk_touch.setStyleSheet("font-size:10px; color:#00695c; font-weight:600;")
        layout.addWidget(self._chk_touch)

        layout.addSpacing(2)

        # Action buttons
        btns = [
            ("✖  Delete",     "#c62828", "#e53935", self._confirm_delete),
            ("🔍  Search",     "#1a6cb5", "#1a80d4", self._go_search),
            ("📊  Stock Card", "#1a6cb5", "#1a80d4", self._open_stock_card),
            ("💾  Save",       "#2e7d32", "#388e3c", self._save),
            ("✖  Close",      "#555555", "#777777", self.back.emit),
        ]

        for label, bg, hover, slot in btns:
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background:{bg}; color:#fff; border:none; border-radius:4px; "
                f"font-weight:600; font-size:11px; }}"
                f"QPushButton:hover {{ background:{hover}; }}"
            )
            btn.clicked.connect(slot)
            layout.addWidget(btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet("font-size:10px; color:#c62828;")
        layout.addWidget(self._status_lbl)
        layout.addStretch()
        return w

    # ── Bottom: barcode entry + stock summary row ─────────────────────────────

    def _build_barcode_stock_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)

        # Barcode entry
        bc_grp = QGroupBox("Barcode And Price Entry")
        bc_grp.setFixedWidth(320)
        bc_layout = QVBoxLayout(bc_grp)
        bc_layout.setSpacing(6)

        # Barcode input row
        bc_input_row = QHBoxLayout()
        bc_input_row.addWidget(QLabel("Barcode:"))
        self._bc_input = QLineEdit()
        self._bc_input.setPlaceholderText("Scan or type…")
        self._bc_input.setFixedHeight(28)
        self._bc_input.returnPressed.connect(self._add_barcode_row)
        bc_input_row.addWidget(self._bc_input, 1)
        bc_layout.addLayout(bc_input_row)

        # Pkg row
        pkg_row = QHBoxLayout()
        pkg_row.addWidget(QLabel("Pkg (pack size):"))
        self._bc_pkg_spin = QSpinBox()
        self._bc_pkg_spin.setRange(1, 9999)
        self._bc_pkg_spin.setValue(1)
        self._bc_pkg_spin.setFixedWidth(70)
        self._bc_pkg_spin.setFixedHeight(28)
        pkg_row.addWidget(self._bc_pkg_spin)
        pkg_row.addStretch()
        bc_layout.addLayout(pkg_row)

        # Buttons
        bc_btn_row = QHBoxLayout()
        gen_btn = QPushButton("⊕  Generate")
        gen_btn.setObjectName("secondaryBtn")
        gen_btn.setFixedHeight(30)
        gen_btn.clicked.connect(self._generate_barcode)
        add_bc_btn = QPushButton("⊕  Add to List")
        add_bc_btn.setObjectName("primaryBtn")
        add_bc_btn.setFixedHeight(30)
        add_bc_btn.clicked.connect(self._add_barcode_row)
        bc_btn_row.addWidget(gen_btn)
        bc_btn_row.addWidget(add_bc_btn)
        bc_layout.addLayout(bc_btn_row)

        del_bc_btn = QPushButton("✖  Remove Selected Row")
        del_bc_btn.setObjectName("dangerBtn")
        del_bc_btn.setFixedHeight(26)
        del_bc_btn.clicked.connect(self._remove_barcode_row)
        bc_layout.addWidget(del_bc_btn)

        row.addWidget(bc_grp)

        # Stock summary table
        stk_grp = QGroupBox("Stock Summary")
        stk_layout = QGridLayout(stk_grp)
        stk_layout.setSpacing(4)

        headers = ["Opening", "In", "Out", "Stock Units", "Stock Pack"]
        for c, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-weight:600; font-size:11px;")
            stk_layout.addWidget(lbl, 0, c + 1)

        for r, row_lbl in enumerate(["Qty", "Value"]):
            lbl = QLabel(row_lbl)
            lbl.setStyleSheet("font-weight:600; font-size:11px;")
            stk_layout.addWidget(lbl, r + 1, 0)

        self._stk_labels = {}
        keys = ["opening_qty", "in_qty", "out_qty", "units", "pack",
                "opening_val", "in_val", "out_val", "", ""]
        for r in range(2):
            for c in range(5):
                key = keys[r * 5 + c]
                lbl = QLabel("0")
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setStyleSheet(
                    "background:#ffffff; border:1px solid #d0d8e4; "
                    "border-radius:2px; padding:2px 6px; font-size:12px;"
                )
                stk_layout.addWidget(lbl, r + 1, c + 1)
                if key:
                    self._stk_labels[key] = lbl

        row.addWidget(stk_grp, 1)
        return row

    # ── Price grid ────────────────────────────────────────────────────────────

    def _build_price_grid(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Currency selector row — one combo per price type, aligned above their columns
        curr_row = QHBoxLayout()
        curr_row.setSpacing(8)

        curr_row.addWidget(QLabel("Cost Currency:"))
        self._cost_curr_combo = QComboBox()
        self._cost_curr_combo.addItems(["USD", "LBP"])
        self._cost_curr_combo.setFixedWidth(70)
        curr_row.addWidget(self._cost_curr_combo)

        curr_row.addSpacing(16)

        # Per-price-type currency combos with coloured labels matching the table columns
        col_colors = ["#00acc1", "#388e3c", "#c2185b", "#5c6bc0"]
        col_bgs    = ["#b2ebf2", "#e8f5e9", "#fce4ec", "#e8eaf6"]
        self._sale_currency_combos = []
        for pt, fg, bg in zip(PRICE_TYPES, col_colors, col_bgs):
            lbl = QLabel(pt + ":")
            lbl.setStyleSheet(f"font-weight:700; color:{fg}; font-size:11px;")
            curr_row.addWidget(lbl)
            combo = QComboBox()
            combo.addItems(["USD", "LBP"])
            combo.setFixedWidth(70)
            combo.setStyleSheet(
                f"background:{bg}; border:1px solid {fg}; border-radius:3px; padding:1px 4px;"
            )
            idx = len(self._sale_currency_combos)
            combo.currentIndexChanged.connect(
                lambda _, i=idx: self._on_sale_currency_changed(i)
            )
            self._sale_currency_combos.append(combo)
            curr_row.addWidget(combo)

        curr_row.addStretch()

        # LBP equivalent display (shows individual price converted to LBP)
        self._lbp_display = QLabel("≈ — LBP")
        self._lbp_display.setStyleSheet(
            "background:#fff9e6; border:1px solid #f0c040; border-radius:4px;"
            " padding:2px 8px; color:#7a5500; font-size:12px; font-weight:600;"
        )
        self._lbp_display.setMinimumWidth(140)
        self._lbp_display.setAlignment(Qt.AlignCenter)
        curr_row.addWidget(self._lbp_display)

        # Fixed / Variable
        self._fixed_radio    = QRadioButton("Fixed Price")
        self._variable_radio = QRadioButton("Variable Price")
        self._fixed_radio.setChecked(True)
        price_radio_grp = QButtonGroup(self)
        price_radio_grp.addButton(self._fixed_radio)
        price_radio_grp.addButton(self._variable_radio)
        curr_row.addWidget(self._fixed_radio)
        curr_row.addWidget(self._variable_radio)

        margin_btn = QPushButton("Set current\nprofit margins")
        margin_btn.setObjectName("secondaryBtn")
        margin_btn.setFixedSize(130, 36)
        margin_btn.clicked.connect(self._set_margins)
        curr_row.addWidget(margin_btn)

        layout.addLayout(curr_row)

        # Price table
        # Columns: ▶ | Barcode | Pkg | Cost | %ind | Individual | %ret | Retail | %who | WholeSale | %semi | Semi-W | Created | Modified | F1% | F2% | F3% | F4%
        col_headers = [
            "", "Barcode", "Pkg", "Cost",
            "%", "Individual",
            "%", "Retail",
            "%", "Whole Sale",
            "%", "Semi-Wholesale",
            "Created", "Modified",
            "F1%", "F2%", "F3%", "F4%",
        ]
        self._price_table = QTableWidget()
        self._price_table.setColumnCount(len(col_headers))
        self._price_table.setHorizontalHeaderLabels(col_headers)
        self._price_table.verticalHeader().setVisible(False)
        self._price_table.setSelectionBehavior(QAbstractItemView.SelectItems)  # per-cell selection
        self._price_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._price_table.setAlternatingRowColors(True)
        self._price_table.setMinimumHeight(120)
        self._price_table.setEditTriggers(
            QAbstractItemView.DoubleClicked |
            QAbstractItemView.SelectedClicked |
            QAbstractItemView.AnyKeyPressed
        )
        self._price_table.itemChanged.connect(self._on_price_cell_changed)

        hdr = self._price_table.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for col in range(len(col_headers)):
            if col != 1:
                hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        # Color price column headers
        price_colors = {5: "#b2ebf2", 7: "#e8f5e9", 9: "#fce4ec", 11: "#e8eaf6"}
        for col, color in price_colors.items():
            item = self._price_table.horizontalHeaderItem(col)
            if item:
                item.setBackground(QColor(color))

        layout.addWidget(self._price_table)
        return w

    # ─────────────────────────────────────────────────────────────────────────
    # Data loading
    # ─────────────────────────────────────────────────────────────────────────

    def _load_item(self, item_id: str):
        detail = ItemService.get_item_detail(item_id)
        if not detail:
            self._lookup_status("✘  Item not found.", error=True)
            return
        self._detail  = detail
        self._item_id = item_id
        self._is_new  = False
        self._card_widget.show()
        self._lookup_input.setText(detail.code)
        self._lookup_status("", error=False)

        self._code_edit.setText(detail.code)
        self._name_edit.setText(detail.name)
        self._altdesc_edit.setPlainText(detail.name_ar)
        self._notes_edit.setPlainText(detail.notes)
        self._brut_cost.setValue(detail.cost_price)
        self._vat_spin.setValue(detail.vat_rate * 100)

        _set_combo(self._cost_currency, detail.cost_currency)
        _set_combo(self._cost_curr_combo, detail.cost_currency)
        _set_combo(self._cat_combo, detail.category_name)
        _set_combo(self._brand_combo, detail.brand_name)

        # Online flags
        self._chk_online.setChecked(bool(detail.is_online))
        self._chk_featured.setChecked(bool(detail.is_pos_featured))
        self._chk_touch.setChecked(bool(getattr(detail, "show_on_touch", False)))

        # Photo
        self._photo_url_edit.setText(detail.photo_url or "")
        self._refresh_photo_preview()

        # Dates
        if detail.id:
            self._date_created_lbl.setText("Created: —")
            self._date_modified_lbl.setText("Modified: —")

        # Stock summary
        total_stock = sum(qty for _, qty in detail.stock_entries)
        if "units" in self._stk_labels:
            self._stk_labels["units"].setText(f"{total_stock:,.0f}")

        # Populate price table from barcodes
        self._rebuild_price_table(detail)
        self._refresh_lbp_display()

        # Load suppliers
        self._load_suppliers(detail)

    def _rebuild_price_table(self, detail: ItemDetail):
        """One row per barcode — each with Cost + price columns."""
        self._price_table.setRowCount(0)

        # Group prices by type
        price_map = {p[1]: (p[2], p[3]) for p in detail.prices}  # type → (amount, currency)

        # Restore currency combos from stored prices
        price_type_order = ["individual", "retail", "wholesale", "semi_wholesale"]
        for i, ptype in enumerate(price_type_order):
            if ptype in price_map:
                _, currency = price_map[ptype]
                combo = self._sale_currency_combos[i]
                combo.blockSignals(True)
                idx = combo.findText(currency)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                combo.blockSignals(False)

        for bc_id, bc, is_primary, pack_qty in detail.barcodes:
            self._add_price_row(bc, pack_qty, detail.cost_price, price_map,
                                created="", modified="")
            # Store DB id in barcode cell so save can update vs insert
            row_idx = self._price_table.rowCount() - 1
            bc_cell = self._price_table.item(row_idx, 1)
            if bc_cell:
                bc_cell.setData(Qt.UserRole, bc_id)

    def _add_price_row(self, barcode: str, pkg: int, cost_per_unit: float,
                       price_map: dict, created: str = "", modified: str = ""):
        """
        Add one row to the price grid.
        cost_per_unit = unit cost (from the Cost panel).
        Row cost = cost_per_unit × pkg.
        Prices are auto-calculated if price_map is empty (new row).
        """
        from datetime import datetime
        now_str = datetime.now().strftime("%d-%b-%y %H:%M")

        self._price_table.blockSignals(True)
        r = self._price_table.rowCount()
        self._price_table.insertRow(r)

        # Col 0 — row selector marker (non-editable)
        arr = QTableWidgetItem("▶")
        arr.setTextAlignment(Qt.AlignCenter)
        arr.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # not editable
        self._price_table.setItem(r, 0, arr)

        # Col 1 — Barcode (editable); UserRole stores the DB barcode id for updates
        bc_item = QTableWidgetItem(barcode)
        bc_item.setFont(QFont("", -1, QFont.Bold))
        self._price_table.setItem(r, 1, bc_item)
        # bc_id is set externally after this call when loading existing barcodes

        # Col 2 — Pkg (editable)
        pkg_item = QTableWidgetItem(str(pkg))
        pkg_item.setTextAlignment(Qt.AlignCenter)
        self._price_table.setItem(r, 2, pkg_item)

        # Col 3 — Cost = unit_cost × pkg (editable)
        row_cost = cost_per_unit * pkg
        cost_item = QTableWidgetItem(f"{row_cost:.4f}")
        cost_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._price_table.setItem(r, 3, cost_item)

        # Price columns: Individual, Retail, WholeSale, Semi-Wholesale
        price_type_keys = ["individual", "retail", "wholesale", "semi_wholesale"]
        price_colors    = ["#b2ebf2",    "#e8f5e9", "#fce4ec",  "#e8eaf6"]
        # Default margins when creating a new row (30%, 30%, 25%, 20%)
        default_margins = [30.0, 30.0, 25.0, 20.0]
        col = 4

        for i, (ptype, color, def_margin) in enumerate(
                zip(price_type_keys, price_colors, default_margins)):

            if ptype in price_map:
                amount, _ = price_map[ptype]
                margin = self._calc_margin(row_cost, amount) if row_cost > 0 else def_margin
            elif "retail" in price_map and i == 0:
                amount, _ = price_map["retail"]
                margin = self._calc_margin(row_cost, amount) if row_cost > 0 else def_margin
            else:
                # New row — auto-calculate price from default margin
                margin = def_margin
                amount = row_cost * (1 + margin / 100) if row_cost > 0 else 0.0

            # % column
            pct_item = QTableWidgetItem(f"{margin:.2f}")
            pct_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._price_table.setItem(r, col, pct_item)
            col += 1

            # Price column (colored + bold)
            price_item = QTableWidgetItem(f"{amount:.4f}")
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            price_item.setBackground(QColor(color))
            price_item.setFont(QFont("", -1, QFont.Bold))
            self._price_table.setItem(r, col, price_item)
            col += 1

        # Col 12 — Created date (non-editable, set once)
        created_item = QTableWidgetItem(created or now_str)
        created_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        created_item.setForeground(QColor("#555555"))
        self._price_table.setItem(r, col, created_item)
        col += 1

        # Col 13 — Modified date (auto-updated on any change)
        modified_item = QTableWidgetItem(modified or now_str)
        modified_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        modified_item.setForeground(QColor("#888888"))
        self._price_table.setItem(r, col, modified_item)
        col += 1

        # F1%–F4% columns
        for f in range(4):
            fi = QTableWidgetItem("0")
            fi.setTextAlignment(Qt.AlignCenter)
            self._price_table.setItem(r, col + f, fi)

        self._price_table.blockSignals(False)

    def _load_suppliers(self, detail: ItemDetail):
        """Populate supplier combo."""
        from database.engine import get_session, init_db
        from database.models.parties import Supplier
        init_db()
        session = get_session()
        try:
            suppliers = session.query(Supplier).filter_by(is_active=True)\
                .order_by(Supplier.name).limit(500).all()
            self._supplier_combo.clear()
            self._supplier_combo.addItem("— Select Supplier —", "")
            for s in suppliers:
                self._supplier_combo.addItem(s.name, s.id)
            if detail.id:
                # Try to pre-select based on item's supplier
                pass
        finally:
            session.close()

    def _load_combos(self):
        self._cat_combo.clear()
        self._cat_combo.addItem("— None —", "")
        for cid, cname, *_ in sorted(ItemService.get_categories(), key=lambda x: x[1]):
            self._cat_combo.addItem(cname, cid)

        self._family_combo.clear()
        self._family_combo.addItem("— None —", "")
        for cid, cname, pid, *_ in ItemService.get_categories():
            if pid:
                self._family_combo.addItem(cname, cid)

        self._brand_combo.clear()
        self._brand_combo.addItem("— None —", "")
        for bid, bname in ItemService.get_brands():
            self._brand_combo.addItem(bname, bid)

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _get_lbp_rate(self) -> int:
        from database.engine import get_session, init_db
        from database.models.items import Setting
        init_db()
        session = get_session()
        try:
            s = session.get(Setting, "lbp_rate")
            return int(s.value) if s else 89_500
        finally:
            session.close()

    @staticmethod
    def _calc_margin(cost: float, price: float) -> float:
        if cost <= 0 or price <= 0:
            return 0.0
        return round((price - cost) / cost * 100, 2)

    def _recalc_margins(self):
        cost = self._brut_cost.value()
        disc = self._discount_spin.value()
        net  = cost * (1 - disc / 100)
        self._net_cost_lbl.setText(f"{net:.4f}")
        self._avg_cost_lbl.setText(f"{net:.4f}")
        # Recalc margins in table
        for r in range(self._price_table.rowCount()):
            pkg_item = self._price_table.item(r, 2)
            pkg = int(pkg_item.text()) if pkg_item else 1
            row_cost_usd = net * pkg
            for i, (price_col, pct_col) in enumerate([(5, 4), (7, 6), (9, 8), (11, 10)]):
                price_item = self._price_table.item(r, price_col)
                if price_item:
                    try:
                        price_val = float(price_item.text())
                        base = self._base_cost_for_currency(row_cost_usd, i)
                        margin = self._calc_margin(base, price_val)
                        pct_item = self._price_table.item(r, pct_col)
                        if pct_item:
                            pct_item.setText(f"{margin:.2f}")
                    except ValueError:
                        pass

    def _focus_barcode_input(self):
        self._bc_input.setFocus()
        self._bc_input.selectAll()

    def _generate_barcode(self):
        """Generate a unique internal barcode from item code + timestamp."""
        import time
        base = self._code_edit.text().strip() or "99"
        suffix = str(int(time.time()))[-6:]
        bc = f"{base}{suffix}"
        self._bc_input.setText(bc)
        self._bc_input.setFocus()
        self._bc_input.selectAll()

    def _add_barcode_row(self):
        """Add the barcode in the input as a new editable row in the price table."""
        bc = self._bc_input.text().strip()
        if not bc:
            self._bc_input.setFocus()
            return

        # Check for duplicates in the table
        for r in range(self._price_table.rowCount()):
            existing = self._price_table.item(r, 1)
            if existing and existing.text().strip() == bc:
                self._bc_input.setStyleSheet(
                    "border:2px solid #c62828; border-radius:4px; padding:4px;"
                )
                return

        pkg = self._bc_pkg_spin.value()
        cost = self._brut_cost.value() * pkg
        self._add_price_row(bc, pkg, self._brut_cost.value(), {})

        # Scroll to and select the new row, then focus cost cell for editing
        new_row = self._price_table.rowCount() - 1
        self._price_table.setCurrentCell(new_row, 3)   # col 3 = Cost
        self._price_table.scrollToItem(self._price_table.item(new_row, 1))
        self._price_table.editItem(self._price_table.item(new_row, 3))

        # Reset inputs
        self._bc_input.clear()
        self._bc_pkg_spin.setValue(1)
        self._bc_input.setStyleSheet("")
        self._bc_input.setFocus()

    def _remove_barcode_row(self):
        """Remove the currently selected row from the price table."""
        row = self._price_table.currentRow()
        if row >= 0:
            self._price_table.removeRow(row)

    # ── Price currency helpers ────────────────────────────────────────────────

    def _sale_currency(self, price_idx: int) -> str:
        """Return 'USD' or 'LBP' for price column index 0-3."""
        return self._sale_currency_combos[price_idx].currentText()

    def _base_cost_for_currency(self, row_cost_usd: float, price_idx: int) -> float:
        """
        Return the cost to use as the base for margin calculation,
        in the target currency of the given price column.
        row_cost_usd is always the USD cost (col 3 value).
        If the price column is LBP → multiply by LBP rate.
        """
        if self._sale_currency(price_idx) == "LBP":
            return row_cost_usd * self._lbp_rate
        return row_cost_usd

    def _on_sale_currency_changed(self, price_idx: int):
        """When a currency combo changes, recalc that column's prices for all rows."""
        PRICE_PAIRS = [(4, 5), (6, 7), (8, 9), (10, 11)]
        pct_col, price_col = PRICE_PAIRS[price_idx]
        self._price_table.blockSignals(True)
        try:
            for r in range(self._price_table.rowCount()):
                cost_item = self._price_table.item(r, 3)
                pct_item  = self._price_table.item(r, pct_col)
                price_item = self._price_table.item(r, price_col)
                if not (cost_item and pct_item and price_item):
                    continue
                try:
                    cost_usd = float(cost_item.text().replace(",", ""))
                    pct      = float(pct_item.text())
                    base     = self._base_cost_for_currency(cost_usd, price_idx)
                    price_item.setText(f"{base * (1 + pct / 100):.4f}")
                except ValueError:
                    pass
        finally:
            self._price_table.blockSignals(False)
            if price_idx == 0:   # Individual currency changed
                self._refresh_lbp_display()

    def _on_price_cell_changed(self, item: QTableWidgetItem):
        """
        Live recalculation in the price grid.
        All % ↔ price conversions respect each column's selected currency.
        If a price column is LBP: price = cost_usd × rate × (1 + %/100)
                                  %    = (price / (cost_usd × rate) − 1) × 100
        """
        col = item.column()
        row = item.row()

        # Columns: Cost=3, [%=4, Price=5], [%=6, Price=7], [%=8, Price=9], [%=10, Price=11]
        PRICE_PAIRS = [(4, 5), (6, 7), (8, 9), (10, 11)]   # (pct_col, price_col)

        self._price_table.blockSignals(True)
        try:
            # Stamp modified date
            from datetime import datetime
            mod_item = self._price_table.item(row, 13)
            if mod_item:
                mod_item.setText(datetime.now().strftime("%d-%b-%y %H:%M"))

            # Read USD cost for this row (col 3 is always USD base)
            cost_item = self._price_table.item(row, 3)
            try:
                cost_usd = float(cost_item.text().replace(",", "")) if cost_item else 0.0
            except ValueError:
                cost_usd = 0.0

            if col == 2:
                # Pkg changed → recalc cost and all prices
                try:
                    new_pkg  = int(item.text())
                    unit_cost = self._brut_cost.value()
                    new_cost  = unit_cost * new_pkg
                    if cost_item:
                        cost_item.setText(f"{new_cost:.4f}")
                    cost_usd = new_cost
                    for i, (pct_col, price_col) in enumerate(PRICE_PAIRS):
                        pct_item   = self._price_table.item(row, pct_col)
                        price_item = self._price_table.item(row, price_col)
                        if pct_item and price_item:
                            try:
                                pct  = float(pct_item.text())
                                base = self._base_cost_for_currency(cost_usd, i)
                                price_item.setText(f"{base * (1 + pct / 100):.4f}")
                            except ValueError:
                                pass
                except ValueError:
                    pass

            elif col == 3:
                # Cost (USD) changed → recalc all prices using existing %
                for i, (pct_col, price_col) in enumerate(PRICE_PAIRS):
                    pct_item   = self._price_table.item(row, pct_col)
                    price_item = self._price_table.item(row, price_col)
                    if pct_item and price_item and cost_usd > 0:
                        try:
                            pct  = float(pct_item.text())
                            base = self._base_cost_for_currency(cost_usd, i)
                            price_item.setText(f"{base * (1 + pct / 100):.4f}")
                        except ValueError:
                            pass

            elif col in (4, 6, 8, 10):
                # % changed → recalc the matching price (respecting currency)
                price_idx  = (col - 4) // 2
                price_col  = col + 1
                price_item = self._price_table.item(row, price_col)
                if price_item and cost_usd > 0:
                    try:
                        pct  = float(item.text())
                        base = self._base_cost_for_currency(cost_usd, price_idx)
                        price_item.setText(f"{base * (1 + pct / 100):.4f}")
                    except ValueError:
                        pass

            elif col in (5, 7, 9, 11):
                # Price changed → recalc % for this row, then sync to all other rows
                price_idx = (col - 5) // 2
                pct_col   = col - 1
                pct_item  = self._price_table.item(row, pct_col)
                try:
                    new_price = float(item.text().replace(",", ""))
                except ValueError:
                    new_price = None

                if pct_item and cost_usd > 0 and new_price is not None:
                    base = self._base_cost_for_currency(cost_usd, price_idx)
                    pct  = (new_price / base - 1) * 100 if base > 0 else 0.0
                    pct_item.setText(f"{pct:.2f}")

                # Propagate the new price to every other barcode row
                if new_price is not None:
                    for other_r in range(self._price_table.rowCount()):
                        if other_r == row:
                            continue
                        other_price_item = self._price_table.item(other_r, col)
                        if other_price_item:
                            other_price_item.setText(f"{new_price:.4f}")
                        # Recalc % for the other row based on its own cost
                        other_cost_item = self._price_table.item(other_r, 3)
                        other_pct_item  = self._price_table.item(other_r, pct_col)
                        if other_cost_item and other_pct_item:
                            try:
                                other_cost = float(other_cost_item.text().replace(",", ""))
                                other_base = self._base_cost_for_currency(other_cost, price_idx)
                                other_pct  = (new_price / other_base - 1) * 100 if other_base > 0 else 0.0
                                other_pct_item.setText(f"{other_pct:.2f}")
                            except ValueError:
                                pass

        finally:
            self._price_table.blockSignals(False)
            self._price_table.viewport().update()
            self._refresh_lbp_display()

    def _refresh_lbp_display(self):
        """Update the LBP equivalent label from row 0's individual price (col 5)."""
        try:
            price_item = self._price_table.item(0, 5)
            if not price_item or not price_item.text().strip():
                self._lbp_display.setText("≈ — LBP")
                return
            price = float(price_item.text().replace(",", ""))
            currency = self._sale_currency_combos[0].currentText()  # Individual currency
            if currency == "USD":
                lbp = price * self._lbp_rate
            else:
                lbp = price
            self._lbp_display.setText(f"≈ {lbp:,.0f} LBP")
        except (ValueError, AttributeError):
            self._lbp_display.setText("≈ — LBP")

    def _set_margins(self):
        """Apply a single margin % to all price columns on all rows."""
        from PySide6.QtWidgets import QInputDialog
        pct, ok = QInputDialog.getDouble(
            self, "Set Profit Margin",
            "Enter margin % to apply to all prices:",
            value=30.0, min=0.0, max=500.0, decimals=2,
        )
        if not ok:
            return
        self._price_table.blockSignals(True)
        try:
            for r in range(self._price_table.rowCount()):
                cost_item = self._price_table.item(r, 3)
                if not cost_item:
                    continue
                try:
                    cost = float(cost_item.text().replace(",", ""))
                except ValueError:
                    continue
                for i, (pct_col, price_col) in enumerate([(4,5),(6,7),(8,9),(10,11)]):
                    pct_item   = self._price_table.item(r, pct_col)
                    price_item = self._price_table.item(r, price_col)
                    if pct_item:
                        pct_item.setText(f"{pct:.2f}")
                    if price_item and cost > 0:
                        base = self._base_cost_for_currency(cost, i)
                        price_item.setText(f"{base * (1 + pct / 100):.4f}")
        finally:
            self._price_table.blockSignals(False)

    # ─────────────────────────────────────────────────────────────────────────
    # Actions
    # ─────────────────────────────────────────────────────────────────────────

    def _collect_barcodes(self) -> list:
        """Extract (id, barcode, is_primary, pack_qty) from every price-table row."""
        result = []
        for r in range(self._price_table.rowCount()):
            bc_cell = self._price_table.item(r, 1)
            pkg_cell = self._price_table.item(r, 2)
            if not bc_cell:
                continue
            barcode = bc_cell.text().strip()
            if not barcode:
                continue
            bc_id = bc_cell.data(Qt.UserRole) or ""   # "" = new row, will INSERT
            try:
                pack_qty = int(pkg_cell.text()) if pkg_cell else 1
            except ValueError:
                pack_qty = 1
            is_primary = (r == 0)
            result.append((bc_id, barcode, is_primary, pack_qty))
        return result

    def _save(self):
        if not self._code_edit.text().strip():
            self._show_error("Product code is required.")
            return
        if not self._name_edit.text().strip():
            self._show_error("Product description is required.")
            return

        # Collect prices from grid
        prices = []
        price_type_keys = ["individual", "retail", "wholesale", "semi_wholesale"]
        if self._price_table.rowCount() > 0:
            for col_idx, ptype in zip([5, 7, 9, 11], price_type_keys):
                price_item = self._price_table.item(0, col_idx)
                if price_item:
                    try:
                        amount = float(price_item.text())
                        currency = self._sale_currency_combos[
                            price_type_keys.index(ptype)
                        ].currentText()
                        prices.append(("", ptype, amount, currency, ptype == "retail"))
                    except ValueError:
                        pass

        barcodes = self._collect_barcodes()
        pack_size = max((bc[3] for bc in barcodes), default=1)

        detail = ItemDetail(
            id=self._item_id,
            code=self._code_edit.text().strip(),
            name=self._name_edit.text().strip(),
            name_ar=self._altdesc_edit.toPlainText().strip(),
            category_id=self._cat_combo.currentData() or "",
            category_name=self._cat_combo.currentText(),
            brand_id=self._brand_combo.currentData() or "",
            brand_name=self._brand_combo.currentText(),
            unit="PCS",
            pack_size=pack_size,
            cost_price=self._brut_cost.value(),
            cost_currency=self._cost_currency.currentText(),
            vat_rate=self._vat_spin.value() / 100.0,
            min_stock=0.0,
            is_active=True,
            is_pos_featured=self._chk_featured.isChecked(),
            is_online=self._chk_online.isChecked(),
            show_on_touch=self._chk_touch.isChecked(),
            photo_url=self._photo_url_edit.text().strip(),
            is_visible=True,
            notes=self._notes_edit.toPlainText(),
            barcodes=barcodes,
            prices=prices,
            stock_entries=[],
        )

        ok, err = ItemService.save_item(detail)
        if ok:
            self._status_lbl.setStyleSheet("color:#2e7d32;")
            self._status_lbl.setText("✔ Saved.")
            self.saved.emit(self._item_id)
        else:
            self._show_error(err)

    # ── Photo helpers ─────────────────────────────────────────────────────────

    def _set_photo_from_url(self):
        self._refresh_photo_preview()

    def _refresh_photo_preview(self):
        url = self._photo_url_edit.text().strip()
        if url:
            # Try to show a thumbnail from the URL
            try:
                import requests as _req
                data = _req.get(url, timeout=5).content
                pix = QPixmap()
                pix.loadFromData(data)
                if not pix.isNull():
                    scaled = pix.scaled(90, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self._img_preview.setPixmap(scaled)
                    self._img_preview.setText("")
                    return
            except Exception:
                pass
            self._img_preview.setPixmap(QPixmap())
            self._img_preview.setText("🖼 Image set")
            self._img_preview.setStyleSheet("color:#1a6cb5;")
        else:
            self._img_preview.setPixmap(QPixmap())
            self._img_preview.setText("[ No Image ]")
            self._img_preview.setStyleSheet("color:#aaaaaa;")

    def _browse_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Item Photo", "",
            "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if not path:
            return
        from sync.service import is_configured, upload_to_storage
        if not is_configured():
            QMessageBox.warning(self, "Not configured", "Supabase sync is not configured.")
            return

        import mimetypes, os
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"
        ext  = os.path.splitext(path)[1].lower()
        remote_path = f"items/{self._item_id}{ext}"

        with open(path, "rb") as f:
            data = f.read()

        ok, result = upload_to_storage("product-images", remote_path, data, mime)
        if ok:
            self._photo_url_edit.setText(result)
            self._refresh_photo_preview()
            self._status_lbl.setStyleSheet("color:#2e7d32;")
            self._status_lbl.setText("Photo uploaded — save to persist.")
        else:
            QMessageBox.warning(self, "Upload failed", result)

    def _clear_photo(self):
        self._photo_url_edit.clear()
        self._refresh_photo_preview()

    def _confirm_delete(self):
        if self._is_new:
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete item '{self._name_edit.text()}'?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            ok, err = ItemService.toggle_active(self._item_id)
            if ok:
                self._status_lbl.setStyleSheet("color:#2e7d32;")
                self._status_lbl.setText("Item deactivated.")

    def _go_search(self):
        self.back.emit()

    def _open_stock_card(self):
        from ui.screens.stock.stock_card import StockCardScreen
        sc = StockCardScreen(item_id=self._item_id, parent=self.window())
        sc.back.connect(sc.deleteLater)
        sc.setWindowFlags(Qt.Window)
        sc.resize(900, 500)
        sc.setWindowTitle(f"Stock Card — {self._name_edit.text()}")
        sc.show()

    def _show_error(self, msg: str):
        self._status_lbl.setStyleSheet("color:#c62828;")
        self._status_lbl.setText(f"✘ {msg}")

    def showEvent(self, event):
        """Load combos when screen becomes visible."""
        super().showEvent(event)
        self._load_combos()
        if self._detail:
            _set_combo(self._cat_combo, self._detail.category_name)
            _set_combo(self._brand_combo, self._detail.brand_name)


def _set_combo(combo: QComboBox, value: str):
    for i in range(combo.count()):
        if combo.itemData(i) == value or combo.itemText(i) == value:
            combo.setCurrentIndex(i)
            return
