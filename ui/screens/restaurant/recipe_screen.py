"""
Recipe & Costing screen — define dishes, list ingredients, see profit margin.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFormLayout, QMessageBox, QFrame,
    QCompleter,
)
from PySide6.QtCore import Qt, Signal, QStringListModel, QTimer
from PySide6.QtGui import QColor, QFont
from services.recipe_service import RecipeService


class RecipeScreen(QWidget):
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_id  = ""
        self._ingredients: list[dict] = []   # working list while editing
        self._build_ui()
        self._load_list()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        hdr = QFrame()
        hdr.setStyleSheet("background:#1a3a5c;")
        hdr.setFixedHeight(48)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(14, 0, 14, 0)
        back_btn = QPushButton("← Back")
        back_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#cfe0f5;border:none;"
            "font-size:13px;font-weight:600;}"
            "QPushButton:hover{color:#fff;}"
        )
        back_btn.clicked.connect(self.back.emit)
        hl.addWidget(back_btn)
        title = QLabel("Recipes & Costing")
        title.setStyleSheet("color:#fff;font-size:16px;font-weight:700;")
        hl.addWidget(title)
        hl.addStretch()
        root.addWidget(hdr)

        # Body splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)

        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, 1)

    def _build_left(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#f5f7fa;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        search = QLineEdit()
        search.setPlaceholderText("Search recipes…")
        search.setFixedHeight(30)
        search.textChanged.connect(self._load_list)
        self._search = search
        lay.addWidget(search)

        self._list_tbl = QTableWidget(0, 3)
        self._list_tbl.setHorizontalHeaderLabels(["Recipe", "Cost", "Margin"])
        self._list_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._list_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._list_tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._list_tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self._list_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self._list_tbl.verticalHeader().setVisible(False)
        self._list_tbl.setAlternatingRowColors(True)
        self._list_tbl.setStyleSheet("font-size:12px;")
        self._list_tbl.itemClicked.connect(self._on_select)
        lay.addWidget(self._list_tbl, 1)

        new_btn = QPushButton("+ New Recipe")
        new_btn.setFixedHeight(34)
        new_btn.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#fff;border:none;"
            "border-radius:5px;font-size:13px;font-weight:700;}"
            "QPushButton:hover{background:#1a6cb5;}"
        )
        new_btn.clicked.connect(self._new_recipe)
        lay.addWidget(new_btn)
        return w

    def _build_right(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#fff;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        # ── Recipe details form ───────────────────────────────────────────────
        grp = QGroupBox("Recipe Details")
        grp.setStyleSheet("QGroupBox{font-weight:700;font-size:13px;padding-top:10px;}")
        form = QFormLayout(grp)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        self._name_edit = QLineEdit()
        self._name_edit.setFixedHeight(30)
        self._name_edit.setPlaceholderText("e.g. Grilled Chicken Plate")

        self._cat_edit = QLineEdit()
        self._cat_edit.setFixedHeight(30)
        self._cat_edit.setPlaceholderText("e.g. Main Course")

        self._desc_edit = QLineEdit()
        self._desc_edit.setFixedHeight(30)
        self._desc_edit.setPlaceholderText("Optional description")

        price_row = QHBoxLayout()
        self._price_edit = QLineEdit()
        self._price_edit.setFixedHeight(30)
        self._price_edit.setFixedWidth(120)
        self._price_edit.setPlaceholderText("0.00")
        self._price_edit.textChanged.connect(self._refresh_margin)
        self._cur_combo = QComboBox()
        self._cur_combo.addItems(["USD", "LBP"])
        self._cur_combo.setFixedHeight(30)
        price_row.addWidget(self._price_edit)
        price_row.addWidget(self._cur_combo)
        price_row.addStretch()

        form.addRow("Name *",       self._name_edit)
        form.addRow("Category",     self._cat_edit)
        form.addRow("Description",  self._desc_edit)
        form.addRow("Selling Price", price_row)
        lay.addWidget(grp)

        # ── Ingredients ───────────────────────────────────────────────────────
        ing_grp = QGroupBox("Ingredients")
        ing_grp.setStyleSheet("QGroupBox{font-weight:700;font-size:13px;padding-top:10px;}")
        ing_lay = QVBoxLayout(ing_grp)
        ing_lay.setSpacing(8)

        # Add ingredient row
        add_row = QHBoxLayout()
        add_row.setSpacing(6)

        self._item_search = QLineEdit()
        self._item_search.setPlaceholderText("Search ingredient…")
        self._item_search.setFixedHeight(30)
        self._item_completer_model = QStringListModel()
        completer = QCompleter(self._item_completer_model, self._item_search)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self._item_search.setCompleter(completer)
        self._item_search.textChanged.connect(self._update_item_completions)
        self._item_results: list[dict] = []

        self._qty_edit = QLineEdit()
        self._qty_edit.setPlaceholderText("Qty")
        self._qty_edit.setFixedWidth(70)
        self._qty_edit.setFixedHeight(30)

        self._unit_combo = QComboBox()
        self._unit_combo.addItems(["PCS", "g", "kg", "ml", "L", "tsp", "tbsp", "cup"])
        self._unit_combo.setFixedHeight(30)
        self._unit_combo.setFixedWidth(70)

        add_btn = QPushButton("Add")
        add_btn.setFixedHeight(30)
        add_btn.setFixedWidth(60)
        add_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;border:none;"
            "border-radius:4px;font-weight:700;}"
            "QPushButton:hover{background:#1b5e20;}"
        )
        add_btn.clicked.connect(self._add_ingredient)

        add_row.addWidget(self._item_search, 2)
        add_row.addWidget(self._qty_edit)
        add_row.addWidget(self._unit_combo)
        add_row.addWidget(add_btn)
        ing_lay.addLayout(add_row)

        # Ingredients table
        self._ing_tbl = QTableWidget(0, 5)
        self._ing_tbl.setHorizontalHeaderLabels(
            ["Ingredient", "Qty", "Unit", "Cost/Unit", "Line Cost"])
        self._ing_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3, 4):
            self._ing_tbl.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._ing_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self._ing_tbl.verticalHeader().setVisible(False)
        self._ing_tbl.setAlternatingRowColors(True)
        self._ing_tbl.setStyleSheet("font-size:12px;")
        self._ing_tbl.setFixedHeight(220)
        ing_lay.addWidget(self._ing_tbl)

        lay.addWidget(ing_grp, 1)

        # ── Cost summary bar ──────────────────────────────────────────────────
        summary = QFrame()
        summary.setStyleSheet(
            "background:#e8f0fb;border-radius:6px;border:1px solid #b0c4de;"
        )
        sl = QHBoxLayout(summary)
        sl.setContentsMargins(14, 8, 14, 8)
        sl.setSpacing(24)

        def _stat(label, attr, color="#1a3a5c"):
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size:10px;color:#6b7a8d;font-weight:600;")
            val = QLabel("—")
            val.setStyleSheet(f"font-size:16px;font-weight:700;color:{color};")
            col.addWidget(lbl)
            col.addWidget(val)
            setattr(self, attr, val)
            return col

        sl.addLayout(_stat("Total Cost",    "_stat_cost"))
        sl.addLayout(_stat("Selling Price", "_stat_price"))
        sl.addLayout(_stat("Profit",        "_stat_profit", "#2e7d32"))
        sl.addLayout(_stat("Margin",        "_stat_margin", "#1a6cb5"))
        sl.addStretch()
        lay.addWidget(summary)

        # ── Status + buttons ──────────────────────────────────────────────────
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("font-size:11px;")
        lay.addWidget(self._status_lbl)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save Recipe")
        save_btn.setFixedHeight(34)
        save_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;border:none;"
            "border-radius:5px;font-size:13px;font-weight:700;padding:0 20px;}"
            "QPushButton:hover{background:#1b5e20;}"
        )
        save_btn.clicked.connect(self._save)

        del_btn = QPushButton("Delete")
        del_btn.setFixedHeight(34)
        del_btn.setStyleSheet(
            "QPushButton{background:#c62828;color:#fff;border:none;"
            "border-radius:5px;font-size:13px;font-weight:700;padding:0 16px;}"
            "QPushButton:hover{background:#8b0000;}"
        )
        del_btn.clicked.connect(self._delete)

        btn_row.addWidget(save_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        return w

    # ── List ──────────────────────────────────────────────────────────────────

    def _load_list(self):
        q = self._search.text().strip().lower()
        recipes = RecipeService.get_all()
        if q:
            recipes = [r for r in recipes if q in r["name"].lower() or q in r["category"].lower()]

        self._list_tbl.setRowCount(0)
        for r in recipes:
            row = self._list_tbl.rowCount()
            self._list_tbl.insertRow(row)
            name_item = QTableWidgetItem(r["name"])
            name_item.setData(Qt.UserRole, r["id"])
            if r["category"]:
                name_item.setToolTip(r["category"])
            self._list_tbl.setItem(row, 0, name_item)

            cur = r["currency"]
            cost_val = f"{r['cost']:,.0f}" if cur == "LBP" else f"{r['cost']:,.2f}"
            self._list_tbl.setItem(row, 1, QTableWidgetItem(cost_val))

            margin_item = QTableWidgetItem(f"{r['margin']:.1f}%")
            if r["margin"] >= 50:
                margin_item.setForeground(QColor("#2e7d32"))
            elif r["margin"] >= 20:
                margin_item.setForeground(QColor("#e65100"))
            else:
                margin_item.setForeground(QColor("#c62828"))
            self._list_tbl.setItem(row, 2, margin_item)

    def _on_select(self, item):
        recipe_id = self._list_tbl.item(item.row(), 0).data(Qt.UserRole)
        detail = RecipeService.get_detail(recipe_id)
        if not detail:
            return
        self._selected_id = recipe_id
        self._name_edit.setText(detail["name"])
        self._cat_edit.setText(detail["category"])
        self._desc_edit.setText(detail["description"])
        self._price_edit.setText(str(detail["selling_price"]))
        idx = self._cur_combo.findText(detail["currency"])
        if idx >= 0:
            self._cur_combo.setCurrentIndex(idx)
        self._ingredients = detail["ingredients"]
        self._refresh_ing_table()
        self._refresh_margin()
        self._status_lbl.setText("")

    # ── Ingredients ───────────────────────────────────────────────────────────

    _item_timer = None

    def _update_item_completions(self):
        if self._item_timer:
            self._item_timer.stop()
        self._item_timer = QTimer(self)
        self._item_timer.setSingleShot(True)
        self._item_timer.setInterval(200)
        self._item_timer.timeout.connect(self._do_item_search)
        self._item_timer.start()

    def _do_item_search(self):
        q = self._item_search.text().strip()
        if not q:
            return
        self._item_results = RecipeService.search_items(q)
        self._item_completer_model.setStringList(
            [f"{i['name']}  [{i['code']}]" for i in self._item_results]
        )

    def _add_ingredient(self):
        text = self._item_search.text().strip()
        if not text:
            return
        # Match against last search results
        match = None
        for item in self._item_results:
            if text.lower() in item["name"].lower() or text in item["code"]:
                match = item
                break
        if not match:
            self._status_lbl.setStyleSheet("color:#c62828;")
            self._status_lbl.setText("Ingredient not found — type and select from the list.")
            return
        try:
            qty = float(self._qty_edit.text().replace(",", "") or 1)
        except ValueError:
            qty = 1.0
        unit = self._unit_combo.currentText()
        self._ingredients.append({
            "item_id":      match["id"],
            "item_name":    match["name"],
            "item_code":    match["code"],
            "quantity":     qty,
            "unit":         unit,
            "cost_per_unit": match["cost_price"],
            "cost_currency": match["cost_currency"],
            "line_cost":    match["cost_price"] * qty,
        })
        self._item_search.clear()
        self._qty_edit.clear()
        self._refresh_ing_table()
        self._refresh_margin()
        self._status_lbl.setText("")

    def _refresh_ing_table(self):
        self._ing_tbl.setRowCount(0)
        for i, ing in enumerate(self._ingredients):
            row = self._ing_tbl.rowCount()
            self._ing_tbl.insertRow(row)
            self._ing_tbl.setItem(row, 0, QTableWidgetItem(ing["item_name"]))
            self._ing_tbl.setItem(row, 1, QTableWidgetItem(str(ing["quantity"])))
            self._ing_tbl.setItem(row, 2, QTableWidgetItem(ing["unit"]))
            cpu = ing["cost_per_unit"]
            lc  = ing["line_cost"]
            cur = ing.get("cost_currency", "USD")
            fmt = (lambda v: f"{v:,.0f}") if cur == "LBP" else (lambda v: f"{v:,.4f}")
            self._ing_tbl.setItem(row, 3, QTableWidgetItem(f"{fmt(cpu)} {cur}"))
            self._ing_tbl.setItem(row, 4, QTableWidgetItem(f"{fmt(lc)} {cur}"))

            # Remove button
            rm = QPushButton("✕")
            rm.setFixedSize(24, 24)
            rm.setStyleSheet(
                "QPushButton{background:#c62828;color:#fff;border:none;"
                "border-radius:3px;font-size:11px;}"
                "QPushButton:hover{background:#8b0000;}"
            )
            rm.clicked.connect(lambda _, idx=i: self._remove_ingredient(idx))
            self._ing_tbl.setCellWidget(row, 4, rm)
            self._ing_tbl.setItem(row, 4, QTableWidgetItem(f"{fmt(lc)} {cur}"))
            self._ing_tbl.setCellWidget(row, 4, rm)

    def _remove_ingredient(self, idx: int):
        if 0 <= idx < len(self._ingredients):
            self._ingredients.pop(idx)
            self._refresh_ing_table()
            self._refresh_margin()

    # ── Cost summary ──────────────────────────────────────────────────────────

    def _refresh_margin(self):
        total_cost = sum(i["line_cost"] for i in self._ingredients)
        try:
            selling = float(self._price_edit.text().replace(",", "") or 0)
        except ValueError:
            selling = 0.0
        cur = self._cur_combo.currentText()
        fmt = (lambda v: f"{v:,.0f} {cur}") if cur == "LBP" else (lambda v: f"${v:,.2f}")
        profit = selling - total_cost
        margin = (profit / selling * 100) if selling > 0 else 0.0

        self._stat_cost.setText(fmt(total_cost))
        self._stat_price.setText(fmt(selling))
        self._stat_profit.setText(fmt(profit))
        self._stat_profit.setStyleSheet(
            f"font-size:16px;font-weight:700;"
            f"color:{'#2e7d32' if profit >= 0 else '#c62828'};"
        )
        self._stat_margin.setText(f"{margin:.1f}%")
        self._stat_margin.setStyleSheet(
            f"font-size:16px;font-weight:700;"
            f"color:{'#2e7d32' if margin >= 30 else '#e65100' if margin >= 0 else '#c62828'};"
        )

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def _new_recipe(self):
        self._selected_id = ""
        self._ingredients = []
        self._name_edit.clear()
        self._cat_edit.clear()
        self._desc_edit.clear()
        self._price_edit.clear()
        self._cur_combo.setCurrentIndex(0)
        self._ing_tbl.setRowCount(0)
        self._refresh_margin()
        self._status_lbl.setText("")
        self._name_edit.setFocus()

    def _save(self):
        name = self._name_edit.text().strip()
        if not name:
            self._status_lbl.setStyleSheet("color:#c62828;")
            self._status_lbl.setText("Name is required.")
            return
        try:
            price = float(self._price_edit.text().replace(",", "") or 0)
        except ValueError:
            price = 0.0

        ok, err = RecipeService.save(
            recipe_id=self._selected_id,
            name=name,
            description=self._desc_edit.text().strip(),
            category=self._cat_edit.text().strip(),
            selling_price=price,
            currency=self._cur_combo.currentText(),
            ingredients=self._ingredients,
        )
        if ok:
            self._status_lbl.setStyleSheet("color:#2e7d32;")
            self._status_lbl.setText("Saved.")
            self._load_list()
        else:
            self._status_lbl.setStyleSheet("color:#c62828;")
            self._status_lbl.setText(f"Error: {err}")

    def _delete(self):
        if not self._selected_id:
            return
        name = self._name_edit.text().strip()
        reply = QMessageBox.question(
            self, "Delete Recipe",
            f"Delete '{name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        ok, err = RecipeService.delete(self._selected_id)
        if ok:
            self._new_recipe()
            self._load_list()
        else:
            self._status_lbl.setStyleSheet("color:#c62828;")
            self._status_lbl.setText(f"Error: {err}")
