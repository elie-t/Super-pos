"""
Daily Sales dialog — current shift report + old sales browser + End of Shift.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QComboBox, QDateEdit, QTabWidget, QWidget, QMessageBox,
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor, QFont

from services.daily_sales_service import DailySalesService


def _fmt(amount: float, currency: str) -> str:
    """Format a monetary amount with its currency symbol."""
    if currency == "LBP":
        return f"ل.ل {amount:,.0f}"
    return f"${amount:,.2f}"


class _Card(QFrame):
    def __init__(self, label: str, bg: str = "#1a3a5c", parent=None):
        super().__init__(parent)
        self.setFixedHeight(62)
        self.setMinimumWidth(120)
        self.setStyleSheet(
            f"QFrame{{background:{bg};border-radius:8px;}}"
            "QLabel{background:transparent;border:none;}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(1)
        self._val = QLabel("—")
        self._val.setStyleSheet("font-size:16px;font-weight:700;color:#fff;")
        self._val.setAlignment(Qt.AlignCenter)
        lbl = QLabel(label)
        lbl.setStyleSheet("font-size:10px;color:#aed6f1;letter-spacing:0.5px;")
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._val)
        lay.addWidget(lbl)

    def set(self, v: str):
        self._val.setText(v)


class _EndOfShiftConfirmDialog(QDialog):
    def __init__(self, count: int, total_lines: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("End of Shift")
        self.setFixedSize(440, 280)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self._build(count, total_lines)

    def _build(self, count: int, total_lines: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setFixedHeight(54)
        hdr.setStyleSheet("background:#c62828;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)
        icon = QLabel("🔴")
        icon.setStyleSheet("font-size:22px;")
        hl.addWidget(icon)
        title = QLabel("  End of Shift")
        title.setStyleSheet("color:#fff;font-size:16px;font-weight:700;letter-spacing:0.5px;")
        hl.addWidget(title)
        hl.addStretch()
        root.addWidget(hdr)

        # Body
        body = QFrame()
        body.setStyleSheet("background:#fff;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(28, 22, 28, 18)
        bl.setSpacing(14)

        q = QLabel("Are you sure you want to close the current shift?")
        q.setStyleSheet("font-size:13px;font-weight:600;color:#1a1a2e;")
        q.setWordWrap(True)
        bl.addWidget(q)

        # Stats row
        stats = QHBoxLayout()
        stats.setSpacing(12)

        def stat_card(label, value, bg):
            f = QFrame()
            f.setStyleSheet(
                f"QFrame{{background:{bg};border-radius:8px;}}"
                "QLabel{background:transparent;border:none;}"
            )
            f.setFixedHeight(58)
            fl = QVBoxLayout(f)
            fl.setContentsMargins(12, 6, 12, 6)
            fl.setSpacing(2)
            vl = QLabel(value)
            vl.setStyleSheet("color:#fff;font-size:15px;font-weight:700;")
            vl.setAlignment(Qt.AlignCenter)
            ll = QLabel(label)
            ll.setStyleSheet("color:#cce;font-size:10px;letter-spacing:0.3px;")
            ll.setAlignment(Qt.AlignCenter)
            fl.addWidget(vl)
            fl.addWidget(ll)
            return f

        stats.addWidget(stat_card("Invoices", f"{count:,}", "#1a3a5c"))
        stats.addWidget(stat_card("Total", total_lines, "#2e7d32"))
        bl.addLayout(stats)

        note = QLabel("All open invoices will be archived and moved to Old Sales.")
        note.setStyleSheet(
            "font-size:11px;color:#1a3a5c;"
            "background:#e3f2fd;border:1px solid #90caf9;"
            "border-radius:4px;padding:6px 10px;"
        )
        note.setWordWrap(True)
        bl.addWidget(note)

        root.addWidget(body, 1)

        # Footer buttons
        foot = QFrame()
        foot.setFixedHeight(54)
        foot.setStyleSheet("background:#f0f4f8;border-top:1px solid #cdd5e0;")
        fl2 = QHBoxLayout(foot)
        fl2.setContentsMargins(20, 8, 20, 8)
        fl2.setSpacing(12)
        fl2.addStretch()

        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(34)
        cancel.setStyleSheet(
            "QPushButton{background:#607d8b;color:#fff;border:none;"
            "border-radius:6px;font-size:13px;font-weight:600;padding:0 20px;}"
            "QPushButton:hover{background:#455a64;}"
        )
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)

        confirm = QPushButton("🔴  Close Shift")
        confirm.setFixedHeight(34)
        confirm.setStyleSheet(
            "QPushButton{background:#c62828;color:#fff;border:none;"
            "border-radius:6px;font-size:13px;font-weight:700;padding:0 20px;}"
            "QPushButton:hover{background:#a01010;}"
        )
        confirm.setCursor(Qt.PointingHandCursor)
        confirm.clicked.connect(self.accept)

        fl2.addWidget(cancel)
        fl2.addWidget(confirm)
        root.addWidget(foot)


class _EndOfShiftSuccessDialog(QDialog):
    def __init__(self, archived: int, total_lines: str, path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Shift Closed")
        self.setFixedSize(420, 260)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self._build(archived, total_lines, path)

    def _build(self, archived: int, total_lines: str, path: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setFixedHeight(54)
        hdr.setStyleSheet("background:#1b5e20;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(20, 0, 20, 0)
        icon = QLabel("✅")
        icon.setStyleSheet("font-size:22px;")
        hl.addWidget(icon)
        title = QLabel("  Shift Closed Successfully")
        title.setStyleSheet("color:#fff;font-size:16px;font-weight:700;")
        hl.addWidget(title)
        hl.addStretch()
        root.addWidget(hdr)

        # Body
        body = QFrame()
        body.setStyleSheet("background:#fff;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(28, 18, 28, 14)
        bl.setSpacing(12)

        # Stats
        stats = QHBoxLayout()
        stats.setSpacing(12)

        def stat_card(label, value, bg):
            f = QFrame()
            f.setStyleSheet(
                f"QFrame{{background:{bg};border-radius:8px;}}"
                "QLabel{background:transparent;border:none;}"
            )
            f.setFixedHeight(58)
            fl = QVBoxLayout(f)
            fl.setContentsMargins(12, 6, 12, 6)
            fl.setSpacing(2)
            vl = QLabel(value)
            vl.setStyleSheet("color:#fff;font-size:15px;font-weight:700;")
            vl.setAlignment(Qt.AlignCenter)
            ll = QLabel(label)
            ll.setStyleSheet("color:#cce;font-size:10px;letter-spacing:0.3px;")
            ll.setAlignment(Qt.AlignCenter)
            fl.addWidget(vl)
            fl.addWidget(ll)
            return f

        stats.addWidget(stat_card("Archived", f"{archived:,}", "#1a3a5c"))
        stats.addWidget(stat_card("Total", total_lines, "#2e7d32"))
        bl.addLayout(stats)

        path_lbl = QLabel(f"📁  {path}")
        path_lbl.setStyleSheet(
            "font-size:10px;color:#444;"
            "background:#f5f5f5;border:1px solid #ddd;"
            "border-radius:4px;padding:5px 8px;"
        )
        path_lbl.setWordWrap(True)
        bl.addWidget(path_lbl)

        root.addWidget(body, 1)

        # Footer
        foot = QFrame()
        foot.setFixedHeight(54)
        foot.setStyleSheet("background:#f0f4f8;border-top:1px solid #cdd5e0;")
        fl2 = QHBoxLayout(foot)
        fl2.setContentsMargins(20, 8, 20, 8)
        fl2.addStretch()
        ok = QPushButton("✓  OK")
        ok.setFixedHeight(34)
        ok.setStyleSheet(
            "QPushButton{background:#1b5e20;color:#fff;border:none;"
            "border-radius:6px;font-size:13px;font-weight:700;padding:0 28px;}"
            "QPushButton:hover{background:#2e7d32;}"
        )
        ok.setCursor(Qt.PointingHandCursor)
        ok.clicked.connect(self.accept)
        fl2.addWidget(ok)
        root.addWidget(foot)


class DailySalesDialog(QDialog):
    def __init__(self, warehouse_id: str = "", parent=None):
        super().__init__(parent)
        self._warehouse_id    = warehouse_id
        self._report: dict    = {}
        self._shift_was_closed = False

        self.setWindowTitle("Daily Sales")
        self.setMinimumSize(900, 660)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self._build_ui()
        self._refresh()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        bar = QFrame()
        bar.setFixedHeight(46)
        bar.setStyleSheet("background:#1a3a5c;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 0, 12, 0)
        title_lbl = QLabel("📊  Daily Sales")
        title_lbl.setStyleSheet("color:#fff;font-size:15px;font-weight:700;")
        bl.addWidget(title_lbl)
        bl.addStretch()
        x = QPushButton("✕")
        x.setFixedSize(28, 28)
        x.setStyleSheet("QPushButton{background:#c62828;color:#fff;border:none;border-radius:4px;font-weight:700;}"
                        "QPushButton:hover{background:#a01010;}")
        x.clicked.connect(self.reject)
        bl.addWidget(x)
        root.addWidget(bar)

        # ── Mode + date controls ──────────────────────────────────────────────
        ctrl = QFrame()
        ctrl.setStyleSheet("background:#f0f4f8;border-bottom:1px solid #cdd5e0;")
        cl = QHBoxLayout(ctrl)
        cl.setContentsMargins(16, 8, 16, 8)
        cl.setSpacing(10)

        mode_lbl = QLabel("View:")
        mode_lbl.setStyleSheet("font-weight:600;color:#1a3a5c;font-size:12px;")
        cl.addWidget(mode_lbl)

        self._mode = QComboBox()
        self._mode.setFixedHeight(30)
        self._mode.setFixedWidth(150)
        self._mode.addItems(["Daily Sales", "Old Sales"])
        self._mode.currentIndexChanged.connect(self._on_mode)
        cl.addWidget(self._mode)

        cl.addSpacing(12)

        self._from_lbl = QLabel("From:")
        self._from_lbl.setStyleSheet("font-weight:600;color:#555;font-size:12px;")
        cl.addWidget(self._from_lbl)

        self._from_dt = QDateEdit()
        self._from_dt.setFixedHeight(30)
        self._from_dt.setDisplayFormat("dd/MM/yyyy")
        self._from_dt.setCalendarPopup(True)
        self._from_dt.setDate(QDate.currentDate())
        cl.addWidget(self._from_dt)

        self._to_lbl = QLabel("To:")
        self._to_lbl.setStyleSheet("font-weight:600;color:#555;font-size:12px;")
        cl.addWidget(self._to_lbl)

        self._to_dt = QDateEdit()
        self._to_dt.setFixedHeight(30)
        self._to_dt.setDisplayFormat("dd/MM/yyyy")
        self._to_dt.setCalendarPopup(True)
        self._to_dt.setDate(QDate.currentDate())
        cl.addWidget(self._to_dt)

        cl.addSpacing(8)
        wh_lbl = QLabel("Warehouse:")
        wh_lbl.setStyleSheet("font-weight:600;color:#555;font-size:12px;")
        cl.addWidget(wh_lbl)

        self._wh = QComboBox()
        self._wh.setFixedHeight(30)
        self._wh.setMinimumWidth(130)
        self._wh.addItem("All", "")
        for wid, wname in DailySalesService.get_warehouses():
            self._wh.addItem(wname, wid)
        if self._warehouse_id:
            idx = self._wh.findData(self._warehouse_id)
            if idx >= 0:
                self._wh.setCurrentIndex(idx)
        cl.addWidget(self._wh)

        cl.addStretch()

        refresh_btn = QPushButton("🔄  Refresh")
        refresh_btn.setFixedHeight(30)
        refresh_btn.setStyleSheet(
            "QPushButton{background:#1a6cb5;color:#fff;border:none;"
            "border-radius:4px;font-size:12px;font-weight:600;padding:0 12px;}"
            "QPushButton:hover{background:#1a3a5c;}"
        )
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh)
        cl.addWidget(refresh_btn)

        root.addWidget(ctrl)

        # ── Summary cards ─────────────────────────────────────────────────────
        cf = QFrame()
        cf.setStyleSheet("background:#fff;border-bottom:1px solid #dde4ed;")
        cfl = QHBoxLayout(cf)
        cfl.setContentsMargins(16, 8, 16, 8)
        cfl.setSpacing(8)

        self._c_count = _Card("Invoices",    "#1a3a5c")
        self._c_lbp   = _Card("Total (ل.ل)", "#2e7d32")
        self._c_usd   = _Card("Total (USD)", "#1565c0")
        self._c_disc  = _Card("Discounts",   "#e65100")
        self._c_cash  = _Card("Cash",        "#00838f")

        for card in (self._c_count, self._c_lbp, self._c_usd,
                     self._c_disc, self._c_cash):
            cfl.addWidget(card, 1)

        # Dynamic highlighted-category cards (populated in _populate)
        self._hl_cards: list[_Card] = []
        self._hl_layout = cfl

        root.addWidget(cf)

        # ── Tabs ──────────────────────────────────────────────────────────────
        tabs = QTabWidget()
        tabs.setStyleSheet(
            "QTabWidget::pane{border:none;background:#fff;}"
            "QTabBar::tab{padding:7px 18px;font-size:12px;font-weight:600;"
            "  color:#555;border:none;border-bottom:2px solid transparent;background:#f0f4f8;}"
            "QTabBar::tab:selected{color:#1a3a5c;border-bottom:2px solid #1a6cb5;background:#fff;}"
        )

        self._cat_table    = self._make_table(["Category", "Qty", "Total", "Currency", "% of Sales"])
        self._cat_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        self._cashier_table = self._make_table(["Cashier", "Invoices", "Total (ل.ل)", "Total (USD)"])
        self._cashier_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        self._cashier_date_table = self._make_table(["Date", "Cashier", "Invoices", "Total (ل.ل)"])
        self._cashier_date_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for col, w_ in ((0, 100), (2, 70), (3, 140)):
            self._cashier_date_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Fixed)
            self._cashier_date_table.setColumnWidth(col, w_)

        self._pay_table = self._make_table(["Payment Method", "Amount", "Currency"])
        self._pay_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

        for tab_widget, label in [
            (self._cat_table,          "📦  By Category"),
            (self._cashier_table,      "👤  By Cashier"),
            (self._cashier_date_table, "📅  By Date/Cashier"),
            (self._pay_table,          "💳  By Payment"),
        ]:
            w = QWidget()
            wl = QVBoxLayout(w)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.addWidget(tab_widget)
            tabs.addTab(w, label)

        root.addWidget(tabs, 1)

        # ── Bottom bar ────────────────────────────────────────────────────────
        bot = QFrame()
        bot.setFixedHeight(52)
        bot.setStyleSheet("background:#f0f4f8;border-top:1px solid #cdd5e0;")
        bl2 = QHBoxLayout(bot)
        bl2.setContentsMargins(16, 8, 16, 8)

        self._period_lbl = QLabel("")
        self._period_lbl.setStyleSheet("font-size:11px;color:#666;")
        bl2.addWidget(self._period_lbl)
        bl2.addStretch()

        export_btn = QPushButton("💾  Export JSON")
        export_btn.setFixedHeight(34)
        export_btn.setStyleSheet(
            "QPushButton{background:#455a64;color:#fff;border:none;"
            "border-radius:6px;font-size:12px;font-weight:600;padding:0 14px;}"
            "QPushButton:hover{background:#263238;}"
        )
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self._export_json)
        bl2.addWidget(export_btn)

        bl2.addSpacing(8)

        print_cashier_btn = QPushButton("🖨  Cashier Report")
        print_cashier_btn.setFixedHeight(34)
        print_cashier_btn.setStyleSheet(
            "QPushButton{background:#00695c;color:#fff;border:none;"
            "border-radius:6px;font-size:12px;font-weight:600;padding:0 14px;}"
            "QPushButton:hover{background:#004d40;}"
        )
        print_cashier_btn.setCursor(Qt.PointingHandCursor)
        print_cashier_btn.clicked.connect(self._print_cashier_report)
        bl2.addWidget(print_cashier_btn)

        bl2.addSpacing(8)

        self._shift_btn = QPushButton("🔴  End of Shift")
        self._shift_btn.setFixedHeight(34)
        self._shift_btn.setStyleSheet(
            "QPushButton{background:#c62828;color:#fff;border:none;"
            "border-radius:6px;font-size:13px;font-weight:700;padding:0 18px;}"
            "QPushButton:hover{background:#a01010;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self._shift_btn.setCursor(Qt.PointingHandCursor)
        self._shift_btn.clicked.connect(self._end_of_shift)
        bl2.addWidget(self._shift_btn)

        root.addWidget(bot)

        # Init mode
        self._on_mode(0)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        t = QTableWidget()
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setAlternatingRowColors(True)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(26)
        t.setShowGrid(True)
        t.horizontalHeader().setStyleSheet(
            "QHeaderView::section{background:#1a3a5c;color:#fff;"
            "font-weight:700;border:none;padding:4px;}"
        )
        for i in range(1, len(headers)):
            t.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        return t

    @staticmethod
    def _cell(text: str, align=Qt.AlignLeft | Qt.AlignVCenter) -> QTableWidgetItem:
        c = QTableWidgetItem(str(text))
        c.setTextAlignment(align)
        return c

    # ── Mode ──────────────────────────────────────────────────────────────────

    def _on_mode(self, idx: int):
        is_old = (idx == 1)
        # In Daily Sales mode, date pickers are optional filters
        # In Old Sales mode, date pickers are required
        self._from_lbl.setText("From:" if is_old else "From (opt):")
        self._to_lbl.setText("To:" if is_old else "To (opt):")
        # End of Shift only makes sense in Daily Sales mode
        self._shift_btn.setEnabled(not is_old)
        self._shift_btn.setToolTip(
            "" if not is_old
            else "End of Shift is only available in Daily Sales mode."
        )

    def _is_old_mode(self) -> bool:
        return self._mode.currentIndex() == 1

    # ── Load ──────────────────────────────────────────────────────────────────

    def _refresh(self):
        from_text = self._from_dt.date().toString("yyyy-MM-dd")
        to_text   = self._to_dt.date().toString("yyyy-MM-dd")
        wh_id     = self._wh.currentData() or ""
        is_old    = self._is_old_mode()

        # In Daily Sales mode, dates are optional: only apply if user changed from default
        if not is_old:
            # Show all non-archived (ignore date pickers — they're "optional" filters)
            # Only apply if the user explicitly changes dates
            self._report = DailySalesService.get_report(
                date_from=from_text,
                date_to=to_text,
                warehouse_id=wh_id,
                archived=False,
            )
        else:
            self._report = DailySalesService.get_report(
                date_from=from_text,
                date_to=to_text,
                warehouse_id=wh_id,
                archived=True,
            )
        self._populate()

    def _populate(self):
        r = self._report
        s = r.get("summary", {})
        tbc = s.get("totals_by_currency", {})  # {"LBP": 170000, "USD": 0}

        # Summary cards
        self._c_count.set(f"{s.get('invoice_count', 0):,}")
        self._c_lbp.set(f"ل.ل {tbc.get('LBP', 0):,.0f}" if tbc.get('LBP') else "—")
        usd = tbc.get('USD', 0)
        self._c_usd.set(f"${usd:,.2f}" if usd else "—")
        self._c_disc.set(_fmt(s.get("discount_total", 0), s.get("primary_currency", "LBP")))

        # Payment cards: cash only
        pay_map: dict[tuple, float] = {
            (p["method"], p["currency"]): p["total"]
            for p in r.get("by_payment", [])
        }
        cash_lbp = pay_map.get(("cash", "LBP"), 0)
        cash_usd = pay_map.get(("cash", "USD"), 0)

        if cash_lbp and not cash_usd:
            self._c_cash.set(f"ل.ل {cash_lbp:,.0f}")
        elif cash_usd and not cash_lbp:
            self._c_cash.set(f"${cash_usd:,.2f}")
        elif cash_lbp or cash_usd:
            self._c_cash.set(f"ل.ل {cash_lbp:,.0f}\n${cash_usd:,.2f}")
        else:
            self._c_cash.set("—")

        # Highlighted category cards — rebuild dynamically
        for old_card in self._hl_cards:
            self._hl_layout.removeWidget(old_card)
            old_card.deleteLater()
        self._hl_cards.clear()

        hl_colors = ["#6a1b9a", "#00695c", "#bf360c", "#1565c0", "#37474f"]
        for i, hl in enumerate(r.get("highlighted_cats", [])):
            sym = "ل.ل" if hl["currency"] == "LBP" else "$"
            card = _Card(hl["name"], hl_colors[i % len(hl_colors)])
            card.set(f"{sym} {hl['total']:,.0f}")
            self._hl_layout.addWidget(card, 1)
            self._hl_cards.append(card)

        # Period label
        mode = "Daily Sales (open shift)" if not self._is_old_mode() else "Old Sales"
        inv_count = s.get("invoice_count", 0)
        self._period_lbl.setText(
            f"{mode}  ·  {inv_count:,} invoice{'s' if inv_count != 1 else ''}"
        )

        # By category
        cats = r.get("by_category", [])
        t = self._cat_table
        t.setRowCount(len(cats))
        for i, row in enumerate(cats):
            t.setItem(i, 0, self._cell(row["category"]))
            t.setItem(i, 1, self._cell(f"{row['qty']:,.2f}",  Qt.AlignRight | Qt.AlignVCenter))
            t.setItem(i, 2, self._cell(f"{row['total']:,.0f}", Qt.AlignRight | Qt.AlignVCenter))
            t.setItem(i, 3, self._cell(row.get("currency", ""), Qt.AlignCenter))
            pct_cell = self._cell(f"{row['pct']:.1f}%", Qt.AlignRight | Qt.AlignVCenter)
            if row["pct"] >= 10:
                pct_cell.setForeground(QColor("#1a6cb5"))
                pct_cell.setFont(QFont("", -1, QFont.Bold))
            t.setItem(i, 4, pct_cell)

        # By cashier
        cashiers = r.get("by_cashier", [])
        t2 = self._cashier_table
        t2.setRowCount(len(cashiers))
        for i, row in enumerate(cashiers):
            t2.setItem(i, 0, self._cell(row["cashier"]))
            t2.setItem(i, 1, self._cell(str(row["invoices"]), Qt.AlignCenter))
            lbp_amt = row["totals"].get("LBP", 0)
            usd_amt = row["totals"].get("USD", 0)
            t2.setItem(i, 2, self._cell(f"ل.ل {lbp_amt:,.0f}" if lbp_amt else "—", Qt.AlignRight | Qt.AlignVCenter))
            t2.setItem(i, 3, self._cell(f"${usd_amt:,.2f}" if usd_amt else "—", Qt.AlignRight | Qt.AlignVCenter))

        # By cashier × date
        cd_rows = r.get("by_cashier_date", [])
        t_cd = self._cashier_date_table
        t_cd.setRowCount(len(cd_rows))
        prev_date = None
        for i, row in enumerate(cd_rows):
            date_txt = row["date"] if row["date"] != prev_date else ""
            prev_date = row["date"]
            lbp_amt = row["totals"].get("LBP", 0)
            total_txt = f"ل.ل {lbp_amt:,.0f}" if lbp_amt else "—"
            t_cd.setItem(i, 0, self._cell(date_txt, Qt.AlignCenter))
            t_cd.setItem(i, 1, self._cell(row["cashier"]))
            t_cd.setItem(i, 2, self._cell(str(row["invoices"]), Qt.AlignCenter))
            amt_cell = self._cell(total_txt, Qt.AlignRight | Qt.AlignVCenter)
            if lbp_amt:
                amt_cell.setFont(QFont("", -1, QFont.Bold))
            t_cd.setItem(i, 3, amt_cell)

        # By payment
        pays = r.get("by_payment", [])
        t3 = self._pay_table
        t3.setRowCount(len(pays))
        for i, row in enumerate(pays):
            t3.setItem(i, 0, self._cell(row["method"].title()))
            t3.setItem(i, 1, self._cell(f"{row['total']:,.0f}", Qt.AlignRight | Qt.AlignVCenter))
            t3.setItem(i, 2, self._cell(row.get("currency", ""), Qt.AlignCenter))

    # ── Actions ───────────────────────────────────────────────────────────────

    def _print_cashier_report(self):
        """Print cashier-by-date summary on POS printer."""
        rows = self._report.get("by_cashier_date", [])
        if not rows:
            QMessageBox.information(self, "No Data", "No sales data to print.")
            return

        from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
        from PySide6.QtGui import QTextDocument, QPageSize, QPageLayout
        from PySide6.QtCore import QSizeF, QMarginsF

        # Build rows HTML
        rows_html = ""
        prev_date = None
        for row in rows:
            lbp = row["totals"].get("LBP", 0)
            total_str = f"&#x644;.&#x644; {lbp:,.0f}" if lbp else "—"
            date_cell = row["date"] if row["date"] != prev_date else ""
            prev_date = row["date"]
            rows_html += (
                f"<tr>"
                f"<td style='padding:3px 4px;border-bottom:1px solid #ddd;font-weight:{'700' if date_cell else '400'};'>{date_cell}</td>"
                f"<td style='padding:3px 4px;border-bottom:1px solid #ddd;'>{row['cashier']}</td>"
                f"<td style='padding:3px 4px;border-bottom:1px solid #ddd;text-align:right;font-weight:700;'>{total_str}</td>"
                f"</tr>"
            )

        mode = "Daily Sales" if not self._is_old_mode() else "Old Sales"
        from_dt = self._from_dt.date().toString("dd/MM/yyyy")
        to_dt   = self._to_dt.date().toString("dd/MM/yyyy")
        period  = f"{from_dt} → {to_dt}" if self._is_old_mode() else from_dt

        html = f"""
        <html><body style='font-family:Arial,sans-serif;font-size:11px;margin:0;padding:4px;'>
        <div style='text-align:center;font-size:13px;font-weight:700;margin-bottom:2px;'>
            Cashier Sales Report
        </div>
        <div style='text-align:center;font-size:10px;color:#555;margin-bottom:8px;'>
            {mode} · {period}
        </div>
        <table style='width:100%;border-collapse:collapse;'>
          <tr style='background:#1a3a5c;color:#fff;'>
            <th style='padding:4px;text-align:left;'>Date</th>
            <th style='padding:4px;text-align:left;'>Cashier</th>
            <th style='padding:4px;text-align:right;'>Total</th>
          </tr>
          {rows_html}
        </table>
        </body></html>"""

        printer = QPrinter(QPrinter.HighResolution)
        # Use 80 mm thermal width
        page_size = QPageSize(QSizeF(80, 200), QPageSize.Millimeter, "80mm")
        printer.setPageSize(page_size)
        printer.setPageMargins(QMarginsF(3, 3, 3, 3), QPageLayout.Millimeter)

        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("Print — Cashier Report")

        def paint(pr):
            doc = QTextDocument()
            doc.setHtml(html)
            doc.print_(pr)

        preview.paintRequested.connect(paint)
        preview.exec()

    def _export_json(self):
        if not self._report or not self._report.get("summary", {}).get("invoice_count"):
            QMessageBox.information(self, "No Data", "No invoices to export.")
            return
        try:
            import json
            from pathlib import Path
            from datetime import datetime
            d = Path.home() / "Documents" / "TannouryMarket" / "shifts"
            d.mkdir(parents=True, exist_ok=True)
            path = d / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._report, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Exported", f"Saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))

    def _auto_print_shift_report(self):
        """Auto-print the shift summary on the configured POS printer after closing."""
        try:
            report = self._report or {}
            s      = report.get("summary", {})
            rows   = report.get("by_cashier_date", [])

            rows_html = ""
            prev_date = None
            for row in rows:
                lbp = row["totals"].get("LBP", 0)
                total_str = f"LL {lbp:,.0f}" if lbp else "—"
                date_cell = row["date"] if row["date"] != prev_date else ""
                prev_date = row["date"]
                rows_html += (
                    f"<tr>"
                    f"<td style='padding:1px 2px;font-size:7pt;font-weight:{'700' if date_cell else '400'};'>{date_cell}</td>"
                    f"<td style='padding:1px 2px;font-size:7pt;'>{row['cashier']}</td>"
                    f"<td style='padding:1px 2px;font-size:7pt;text-align:right;font-weight:700;'>{total_str}</td>"
                    f"</tr>"
                )

            tbc   = s.get("totals_by_currency", {})
            total_line = "  ·  ".join(
                _fmt(amt, cur) for cur, amt in sorted(tbc.items()) if amt
            ) or "0"

            from datetime import date as _date
            html = f"""<html dir='ltr'><head><meta charset='utf-8'></head>
<body dir='ltr' style='margin:0;padding:0;font-family:"Courier New",Courier,monospace;font-size:7pt;line-height:1.2;color:#000;'>
<div style='text-align:center;font-size:11pt;font-weight:700;'>End of Shift</div>
<div style='text-align:center;font-size:8pt;'>{_date.today().strftime('%Y-%m-%d')}</div>
<hr style='border:1px dashed #000;margin:2px 0;'>
<table style='width:100%;border-collapse:collapse;table-layout:fixed;'>
  <colgroup><col width='34%'><col width='33%'><col width='33%'></colgroup>
  <tr style='font-weight:700;font-size:7pt;'>
    <td style='padding:1px 2px;'>Date</td>
    <td style='padding:1px 2px;'>Cashier</td>
    <td style='padding:1px 2px;text-align:right;'>Total</td>
  </tr>
  {rows_html}
</table>
<hr style='border:1px solid #000;margin:2px 0;'>
<div style='text-align:right;font-size:8pt;font-weight:700;'>TOTAL: {total_line}</div>
<div style='text-align:right;font-size:7pt;'>Invoices: {s.get("invoice_count", 0)}</div>
<div style='text-align:center;margin-top:4px;font-size:7pt;'>*** Shift Closed ***</div>
</body></html>"""

            from PySide6.QtPrintSupport import QPrinter
            from PySide6.QtGui import QPageSize
            from PySide6.QtCore import QSizeF
            from utils.receipt_printer import _render_to_printer, _get_qt_printer_name

            qt_name = _get_qt_printer_name()
            printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
            if qt_name:
                printer.setPrinterName(qt_name)
            printer.setFullPage(False)
            _render_to_printer(html, printer)
        except Exception:
            pass  # never block the shift close on a print failure

    def _end_of_shift(self):
        self._refresh()
        s     = self._report.get("summary", {})
        count = s.get("invoice_count", 0)
        tbc   = s.get("totals_by_currency", {})

        if count == 0:
            QMessageBox.information(self, "No Data", "No open invoices to close.")
            return

        total_lines = "  ·  ".join(
            _fmt(amt, cur) for cur, amt in sorted(tbc.items()) if amt
        ) or "0"

        if not _EndOfShiftConfirmDialog(count, total_lines, self).exec():
            return

        try:
            wh_id = self._wh.currentData() or ""
            archived, path = DailySalesService.close_shift(wh_id)
            self._auto_print_shift_report()
            _EndOfShiftSuccessDialog(archived, total_lines, path, self).exec()
            self._shift_was_closed = True
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Failed", str(exc))
