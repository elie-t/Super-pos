"""
Change Selling Prices — bulk price adjustment tool.

Two modes:
  1. Bulk Adjust  — raise/lower prices by % or fixed amount for a filtered set
  2. Relationships — set price-type margins relative to individual or cost price
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QComboBox, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QRadioButton, QButtonGroup, QCheckBox,
    QDoubleSpinBox, QFrame, QAbstractItemView, QTabWidget,
    QMessageBox, QScrollArea,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

PRICE_TYPES = [
    ("individual",    "Individual"),
    ("retail",        "Online / Retail"),
    ("wholesale",     "Wholesale"),
    ("semi_wholesale","Semi-Wholesale"),
]


class ChangePricesScreen(QWidget):
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []          # loaded items with prices
        self._selected_ids: set[str] = set()
        self._build_ui()
        self._load_categories()
        self._load_items()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.setFixedWidth(90)
        back_btn.setStyleSheet(
            "QPushButton{background:#546e7a;color:#fff;border:none;"
            "border-radius:5px;font-weight:700;padding:4px 10px;}"
            "QPushButton:hover{background:#37474f;}"
        )
        back_btn.clicked.connect(self.back)
        hdr.addWidget(back_btn)
        title = QLabel("Change Selling Prices")
        title.setStyleSheet("font-size:16px;font-weight:700;color:#1a3a5c;")
        hdr.addWidget(title)
        hdr.addStretch()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("font-size:12px;font-weight:700;")
        hdr.addWidget(self._status_lbl)
        root.addLayout(hdr)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(4)

        # ── Left: filter + item table ─────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 4, 0)
        ll.setSpacing(6)

        # Filter row
        flt = QHBoxLayout()
        flt.setSpacing(6)
        self._cat_combo = QComboBox()
        self._cat_combo.setFixedHeight(28)
        self._cat_combo.currentIndexChanged.connect(self._load_items)
        flt.addWidget(QLabel("Category:"))
        flt.addWidget(self._cat_combo, 1)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search name / code…")
        self._search_edit.setFixedHeight(28)
        self._search_edit.textChanged.connect(self._apply_filter)
        flt.addWidget(self._search_edit, 1)
        ll.addLayout(flt)

        # Select all row
        sel_row = QHBoxLayout()
        self._sel_all_chk = QCheckBox("Select all")
        self._sel_all_chk.stateChanged.connect(self._toggle_select_all)
        sel_row.addWidget(self._sel_all_chk)
        sel_row.addStretch()
        self._count_lbl = QLabel("0 items")
        self._count_lbl.setStyleSheet("font-size:11px;color:#666;")
        sel_row.addWidget(self._count_lbl)
        ll.addLayout(sel_row)

        # Items table
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["", "Code", "Name", "Individual", "Retail", "Wholesale"])
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 28)
        for c in (1, 3, 4, 5):
            self._table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionMode(QAbstractItemView.NoSelection)
        self._table.setStyleSheet("font-size:11px;")
        ll.addWidget(self._table, 1)
        splitter.addWidget(left)

        # ── Right: adjustment panels ──────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)
        rl.setSpacing(8)

        tabs = QTabWidget()
        tabs.addTab(self._build_bulk_tab(),          "Bulk Adjust")
        tabs.addTab(self._build_relationships_tab(), "Relationships")
        rl.addWidget(tabs)
        rl.addStretch()
        splitter.addWidget(right)

        splitter.setSizes([620, 380])
        root.addWidget(splitter, 1)

    # ── Bulk Adjust tab ───────────────────────────────────────────────────────

    def _build_bulk_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setSpacing(12)
        l.setContentsMargins(10, 12, 10, 12)

        # Which price types
        pt_grp = QGroupBox("Apply to price types")
        pt_grp.setStyleSheet(
            "QGroupBox{font-weight:700;font-size:12px;padding-top:8px;}"
            "QCheckBox{font-size:12px;color:#1a1a1a;font-weight:normal;}"
        )
        pt_l = QVBoxLayout(pt_grp)
        self._pt_checks: dict[str, QCheckBox] = {}
        for key, label in PRICE_TYPES:
            chk = QCheckBox(label)
            chk.setChecked(True)
            self._pt_checks[key] = chk
            pt_l.addWidget(chk)
        l.addWidget(pt_grp)

        # Currency
        cur_row = QHBoxLayout()
        cur_row.addWidget(QLabel("Currency:"))
        self._bulk_cur = QComboBox()
        self._bulk_cur.addItems(["USD", "LBP"])
        self._bulk_cur.setFixedWidth(80)
        cur_row.addWidget(self._bulk_cur)
        cur_row.addStretch()
        l.addLayout(cur_row)

        # Adjust mode
        mode_grp = QGroupBox("Adjustment")
        mode_grp.setStyleSheet(
            "QGroupBox{font-weight:700;font-size:12px;padding-top:8px;}"
            "QRadioButton{font-size:12px;color:#1a1a1a;font-weight:normal;}"
        )
        mode_l = QVBoxLayout(mode_grp)

        self._mode_bg = QButtonGroup(w)
        self._mode_pct = QRadioButton("By percentage (%)")
        self._mode_amt = QRadioButton("By fixed amount")
        self._mode_pct.setChecked(True)
        self._mode_bg.addButton(self._mode_pct)
        self._mode_bg.addButton(self._mode_amt)
        mode_l.addWidget(self._mode_pct)
        mode_l.addWidget(self._mode_amt)

        val_row = QHBoxLayout()
        self._dir_combo = QComboBox()
        self._dir_combo.addItems(["Increase  (+)", "Decrease  (−)"])
        self._dir_combo.setFixedWidth(130)
        val_row.addWidget(self._dir_combo)
        self._bulk_val = QDoubleSpinBox()
        self._bulk_val.setRange(0, 9_999_999)
        self._bulk_val.setDecimals(2)
        self._bulk_val.setValue(10)
        self._bulk_val.setFixedWidth(110)
        self._bulk_val.setFixedHeight(30)
        val_row.addWidget(self._bulk_val)
        self._bulk_suffix = QLabel("%")
        self._bulk_suffix.setStyleSheet("font-size:13px;font-weight:700;")
        val_row.addWidget(self._bulk_suffix)
        val_row.addStretch()
        mode_l.addLayout(val_row)
        l.addWidget(mode_grp)

        self._mode_pct.toggled.connect(lambda on: self._bulk_suffix.setText("%" if on else ""))

        # Round LBP toggle
        self._round_lbp = QCheckBox("Round LBP to nearest 500")
        self._round_lbp.setChecked(True)
        l.addWidget(self._round_lbp)

        apply_btn = QPushButton("Apply to Selected Items")
        apply_btn.setFixedHeight(38)
        apply_btn.setStyleSheet(
            "QPushButton{background:#1565c0;color:#fff;border:none;"
            "border-radius:6px;font-weight:700;font-size:13px;}"
            "QPushButton:hover{background:#1976d2;}"
        )
        apply_btn.clicked.connect(self._apply_bulk)
        l.addWidget(apply_btn)
        l.addStretch()
        return w

    # ── Relationships tab ─────────────────────────────────────────────────────

    def _build_relationships_tab(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setSpacing(12)
        l.setContentsMargins(10, 12, 10, 12)

        info = QLabel(
            "Set prices as a % of another price or cost.\n"
            "Leave a row at 0% to skip that price type."
        )
        info.setStyleSheet("font-size:11px;color:#555;")
        info.setWordWrap(True)
        l.addWidget(info)

        # Currency
        cur_row = QHBoxLayout()
        cur_row.addWidget(QLabel("Currency:"))
        self._rel_cur = QComboBox()
        self._rel_cur.addItems(["USD", "LBP"])
        self._rel_cur.setFixedWidth(80)
        cur_row.addWidget(self._rel_cur)
        cur_row.addStretch()
        l.addLayout(cur_row)

        # Base price
        base_grp = QGroupBox("Base (source)")
        base_grp.setStyleSheet(
            "QGroupBox{font-weight:700;font-size:12px;padding-top:8px;}"
            "QRadioButton{font-size:12px;color:#1a1a1a;font-weight:normal;}"
        )
        base_l = QVBoxLayout(base_grp)
        self._base_bg = QButtonGroup(w)
        self._base_cost = QRadioButton("Cost price")
        self._base_indiv = QRadioButton("Individual price")
        self._base_indiv.setChecked(True)
        self._base_bg.addButton(self._base_cost)
        self._base_bg.addButton(self._base_indiv)
        base_l.addWidget(self._base_cost)
        base_l.addWidget(self._base_indiv)
        l.addWidget(base_grp)

        # Per price type margin
        margins_grp = QGroupBox("Target price = Base × (1 + margin %)")
        margins_grp.setStyleSheet(
            "QGroupBox{font-weight:700;font-size:12px;padding-top:8px;}"
            "QCheckBox{font-size:12px;color:#1a1a1a;font-weight:normal;}"
            "QLabel{color:#1a1a1a;font-weight:normal;}"
        )
        mg_l = QVBoxLayout(margins_grp)
        self._margin_spins: dict[str, QDoubleSpinBox] = {}
        self._margin_checks: dict[str, QCheckBox] = {}

        for key, label in PRICE_TYPES:
            row = QHBoxLayout()
            chk = QCheckBox()
            chk.setChecked(True)
            self._margin_checks[key] = chk
            row.addWidget(chk)
            row.addWidget(QLabel(f"{label}:"))
            row.addStretch()
            spin = QDoubleSpinBox()
            spin.setRange(-100, 9999)
            spin.setDecimals(1)
            spin.setSuffix(" %")
            spin.setFixedWidth(100)
            spin.setFixedHeight(28)
            # Sensible defaults
            defaults = {"individual": 30, "retail": 25, "wholesale": 15, "semi_wholesale": 20}
            spin.setValue(defaults.get(key, 20))
            self._margin_spins[key] = spin
            row.addWidget(spin)
            mg_l.addLayout(row)

        l.addWidget(margins_grp)

        # Round toggle
        self._round_lbp_rel = QCheckBox("Round LBP to nearest 500")
        self._round_lbp_rel.setChecked(True)
        l.addWidget(self._round_lbp_rel)

        apply_btn = QPushButton("Apply Margins to Selected Items")
        apply_btn.setFixedHeight(38)
        apply_btn.setStyleSheet(
            "QPushButton{background:#6a1b9a;color:#fff;border:none;"
            "border-radius:6px;font-weight:700;font-size:13px;}"
            "QPushButton:hover{background:#7b1fa2;}"
        )
        apply_btn.clicked.connect(self._apply_relationships)
        l.addWidget(apply_btn)
        l.addStretch()
        return w

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_categories(self):
        from services.item_service import ItemService
        self._cat_combo.blockSignals(True)
        self._cat_combo.clear()
        self._cat_combo.addItem("— All Categories —", "")
        for cid, cname, *_ in ItemService.get_categories():
            self._cat_combo.addItem(cname, cid)
        self._cat_combo.blockSignals(False)

    def _load_items(self):
        from database.engine import get_session, init_db
        from database.models.items import Item, ItemPrice, Category
        init_db()
        session = get_session()
        try:
            cat_id = self._cat_combo.currentData()
            q = session.query(Item).filter_by(is_active=True)
            if cat_id:
                q = q.filter(Item.category_id == cat_id)
            items = q.order_by(Item.name).all()

            self._items = []
            for item in items:
                prices: dict[str, float] = {}
                for p in session.query(ItemPrice).filter_by(item_id=item.id).all():
                    key = f"{p.price_type}_{p.currency}"
                    prices[key] = float(p.amount or 0)
                self._items.append({
                    "id":        item.id,
                    "code":      item.code or "",
                    "name":      item.name or "",
                    "cost":      float(item.cost_price or 0),
                    "cost_cur":  item.cost_currency or "USD",
                    "unit":      item.unit or "PCS",
                    "prices":    prices,
                })
        finally:
            session.close()

        self._selected_ids = set()
        self._sel_all_chk.setChecked(False)
        self._apply_filter()

    def _apply_filter(self):
        q = self._search_edit.text().strip().lower()
        visible = [
            it for it in self._items
            if not q or q in it["name"].lower() or q in it["code"].lower()
        ]
        self._populate_table(visible)

    def _populate_table(self, items: list[dict]):
        self._table.setRowCount(0)
        cur = "USD"  # display currency
        for it in items:
            r = self._table.rowCount()
            self._table.insertRow(r)

            chk = QCheckBox()
            chk.setChecked(it["id"] in self._selected_ids)
            chk.stateChanged.connect(
                lambda state, iid=it["id"]: self._on_check(iid, state))
            cell_w = QWidget()
            chl = QHBoxLayout(cell_w)
            chl.setContentsMargins(4, 0, 0, 0)
            chl.addWidget(chk)
            self._table.setCellWidget(r, 0, cell_w)

            self._table.setItem(r, 1, QTableWidgetItem(it["code"]))
            self._table.setItem(r, 2, QTableWidgetItem(it["name"]))

            for col, ptype in ((3, "individual"), (4, "retail"), (5, "wholesale")):
                amt = it["prices"].get(f"{ptype}_{cur}", 0)
                txt = f"{amt:,.2f}" if amt else "—"
                self._table.setItem(r, col, QTableWidgetItem(txt))

        self._count_lbl.setText(f"{len(items)} items")

    def _on_check(self, item_id: str, state: int):
        if state == Qt.Checked:
            self._selected_ids.add(item_id)
        else:
            self._selected_ids.discard(item_id)

    def _toggle_select_all(self, state: int):
        checked = state == Qt.Checked
        q = self._search_edit.text().strip().lower()
        for it in self._items:
            if not q or q in it["name"].lower() or q in it["code"].lower():
                if checked:
                    self._selected_ids.add(it["id"])
                else:
                    self._selected_ids.discard(it["id"])
        self._apply_filter()

    # ── Apply bulk ────────────────────────────────────────────────────────────

    def _apply_bulk(self):
        if not self._selected_ids:
            self._set_status("Select at least one item.", error=True)
            return
        chosen_types = [k for k, chk in self._pt_checks.items() if chk.isChecked()]
        if not chosen_types:
            self._set_status("Choose at least one price type.", error=True)
            return

        cur      = self._bulk_cur.currentText()
        val      = self._bulk_val.value()
        is_pct   = self._mode_pct.isChecked()
        increase = self._dir_combo.currentIndex() == 0
        factor   = (val / 100) if is_pct else val
        if not increase:
            factor = -factor

        confirm = QMessageBox.question(
            self, "Confirm",
            f"Apply {'+'if increase else '−'}{val}{'%' if is_pct else f' {cur}'} "
            f"to {len(self._selected_ids)} item(s) "
            f"for: {', '.join(chosen_types)}?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        from database.engine import get_session, init_db
        from database.models.items import ItemPrice
        from database.models.base import new_uuid
        init_db()
        session = get_session()
        updated = 0
        try:
            for item in self._items:
                if item["id"] not in self._selected_ids:
                    continue
                for ptype in chosen_types:
                    key = f"{ptype}_{cur}"
                    old = item["prices"].get(key, 0)
                    if old <= 0:
                        continue
                    if is_pct:
                        new_price = old * (1 + factor)
                    else:
                        new_price = old + factor
                    new_price = max(0, new_price)
                    if cur == "LBP" and self._round_lbp.isChecked():
                        new_price = round(new_price / 500) * 500

                    row = session.query(ItemPrice).filter_by(
                        item_id=item["id"], price_type=ptype,
                        currency=cur, pack_qty=1,
                    ).first()
                    if row:
                        row.amount = new_price
                    else:
                        session.add(ItemPrice(
                            id=new_uuid(), item_id=item["id"],
                            price_type=ptype, currency=cur,
                            amount=new_price, is_default=False,
                            is_active=True, pack_qty=1,
                        ))
                    item["prices"][key] = new_price
                    updated += 1
            session.commit()
        except Exception as exc:
            session.rollback()
            self._set_status(f"Error: {exc}", error=True)
            return
        finally:
            session.close()

        self._apply_filter()
        self._set_status(f"✔ Updated {updated} price(s) across {len(self._selected_ids)} item(s).")

    # ── Apply relationships ───────────────────────────────────────────────────

    def _apply_relationships(self):
        if not self._selected_ids:
            self._set_status("Select at least one item.", error=True)
            return
        chosen_types = [k for k, chk in self._margin_checks.items() if chk.isChecked()]
        if not chosen_types:
            self._set_status("Choose at least one price type.", error=True)
            return

        cur      = self._rel_cur.currentText()
        use_cost = self._base_cost.isChecked()

        confirm = QMessageBox.question(
            self, "Confirm",
            f"Set margins from {'cost' if use_cost else 'individual price'} "
            f"for {len(self._selected_ids)} item(s)?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        from database.engine import get_session, init_db
        from database.models.items import ItemPrice
        from database.models.base import new_uuid
        init_db()
        session = get_session()
        updated = 0
        try:
            for item in self._items:
                if item["id"] not in self._selected_ids:
                    continue

                if use_cost:
                    base_val = item["cost"] if item["cost_cur"] == cur else 0
                else:
                    base_val = item["prices"].get(f"individual_{cur}", 0)

                if base_val <= 0:
                    continue

                for ptype in chosen_types:
                    if use_cost and ptype == "individual" and not self._margin_checks["individual"].isChecked():
                        continue
                    margin = self._margin_spins[ptype].value() / 100
                    new_price = base_val * (1 + margin)
                    new_price = max(0, new_price)
                    if cur == "LBP" and self._round_lbp_rel.isChecked():
                        new_price = round(new_price / 500) * 500

                    row = session.query(ItemPrice).filter_by(
                        item_id=item["id"], price_type=ptype,
                        currency=cur, pack_qty=1,
                    ).first()
                    if row:
                        row.amount = new_price
                    else:
                        session.add(ItemPrice(
                            id=new_uuid(), item_id=item["id"],
                            price_type=ptype, currency=cur,
                            amount=new_price, is_default=False,
                            is_active=True, pack_qty=1,
                        ))
                    item["prices"][f"{ptype}_{cur}"] = new_price
                    updated += 1

            session.commit()
        except Exception as exc:
            session.rollback()
            self._set_status(f"Error: {exc}", error=True)
            return
        finally:
            session.close()

        self._apply_filter()
        self._set_status(f"✔ Set {updated} price(s) across {len(self._selected_ids)} item(s).")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, msg: str, error: bool = False):
        self._status_lbl.setText(msg)
        self._status_lbl.setStyleSheet(
            f"font-size:12px;font-weight:700;color:{'#c62828' if error else '#2e7d32'};")

    def refresh(self):
        self._load_categories()
        self._load_items()
