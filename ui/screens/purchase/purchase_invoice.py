"""
Purchase Invoice — keyboard-driven entry.

Flow:
  1. Supplier  (Enter to search)
  2. Date      (arrow keys, defaults to today)
  3. Warehouse (combo, Enter → jump to barcode)
  4. Barcode   (Enter → lookup item)
       ↳ if pack_qty > 1 → Box qty → Pcs (auto = box × pack_qty)
       ↳ if pack_qty = 1 → Pcs
  5. Price     (auto-filled with last purchase cost)
  6. Disc %
  7. VAT %
  8. Total     (Enter → add line → jump to Barcode for next line)
     ↳ if Total edited manually → back-calculates Price
"""
from datetime import date as _date

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QLabel, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFrame, QGroupBox, QDoubleSpinBox,
    QDateEdit, QMessageBox, QDialog, QListWidget, QListWidgetItem,
    QDialogButtonBox, QSpinBox, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QDate, QStringListModel, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QCompleter

from services.purchase_service import PurchaseService, PurchaseLineItem
from services.supplier_service import SupplierService, SupplierDetail
from services.auth_service import AuthService
from services.item_service import ItemService


# ── tiny supplier picker dialog ────────────────────────────────────────────────

class SupplierPickerDialog(QDialog):
    def __init__(self, results, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Supplier")
        self.setMinimumWidth(480)
        self._chosen: SupplierDetail | None = None
        lay = QVBoxLayout(self)
        self._list = QListWidget()
        for sup in results:
            item = QListWidgetItem(f"{sup.name}  ({sup.phone or ''})")
            item.setData(Qt.UserRole, sup)
            self._list.addItem(item)
        self._list.doubleClicked.connect(self._accept)
        lay.addWidget(self._list)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _accept(self):
        item = self._list.currentItem()
        if item:
            self._chosen = item.data(Qt.UserRole)
            self.accept()

    @property
    def chosen(self):
        return self._chosen


# ── Item picker dialog (Ctrl+Enter from barcode field) ────────────────────────

class ItemPickerDialog(QDialog):
    """
    Browse items by name, sorted by purchase frequency.
    Arrow keys navigate, Enter selects.
    """

    def __init__(self, query: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Item Search  —  ↑↓ browse · Enter select")
        self.setMinimumSize(780, 480)
        self._chosen: dict | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # Search bar
        top = QHBoxLayout()
        self._search = QLineEdit(query)
        self._search.setPlaceholderText("Type to filter…")
        self._search.setFixedHeight(34)
        self._search.setStyleSheet("font-size:13px;")
        top.addWidget(self._search)
        search_btn = QPushButton("🔍  Search")
        search_btn.setFixedHeight(34)
        search_btn.setObjectName("primaryBtn")
        search_btn.clicked.connect(self._load)
        top.addWidget(search_btn)
        lay.addLayout(top)

        # Hint
        hint = QLabel("Sorted by most purchased first.  Ctrl+Enter or double-click to select.")
        hint.setStyleSheet("color:#888; font-size:11px;")
        lay.addWidget(hint)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["#", "Code", "Barcode", "Name", "Pkg", "Purchases"]
        )
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

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._rows: list[dict] = []

        # debounce search
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
        self._rows = PurchaseService.search_items_by_usage(query, limit=80)
        self._table.setRowCount(0)
        self._table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            vals = [
                str(i + 1),
                row["code"],
                row["barcode"],
                row["name"],
                str(row["pack_qty"]),
                str(row["usage"]) if row["usage"] else "—",
            ]
            for col, val in enumerate(vals):
                cell = QTableWidgetItem(val)
                if col == 5:
                    cell.setTextAlignment(Qt.AlignCenter)
                    if row["usage"]:
                        cell.setForeground(QColor("#2e7d32"))
                        cell.setFont(QFont("", -1, QFont.Bold))
                self._table.setItem(i, col, cell)

        if self._rows:
            self._table.selectRow(0)

    def _accept(self):
        r = self._table.currentRow()
        if 0 <= r < len(self._rows):
            self._chosen = self._rows[r]
            self.accept()

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if self._table.hasFocus() or not self._search.hasFocus():
                self._accept()
                return
        if key in (Qt.Key_Down, Qt.Key_Up):
            self._table.setFocus()
        super().keyPressEvent(event)

    @property
    def chosen(self) -> dict | None:
        return self._chosen


# ── Calculator dialog ──────────────────────────────────────────────────────────

class CalculatorDialog(QDialog):
    """Simple calculator. Close with F1, Enter or OK → returns the display value."""

    def __init__(self, initial: float = 0.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calculator  (F1 / Enter = use value)")
        self.setFixedSize(280, 340)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self._expr   = ""          # expression string being built
        self._result = initial
        self._just_evaluated = False

        lay = QVBoxLayout(self)
        lay.setSpacing(6)
        lay.setContentsMargins(10, 10, 10, 10)

        # Display
        self._display = QLineEdit(str(initial) if initial else "0")
        self._display.setReadOnly(True)
        self._display.setAlignment(Qt.AlignRight)
        self._display.setFixedHeight(44)
        self._display.setStyleSheet(
            "font-size:20px; font-weight:700; color:#1a3a5c;"
            "background:#f0f4f8; border:2px solid #1a6cb5; border-radius:4px; padding:0 8px;"
        )
        lay.addWidget(self._display)

        # Expression hint
        self._expr_lbl = QLabel("")
        self._expr_lbl.setAlignment(Qt.AlignRight)
        self._expr_lbl.setStyleSheet("color:#888; font-size:11px; padding-right:4px;")
        lay.addWidget(self._expr_lbl)

        # Button grid
        grid = QGridLayout()
        grid.setSpacing(5)
        layout_map = [
            ("C",   0, 0, "clear"),   ("⌫",  0, 1, "back"),   ("%",   0, 2, "pct"),  ("÷",  0, 3, "op"),
            ("7",   1, 0, "digit"),   ("8",  1, 1, "digit"),   ("9",   1, 2, "digit"), ("×",  1, 3, "op"),
            ("4",   2, 0, "digit"),   ("5",  2, 1, "digit"),   ("6",   2, 2, "digit"), ("−",  2, 3, "op"),
            ("1",   3, 0, "digit"),   ("2",  3, 1, "digit"),   ("3",   3, 2, "digit"), ("+",  3, 3, "op"),
            ("0",   4, 0, "digit"),   (".",  4, 1, "digit"),   ("=",   4, 2, "eq"),    ("F1", 4, 3, "use"),
        ]
        for (label, r, c, kind) in layout_map:
            btn = QPushButton(label)
            btn.setFixedHeight(44)
            if kind == "digit":
                btn.setStyleSheet(
                    "QPushButton{background:#ffffff;border:1px solid #cdd5e0;"
                    "border-radius:4px;font-size:15px;font-weight:600;color:#1a3a5c;}"
                    "QPushButton:hover{background:#e8f0fb;}"
                    "QPushButton:pressed{background:#c8d8f0;}"
                )
            elif kind == "op":
                btn.setStyleSheet(
                    "QPushButton{background:#e8f0fb;border:1px solid #1a6cb5;"
                    "border-radius:4px;font-size:16px;font-weight:700;color:#1a6cb5;}"
                    "QPushButton:hover{background:#c8d8f0;}"
                )
            elif kind == "eq":
                btn.setStyleSheet(
                    "QPushButton{background:#1a6cb5;color:#fff;border:none;"
                    "border-radius:4px;font-size:16px;font-weight:700;}"
                    "QPushButton:hover{background:#1a3a5c;}"
                )
            elif kind == "use":
                btn.setStyleSheet(
                    "QPushButton{background:#2e7d32;color:#fff;border:none;"
                    "border-radius:4px;font-size:13px;font-weight:700;}"
                    "QPushButton:hover{background:#1b5e20;}"
                )
            elif kind == "clear":
                btn.setStyleSheet(
                    "QPushButton{background:#c62828;color:#fff;border:none;"
                    "border-radius:4px;font-size:14px;font-weight:700;}"
                    "QPushButton:hover{background:#8b0000;}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton{background:#f0f4f8;border:1px solid #cdd5e0;"
                    "border-radius:4px;font-size:14px;font-weight:600;color:#555;}"
                    "QPushButton:hover{background:#e0e0e0;}"
                )
            btn.clicked.connect(lambda _, lbl=label, k=kind: self._on_btn(lbl, k))
            grid.addWidget(btn, r, c)

        lay.addLayout(grid)
        self._init_display(0)

    def _init_display(self, val):
        if val:
            self._expr = str(val)
            self._display.setText(str(val))
        else:
            self._expr = ""
            self._display.setText("0")

    def _on_btn(self, label: str, kind: str):
        if kind == "clear":
            self._expr = ""
            self._display.setText("0")
            self._expr_lbl.setText("")
            self._just_evaluated = False
        elif kind == "back":
            if self._just_evaluated:
                self._expr = ""
                self._display.setText("0")
                self._just_evaluated = False
            else:
                self._expr = self._expr[:-1]
                self._display.setText(self._expr or "0")
        elif kind == "pct":
            self._evaluate()
            try:
                self._result = round(self._result / 100, 6)
                self._expr = str(self._result)
                self._display.setText(self._expr)
            except Exception:
                pass
        elif kind == "op":
            op_map = {"×": "*", "÷": "/", "−": "-"}
            sym = op_map.get(label, label)
            if self._just_evaluated:
                self._expr = str(self._result) + sym
                self._just_evaluated = False
            else:
                self._expr += sym
            self._display.setText(self._expr)
        elif kind == "digit":
            if self._just_evaluated:
                self._expr = ""
                self._just_evaluated = False
            self._expr += label
            self._display.setText(self._expr)
        elif kind == "eq":
            self._evaluate()
        elif kind == "use":
            self._evaluate()
            self.accept()   # F1 button = send value

    def _evaluate(self):
        try:
            safe = self._expr.replace("×", "*").replace("÷", "/").replace("−", "-")
            self._result = round(float(eval(safe)), 6)  # noqa: S307
            self._expr_lbl.setText(f"= {self._result}")
            self._display.setText(str(self._result))
            self._just_evaluated = True
        except Exception:
            self._display.setText("Error")
            self._expr = ""

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_F1:
            self._evaluate()
            self.accept()          # F1 = send value back
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self._evaluate()       # Enter = evaluate only, stay in calculator
        elif key == Qt.Key_Escape:
            self.reject()
        elif key == Qt.Key_Backspace:
            self._on_btn("⌫", "back")
        elif Qt.Key_0 <= key <= Qt.Key_9:
            self._on_btn(chr(key), "digit")
        elif key == Qt.Key_Period:
            self._on_btn(".", "digit")
        elif key == Qt.Key_Plus:
            self._on_btn("+", "op")
        elif key == Qt.Key_Minus:
            self._on_btn("−", "op")
        elif key == Qt.Key_Asterisk:
            self._on_btn("×", "op")
        elif key == Qt.Key_Slash:
            self._on_btn("÷", "op")
        else:
            super().keyPressEvent(event)

    @property
    def value(self) -> float:
        return self._result


# ── Post-save action dialog ────────────────────────────────────────────────────

class PostSaveDialog(QDialog):
    """Shown after a purchase invoice is saved — lets user pick next action."""

    def __init__(self, inv_number: str, line_count: int, total: float,
                 currency: str, invoice_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Invoice Saved")
        self.setFixedSize(560, 190)
        self.choice = None      # "done" | "print" | "edit" | "pricing"
        self._invoice_id = invoice_id

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(18)

        msg = QLabel(
            f"✓  Invoice  <b>{inv_number}</b>  saved — "
            f"{line_count} lines · Total: <b>{total:,.2f} {currency}</b>"
        )
        msg.setStyleSheet("font-size:14px; color:#1a3a5c;")
        msg.setAlignment(Qt.AlignCenter)
        lay.addWidget(msg)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        for label, bg, hover, key in [
            ("✓  Done",       "#607d8b", "#455a64", "done"),
            ("🖨  Print",     "#1a6cb5", "#1a3a5c", "print"),
            ("✏  Edit",      "#e65100", "#bf360c", "edit"),
            ("💰  Pricing",  "#2e7d32", "#1b5e20", "pricing"),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(46)
            btn.setStyleSheet(
                f"QPushButton{{background:{bg};color:#fff;font-size:13px;font-weight:700;"
                f"border:none;border-radius:6px;}}"
                f"QPushButton:hover{{background:{hover};}}"
            )
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=key: self._pick(k))
            btn_row.addWidget(btn)

        lay.addLayout(btn_row)

    def _pick(self, choice: str):
        self.choice = choice
        self.accept()


# ── main screen ────────────────────────────────────────────────────────────────

class PurchaseInvoiceScreen(QWidget):
    back    = Signal()
    deleted = Signal()                  # emitted after successful delete → go to invoice list
    edit_item_requested = Signal(str, str)  # emits (item_id, supplier_id) → module opens Item Maintenance

    # Table column indices
    COL_NUM  = 0
    COL_W    = 1
    COL_CODE = 2
    COL_BC   = 3
    COL_DESC = 4
    COL_BOX  = 5
    COL_PCS  = 6
    COL_PRC  = 7
    COL_DSC  = 8
    COL_VAT  = 9
    COL_TOT  = 10
    COL_EDIT = 11
    COL_DEL  = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self._supplier: SupplierDetail | None = None
        self._lines: list[dict] = []          # list of line dicts
        self._current_item: PurchaseLineItem | None = None
        self._current_pack_qty = 1
        self._current_pcs_price = 0.0         # last_cost in invoice currency (per piece)
        self._current_box_price = 0.0         # last_cost × pack_qty in invoice currency
        self._editing_row: int = -1           # -1 = new line, ≥0 = editing existing row
        self._wh_num_map: dict[str, int] = {} # wh_id → warehouse number
        self._loaded_invoice_id: str = ""     # set when editing an existing invoice
        self._build_ui()
        self._load_defaults()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_top_bar())
        root.addWidget(self._make_setup_row())
        root.addWidget(self._make_entry_bar())
        root.addWidget(self._make_table(), stretch=1)
        root.addWidget(self._make_item_info_bar())
        root.addWidget(self._make_totals_bar())
        root.addWidget(self._make_footer())

    # ─ top bar ────────────────────────────────────────────────────────────────

    def _make_top_bar(self):
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background:#c62828;")
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
        back_btn.clicked.connect(self.back.emit)
        lay.addWidget(back_btn)

        title = QLabel("Purchase Invoice")
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

    # ─ setup row (supplier / date / warehouse) ────────────────────────────────

    def _make_setup_row(self):
        frame = QFrame()
        frame.setStyleSheet("QFrame{background:#f0f4f8;border-bottom:1px solid #cdd5e0;} QLabel{color:#1a1a2e;}")
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(10)

        # Supplier
        lay.addWidget(QLabel("Supplier:"))
        self._sup_input = QLineEdit()
        self._sup_input.setPlaceholderText("Type name…")
        self._sup_input.setFixedHeight(30)
        self._sup_input.setMinimumWidth(200)
        self._sup_input.returnPressed.connect(self._search_supplier)
        # autocomplete
        self._sup_completer_model = QStringListModel()
        sup_completer = QCompleter(self._sup_completer_model, self._sup_input)
        sup_completer.setCaseSensitivity(Qt.CaseInsensitive)
        sup_completer.setFilterMode(Qt.MatchContains)
        sup_completer.setMaxVisibleItems(12)
        sup_completer.activated.connect(self._on_supplier_autocomplete)
        self._sup_input.setCompleter(sup_completer)
        self._sup_completer = sup_completer
        # debounce timer for live search
        self._sup_timer = QTimer()
        self._sup_timer.setSingleShot(True)
        self._sup_timer.setInterval(250)
        self._sup_timer.timeout.connect(self._update_sup_completions)
        self._sup_input.textEdited.connect(lambda _: self._sup_timer.start())
        lay.addWidget(self._sup_input)

        search_btn = QPushButton("🔍")
        search_btn.setFixedSize(30, 30)
        search_btn.setCursor(Qt.PointingHandCursor)
        search_btn.clicked.connect(self._search_supplier)
        lay.addWidget(search_btn)

        self._sup_name_label = QLabel("—")
        self._sup_name_label.setStyleSheet(
            "color:#1a6cb5;font-weight:700;font-size:13px;min-width:160px;"
        )
        lay.addWidget(self._sup_name_label)

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
        # pressing Enter in warehouse combo → focus barcode
        self._wh_combo.installEventFilter(self)
        lay.addWidget(self._wh_combo)

        lay.addStretch()

        # Currency
        lay.addWidget(QLabel("Currency:"))
        self._cur_combo = QComboBox()
        self._cur_combo.setFixedHeight(30)
        self._cur_combo.addItems(["USD", "LBP"])
        lay.addWidget(self._cur_combo)

        return frame

    # ─ entry bar ──────────────────────────────────────────────────────────────

    def _make_entry_bar(self):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:#e8f0fb;border-bottom:2px solid #1a6cb5;} QLabel{color:#1a1a2e;}"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(6)

        # Barcode
        bc_lbl = QLabel("Barcode / Code:")
        bc_lbl.setStyleSheet("font-weight:600;")
        lay.addWidget(bc_lbl)
        self._bc_input = QLineEdit()
        self._bc_input.setPlaceholderText("Scan or type…")
        self._bc_input.setFixedHeight(32)
        self._bc_input.setMinimumWidth(160)
        self._bc_input.setStyleSheet("font-size:13px;font-weight:600;")
        self._bc_input.installEventFilter(self)
        lay.addWidget(self._bc_input)

        self._item_desc_label = QLabel("")
        self._item_desc_label.setStyleSheet(
            "color:#1a3a5c;font-weight:600;min-width:180px;font-size:12px;"
        )
        lay.addWidget(self._item_desc_label)

        lay.addSpacing(8)

        # Box
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

        # Pcs
        self._pcs_lbl = QLabel("Pcs:")
        self._pcs_lbl.setStyleSheet("font-weight:600;")
        lay.addWidget(self._pcs_lbl)
        self._pcs_spin = QDoubleSpinBox()
        self._pcs_spin.setRange(0, 999999)
        self._pcs_spin.setDecimals(3)
        self._pcs_spin.setFixedHeight(32)
        self._pcs_spin.setFixedWidth(80)
        self._pcs_spin.installEventFilter(self)
        self._pcs_spin.valueChanged.connect(self._on_pcs_changed)
        lay.addWidget(self._pcs_spin)

        # Price
        self._price_lbl = QLabel("Price:")
        self._price_lbl.setStyleSheet("font-weight:600;")
        lay.addWidget(self._price_lbl)
        self._price_spin = QDoubleSpinBox()
        self._price_spin.setRange(0, 999999999)
        self._price_spin.setDecimals(2)
        self._price_spin.setGroupSeparatorShown(True)
        self._price_spin.setFixedHeight(32)
        self._price_spin.setFixedWidth(120)
        self._price_spin.installEventFilter(self)
        # also catch F1 on the spinbox's internal line edit
        for child in self._price_spin.children():
            if hasattr(child, 'installEventFilter'):
                child.installEventFilter(self)
        lay.addWidget(self._price_spin)

        # Disc %
        disc_lbl = QLabel("Disc%:")
        disc_lbl.setStyleSheet("font-weight:600;")
        lay.addWidget(disc_lbl)
        self._disc_spin = QDoubleSpinBox()
        self._disc_spin.setRange(0, 100)
        self._disc_spin.setDecimals(2)
        self._disc_spin.setFixedHeight(32)
        self._disc_spin.setFixedWidth(70)
        self._disc_spin.installEventFilter(self)
        lay.addWidget(self._disc_spin)

        # VAT %
        vat_lbl = QLabel("VAT%:")
        vat_lbl.setStyleSheet("font-weight:600;")
        lay.addWidget(vat_lbl)
        self._vat_spin = QDoubleSpinBox()
        self._vat_spin.setRange(0, 100)
        self._vat_spin.setDecimals(2)
        self._vat_spin.setFixedHeight(32)
        self._vat_spin.setFixedWidth(70)
        self._vat_spin.installEventFilter(self)
        lay.addWidget(self._vat_spin)

        # Total
        tot_lbl = QLabel("Total:")
        tot_lbl.setStyleSheet("font-weight:700;color:#1a3a5c;")
        lay.addWidget(tot_lbl)
        self._total_spin = QDoubleSpinBox()
        self._total_spin.setRange(0, 999999999)
        self._total_spin.setDecimals(2)
        self._total_spin.setGroupSeparatorShown(True)
        self._total_spin.setFixedHeight(32)
        self._total_spin.setFixedWidth(130)
        self._total_spin.setStyleSheet("font-weight:700;font-size:13px;")
        self._total_spin.installEventFilter(self)
        # back-calc price when total is changed
        self._total_spin.valueChanged.connect(self._on_total_changed)
        lay.addWidget(self._total_spin)

        self._total_editing = False   # flag to avoid recursion

        # Add / Update button
        self._add_btn = QPushButton("✓  Add")
        self._add_btn.setObjectName("primaryBtn")
        self._add_btn.setFixedHeight(32)
        self._add_btn.setFixedWidth(90)
        self._add_btn.setCursor(Qt.PointingHandCursor)
        self._add_btn.clicked.connect(self._add_line)
        lay.addWidget(self._add_btn)

        # New item button — opens Item Maintenance with blank form
        new_item_btn = QPushButton("＋ New Item")
        new_item_btn.setFixedHeight(32)
        new_item_btn.setFixedWidth(90)
        new_item_btn.setCursor(Qt.PointingHandCursor)
        new_item_btn.setStyleSheet(
            "QPushButton{background:#1565c0;color:#fff;border:none;border-radius:4px;"
            "font-size:12px;font-weight:700;}"
            "QPushButton:hover{background:#0d47a1;}"
        )
        new_item_btn.clicked.connect(self._open_new_item)
        lay.addWidget(new_item_btn)

        # Cancel edit button (hidden when not editing)
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

        self._set_box_enabled(1)
        return frame

    # ─ table ──────────────────────────────────────────────────────────────────

    def _make_table(self):
        self._table = QTableWidget()
        self._table.setColumnCount(13)
        self._table.setHorizontalHeaderLabels([
            "#", "W", "Code", "Barcode", "Description",
            "Box", "Pcs", "Price", "Disc%", "VAT%", "Total", "", "",
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked
        )
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        self._table.itemChanged.connect(self._on_cell_edited)
        self._table.itemSelectionChanged.connect(self._on_row_selected)
        self._table_updating = False
        # Inline editor: tall, clearly visible, dark text on white
        self._table.setStyleSheet(
            "QTableWidget QLineEdit {"
            "  color:#1a3a5c; background:#ffffff;"
            "  border:2px solid #1a6cb5;"
            "  font-size:14px; font-weight:700;"
            "  min-height:28px; padding:0 4px;"
            "}"
        )
        self._table.installEventFilter(self)
        hdr = self._table.horizontalHeader()
        # Description: fixed width so price/total columns have room
        hdr.setSectionResizeMode(self.COL_DESC, QHeaderView.Fixed)
        self._table.setColumnWidth(self.COL_DESC, 220)
        # Numeric columns: fixed minimum widths so editors are comfortable
        for col in (self.COL_NUM, self.COL_W, self.COL_CODE, self.COL_BC):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        for col, w in (
            (self.COL_BOX, 52), (self.COL_PCS, 72), (self.COL_PRC, 120),
            (self.COL_DSC, 68), (self.COL_VAT, 68), (self.COL_TOT, 120),
        ):
            hdr.setSectionResizeMode(col, QHeaderView.Fixed)
            self._table.setColumnWidth(col, w)
        for col in (self.COL_EDIT, self.COL_DEL):              # edit/del buttons
            hdr.setSectionResizeMode(col, QHeaderView.Fixed)
            self._table.setColumnWidth(col, 30)
        # Taller rows — editor fits comfortably
        self._table.verticalHeader().setDefaultSectionSize(34)
        hdr.setStyleSheet(
            "QHeaderView::section{background:#1b5e20;color:#fff;"
            "font-weight:700;border:none;padding:4px;}"
        )
        return self._table

    # ─ item info bar (shows when a row is selected) ───────────────────────────

    def _make_item_info_bar(self):
        frame = QFrame()
        frame.setFixedHeight(38)
        frame.setStyleSheet(
            "background:#1a3a5c;"
            "border-top:1px solid #0d2238; border-bottom:1px solid #0d2238;"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(0)

        def lbl(text, bold=False, min_w=0, color="#cfe0f5"):
            l = QLabel(text)
            style = f"color:{color}; font-size:12px;"
            if bold:
                style += " font-weight:700;"
            if min_w:
                style += f" min-width:{min_w}px;"
            l.setStyleSheet(style)
            return l

        lay.addWidget(lbl("Item: ", bold=True))
        self._info_name   = lbl("—", min_w=200, color="#ffffff")
        self._info_name.setStyleSheet(
            "color:#ffffff; font-size:12px; font-weight:700; min-width:200px;"
        )
        lay.addWidget(self._info_name)

        lay.addWidget(lbl("   │  "))
        self._info_sub = lbl("—", color="#cfe0f5", min_w=90)
        lay.addWidget(self._info_sub)

        lay.addWidget(lbl("   │  Stock: ", bold=True))
        self._info_stock  = lbl("—", color="#1565c0")
        self._info_stock.setStyleSheet("color:#1565c0; font-size:13px; font-weight:700; min-width:70px;")
        lay.addWidget(self._info_stock)

        lay.addWidget(lbl("   │  Box: ", bold=True))
        self._info_box = lbl("—", color="#ffd54f")
        self._info_box.setStyleSheet("color:#ffd54f; font-size:12px; font-weight:700; min-width:50px;")
        lay.addWidget(self._info_box)

        lay.addWidget(lbl("   │  ", bold=False))

        # Selling prices — up to 4 price types
        self._info_price_labels: list[QLabel] = []
        for _ in range(6):
            pl = lbl("", min_w=110)
            self._info_price_labels.append(pl)
            lay.addWidget(pl)

        lay.addStretch()
        self._item_info_frame = frame
        return frame

    # ─ totals bar — removed, totals now live in footer right panel ───────────

    def _make_totals_bar(self):
        # Placeholder — totals are rendered inside _make_footer
        frame = QFrame()
        frame.setFixedHeight(0)
        return frame

    # ─ footer ─────────────────────────────────────────────────────────────────

    def _make_footer(self):
        frame = QFrame()
        frame.setStyleSheet("QFrame{background:#e8f0fb;border-top:2px solid #1a6cb5;} QLabel{color:#1a1a2e;}")
        outer = QHBoxLayout(frame)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(10)

        # ── Left: buttons + order + note ─────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(4)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        save_btn = QPushButton("💾  Save Invoice")
        save_btn.setFixedHeight(36)
        save_btn.setMinimumWidth(150)
        save_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;font-size:13px;font-weight:700;"
            "border-radius:4px;border:none;}"
            "QPushButton:hover{background:#1b5e20;}"
        )
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save_invoice)
        btn_row.addWidget(save_btn)

        clear_btn = QPushButton("🗑  Clear All")
        clear_btn.setObjectName("warningBtn")
        clear_btn.setFixedHeight(36)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_all)
        btn_row.addWidget(clear_btn)

        self._delete_btn = QPushButton("✖  Delete Invoice")
        self._delete_btn.setFixedHeight(36)
        self._delete_btn.setStyleSheet(
            "QPushButton{background:#6a1010;color:#fff;font-size:13px;font-weight:700;"
            "border-radius:4px;border:none;}"
            "QPushButton:hover{background:#a01010;}"
        )
        self._delete_btn.setCursor(Qt.PointingHandCursor)
        self._delete_btn.clicked.connect(self._delete_invoice)
        self._delete_btn.hide()   # shown only when editing an existing invoice
        btn_row.addWidget(self._delete_btn)

        collector_btn = QPushButton("📥  Fill from Data Collector")
        collector_btn.setFixedHeight(36)
        collector_btn.setStyleSheet(
            "QPushButton{background:#5c35a0;color:#fff;font-size:13px;"
            "border-radius:4px;border:none;padding:0 12px;}"
            "QPushButton:hover{background:#4527a0;}"
        )
        collector_btn.setCursor(Qt.PointingHandCursor)
        collector_btn.clicked.connect(self._fill_from_collector)
        btn_row.addWidget(collector_btn)

        btn_row.addStretch()
        left.addLayout(btn_row)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)
        order_lbl = QLabel("Order#:")
        order_lbl.setStyleSheet("font-size:11px;")
        meta_row.addWidget(order_lbl)
        self._order_input = QLineEdit()
        self._order_input.setFixedHeight(24)
        self._order_input.setFixedWidth(100)
        self._order_input.setStyleSheet("font-size:11px;")
        meta_row.addWidget(self._order_input)
        meta_row.addSpacing(10)
        note_lbl = QLabel("Note:")
        note_lbl.setStyleSheet("font-size:11px;")
        meta_row.addWidget(note_lbl)
        self._notes_input = QLineEdit()
        self._notes_input.setFixedHeight(28)
        self._notes_input.setMinimumWidth(240)
        self._notes_input.setStyleSheet("font-size:12px;")
        meta_row.addWidget(self._notes_input)
        meta_row.addStretch()
        left.addLayout(meta_row)

        outer.addLayout(left, 1)
        outer.addStretch()

        # ── Right: stacked totals ─────────────────────────────────────────────
        totals_frame = QFrame()
        totals_frame.setStyleSheet(
            "QFrame{background:#f8faff;border-left:3px solid #1a6cb5;border-radius:0;padding:0 8px;}"
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

        self._lines_count_lbl = stat_row(0, "Lines:")
        self._subtotal_lbl    = stat_row(1, "Sub-Total:")
        self._disc_lbl        = stat_row(2, "Discount:")
        self._vat_lbl         = stat_row(3, "VAT:")
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#bbd0ee;")
        tlay.addWidget(sep, 4, 0, 1, 2)
        self._grand_total_lbl = stat_row(5, "Grand Total:", big=True, color="#c62828")

        outer.addWidget(totals_frame)
        return frame

    # ── Defaults ──────────────────────────────────────────────────────────────

    def _load_defaults(self):
        warehouses = ItemService.get_warehouses()
        self._wh_num_map = {}
        self._wh_combo.blockSignals(True)
        self._wh_combo.clear()
        for wh_id, wh_name, is_default, wh_num, _def_cust in warehouses:
            self._wh_combo.addItem(wh_name, wh_id)
            if is_default:
                self._wh_combo.setCurrentText(wh_name)
            if wh_num is not None:
                self._wh_num_map[wh_id] = wh_num
        self._wh_combo.blockSignals(False)
        self._wh_combo.currentIndexChanged.connect(self._on_warehouse_changed)
        self._refresh_invoice_number()
        # Load LBP rate for price conversion
        try:
            from database.engine import get_session, init_db
            from database.models.items import Setting
            init_db()
            _s = get_session()
            try:
                r = _s.get(Setting, "lbp_rate")
                self._lbp_rate = (int(r.value) if r and r.value else 0) or 90_000
            finally:
                _s.close()
        except Exception:
            self._lbp_rate = 90_000
        self._sup_input.setFocus()

    def _refresh_invoice_number(self):
        wh_id = self._wh_combo.currentData() or ""
        self._inv_no = PurchaseService.next_invoice_number(wh_id)
        self._inv_no_label.setText(f"Invoice #  {self._inv_no}")

    def _on_warehouse_changed(self):
        self._refresh_invoice_number()

    # ── Supplier autocomplete ─────────────────────────────────────────────────

    def _update_sup_completions(self):
        query = self._sup_input.text().strip()
        if len(query) < 1:
            self._sup_completer_model.setStringList([])
            return
        results = SupplierService.search(query, limit=30)
        self._sup_completer_model.setStringList([s.name for s in results])

    def _on_supplier_autocomplete(self, name: str):
        """Called when user selects a suggestion from the dropdown."""
        results = SupplierService.search(name, limit=5)
        exact = next((s for s in results if s.name == name), None)
        if exact:
            self._set_supplier(exact)
        elif results:
            self._set_supplier(results[0])

    # ── Supplier search ───────────────────────────────────────────────────────

    def _search_supplier(self):
        query = self._sup_input.text().strip()
        if not query:
            return
        results = SupplierService.search(query, limit=50)
        if not results:
            QMessageBox.warning(self, "Not Found", f"No supplier found for '{query}'.")
            return
        if len(results) == 1:
            self._set_supplier(results[0])
        else:
            dlg = SupplierPickerDialog(results, self)
            if dlg.exec() and dlg.chosen:
                self._set_supplier(dlg.chosen)

    def _set_supplier(self, sup: SupplierDetail):
        self._supplier = sup
        self._sup_name_label.setText(sup.name)
        self._sup_input.setText(sup.name)
        # Auto-set currency from supplier's preferred currency
        sup_currency = getattr(sup, "currency", "USD") or "USD"
        idx = self._cur_combo.findText(sup_currency)
        if idx >= 0:
            self._cur_combo.setCurrentIndex(idx)
        # advance focus to date
        self._date_edit.setFocus()

    # ── Barcode entry ──────────────────────────────────────────────────────────

    def _on_barcode_entered(self):
        query = self._bc_input.text().strip()
        if not query:
            return

        # try barcode first, fall back to code
        item = PurchaseService.lookup_item(query, "barcode")
        if not item:
            item = PurchaseService.lookup_item(query, "code")
        if not item:
            self._item_desc_label.setText("⚠ Not found")
            self._item_desc_label.setStyleSheet("color:#c62828;font-weight:600;")
            return

        # Duplicate check (only when not already editing that row)
        for idx, line in enumerate(self._lines):
            if line["item"].item_id == item.item_id and idx != self._editing_row:
                line_num = idx + 1
                ans = QMessageBox.question(
                    self, "Item Already Listed",
                    f"This item is already in line #{line_num}.\n\n"
                    f"Add another line anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if ans != QMessageBox.Yes:
                    self._bc_input.clear()
                    self._bc_input.setFocus()
                    return
                break  # user confirmed duplicate → continue loading

        self._current_item = item
        self._current_pack_qty = item.pack_qty

        self._item_desc_label.setText(item.description[:36])
        self._item_desc_label.setStyleSheet("color:#1a3a5c;font-weight:600;font-size:12px;")

        # Update info bar immediately on item found
        self._load_item_info(
            item.item_id, item.description,
            subgroup=getattr(item, "subgroup", ""),
        )

        # Convert last_cost to invoice currency only if currencies differ
        inv_currency = self._cur_combo.currentText()
        last_cost_currency = getattr(item, "last_cost_currency", "USD") or "USD"
        if inv_currency == "LBP" and last_cost_currency == "USD":
            rate = self._lbp_rate
        elif inv_currency == "USD" and last_cost_currency == "LBP":
            rate = 1.0 / self._lbp_rate if self._lbp_rate else 1.0
        else:
            rate = 1.0
        self._current_pcs_price = item.last_cost * rate
        self._current_box_price = item.last_cost * item.pack_qty * rate

        # Reset entry fields — set prices BEFORE touching spins so _on_box_changed
        # fires with correct values already in place
        self._block_total(True)
        self._box_spin.setValue(0)
        self._pcs_spin.setValue(0)
        self._price_spin.setValue(self._current_pcs_price)
        self._disc_spin.setValue(0)
        self._vat_spin.setValue(0)          # VAT stays 0 unless user sets it
        self._total_spin.setValue(0)
        self._block_total(False)

        self._set_box_enabled(item.pack_qty)
        self._bc_input.clearFocus()
        if self._current_pack_qty > 1:
            QTimer.singleShot(0, self._focus_box)
        else:
            QTimer.singleShot(0, self._focus_pcs)

    def _focus_box(self):
        self._box_spin.setFocus()
        self._box_spin.selectAll()

    def _focus_pcs(self):
        self._pcs_spin.setFocus()
        self._pcs_spin.selectAll()

    def _set_box_enabled(self, pack_qty: int):
        active = pack_qty > 1
        self._box_lbl.setStyleSheet(
            "font-weight:600;" if active else "font-weight:600;color:#aaa;"
        )
        self._pcs_lbl.setText(f"Pcs ({pack_qty}):" if active else "Pcs:")
        self._pcs_spin.setStyleSheet("")
        self._price_lbl.setText("Price:")

    def _on_box_changed(self, val):
        if self._current_pack_qty > 1:
            auto = val > 0
            self._pcs_spin.setStyleSheet(
                "background:#e8e8e8;color:#555;" if auto else ""
            )
            self._price_lbl.setText("Price/Box:" if auto else "Price:")
            self._pcs_spin.blockSignals(True)
            self._pcs_spin.setValue(val * self._current_pack_qty)
            self._pcs_spin.blockSignals(False)
            # Switch price between box price and pcs price
            self._block_total(True)
            self._price_spin.setValue(
                self._current_box_price if auto else self._current_pcs_price
            )
            self._block_total(False)
        self._recalc_total()

    def _on_pcs_changed(self, val):
        """User edited pcs — reset box to 0 so they don't conflict."""
        if self._current_pack_qty > 1 and self._box_spin.value() > 0:
            self._box_spin.blockSignals(True)
            self._box_spin.setValue(0)
            self._box_spin.blockSignals(False)
            self._pcs_spin.setStyleSheet("")
            self._price_lbl.setText("Price:")
        self._recalc_total()

    def _recalc_total(self):
        boxes = self._box_spin.value()
        pcs   = self._pcs_spin.value()
        price = self._price_spin.value()
        disc  = self._disc_spin.value()
        vat   = self._vat_spin.value()
        # When boxes are used: price is per box → total = boxes × price_per_box
        qty = boxes if (self._current_pack_qty > 1 and boxes > 0) else pcs
        net = qty * price * (1 - disc / 100) * (1 + vat / 100)
        self._block_total(True)
        self._total_spin.setValue(round(net, 2))
        self._block_total(False)

    def _on_total_changed(self, val):
        """Back-calculate unit price when total is edited by the user."""
        if self._total_editing:
            return
        boxes = self._box_spin.value()
        pcs   = self._pcs_spin.value()
        disc  = self._disc_spin.value()
        vat   = self._vat_spin.value()
        qty   = boxes if (self._current_pack_qty > 1 and boxes > 0) else pcs
        denom = qty * (1 - disc / 100) * (1 + vat / 100)
        if denom > 0:
            self._price_spin.blockSignals(True)
            self._price_spin.setValue(round(val / denom, 2))
            self._price_spin.blockSignals(False)

    def _block_total(self, block: bool):
        self._total_editing = block
        self._total_spin.blockSignals(block)

    def _open_item_picker(self):
        """Open item search dialog. Selected item loads into the entry bar."""
        query = self._bc_input.text().strip()
        dlg = ItemPickerDialog(query, self)
        if dlg.exec() and dlg.chosen:
            row = dlg.chosen
            # Use lookup_item so pack_qty is resolved correctly (box barcode check)
            item = PurchaseService.lookup_item(row["code"], "code")
            if not item:
                return
            self._current_item = item
            self._current_pack_qty = item.pack_qty

            self._bc_input.setText(row["barcode"] or row["code"])
            self._item_desc_label.setText(row["name"][:36])
            self._item_desc_label.setStyleSheet(
                "color:#1a3a5c;font-weight:600;font-size:12px;"
            )

            # Update info bar immediately
            self._load_item_info(
                item.item_id, item.description,
                subgroup=getattr(item, "subgroup", ""),
            )

            inv_currency = self._cur_combo.currentText()
            last_cost_currency = getattr(item, "last_cost_currency", "USD") or "USD"
            if inv_currency == "LBP" and last_cost_currency == "USD":
                rate = self._lbp_rate
            elif inv_currency == "USD" and last_cost_currency == "LBP":
                rate = 1.0 / self._lbp_rate if self._lbp_rate else 1.0
            else:
                rate = 1.0
            self._current_pcs_price = item.last_cost * rate
            self._current_box_price = item.last_cost * item.pack_qty * rate

            self._block_total(True)
            self._box_spin.setValue(0)
            self._pcs_spin.setValue(0)
            self._price_spin.setValue(self._current_pcs_price)
            self._disc_spin.setValue(0)
            self._vat_spin.setValue(0)
            self._total_spin.setValue(0)
            self._block_total(False)

            self._set_box_enabled(row["pack_qty"])
            self._bc_input.clearFocus()
            if self._current_pack_qty > 1:
                QTimer.singleShot(0, self._focus_box)
            else:
                QTimer.singleShot(0, self._focus_pcs)

    def _open_calculator(self, initial: float, target: str, row: int):
        """Open calculator. On accept, push value to price field or table cell."""
        dlg = CalculatorDialog(initial, self)
        if dlg.exec() == QDialog.Accepted:
            val = dlg.value
            if target == "entry":
                self._price_spin.setValue(val)
                self._recalc_total()
                self._price_spin.setFocus()
            elif target == "table" and 0 <= row < len(self._lines):
                self._lines[row]["price"] = val
                pcs  = self._lines[row]["pcs"]
                disc = self._lines[row]["disc"]
                vat  = self._lines[row]["vat"]
                self._lines[row]["total"] = round(
                    pcs * val * (1 - disc / 100) * (1 + vat / 100), 2
                )
                self._refresh_table()
                self._refresh_totals()

    # ── eventFilter — Enter key navigation ────────────────────────────────────

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.KeyPress:
            key = event.key()

            # ── Enter / Ctrl+Enter on barcode field ──────────────────────────
            if key in (Qt.Key_Return, Qt.Key_Enter) and obj is self._bc_input:
                if event.modifiers() & Qt.ControlModifier:
                    self._open_item_picker()
                else:
                    self._on_barcode_entered()
                return True

            # ── F1 → open calculator on price column (table or entry-bar price spin) ──
            if key == Qt.Key_F1:
                # F1 on the table while price column is selected
                if obj is self._table or obj is self._table.viewport():
                    col = self._table.currentColumn()
                    if col == self.COL_PRC:
                        row = self._table.currentRow()
                        current_val = self._lines[row]["price"] if 0 <= row < len(self._lines) else 0.0
                        self._open_calculator(current_val, "table", row)
                        return True
                # F1 on the entry-bar price spinbox
                if obj is self._price_spin:
                    self._open_calculator(self._price_spin.value(), "entry", -1)
                    return True

            if key in (Qt.Key_Return, Qt.Key_Enter):
                if obj is self._wh_combo:
                    self._bc_input.setFocus()
                    self._bc_input.selectAll()
                    return True
                if obj is self._box_spin:
                    if self._current_pack_qty > 1 and self._box_spin.value() > 0:
                        # box filled → pcs auto-calculated → skip to price
                        self._recalc_total()
                        self._price_spin.setFocus()
                        self._price_spin.selectAll()
                    else:
                        # box is 0 → user wants to enter pcs manually
                        self._pcs_spin.setFocus()
                        self._pcs_spin.selectAll()
                    return True
                if obj is self._pcs_spin:
                    self._recalc_total()
                    self._price_spin.setFocus()
                    self._price_spin.selectAll()
                    return True
                if obj is self._price_spin:
                    self._recalc_total()
                    self._disc_spin.setFocus()
                    self._disc_spin.selectAll()
                    return True
                if obj is self._disc_spin:
                    self._recalc_total()
                    self._vat_spin.setFocus()
                    self._vat_spin.selectAll()
                    return True
                if obj is self._vat_spin:
                    self._recalc_total()
                    self._total_spin.setFocus()
                    self._total_spin.selectAll()
                    return True
                if obj is self._total_spin:
                    self._add_line()
                    return True
        return super().eventFilter(obj, event)

    # ── Add line ──────────────────────────────────────────────────────────────

    def _add_line(self):
        if not self._current_item:
            self._bc_input.setFocus()
            return

        pcs = self._pcs_spin.value()
        if pcs <= 0:
            QMessageBox.warning(self, "Quantity", "Please enter a quantity.")
            self._pcs_spin.setFocus()
            return

        line = {
            "item":  self._current_item,
            "box":   self._box_spin.value(),
            "pcs":   pcs,
            "pkg":   self._current_pack_qty,
            "price": self._price_spin.value(),
            "disc":  self._disc_spin.value(),
            "vat":   self._vat_spin.value(),
            "total": self._total_spin.value(),
        }

        if self._editing_row >= 0:
            self._lines[self._editing_row] = line
        else:
            self._lines.append(line)

        self._refresh_table()
        self._refresh_totals()
        self._clear_entry()

    def _edit_line(self, row: int):
        """Open Item Maintenance for the item on this line."""
        if row < 0 or row >= len(self._lines):
            return
        item_id = self._lines[row]["item"].item_id
        supplier_id = self._supplier.id if self._supplier else ""
        self.edit_item_requested.emit(item_id, supplier_id)

    def _open_new_item(self):
        """Open Item Maintenance with a blank form to create a new item."""
        supplier_id = self._supplier.id if self._supplier else ""
        self.edit_item_requested.emit("", supplier_id)

    def _cancel_edit(self):
        self._editing_row = -1
        self._clear_entry()

    def _clear_entry(self):
        self._current_item = None
        self._current_pack_qty = 1
        self._editing_row = -1
        self._bc_input.clear()
        self._item_desc_label.setText("")
        self._block_total(True)
        self._box_spin.setValue(0)
        self._pcs_spin.setValue(0)
        self._price_spin.setValue(0)
        self._disc_spin.setValue(0)
        self._vat_spin.setValue(0)
        self._total_spin.setValue(0)
        self._block_total(False)
        self._set_box_enabled(1)
        # Reset add button style
        self._add_btn.setText("✓  Add")
        self._add_btn.setStyleSheet("")   # revert to objectName style
        self._add_btn.setObjectName("primaryBtn")
        self._add_btn.style().unpolish(self._add_btn)
        self._add_btn.style().polish(self._add_btn)
        self._cancel_edit_btn.hide()
        self._bc_input.setFocus()

    # ── Table refresh ──────────────────────────────────────────────────────────

    # Columns that the user can double-click and edit directly
    _EDITABLE_COLS = {
        COL_BOX,   # 4
        COL_PCS,   # 5
        COL_PRC,   # 6
        COL_DSC,   # 7
        COL_VAT,   # 8
        COL_TOT,   # 9
    }

    def _refresh_table(self):
        self._table_updating = True
        self._table.setRowCount(0)
        self._table.setRowCount(len(self._lines))
        wh_id = self._wh_combo.currentData() or ""
        wh_num = self._wh_num_map.get(wh_id, "")
        wh_str = str(wh_num) if wh_num != "" else ""
        for row, line in enumerate(self._lines):
            item = line["item"]
            pkg = line["pkg"]
            box = line["box"]
            pcs = line["pcs"]
            box_str = str(int(box)) if pkg > 1 else ""
            pcs_str = f"({int(pcs)})" if pkg > 1 else f"{pcs:.3f}"
            vals = [
                str(row + 1),
                wh_str,
                item.code,
                item.barcode,
                item.description,
                box_str,
                pcs_str,
                f"{line['price']:.4f}",
                f"{line['disc']:.2f}",
                f"{line['vat']:.2f}",
                f"{line['total']:.2f}",
                "",
            ]
            for col, val in enumerate(vals):
                cell = QTableWidgetItem(val)
                if col in (self.COL_PRC, self.COL_TOT):
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if col in (self.COL_W, self.COL_DSC, self.COL_VAT, self.COL_BOX, self.COL_PCS):
                    cell.setTextAlignment(Qt.AlignCenter)
                # Pcs is read-only when pkg>1 (auto-calculated from box)
                if col == self.COL_PCS and pkg > 1:
                    cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                # Editable columns: normal flags; read-only: remove Editable flag
                if col not in self._EDITABLE_COLS:
                    cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                else:
                    cell.setFlags(cell.flags() | Qt.ItemIsEditable)
                self._table.setItem(row, col, cell)

            # Edit button
            edit_btn = QPushButton("✏")
            edit_btn.setToolTip("Edit this line")
            edit_btn.setStyleSheet(
                "QPushButton{background:#e65100;color:#fff;border:none;border-radius:3px;}"
                "QPushButton:hover{background:#bf360c;}"
            )
            edit_btn.setFixedSize(24, 24)
            edit_btn.setCursor(Qt.PointingHandCursor)
            edit_btn.clicked.connect(lambda _, r=row: self._edit_line(r))
            self._table.setCellWidget(row, self.COL_EDIT, edit_btn)

            # Delete button
            del_btn = QPushButton("✕")
            del_btn.setToolTip("Remove line")
            del_btn.setStyleSheet(
                "QPushButton{background:#c62828;color:#fff;border:none;border-radius:3px;}"
                "QPushButton:hover{background:#8b0000;}"
            )
            del_btn.setFixedSize(24, 24)
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.clicked.connect(lambda _, r=row: self._delete_line(r))
            self._table.setCellWidget(row, self.COL_DEL, del_btn)

        self._table_updating = False
        if self._lines:
            self._table.scrollToItem(self._table.item(len(self._lines) - 1, 0))

    def _on_cell_edited(self, cell):
        if self._table_updating:
            return
        row = cell.row()
        col = cell.column()
        if row < 0 or row >= len(self._lines) or col not in self._EDITABLE_COLS:
            return

        try:
            val = float(cell.text().replace(",", "").replace("%", "").strip())
        except ValueError:
            return  # user typed something invalid — ignore

        line = self._lines[row]

        if col == self.COL_BOX:
            line["box"] = val
            if line["pkg"] > 1:
                line["pcs"] = val * line["pkg"]
        elif col == self.COL_PCS:
            line["pcs"] = val
            # Pcs edited manually — reset box, convert price from per-box to per-piece
            if line["pkg"] > 1 and line.get("box", 0) > 0:
                line["box"]   = 0
                line["price"] = round(line["price"] / line["pkg"], 4)
        elif col == self.COL_PRC:
            line["price"] = val
        elif col == self.COL_DSC:
            line["disc"] = val
        elif col == self.COL_VAT:
            line["vat"] = val
        elif col == self.COL_TOT:
            # back-calc price from total
            box  = line.get("box", 0)
            pcs  = line["pcs"]
            disc = line["disc"]
            vat  = line["vat"]
            qty  = box if (line["pkg"] > 1 and box > 0) else pcs
            denom = qty * (1 - disc / 100) * (1 + vat / 100)
            if denom > 0:
                line["price"] = round(val / denom, 4)
            line["total"] = val
            self._refresh_table()
            self._refresh_totals()
            return

        # Recalc total — use box×price when box mode, pcs×price otherwise
        box   = line.get("box", 0)
        qty   = box if (line["pkg"] > 1 and box > 0) else line["pcs"]
        price = line["price"]
        disc  = line["disc"]
        vat   = line["vat"]
        line["total"] = round(qty * price * (1 - disc / 100) * (1 + vat / 100), 2)

        self._refresh_table()
        self._refresh_totals()

    def _on_row_selected(self):
        if self._table_updating:
            return
        row = self._table.currentRow()
        if row < 0 or row >= len(self._lines):
            self._clear_item_info()
            return
        line = self._lines[row]
        item = line["item"]
        self._load_item_info(
            item.item_id, item.description,
            subgroup=getattr(item, "subgroup", ""),
        )

    def _load_item_info(self, item_id: str, name: str, subgroup: str = ""):
        from database.engine import get_session, init_db
        from database.models.items import ItemPrice, ItemStock
        init_db()
        session = get_session()
        try:
            wh_id = self._wh_combo.currentData()
            stock = session.query(ItemStock).filter_by(
                item_id=item_id, warehouse_id=wh_id
            ).first()
            stock_qty = stock.quantity if stock else 0.0

            prices = session.query(ItemPrice).filter_by(item_id=item_id).order_by(
                ItemPrice.is_default.desc(), ItemPrice.price_type
            ).all()

        finally:
            session.close()

        # pack_qty comes from the lookup result stored on _current_item
        pack_qty = getattr(self._current_item, "pack_qty", 1) or 1

        self._info_name.setText(name[:40])
        self._info_sub.setText(subgroup or "—")
        self._info_stock.setText(f"{stock_qty:,.3f} u")
        self._info_box.setText(f"{pack_qty} pcs/box" if pack_qty > 1 else "unit")

        # Fill price labels
        for lbl in self._info_price_labels:
            lbl.setText("")

        type_display = {
            "retail": "Retail", "wholesale": "W/Sale",
            "semi_wholesale": "Semi-W", "cost": "Cost",
        }
        for i, p in enumerate(prices[:6]):
            kind = type_display.get(p.price_type, p.price_type.capitalize())
            self._info_price_labels[i].setText(
                f"{kind}: {p.amount:,.4f} {p.currency}   "
            )

    def _clear_item_info(self):
        self._info_name.setText("—")
        self._info_sub.setText("—")
        self._info_stock.setText("—")
        self._info_box.setText("—")
        for lbl in self._info_price_labels:
            lbl.setText("")

    def _delete_line(self, row: int):
        if 0 <= row < len(self._lines):
            self._lines.pop(row)
            self._refresh_table()
            self._refresh_totals()

    # ── Totals ────────────────────────────────────────────────────────────────

    def _refresh_totals(self):
        subtotal = 0.0
        disc_val = 0.0
        vat_val  = 0.0
        for line in self._lines:
            box    = line.get("box", 0)
            pcs    = line["pcs"]
            pkg    = line.get("pkg", 1)
            price  = line["price"]
            disc   = line["disc"]
            vat    = line["vat"]
            qty    = box if (pkg > 1 and box > 0) else pcs
            gross  = qty * price
            d      = gross * disc / 100
            net_hd = gross - d
            v      = net_hd * vat / 100
            subtotal += gross
            disc_val += d
            vat_val  += v

        grand = subtotal - disc_val + vat_val

        self._lines_count_lbl.setText(str(len(self._lines)))
        self._subtotal_lbl.setText(f"{subtotal:,.2f}")
        self._disc_lbl.setText(f"{disc_val:,.2f}")
        self._vat_lbl.setText(f"{vat_val:,.2f}")
        self._grand_total_lbl.setText(f"{grand:,.2f}")

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save_invoice(self):
        if not self._supplier:
            QMessageBox.warning(self, "Supplier", "Please select a supplier first.")
            self._sup_input.setFocus()
            return
        if not self._lines:
            QMessageBox.warning(self, "Empty", "No lines to save.")
            return

        wh_id    = self._wh_combo.currentData()
        operator = AuthService.current_user()
        inv_date = self._date_edit.date().toString("yyyy-MM-dd")
        currency = self._cur_combo.currentText()

        # Convert lines to PurchaseLineItem objects
        line_items = []
        for line in self._lines:
            it = line["item"]
            line_items.append(PurchaseLineItem(
                item_id=it.item_id,
                code=it.code,
                barcode=it.barcode,
                description=it.description,
                pack_qty=line["pkg"],
                box_qty=line["box"],
                pcs_qty=line["pcs"],
                price=line["price"],
                disc_pct=line["disc"],
                vat_pct=line["vat"],
                total=line["total"],
            ))

        ok, result = PurchaseService.save_invoice(
            supplier_id=self._supplier.id,
            operator_id=operator.id if operator else "",
            warehouse_id=wh_id,
            invoice_number=self._inv_no,
            invoice_date=inv_date,
            due_date=inv_date,
            order_number=self._order_input.text().strip(),
            currency=currency,
            lines=line_items,
            payment_mode="account",
            notes=self._notes_input.text().strip(),
            invoice_id=self._loaded_invoice_id or None,
        )

        if ok:
            invoice_id = result
            total = sum(l.total for l in line_items)
            dlg = PostSaveDialog(
                inv_number=self._inv_no,
                line_count=len(line_items),
                total=total,
                currency=currency,
                invoice_id=invoice_id,
                parent=self,
            )
            dlg.exec()

            if dlg.choice == "edit":
                self.load_invoice(invoice_id)
            elif dlg.choice == "pricing":
                from ui.screens.purchase.pricing_review import PricingReviewDialog
                PricingReviewDialog(invoice_id, self).exec()
                self._clear_all()
                self._refresh_invoice_number()
            elif dlg.choice == "print":
                QMessageBox.information(self, "Print", "Print feature coming soon.")
                self._clear_all()
                self._refresh_invoice_number()
            else:  # "done" or dialog closed
                self._clear_all()
                self._refresh_invoice_number()
        else:
            QMessageBox.critical(self, "Error", f"Failed to save:\n{result}")

    # ── Data collector import ──────────────────────────────────────────────────

    def _fill_from_collector(self):
        from ui.widgets.data_collector_dialog import DataCollectorDialog
        dlg = DataCollectorDialog(self)
        if not dlg.exec():
            return
        added = skipped = 0
        for row in dlg.rows:
            item = row["item"]
            if not item:
                skipped += 1
                continue
            qty = row["qty"]
            # Check for existing line — merge qty
            for line in self._lines:
                if line["item"].item_id == item.item_id:
                    line["pcs"] += qty
                    line["box"] = round(line["pcs"] / item.pack_qty) if item.pack_qty > 1 else 0
                    line["total"] = round(line["pcs"] * line["price"] * (1 - line["disc"] / 100), 2)
                    added += 1
                    break
            else:
                price = item.last_cost * item.pack_qty if item.pack_qty > 1 else item.last_cost
                if self._cur_combo.currentText() == "LBP":
                    price = price * self._lbp_rate
                self._lines.append({
                    "item":  item,
                    "box":   0,
                    "pcs":   qty,
                    "pkg":   item.pack_qty,
                    "price": price,
                    "disc":  0.0,
                    "vat":   item.vat_pct,
                    "total": round(qty * price, 2),
                })
                added += 1
        self._refresh_table()
        self._refresh_totals()
        QMessageBox.information(
            self, "Imported",
            f"Imported {added} item(s)." +
            (f"\n{skipped} barcode(s) not found — skipped." if skipped else "")
        )

    # ── Clear all ─────────────────────────────────────────────────────────────

    def _delete_invoice(self):
        if not self._loaded_invoice_id:
            return
        reply = QMessageBox.question(
            self, "Delete Invoice",
            f"Delete invoice {self._inv_no}?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        ok, err = PurchaseService.delete_invoice(self._loaded_invoice_id)
        if ok:
            self.deleted.emit()
        else:
            QMessageBox.warning(self, "Error", err)

    def _clear_all(self):
        self._loaded_invoice_id = ""
        self._lines.clear()
        self._supplier = None
        self._sup_name_label.setText("—")
        self._sup_input.clear()
        self._date_edit.setDate(QDate.currentDate())
        self._notes_input.clear()
        self._order_input.clear()
        self._refresh_table()
        self._refresh_totals()
        self._clear_entry()
        self._sup_input.setFocus()

    def load_invoice(self, invoice_id: str):
        """Populate screen from an existing saved invoice."""
        data = PurchaseService.get_invoice(invoice_id)
        if not data:
            QMessageBox.warning(self, "Not Found", "Invoice could not be loaded.")
            return

        # Header fields
        self._loaded_invoice_id = invoice_id
        self._inv_no = data["invoice_number"]
        self._inv_no_label.setText(f"Invoice #  {self._inv_no}  [EDIT]")
        self._delete_btn.show()

        # Supplier
        if data["supplier"]:
            from services.supplier_service import SupplierDetail
            sup = data["supplier"]
            self._supplier = SupplierDetail(
                id=sup.id, name=sup.name,
                code=getattr(sup, "code", "") or "",
                phone=getattr(sup, "phone", "") or "",
                phone2=getattr(sup, "phone2", "") or "",
                email=getattr(sup, "email", "") or "",
                address=getattr(sup, "address", "") or "",
                classification=getattr(sup, "classification", "") or "",
                credit_limit=getattr(sup, "credit_limit", 0.0) or 0.0,
                currency=getattr(sup, "currency", "USD") or "USD",
                balance=getattr(sup, "balance", 0.0) or 0.0,
                notes=getattr(sup, "notes", "") or "",
                is_active=getattr(sup, "is_active", True),
            )
            self._sup_name_label.setText(sup.name)
            self._sup_input.setText(sup.name)

        # Date
        if data["date"]:
            self._date_edit.setDate(QDate.fromString(data["date"], "yyyy-MM-dd"))

        # Currency
        idx = self._cur_combo.findText(data["currency"])
        if idx >= 0:
            self._cur_combo.setCurrentIndex(idx)

        # Warehouse
        for i in range(self._wh_combo.count()):
            if self._wh_combo.itemData(i) == data["warehouse_id"]:
                self._wh_combo.setCurrentIndex(i)
                break

        self._order_input.setText(data["order_number"])
        self._notes_input.setText(data["notes"])

        # Lines — build the same dict structure _refresh_table expects
        self._lines.clear()
        for li in data["lines"]:
            item_proxy = PurchaseLineItem(
                item_id=li["item_id"],
                code=li["code"],
                barcode=li["barcode"],
                description=li["description"],
                pack_qty=li["pack_qty"],
                box_qty=li["box"],
                pcs_qty=li["pcs"],
                price=li["price"],
                disc_pct=li["disc"],
                vat_pct=li["vat"],
                total=li["total"],
                last_cost=li["last_cost"],
            )
            self._lines.append({
                "item":  item_proxy,
                "box":   li["box"],
                "pcs":   li["pcs"],
                "pkg":   li["pack_qty"],
                "price": li["price"],
                "disc":  li["disc"],
                "vat":   li["vat"],
                "total": li["total"],
            })

        self._refresh_table()
        self._refresh_totals()
        self._bc_input.setFocus()

    def refresh(self):
        pass
