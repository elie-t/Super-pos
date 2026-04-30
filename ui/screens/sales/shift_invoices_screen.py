"""
Shift Invoices Screen — lists consolidated POS shift invoices with line-item detail.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSplitter, QLineEdit, QDateEdit,
)
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QColor, QFont

from database.engine import get_session, init_db
from database.models.invoices import SalesInvoice, SalesInvoiceItem
from database.models.users import User
from database.models.items import Warehouse


class ShiftInvoicesScreen(QWidget):
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []
        self._build_ui()
        self._load()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background:#1a3a5c;")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 0, 12, 0)

        back_btn = QPushButton("←  Back")
        back_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.15);color:#fff;border:1px solid rgba(255,255,255,0.3);"
            "border-radius:4px;padding:4px 12px;font-size:12px;}"
            "QPushButton:hover{background:rgba(255,255,255,0.3);}"
        )
        back_btn.setFixedHeight(28)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.back.emit)
        bl.addWidget(back_btn)

        title = QLabel("📋  Shift Sales Invoices")
        title.setStyleSheet("color:#fff;font-size:15px;font-weight:700;margin-left:12px;")
        bl.addWidget(title)
        bl.addStretch()

        root.addWidget(bar)

        # Filter bar
        fbar = QFrame()
        fbar.setStyleSheet("background:#f0f4f8;border-bottom:1px solid #cdd5e0;")
        fl = QHBoxLayout(fbar)
        fl.setContentsMargins(12, 6, 12, 6)
        fl.setSpacing(10)

        fl.addWidget(QLabel("From:"))
        self._from_dt = QDateEdit()
        self._from_dt.setFixedHeight(30)
        self._from_dt.setDisplayFormat("dd/MM/yyyy")
        self._from_dt.setCalendarPopup(True)
        # Default: first day of current month
        today = QDate.currentDate()
        self._from_dt.setDate(QDate(today.year(), today.month(), 1))
        fl.addWidget(self._from_dt)

        fl.addWidget(QLabel("To:"))
        self._to_dt = QDateEdit()
        self._to_dt.setFixedHeight(30)
        self._to_dt.setDisplayFormat("dd/MM/yyyy")
        self._to_dt.setCalendarPopup(True)
        self._to_dt.setDate(today)
        fl.addWidget(self._to_dt)

        fl.addSpacing(8)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search shift #…")
        self._search.setFixedHeight(30)
        self._search.setFixedWidth(180)
        self._search.textChanged.connect(self._filter)
        fl.addWidget(self._search)

        fl.addStretch()

        load_btn = QPushButton("🔄  Load")
        load_btn.setFixedHeight(30)
        load_btn.setStyleSheet(
            "QPushButton{background:#1a6cb5;color:#fff;border:none;"
            "border-radius:4px;font-size:12px;font-weight:600;padding:0 14px;}"
            "QPushButton:hover{background:#1a3a5c;}"
        )
        load_btn.setCursor(Qt.PointingHandCursor)
        load_btn.clicked.connect(self._load)
        fl.addWidget(load_btn)

        root.addWidget(fbar)

        # Splitter: list left | detail right
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle{background:#cdd5e0;}")

        # ── Left: shift list ──────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        self._list = QTableWidget()
        self._list.setColumnCount(5)
        self._list.setHorizontalHeaderLabels(["Shift #", "Date", "Invoices", "Total", "Status"])
        self._list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.verticalHeader().setVisible(False)
        self._list.verticalHeader().setDefaultSectionSize(30)
        self._list.setAlternatingRowColors(True)
        self._list.setShowGrid(True)
        self._list.currentItemChanged.connect(self._on_shift_selected)
        lhdr = self._list.horizontalHeader()
        lhdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        lhdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        lhdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        lhdr.setSectionResizeMode(3, QHeaderView.Stretch)
        lhdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        lhdr.setStyleSheet(
            "QHeaderView::section{background:#1a3a5c;color:#fff;font-weight:700;"
            "border:none;padding:4px;}"
        )
        ll.addWidget(self._list)

        # Footer total
        self._list_footer = QLabel("")
        self._list_footer.setStyleSheet(
            "background:#e8f0fb;border-top:1px solid #cdd5e0;"
            "color:#1a3a5c;font-size:11px;font-weight:600;padding:4px 12px;"
        )
        ll.addWidget(self._list_footer)
        splitter.addWidget(left)

        # ── Right: line items ─────────────────────────────────────────────────
        right = QFrame()
        right.setStyleSheet("QFrame{background:#f8fafc;border-left:2px solid #cdd5e0;}")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        detail_hdr = QFrame()
        detail_hdr.setFixedHeight(36)
        detail_hdr.setStyleSheet("background:#e8f0fb;border-bottom:1px solid #cdd5e0;")
        dhl = QHBoxLayout(detail_hdr)
        dhl.setContentsMargins(10, 0, 10, 0)
        self._detail_title = QLabel("← Select a shift")
        self._detail_title.setStyleSheet("font-size:12px;font-weight:700;color:#1a3a5c;")
        dhl.addWidget(self._detail_title)
        dhl.addStretch()
        self._detail_total = QLabel("")
        self._detail_total.setStyleSheet("font-size:13px;font-weight:700;color:#2e7d32;")
        dhl.addWidget(self._detail_total)
        rl.addWidget(detail_hdr)

        self._detail = QTableWidget()
        self._detail.setColumnCount(5)
        self._detail.setHorizontalHeaderLabels(["Item", "Qty", "Unit Price", "Total", "Currency"])
        self._detail.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._detail.setSelectionMode(QAbstractItemView.NoSelection)
        self._detail.verticalHeader().setVisible(False)
        self._detail.verticalHeader().setDefaultSectionSize(26)
        self._detail.setAlternatingRowColors(True)
        self._detail.setShowGrid(True)
        dhdr = self._detail.horizontalHeader()
        dhdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3, 4):
            dhdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        dhdr.setStyleSheet(
            "QHeaderView::section{background:#2a5a8c;color:#fff;font-weight:700;"
            "border:none;padding:4px;}"
        )
        rl.addWidget(self._detail, 1)

        splitter.addWidget(right)
        splitter.setSizes([480, 520])
        root.addWidget(splitter, 1)

    # ── Data ──────────────────────────────────────────────────────────────────

    def _load(self):
        date_from = self._from_dt.date().toString("yyyy-MM-dd")
        date_to   = self._to_dt.date().toString("yyyy-MM-dd")

        init_db()
        session = get_session()
        try:
            q = (
                session.query(SalesInvoice)
                .filter(
                    SalesInvoice.source       == "pos_shift",
                    SalesInvoice.invoice_date >= date_from,
                    SalesInvoice.invoice_date <= date_to,
                )
                .order_by(SalesInvoice.invoice_date.desc(),
                          SalesInvoice.created_at.desc())
                .all()
            )

            op_ids = list({inv.operator_id for inv in q})
            op_map: dict[str, str] = {}
            if op_ids:
                for u in session.query(User).filter(User.id.in_(op_ids)).all():
                    op_map[u.id] = u.full_name or u.username or "Unknown"

            self._rows = [
                {
                    "id":             inv.id,
                    "number":         inv.invoice_number,
                    "date":           inv.invoice_date,
                    "total":          inv.total,
                    "currency":       inv.currency,
                    "payment_status": inv.payment_status,
                    "amount_paid":    inv.amount_paid,
                    "operator":       op_map.get(inv.operator_id, ""),
                    "notes":          inv.notes or "",
                }
                for inv in q
            ]
        finally:
            session.close()

        self._filter()

    def _filter(self):
        q = self._search.text().strip().lower()
        rows = [r for r in self._rows if not q or q in r["number"].lower()]
        self._fill(rows)

    def _fill(self, rows: list[dict]):
        self._list.setRowCount(len(rows))
        grand = 0.0

        for i, r in enumerate(rows):
            grand += r["total"]
            paid_color = "#2e7d32" if r["payment_status"] == "paid" else "#e65100"

            # Parse invoice count from notes e.g. "Shift close: 7 POS invoices…"
            inv_count = ""
            if "POS invoices" in r["notes"]:
                try:
                    inv_count = r["notes"].split(":")[1].split("POS")[0].strip()
                except Exception:
                    pass

            def cell(txt, align=Qt.AlignCenter, bold=False, color=None, _r=r):
                it = QTableWidgetItem(str(txt))
                it.setTextAlignment(align)
                it.setData(Qt.UserRole, _r["id"])
                if bold:
                    it.setFont(QFont("", -1, QFont.Bold))
                if color:
                    it.setForeground(QColor(color))
                return it

            self._list.setItem(i, 0, cell(r["number"]))
            self._list.setItem(i, 1, cell(r["date"]))
            self._list.setItem(i, 2, cell(inv_count))
            cur = r["currency"]
            if cur == "LBP":
                total_fmt = f"ل.ل {r['total']:,.0f}"
            else:
                total_fmt = f"${r['total']:,.2f}"
            self._list.setItem(i, 3, cell(total_fmt, Qt.AlignRight | Qt.AlignVCenter, bold=True))
            self._list.setItem(i, 4, cell(r["payment_status"].upper(),
                                          color=paid_color, bold=True))

        self._list_footer.setText(
            f"  {len(rows)} shift{'s' if len(rows) != 1 else ''}  ·  total visible"
        )
        self._detail.setRowCount(0)
        self._detail_title.setText("← Select a shift")
        self._detail_total.setText("")

    def _on_shift_selected(self, current, _prev):
        if not current:
            return
        inv_id  = current.data(Qt.UserRole)
        inv_num = ""
        for r in self._rows:
            if r["id"] == inv_id:
                inv_num = r["number"]
                break

        init_db()
        session = get_session()
        try:
            lines = (
                session.query(SalesInvoiceItem)
                .filter_by(invoice_id=inv_id)
                .order_by(SalesInvoiceItem.item_name)
                .all()
            )
        finally:
            session.close()

        self._detail_title.setText(f"Shift  {inv_num}")
        self._detail.setRowCount(len(lines))
        grand = 0.0
        primary_cur = "LBP"
        for i, li in enumerate(lines):
            grand += li.line_total
            primary_cur = li.currency
            cur = li.currency
            for col, (txt, align) in enumerate([
                (li.item_name,                       Qt.AlignLeft | Qt.AlignVCenter),
                (f"{li.quantity:,.3f}",              Qt.AlignCenter),
                (f"{li.unit_price:,.0f}",            Qt.AlignRight | Qt.AlignVCenter),
                (f"{li.line_total:,.0f}",            Qt.AlignRight | Qt.AlignVCenter),
                (cur,                                Qt.AlignCenter),
            ]):
                it = QTableWidgetItem(txt)
                it.setTextAlignment(align)
                self._detail.setItem(i, col, it)

        if primary_cur == "LBP":
            total_str = f"ل.ل {grand:,.0f}"
        else:
            total_str = f"${grand:,.2f}"
        self._detail_total.setText(total_str)

    def refresh(self):
        self._load()
