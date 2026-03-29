"""
Old Inventory Screen — shows current stock levels with flexible filters.
"""
from __future__ import annotations

from PySide6.QtCore    import Qt, Signal, QThread, QObject
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFrame, QComboBox,
    QRadioButton, QButtonGroup, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSizePolicy, QCheckBox,
    QFileDialog, QMessageBox,
)
from PySide6.QtGui import QFont, QColor


PRICE_TYPES = [
    ("Individual",      "individual"),
    ("Retail",          "retail"),
    ("Wholesale",       "wholesale"),
    ("Semi-Wholesale",  "semi_wholesale"),
]


class _Worker(QObject):
    done  = Signal(list)
    error = Signal(str)

    def __init__(self, kwargs):
        super().__init__()
        self._kw = kwargs

    def run(self):
        try:
            from services.inventory_service import InventoryService
            rows = InventoryService.run_inventory(**self._kw)
            self.done.emit(rows)
        except Exception as e:
            self.error.emit(str(e))


class InventoryScreen(QWidget):
    back = Signal()

    # ── Init ──────────────────────────────────────────────────────────────────
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows    = []
        self._thread  = None
        self._warehouses = []
        self._groups     = []
        self._subgroups  = []
        self._brands     = []
        self._suppliers  = []
        self._build_ui()
        self._load_options()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_top_bar())

        body = QHBoxLayout()
        body.setContentsMargins(10, 10, 10, 6)
        body.setSpacing(10)
        body.addWidget(self._make_filter_panel(), 3)
        body.addWidget(self._make_options_panel(), 2)

        body_w = QWidget()
        body_w.setStyleSheet("background:#f5f7fa;")
        body_w.setLayout(body)
        root.addWidget(body_w)

        root.addWidget(self._make_table_area(), 1)
        root.addWidget(self._make_footer())

    # ─ top bar ────────────────────────────────────────────────────────────────
    def _make_top_bar(self):
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background:#1a3a5c;")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 12, 0)

        back_btn = QPushButton("←  Back")
        back_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.1);color:#fff;border:1px solid "
            "rgba(255,255,255,0.25);border-radius:4px;padding:4px 12px;font-size:12px;}"
            "QPushButton:hover{background:rgba(255,255,255,0.2);}"
        )
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.back)
        lay.addWidget(back_btn)

        title = QLabel("Old Inventory")
        title.setStyleSheet("color:#fff;font-size:15px;font-weight:700;margin-left:12px;")
        lay.addWidget(title)
        lay.addStretch()

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#cfe0f5;font-size:12px;")
        lay.addWidget(self._status_lbl)
        return bar

    # ─ filter panel ───────────────────────────────────────────────────────────
    def _make_filter_panel(self):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:#fff;border:1px solid #d0d9e8;border-radius:6px;}"
            "QLabel{color:#333;font-size:12px;}"
        )
        lay = QGridLayout(frame)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setHorizontalSpacing(8)
        lay.setVerticalSpacing(6)

        def lbl(text):
            l = QLabel(text)
            l.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            return l

        def inp(w=180):
            e = QLineEdit()
            e.setFixedHeight(26)
            e.setFixedWidth(w)
            e.setStyleSheet("font-size:12px;")
            return e

        row = 0
        lay.addWidget(lbl("Barcode:"), row, 0)
        self._bc_input = inp()
        self._bc_input.returnPressed.connect(self._go)
        lay.addWidget(self._bc_input, row, 1, 1, 2)

        row += 1
        lay.addWidget(lbl("Name contains:"), row, 0)
        self._name_input = inp(240)
        lay.addWidget(self._name_input, row, 1, 1, 2)

        row += 1
        lay.addWidget(lbl("Group:"), row, 0)
        self._group_combo = QComboBox()
        self._group_combo.setFixedHeight(26)
        self._group_combo.setFixedWidth(240)
        self._group_combo.setStyleSheet("font-size:12px;")
        self._group_combo.currentIndexChanged.connect(self._on_group_changed)
        lay.addWidget(self._group_combo, row, 1, 1, 2)

        row += 1
        lay.addWidget(lbl("Sub-Group:"), row, 0)
        self._subgroup_combo = QComboBox()
        self._subgroup_combo.setFixedHeight(26)
        self._subgroup_combo.setFixedWidth(240)
        self._subgroup_combo.setStyleSheet("font-size:12px;")
        lay.addWidget(self._subgroup_combo, row, 1, 1, 2)

        row += 1
        lay.addWidget(lbl("Brand:"), row, 0)
        self._brand_combo = QComboBox()
        self._brand_combo.setFixedHeight(26)
        self._brand_combo.setFixedWidth(240)
        self._brand_combo.setStyleSheet("font-size:12px;")
        lay.addWidget(self._brand_combo, row, 1, 1, 2)

        row += 1
        lay.addWidget(lbl("Supplier:"), row, 0)
        self._supplier_combo = QComboBox()
        self._supplier_combo.setFixedHeight(26)
        self._supplier_combo.setFixedWidth(240)
        self._supplier_combo.setStyleSheet("font-size:12px;")
        lay.addWidget(self._supplier_combo, row, 1, 1, 2)

        row += 1
        lay.addWidget(lbl("Warehouse:"), row, 0)
        self._wh_combo = QComboBox()
        self._wh_combo.setFixedHeight(26)
        self._wh_combo.setFixedWidth(240)
        self._wh_combo.setStyleSheet("font-size:12px;")
        lay.addWidget(self._wh_combo, row, 1, 1, 2)

        row += 1
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#e0e8f0;")
        lay.addWidget(sep, row, 0, 1, 3)

        row += 1
        zeros_lbl = QLabel("Stock zeros:")
        zeros_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(zeros_lbl, row, 0)
        self._with_zeros = QRadioButton("With Zeros (+)")
        self._without_zeros = QRadioButton("Without Zeros (−)")
        self._without_zeros.setChecked(True)
        zgrp = QButtonGroup(self)
        zgrp.addButton(self._with_zeros)
        zgrp.addButton(self._without_zeros)
        lay.addWidget(self._with_zeros,    row, 1)
        lay.addWidget(self._without_zeros, row, 2)

        lay.setRowStretch(row + 1, 1)
        return frame

    # ─ options panel ──────────────────────────────────────────────────────────
    def _make_options_panel(self):
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame{background:#fff;border:1px solid #d0d9e8;border-radius:6px;}"
            "QLabel{color:#333;font-size:12px;}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(8)

        def section(text):
            l = QLabel(text)
            l.setStyleSheet("font-weight:700;font-size:12px;color:#1a3a5c;border:none;")
            return l

        # Unit mode
        lay.addWidget(section("Unit Display"))
        unit_row = QHBoxLayout()
        self._pcs_radio  = QRadioButton("Pcs")
        self._box_radio  = QRadioButton("Boxes")
        self._pcs_radio.setChecked(True)
        ugrp = QButtonGroup(self)
        ugrp.addButton(self._pcs_radio)
        ugrp.addButton(self._box_radio)
        unit_row.addWidget(self._pcs_radio)
        unit_row.addWidget(self._box_radio)
        unit_row.addStretch()
        lay.addLayout(unit_row)

        # Price type
        lay.addWidget(section("Price Type"))
        self._price_btns: list[QRadioButton] = []
        pgrp = QButtonGroup(self)
        for label, key in PRICE_TYPES:
            rb = QRadioButton(label)
            rb.setProperty("price_key", key)
            if key == "individual":
                rb.setChecked(True)
            pgrp.addButton(rb)
            self._price_btns.append(rb)
            lay.addWidget(rb)

        # Currency
        lay.addWidget(section("Currency"))
        cur_row = QHBoxLayout()
        self._usd_radio = QRadioButton("USD")
        self._lbp_radio = QRadioButton("LBP")
        self._usd_radio.setChecked(True)
        cgrp = QButtonGroup(self)
        cgrp.addButton(self._usd_radio)
        cgrp.addButton(self._lbp_radio)
        cur_row.addWidget(self._usd_radio)
        cur_row.addWidget(self._lbp_radio)
        cur_row.addStretch()
        lay.addLayout(cur_row)

        # Active status
        lay.addWidget(section("Item Status"))
        self._active_only  = QRadioButton("Only Active")
        self._inactive_only = QRadioButton("Not Active")
        self._all_active   = QRadioButton("All")
        self._active_only.setChecked(True)
        agrp = QButtonGroup(self)
        agrp.addButton(self._active_only)
        agrp.addButton(self._inactive_only)
        agrp.addButton(self._all_active)
        lay.addWidget(self._active_only)
        lay.addWidget(self._inactive_only)
        lay.addWidget(self._all_active)

        lay.addStretch()

        # Go button
        go_btn = QPushButton("▶   Go")
        go_btn.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#fff;font-size:14px;font-weight:700;"
            "border:none;border-radius:5px;padding:8px 0;}"
            "QPushButton:hover{background:#0d2340;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        go_btn.setCursor(Qt.PointingHandCursor)
        go_btn.clicked.connect(self._go)
        self._go_btn = go_btn
        lay.addWidget(go_btn)
        return frame

    # ─ table ─────────────────────────────────────────────────────────────────
    def _make_table_area(self):
        frame = QWidget()
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(0)

        self._table = QTableWidget()
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet("font-size:12px;")
        self._table.setSortingEnabled(True)
        hdr = self._table.horizontalHeader()
        hdr.setStretchLastSection(False)
        lay.addWidget(self._table)
        return frame

    # ─ footer ────────────────────────────────────────────────────────────────
    def _make_footer(self):
        bar = QFrame()
        bar.setFixedHeight(40)
        bar.setStyleSheet("background:#e8f0fb;border-top:1px solid #c0ccd8;")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(10)

        self._count_lbl = QLabel("0 items")
        self._count_lbl.setStyleSheet("font-size:12px;color:#555;")
        lay.addWidget(self._count_lbl)

        self._total_qty_lbl = QLabel("")
        self._total_qty_lbl.setStyleSheet("font-size:12px;color:#1a3a5c;font-weight:600;")
        lay.addWidget(self._total_qty_lbl)

        self._total_cost_lbl = QLabel("")
        self._total_cost_lbl.setStyleSheet("font-size:12px;color:#555;")
        lay.addWidget(self._total_cost_lbl)

        lay.addStretch()

        export_btn = QPushButton("Export CSV")
        export_btn.setStyleSheet(
            "QPushButton{background:#37474f;color:#fff;font-size:11px;font-weight:700;"
            "border:none;border-radius:4px;padding:4px 14px;}"
            "QPushButton:hover{background:#263238;}"
        )
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self._export_csv)
        lay.addWidget(export_btn)
        return bar

    # ── Options loading ────────────────────────────────────────────────────────
    def _load_options(self):
        from services.inventory_service import InventoryService
        try:
            whs, groups, subgroups, brands, suppliers = InventoryService.get_filter_options()
        except Exception:
            whs = groups = subgroups = brands = suppliers = []

        self._warehouses = whs
        self._groups     = groups
        self._subgroups  = subgroups
        self._brands     = brands
        self._suppliers  = suppliers

        self._wh_combo.addItem("All Warehouses", "")
        for wid, wname in whs:
            self._wh_combo.addItem(wname, wid)

        self._group_combo.addItem("All Groups", "")
        for gid, gname in groups:
            self._group_combo.addItem(gname, gid)

        self._brand_combo.addItem("All Brands", "")
        for bid, bname in brands:
            self._brand_combo.addItem(bname, bid)

        self._supplier_combo.addItem("All Suppliers", "")
        for sid, sname in suppliers:
            self._supplier_combo.addItem(sname, sid)

        self._subgroup_combo.addItem("All Sub-Groups", "")
        for sid, sname, _ in subgroups:
            self._subgroup_combo.addItem(sname, sid)

    def _on_group_changed(self):
        group_id = self._group_combo.currentData() or ""
        self._subgroup_combo.blockSignals(True)
        self._subgroup_combo.clear()
        self._subgroup_combo.addItem("All Sub-Groups", "")
        for sid, sname, parent_id in self._subgroups:
            if not group_id or parent_id == group_id:
                self._subgroup_combo.addItem(sname, sid)
        self._subgroup_combo.blockSignals(False)

    # ── Run ────────────────────────────────────────────────────────────────────
    def _go(self):
        if self._thread and self._thread.isRunning():
            return

        price_type = "individual"
        for rb in self._price_btns:
            if rb.isChecked():
                price_type = rb.property("price_key")
                break

        if self._active_only.isChecked():
            active_filter = "active"
        elif self._inactive_only.isChecked():
            active_filter = "inactive"
        else:
            active_filter = "all"

        kwargs = dict(
            warehouse_id  = self._wh_combo.currentData() or "",
            barcode       = self._bc_input.text().strip(),
            name_contains = self._name_input.text().strip(),
            group_id      = self._group_combo.currentData() or "",
            subgroup_id   = self._subgroup_combo.currentData() or "",
            brand_id      = self._brand_combo.currentData() or "",
            supplier_id   = self._supplier_combo.currentData() or "",
            price_type    = price_type,
            currency      = "USD" if self._usd_radio.isChecked() else "LBP",
            active_filter = active_filter,
            with_zeros    = self._with_zeros.isChecked(),
            unit_mode     = "pcs" if self._pcs_radio.isChecked() else "boxes",
        )

        self._go_btn.setEnabled(False)
        self._status_lbl.setText("Loading…")

        worker = _Worker(kwargs)
        thread = QThread(self)
        worker.moveToThread(thread)
        worker.done.connect(self._on_done)
        worker.error.connect(self._on_error)
        thread.started.connect(worker.run)
        self._thread  = thread
        self._worker  = worker
        thread.start()

    def _on_done(self, rows):
        self._thread.quit()
        self._go_btn.setEnabled(True)
        self._rows = rows
        use_boxes = self._box_radio.isChecked()
        currency  = "USD" if self._usd_radio.isChecked() else "LBP"
        self._populate_table(rows, use_boxes, currency)

    def _on_error(self, msg):
        self._thread.quit()
        self._go_btn.setEnabled(True)
        self._status_lbl.setText("Error")
        QMessageBox.critical(self, "Inventory Error", msg)

    # ── Table population ───────────────────────────────────────────────────────
    def _populate_table(self, rows, use_boxes: bool, currency: str):
        COL_HEADERS = ["#", "Code", "Name", "Barcode", "Group", "Sub-Group",
                       "Brand", "Supplier", "Qty", "Pack", "Cost", "Price"]

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(rows))
        self._table.setColumnCount(len(COL_HEADERS))
        self._table.setHorizontalHeaderLabels(COL_HEADERS)

        cur_sym = "ل.ل " if currency == "LBP" else "$"
        fmt_cur = (lambda v: f"ل.ل {v:,.0f}") if currency == "LBP" else (lambda v: f"${v:,.2f}")
        fmt_qty = (lambda r: f"{r.qty_pcs / r.pack_size:,.2f}") if use_boxes else (lambda r: f"{r.qty_pcs:,.2f}")

        total_qty  = 0.0
        total_cost = 0.0

        for i, r in enumerate(rows):
            qty_disp = r.qty_pcs / r.pack_size if use_boxes else r.qty_pcs
            total_qty  += qty_disp
            total_cost += r.cost * r.qty_pcs

            cells = [
                (str(i + 1),        Qt.AlignCenter),
                (r.code,            Qt.AlignLeft | Qt.AlignVCenter),
                (r.name,            Qt.AlignLeft | Qt.AlignVCenter),
                (r.barcode,         Qt.AlignCenter),
                (r.category,        Qt.AlignLeft | Qt.AlignVCenter),
                (r.subgroup,        Qt.AlignLeft | Qt.AlignVCenter),
                (r.brand,           Qt.AlignLeft | Qt.AlignVCenter),
                (r.supplier,        Qt.AlignLeft | Qt.AlignVCenter),
                (fmt_qty(r),        Qt.AlignRight | Qt.AlignVCenter),
                (str(r.pack_size),  Qt.AlignCenter),
                (fmt_cur(r.cost),   Qt.AlignRight | Qt.AlignVCenter),
                (fmt_cur(r.price),  Qt.AlignRight | Qt.AlignVCenter),
            ]
            for col, (text, align) in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(align)
                if col == 8:   # Qty — colour by sign
                    if r.qty_pcs < 0:
                        item.setForeground(QColor("#c62828"))
                    elif r.qty_pcs > 0:
                        item.setForeground(QColor("#1b5e20"))
                if col in (10, 11):
                    item.setFont(QFont("", -1, QFont.Bold))
                self._table.setItem(i, col, item)

        # Column sizing
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)   # Name stretches
        for col in range(len(COL_HEADERS)):
            if col != 2:
                hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        self._table.setSortingEnabled(True)

        # Footer stats
        n = len(rows)
        self._count_lbl.setText(f"{n} item{'s' if n != 1 else ''}")
        self._total_qty_lbl.setText(f"Total Qty: {total_qty:,.2f} {'boxes' if use_boxes else 'pcs'}")
        self._total_cost_lbl.setText(f"Total Cost: {fmt_cur(total_cost)}")
        self._status_lbl.setText(f"{n} results")

    # ── Export ─────────────────────────────────────────────────────────────────
    def _export_csv(self):
        if not self._rows:
            QMessageBox.information(self, "Export", "Run inventory first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "inventory.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            use_boxes = self._box_radio.isChecked()
            currency  = "USD" if self._usd_radio.isChecked() else "LBP"
            fmt_cur = (lambda v: f"{v:.0f}") if currency == "LBP" else (lambda v: f"{v:.4f}")
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write("Code,Name,Barcode,Group,Sub-Group,Brand,Supplier,Qty,Pack,Cost,Price\n")
                for r in self._rows:
                    qty = r.qty_pcs / r.pack_size if use_boxes else r.qty_pcs
                    f.write(
                        f'"{r.code}","{r.name}","{r.barcode}",'
                        f'"{r.category}","{r.subgroup}","{r.brand}","{r.supplier}",'
                        f'{qty:.2f},{r.pack_size},{fmt_cur(r.cost)},{fmt_cur(r.price)}\n'
                    )
            QMessageBox.information(self, "Export", f"Saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def refresh(self):
        self._load_options()
