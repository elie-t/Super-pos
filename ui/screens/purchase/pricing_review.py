"""Pricing Review dialog — shown after a purchase invoice is saved.

Lets the user update selling prices for every item in the invoice,
using the new purchase cost as the base for margin calculations.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QComboBox, QFrame, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont

from config import DEFAULT_LBP_RATE


def _load_lbp_rate() -> int:
    try:
        from database.engine import get_session, init_db
        from database.models.items import Setting
        init_db()
        s = get_session()
        try:
            r = s.get(Setting, "lbp_rate")
            return int(r.value) if r and r.value else DEFAULT_LBP_RATE
        finally:
            s.close()
    except Exception:
        return DEFAULT_LBP_RATE


COL_ITEM  = 0
COL_COST  = 1
COL_CUR   = 2
COL_OLD   = 3
COL_OLD_P = 4
COL_NEW_P = 5
COL_NEW   = 6

# Alternating background per item group
GROUP_BG = ["#eef4ff", "#f8fafc"]


class PricingReviewDialog(QDialog):

    def __init__(self, invoice_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pricing Review")
        self.setMinimumSize(1020, 600)
        self._invoice_id = invoice_id
        self._updating   = False
        self._row_data: list[dict] = []
        self._lbp_rate   = _load_lbp_rate()

        self._build_ui()
        self._load_data()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setFixedHeight(44)
        hdr.setStyleSheet("background:#1a3a5c;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(12, 0, 12, 0)
        t = QLabel("💰  Pricing Review — Update Selling Prices")
        t.setStyleSheet("color:#fff;font-size:14px;font-weight:700;")
        hl.addWidget(t)
        hl.addStretch()
        hint = QLabel("Edit  New %  or  New Price  ·  Currency combo switches USD ↔ LBP")
        hint.setStyleSheet("color:#a8c8e8;font-size:11px;")
        hl.addWidget(hint)
        lay.addWidget(hdr)

        # Legend row
        leg = QFrame()
        leg.setFixedHeight(26)
        leg.setStyleSheet("background:#f0f4f8;border-bottom:1px solid #cdd5e0;color:#1a1a2e;")
        ll = QHBoxLayout(leg)
        ll.setContentsMargins(12, 0, 12, 0)
        ll.setSpacing(20)
        for color, text in (("#bbdefb", "New % (editable)"), ("#e8f5e9", "New Price (editable)"),
                            ("#f5f5f5", "Old values (read-only)")):
            swatch = QLabel("  ")
            swatch.setFixedWidth(20)
            swatch.setStyleSheet(f"background:{color};border:1px solid #ccc;")
            lbl = QLabel(text)
            lbl.setStyleSheet("font-size:11px;color:#445566;")
            ll.addWidget(swatch)
            ll.addWidget(lbl)
        ll.addStretch()
        lay.addWidget(leg)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "Item", "New Cost", "Currency",
            "Old Price", "Old %", "New %", "New Price",
        ])
        self._table.setAlternatingRowColors(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked
        )
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(30)
        self._table.setShowGrid(True)
        self._table.itemChanged.connect(self._on_cell_changed)

        th = self._table.horizontalHeader()
        th.setSectionResizeMode(COL_ITEM, QHeaderView.Stretch)
        for col, w in ((COL_COST, 110), (COL_CUR, 80),
                       (COL_OLD, 90), (COL_OLD_P, 70), (COL_NEW_P, 70), (COL_NEW, 100)):
            th.setSectionResizeMode(col, QHeaderView.Fixed)
            self._table.setColumnWidth(col, w)
        th.setStyleSheet(
            "QHeaderView::section{background:#1a3a5c;color:#fff;font-weight:700;"
            "border:none;padding:4px;}"
        )
        # Inline editor styling
        self._table.setStyleSheet(
            "QTableWidget QLineEdit{"
            "color:#1a1a2e;background:#fff;border:2px solid #1a6cb5;"
            "font-size:13px;font-weight:700;min-height:24px;}"
        )
        lay.addWidget(self._table, 1)

        # Footer
        footer = QFrame()
        footer.setFixedHeight(52)
        footer.setStyleSheet("background:#e8f0fb;border-top:2px solid #1a6cb5;color:#1a1a2e;")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(12, 6, 12, 6)
        fl.setSpacing(10)

        save_btn = QPushButton("💾  Save Prices")
        save_btn.setFixedHeight(36)
        save_btn.setMinimumWidth(140)
        save_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;font-size:13px;font-weight:700;"
            "border:none;border-radius:5px;}"
            "QPushButton:hover{background:#1b5e20;}"
        )
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.clicked.connect(self._save_prices)
        fl.addWidget(save_btn)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(36)
        close_btn.setMinimumWidth(80)
        close_btn.setStyleSheet(
            "QPushButton{background:#607d8b;color:#fff;font-size:13px;font-weight:700;"
            "border:none;border-radius:5px;}"
            "QPushButton:hover{background:#455a64;}"
        )
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        fl.addWidget(close_btn)

        fl.addStretch()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("font-size:12px;font-weight:700;")
        fl.addWidget(self._status_lbl)

        lay.addWidget(footer)

    # ── Data ─────────────────────────────────────────────────────────────────

    def _load_data(self):
        from services.purchase_service import PurchaseService

        items = PurchaseService.get_invoice_pricing_data(self._invoice_id)

        rows: list[dict] = []
        for item_idx, item in enumerate(items):
            cost_usd     = item["cost_usd"]
            price_info   = item["prices"].get("individual", {})
            old_amount   = price_info.get("amount", 0.0) or 0.0
            old_currency = price_info.get("currency", "USD") or "USD"
            base_old     = (cost_usd * self._lbp_rate) if old_currency == "LBP" else cost_usd
            old_pct      = (old_amount / base_old - 1) * 100 if base_old > 0 and old_amount > 0 else 0.0
            rows.append({
                "item_id":      item["item_id"],
                "price_id":     price_info.get("id", ""),
                "code":         item["code"],
                "description":  item["description"],
                "cost":         item["cost"],
                "inv_currency": item["inv_currency"],
                "cost_usd":     cost_usd,
                "old_amount":   old_amount,
                "old_currency": old_currency,
                "old_pct":      old_pct,
                "new_amount":   old_amount,
                "new_currency": old_currency,
                "new_pct":      old_pct,
                "changed":      False,
            })

        self._row_data = rows
        self._updating = True
        self._table.setRowCount(len(rows))

        for r, d in enumerate(rows):
            gc = GROUP_BG[r % 2]

            def ro(text, align=Qt.AlignCenter, bg=gc):
                it = QTableWidgetItem(str(text))
                it.setTextAlignment(align)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                it.setBackground(QColor(bg))
                return it

            desc     = f"{d['description']}  [{d['code']}]"
            # Always show cost in USD so the margin % is meaningful regardless
            # of whether the purchase invoice was entered in LBP or USD.
            cost_txt = f"{d['cost_usd']:.4f}  USD"

            self._table.setItem(r, COL_ITEM, ro(desc, Qt.AlignLeft | Qt.AlignVCenter))
            self._table.setItem(r, COL_COST, ro(cost_txt))

            # Currency combo
            cur_combo = QComboBox()
            cur_combo.addItems(["USD", "LBP"])
            cur_combo.setCurrentText(d["new_currency"])
            cur_combo.setStyleSheet("background:#fff;color:#1a1a2e;")
            cur_combo.currentTextChanged.connect(
                lambda cur, row=r: self._on_currency_changed(row, cur)
            )
            self._table.setCellWidget(r, COL_CUR, cur_combo)

            # Old price / Old %
            old_it = ro(f"{d['old_amount']:.4f}", bg="#f5f5f5")
            old_it.setForeground(QColor("#888"))
            self._table.setItem(r, COL_OLD, old_it)

            old_pct_it = ro(f"{d['old_pct']:.2f}", bg="#f5f5f5")
            old_pct_it.setForeground(QColor("#888"))
            self._table.setItem(r, COL_OLD_P, old_pct_it)

            # New % (editable, yellow)
            new_pct_it = QTableWidgetItem(f"{d['new_pct']:.2f}")
            new_pct_it.setTextAlignment(Qt.AlignCenter)
            new_pct_it.setBackground(QColor("#bbdefb"))
            self._table.setItem(r, COL_NEW_P, new_pct_it)

            # New Price (editable, green)
            new_it = QTableWidgetItem(f"{d['new_amount']:.4f}")
            new_it.setTextAlignment(Qt.AlignCenter)
            new_it.setBackground(QColor("#e8f5e9"))
            self._table.setItem(r, COL_NEW, new_it)

        self._updating = False

    # ── Interaction ───────────────────────────────────────────────────────────

    def _base_cost(self, row: int) -> float:
        d = self._row_data[row]
        w = self._table.cellWidget(row, COL_CUR)
        cur = w.currentText() if w else d["new_currency"]
        return d["cost_usd"] * self._lbp_rate if cur == "LBP" else d["cost_usd"]

    def _on_cell_changed(self, item):
        if self._updating:
            return
        row = item.row()
        col = item.column()
        if row >= len(self._row_data):
            return
        base = self._base_cost(row)
        if base <= 0:
            return

        self._updating = True
        try:
            if col == COL_NEW_P:
                try:
                    pct = float(item.text())
                except ValueError:
                    return
                new_price = base * (1 + pct / 100)
                self._row_data[row]["new_pct"]    = pct
                self._row_data[row]["new_amount"] = new_price
                self._row_data[row]["changed"]    = True
                pi = self._table.item(row, COL_NEW)
                if pi:
                    pi.setText(f"{new_price:.4f}")
                    pi.setBackground(QColor("#c8e6c9"))
                item.setBackground(QColor("#90caf9"))

            elif col == COL_NEW:
                try:
                    new_price = float(item.text())
                except ValueError:
                    return
                pct = (new_price / base - 1) * 100 if base > 0 else 0.0
                self._row_data[row]["new_amount"] = new_price
                self._row_data[row]["new_pct"]    = pct
                self._row_data[row]["changed"]    = True
                pi = self._table.item(row, COL_NEW_P)
                if pi:
                    pi.setText(f"{pct:.2f}")
                    pi.setBackground(QColor("#90caf9"))
                item.setBackground(QColor("#c8e6c9"))
        finally:
            self._updating = False

    def _on_currency_changed(self, row: int, currency: str):
        if self._updating or row >= len(self._row_data):
            return
        self._updating = True
        try:
            d = self._row_data[row]
            d["new_currency"] = currency
            base = d["cost_usd"] * self._lbp_rate if currency == "LBP" else d["cost_usd"]
            if base > 0:
                new_price = base * (1 + d["new_pct"] / 100)
                d["new_amount"] = new_price
                d["changed"]    = True
                pi = self._table.item(row, COL_NEW)
                if pi:
                    pi.setText(f"{new_price:.4f}")
                    pi.setBackground(QColor("#c8e6c9"))
        finally:
            self._updating = False

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save_prices(self):
        from services.purchase_service import PurchaseService

        updates = []
        for r, d in enumerate(self._row_data):
            w = self._table.cellWidget(r, COL_CUR)
            currency = w.currentText() if w else d["new_currency"]
            if d["new_amount"] > 0:
                updates.append({
                    "price_id":   d["price_id"],   # exact DB row — may be "" if no record yet
                    "item_id":    d["item_id"],
                    "price_type": "individual",
                    "amount":     d["new_amount"],
                    "currency":   currency,
                })

        ok, err = PurchaseService.save_pricing_updates(updates)
        if ok:
            self._status_lbl.setText(f"✓  {len(updates)} prices saved.")
            self._status_lbl.setStyleSheet("font-size:12px;color:#2e7d32;font-weight:700;")
            # Reset highlight to normal
            self._updating = True
            for r, d in enumerate(self._row_data):
                d["changed"] = False
                pi_pct = self._table.item(r, COL_NEW_P)
                pi_pr  = self._table.item(r, COL_NEW)
                if pi_pct:
                    pi_pct.setBackground(QColor("#bbdefb"))
                if pi_pr:
                    pi_pr.setBackground(QColor("#e8f5e9"))
            self._updating = False
        else:
            QMessageBox.critical(self, "Error", f"Failed to save prices:\n{err}")
