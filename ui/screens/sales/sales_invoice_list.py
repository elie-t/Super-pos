"""
Sales Invoice List — all sales invoices (manual + shift) with detail view.
Columns: Invoice # | W | Date | Branch / Warehouse | Amount | Cashier | Status
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QLineEdit, QDateEdit, QComboBox,
    QDialog, QSplitter, QGridLayout, QMessageBox, QProgressDialog,
)
from PySide6.QtCore import Qt, Signal, QDate
from PySide6.QtGui import QColor, QFont
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog

from services.sales_invoice_service import SalesInvoiceService
from services.auth_service import AuthService


# ── Print helper ───────────────────────────────────────────────────────────────

def _print_invoice(d: dict, parent=None):
    cur = d["currency"]
    sym = "ل.ل" if cur == "LBP" else "$"
    wn = d["warehouse_num"]
    wn_str = str(wn) if wn != "" else "—"

    rows_html = ""
    for i, li in enumerate(d["lines"], 1):
        rows_html += (
            f"<tr style='background:{'#f9f9f9' if i%2==0 else '#fff'};'>"
            f"<td align='center'>{i}</td>"
            f"<td align='center'>{li.get('warehouse_num','')}</td>"
            f"<td>{li['barcode']}</td>"
            f"<td>{li['item_name']}</td>"
            f"<td align='right'>{li['qty']:,.3f}</td>"
            f"<td align='right'>{li['price']:,.0f}</td>"
            f"<td align='center'>{li['disc_pct']:.1f}%</td>"
            f"<td align='right'><b>{li['total']:,.0f}</b></td>"
            f"</tr>"
        )

    html = f"""
    <html><body style='font-family:Arial,sans-serif;font-size:12px;'>
    <h2 style='color:#1b5e20;margin-bottom:4px;'>Sales Invoice — {d['invoice_number']}</h2>
    <table style='border-collapse:collapse;width:100%;margin-bottom:10px;'>
      <tr><td width='120'><b>Date:</b></td><td>{d['invoice_date']}</td>
          <td width='120'><b>Warehouse:</b></td><td>W{wn_str} {d['warehouse_name']}</td></tr>
      <tr><td><b>Client:</b></td><td>{d['customer_name']}</td>
          <td><b>Cashier:</b></td><td>{d['cashier']}</td></tr>
      <tr><td><b>Currency:</b></td><td>{cur}</td>
          <td><b>Status:</b></td><td>{d['payment_status'].upper()}</td></tr>
    </table>
    <table border='1' cellpadding='4' cellspacing='0'
           style='border-collapse:collapse;width:100%;border-color:#ccc;'>
      <tr style='background:#1b5e20;color:#fff;'>
        <th>#</th><th>W</th><th>Barcode</th><th>Description</th>
        <th>Qty</th><th>Price</th><th>Disc%</th><th>Total</th>
      </tr>
      {rows_html}
    </table>
    <p style='text-align:right;font-size:14px;margin-top:8px;'>
      <b>Total: {sym} {d['total']:,.0f}</b>
    </p>
    {'<p style="color:#c62828;font-weight:bold;">VOIDED / CANCELLED</p>' if d.get("status") == "cancelled" else ''}
    </body></html>"""

    printer = QPrinter(QPrinter.HighResolution)
    printer.setPageSize(QPrinter.A4)

    preview = QPrintPreviewDialog(printer, parent)
    preview.setWindowTitle(f"Print — {d['invoice_number']}")

    def paint(pr):
        from PySide6.QtGui import QTextDocument
        doc = QTextDocument()
        doc.setHtml(html)
        doc.print_(pr)

    preview.paintRequested.connect(paint)
    preview.exec()


# ── Invoice detail dialog ──────────────────────────────────────────────────────

class InvoiceDetailDialog(QDialog):
    def __init__(self, inv_data: dict, parent=None):
        super().__init__(parent)
        d = inv_data
        wn = d["warehouse_num"]
        wn_str = str(wn) if wn != "" else "—"
        self.setWindowTitle(
            f"Invoice  {d['invoice_number']}  —  W{wn_str}  {d['warehouse_name']}"
        )
        self.setMinimumSize(900, 560)
        self._build(d, wn_str)

    def _build(self, d: dict, wn_str: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header strip ──────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(44)
        hdr.setStyleSheet("background:#1b5e20;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(16, 0, 16, 0)
        title = QLabel(f"📋  {d['invoice_number']}")
        title.setStyleSheet("color:#fff;font-size:15px;font-weight:700;")
        hl.addWidget(title)
        hl.addStretch()
        status_lbl = QLabel(d["payment_status"].upper())
        status_color = "#a5d6a7" if d["payment_status"] == "paid" else "#ef9a9a"
        status_lbl.setStyleSheet(
            f"color:{status_color};font-size:13px;font-weight:700;"
            f"background:rgba(255,255,255,0.1);border-radius:4px;padding:2px 10px;"
        )
        hl.addWidget(status_lbl)
        root.addWidget(hdr)

        # ── Info grid ─────────────────────────────────────────────────────────
        info = QFrame()
        info.setStyleSheet("background:#f0f4f8;border-bottom:1px solid #cdd5e0;")
        gl = QGridLayout(info)
        gl.setContentsMargins(20, 10, 20, 10)
        gl.setHorizontalSpacing(24)
        gl.setVerticalSpacing(4)

        def pair(label, value, row, col):
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#667;font-size:11px;font-weight:600;")
            val = QLabel(str(value))
            val.setStyleSheet("color:#1a1a2e;font-size:13px;font-weight:700;")
            gl.addWidget(lbl, row * 2,     col)
            gl.addWidget(val, row * 2 + 1, col)

        type_label = "Shift Invoice" if d["source"] == "pos_shift" else "Sales Invoice"
        pair("Type",          type_label,          0, 0)
        pair("Invoice #",     d["invoice_number"],  0, 1)
        pair("Date",          d["invoice_date"],    0, 2)
        pair("W",             wn_str,               0, 3)
        pair("Client",        d["customer_name"],   1, 0)
        pair("Branch",        d["warehouse_name"],  1, 1)
        pair("Cashier",       d["cashier"],         1, 2)
        pair("Currency",      d["currency"],        1, 3)

        root.addWidget(info)

        # ── Line items table ───────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            ["#", "W", "Barcode", "Description", "Qty", "Price", "Disc%", "Total"]
        )
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.NoSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(28)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        hdr_view = self._table.horizontalHeader()
        hdr_view.setSectionResizeMode(3, QHeaderView.Stretch)
        for c, w in ((0, 36), (1, 36), (2, 130), (4, 70), (5, 110), (6, 56), (7, 110)):
            hdr_view.setSectionResizeMode(c, QHeaderView.Fixed)
            self._table.setColumnWidth(c, w)
        hdr_view.setStyleSheet(
            "QHeaderView::section{background:#1b5e20;color:#fff;"
            "font-weight:700;border:none;padding:4px;}"
        )
        root.addWidget(self._table, 1)

        # Fill table
        lines = d["lines"]
        self._table.setRowCount(len(lines))
        for i, li in enumerate(lines):
            wn = li.get("warehouse_num", "")
            for col, (txt, align) in enumerate([
                (str(i + 1),                    Qt.AlignCenter),
                (str(wn),                       Qt.AlignCenter),
                (li["barcode"],                 Qt.AlignCenter),
                (li["item_name"],               Qt.AlignLeft | Qt.AlignVCenter),
                (f"{li['qty']:,.3f}",           Qt.AlignCenter),
                (f"{li['price']:,.0f}",         Qt.AlignRight | Qt.AlignVCenter),
                (f"{li['disc_pct']:.1f}%",      Qt.AlignCenter),
                (f"{li['total']:,.0f}",         Qt.AlignRight | Qt.AlignVCenter),
            ]):
                cell = QTableWidgetItem(txt)
                cell.setTextAlignment(align)
                if col == 7:
                    cell.setFont(QFont("", -1, QFont.Bold))
                if col == 1:
                    cell.setForeground(QColor("#1565c0"))
                    cell.setFont(QFont("", -1, QFont.Bold))
                self._table.setItem(i, col, cell)

        # ── Totals footer ──────────────────────────────────────────────────────
        foot = QFrame()
        foot.setFixedHeight(44)
        foot.setStyleSheet("background:#1a3a5c;")
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(16, 0, 16, 0)
        fl.setSpacing(24)

        cur = d["currency"]
        sym = "ل.ل" if cur == "LBP" else "$"

        def total_lbl(label, value):
            w = QWidget()
            wl = QHBoxLayout(w)
            wl.setContentsMargins(0, 0, 0, 0)
            wl.setSpacing(6)
            l = QLabel(label)
            l.setStyleSheet("color:#cfe0f5;font-size:11px;")
            v = QLabel(f"{sym} {value:,.0f}")
            v.setStyleSheet("color:#fff;font-size:13px;font-weight:700;")
            wl.addWidget(l)
            wl.addWidget(v)
            return w

        fl.addWidget(total_lbl("SubTotal:", d["subtotal"]))
        if d["discount_value"]:
            fl.addWidget(total_lbl("Discount:", d["discount_value"]))
        if d["vat_value"]:
            fl.addWidget(total_lbl("VAT:", d["vat_value"]))
        fl.addStretch()

        total_w = QLabel(f"Total:  {sym} {d['total']:,.0f}")
        total_w.setStyleSheet("color:#a5d6a7;font-size:16px;font-weight:700;")
        fl.addWidget(total_w)

        root.addWidget(foot)

        # Close button
        btn_bar = QFrame()
        btn_bar.setFixedHeight(40)
        btn_bar.setStyleSheet("background:#f0f4f8;border-top:1px solid #cdd5e0;")
        bl = QHBoxLayout(btn_bar)
        bl.setContentsMargins(12, 4, 12, 4)
        bl.addStretch()
        close = QPushButton("Close")
        close.setFixedHeight(30)
        close.setStyleSheet(
            "QPushButton{background:#607d8b;color:#fff;border:none;"
            "border-radius:4px;font-size:12px;font-weight:700;padding:0 20px;}"
            "QPushButton:hover{background:#455a64;}"
        )
        close.clicked.connect(self.accept)
        bl.addWidget(close)
        root.addWidget(btn_bar)


# ── List screen ────────────────────────────────────────────────────────────────

class SalesInvoiceListScreen(QWidget):
    back = Signal()
    edit_requested      = Signal(dict)   # full invoice dict
    duplicate_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []
        self._selected_id: str = ""
        self._build_ui()
        self._load()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────────
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background:#1b5e20;")
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
        title = QLabel("📋  Sales Invoices")
        title.setStyleSheet("color:#fff;font-size:15px;font-weight:700;margin-left:12px;")
        bl.addWidget(title)
        bl.addStretch()
        root.addWidget(bar)

        # ── Filter bar ────────────────────────────────────────────────────────
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
        fl.addWidget(QLabel("Type:"))
        self._type_combo = QComboBox()
        self._type_combo.setFixedHeight(30)
        self._type_combo.addItems(["All", "Manual", "Shift"])
        self._type_combo.currentIndexChanged.connect(self._filter)
        fl.addWidget(self._type_combo)

        fl.addSpacing(8)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Invoice # or branch…")
        self._search.setFixedHeight(30)
        self._search.setFixedWidth(180)
        self._search.textChanged.connect(self._filter)
        fl.addWidget(self._search)

        fl.addStretch()
        load_btn = QPushButton("🔄  Load")
        load_btn.setFixedHeight(30)
        load_btn.setStyleSheet(
            "QPushButton{background:#1b5e20;color:#fff;border:none;"
            "border-radius:4px;font-size:12px;font-weight:600;padding:0 14px;}"
            "QPushButton:hover{background:#1a3a5c;}"
        )
        load_btn.setCursor(Qt.PointingHandCursor)
        load_btn.clicked.connect(self._load)
        fl.addWidget(load_btn)
        root.addWidget(fbar)

        # ── Action bar ────────────────────────────────────────────────────────
        abar = QFrame()
        abar.setFixedHeight(38)
        abar.setStyleSheet("background:#fff;border-bottom:1px solid #cdd5e0;")
        al = QHBoxLayout(abar)
        al.setContentsMargins(12, 0, 12, 0)
        al.setSpacing(8)

        def _action_btn(label, bg, hover):
            b = QPushButton(label)
            b.setFixedHeight(28)
            b.setEnabled(False)
            b.setStyleSheet(
                f"QPushButton{{background:{bg};color:#fff;border:none;border-radius:4px;"
                f"font-size:12px;font-weight:700;padding:0 14px;}}"
                f"QPushButton:hover{{background:{hover};}}"
                f"QPushButton:disabled{{background:#bdbdbd;color:#fff;}}"
            )
            b.setCursor(Qt.PointingHandCursor)
            return b

        self._edit_btn   = _action_btn("✏  Edit",       "#1565c0", "#0d47a1")
        self._dup_btn    = _action_btn("⎘  Duplicate",  "#6a1b9a", "#4a148c")
        self._print_btn  = _action_btn("🖨  Print",      "#00695c", "#004d40")
        self._delete_btn = _action_btn("🗑  Delete",     "#c62828", "#b71c1c")

        self._edit_btn.clicked.connect(self._action_edit)
        self._dup_btn.clicked.connect(self._action_duplicate)
        self._print_btn.clicked.connect(self._action_print)
        self._delete_btn.clicked.connect(self._action_delete)

        al.addWidget(self._edit_btn)
        al.addWidget(self._dup_btn)
        al.addWidget(self._print_btn)
        al.addWidget(self._delete_btn)
        al.addStretch()

        # Superuser only: bulk purge shift invoices
        user = AuthService.current_user()
        is_super = user and (
            str(user.role).strip().lower() == "admin"
            or bool(getattr(user, "is_power_user", False))
        )
        if is_super:
            purge_btn = QPushButton("🗑  Purge Shift Invoices…")
            purge_btn.setFixedHeight(28)
            purge_btn.setCursor(Qt.PointingHandCursor)
            purge_btn.setStyleSheet(
                "QPushButton{background:#4e342e;color:#fff;border:none;border-radius:4px;"
                "font-size:11px;font-weight:700;padding:0 10px;}"
                "QPushButton:hover{background:#3e2723;}"
            )
            purge_btn.clicked.connect(self._purge_shift_invoices)
            al.addWidget(purge_btn)

            recv_btn = QPushButton("⬇  Receive Shift Invoices")
            recv_btn.setFixedHeight(28)
            recv_btn.setCursor(Qt.PointingHandCursor)
            recv_btn.setStyleSheet(
                "QPushButton{background:#1a3a5c;color:#fff;border:none;border-radius:4px;"
                "font-size:11px;font-weight:700;padding:0 10px;}"
                "QPushButton:hover{background:#1a6cb5;}"
            )
            recv_btn.clicked.connect(self._receive_shift_invoices)
            al.addWidget(recv_btn)
        self._action_lbl = QLabel("Select an invoice to enable actions")
        self._action_lbl.setStyleSheet("color:#999;font-size:11px;")
        al.addWidget(self._action_lbl)
        root.addWidget(abar)

        # ── Invoice table ─────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["Invoice #", "W", "Date", "Branch / Warehouse", "Amount", "Cashier", "Status"]
        )
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(30)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.doubleClicked.connect(self._open_detail)
        self._table.selectionModel().selectionChanged.connect(self._on_selection)
        hdr = self._table.horizontalHeader()
        # W column narrow, Branch stretches
        for c, w in ((0, 120), (1, 36), (2, 90), (4, 130), (5, 140), (6, 80)):
            hdr.setSectionResizeMode(c, QHeaderView.Fixed)
            self._table.setColumnWidth(c, w)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        hdr.setStyleSheet(
            "QHeaderView::section{background:#1b5e20;color:#fff;"
            "font-weight:700;border:none;padding:4px;}"
        )
        root.addWidget(self._table, 1)

        # ── Footer ────────────────────────────────────────────────────────────
        foot = QFrame()
        foot.setFixedHeight(36)
        foot.setStyleSheet("background:#e8f5e9;border-top:1px solid #cdd5e0;")
        fol = QHBoxLayout(foot)
        fol.setContentsMargins(12, 0, 12, 0)
        self._footer_lbl = QLabel("")
        self._footer_lbl.setStyleSheet("color:#1b5e20;font-size:11px;font-weight:600;")
        fol.addWidget(self._footer_lbl)
        fol.addStretch()
        hint = QLabel("Double-click to open invoice detail")
        hint.setStyleSheet("color:#888;font-size:11px;")
        fol.addWidget(hint)
        root.addWidget(foot)

    # ── Data ───────────────────────────────────────────────────────────────────

    def _load(self):
        date_from = self._from_dt.date().toString("yyyy-MM-dd")
        date_to   = self._to_dt.date().toString("yyyy-MM-dd")
        self._rows = SalesInvoiceService.list_invoices(
            limit=500, date_from=date_from, date_to=date_to
        )
        self._filter()

    def _filter(self):
        q = self._search.text().strip().lower()
        type_filter = self._type_combo.currentText()
        rows = self._rows
        if q:
            rows = [r for r in rows
                    if q in r["invoice_number"].lower()
                    or q in r["warehouse_name"].lower()
                    or q in r["cashier"].lower()]
        if type_filter == "Manual":
            rows = [r for r in rows if r["source"] == "manual"]
        elif type_filter == "Shift":
            rows = [r for r in rows if r["source"] == "pos_shift"]
        self._fill(rows)

    def _fill(self, rows: list[dict]):
        self._table.setRowCount(len(rows))
        grand_lbp = 0.0
        grand_usd = 0.0

        for i, r in enumerate(rows):
            if r["currency"] == "LBP":
                grand_lbp += r["total"]
            else:
                grand_usd += r["total"]

            paid_color = "#2e7d32" if r["payment_status"] == "paid" else "#e65100"
            cur = r["currency"]
            total_fmt = f"ل.ل {r['total']:,.0f}" if cur == "LBP" else f"${r['total']:,.2f}"
            wn = r["warehouse_num"]
            wn_str = str(wn) if wn != "" else "—"

            def cell(txt, align=Qt.AlignCenter, bold=False, color=None, _r=r):
                it = QTableWidgetItem(str(txt))
                it.setTextAlignment(align)
                it.setData(Qt.UserRole, _r["id"])
                if bold:
                    it.setFont(QFont("", -1, QFont.Bold))
                if color:
                    it.setForeground(QColor(color))
                return it

            self._table.setItem(i, 0, cell(r["invoice_number"], Qt.AlignLeft | Qt.AlignVCenter))
            wn_cell = cell(wn_str, bold=True, color="#1565c0")
            self._table.setItem(i, 1, wn_cell)
            self._table.setItem(i, 2, cell(r["date"]))
            self._table.setItem(i, 3, cell(r["warehouse_name"], Qt.AlignLeft | Qt.AlignVCenter))
            self._table.setItem(i, 4, cell(total_fmt, Qt.AlignRight | Qt.AlignVCenter, bold=True))
            self._table.setItem(i, 5, cell(r["cashier"], Qt.AlignLeft | Qt.AlignVCenter))
            self._table.setItem(i, 6, cell(r["payment_status"].upper(), color=paid_color, bold=True))

        parts = []
        if grand_lbp:
            parts.append(f"ل.ل {grand_lbp:,.0f}")
        if grand_usd:
            parts.append(f"${grand_usd:,.2f}")
        total_str = "  ·  ".join(parts) if parts else "0"
        self._footer_lbl.setText(
            f"  {len(rows)} invoice{'s' if len(rows) != 1 else ''}  ·  {total_str}"
        )

    def _open_detail(self, index):
        item = self._table.item(index.row(), 0)
        if not item:
            return
        inv_id = item.data(Qt.UserRole)
        inv_data = SalesInvoiceService.get_invoice(inv_id)
        if inv_data:
            InvoiceDetailDialog(inv_data, self).exec()

    def _on_selection(self):
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            self._selected_id = ""
            for b in (self._edit_btn, self._dup_btn, self._print_btn, self._delete_btn):
                b.setEnabled(False)
            self._action_lbl.setText("Select an invoice to enable actions")
            return
        item = self._table.item(rows[0].row(), 0)
        if not item:
            return
        self._selected_id = item.data(Qt.UserRole)
        inv_num = item.text()
        for b in (self._edit_btn, self._dup_btn, self._print_btn, self._delete_btn):
            b.setEnabled(True)
        self._action_lbl.setText(f"Invoice  {inv_num}  selected")

    def _get_selected_data(self) -> dict | None:
        if not self._selected_id:
            return None
        return SalesInvoiceService.get_invoice(self._selected_id)

    def _action_edit(self):
        d = self._get_selected_data()
        if not d:
            return
        if d["status"] == "cancelled":
            QMessageBox.warning(self, "Edit", "Cannot edit a cancelled invoice.")
            return

        user = AuthService.current_user()
        is_super = user and (
            str(user.role).strip().lower() == "admin"
            or bool(getattr(user, "is_power_user", False))
        )

        if d["source"] == "pos_shift" and not is_super:
            QMessageBox.information(
                self, "Edit",
                "POS shift invoices can only be edited by a superuser."
            )
            return

        # Non-superusers must enter a supervisor PIN
        if not is_super and not self._ask_supervisor_pin():
            return

        if QMessageBox.question(
            self, "Edit Invoice",
            f"Edit invoice {d['invoice_number']}?\n\n"
            "The original invoice will be voided and stock restored.\n"
            "A new invoice will be created when you save.",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        ok, err = SalesInvoiceService.delete_invoice(self._selected_id)
        if not ok:
            QMessageBox.critical(self, "Error", f"Could not void invoice:\n{err}")
            return
        self._load()
        self.edit_requested.emit(d)

    def _receive_shift_invoices(self):
        """Force-pull sales invoices from Supabase (resets cursor 30 days back)."""
        from sync.service import is_configured, pull_sales_invoices, _state_set
        if not is_configured():
            QMessageBox.warning(self, "Not Configured",
                                "Supabase is not configured. Check your .env file.")
            return
        from datetime import datetime, timezone, timedelta
        _state_set("sales_invoices_pull",
                   (datetime.now(timezone.utc) - timedelta(days=30)).isoformat())
        prog = QProgressDialog("Pulling invoices from server…", None, 0, 0, self)
        prog.setWindowTitle("Receive")
        prog.setMinimumDuration(0)
        prog.setValue(0)
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        pulled, err = pull_sales_invoices()
        prog.close()
        if err:
            QMessageBox.warning(self, "Error", f"Pull failed:\n{err}")
        else:
            QMessageBox.information(self, "Done",
                                    f"✔ {pulled} invoice(s) received from server.")
        self._load()

    def _purge_shift_invoices(self):
        """Superuser: bulk-cancel all pos_shift invoices before a chosen date."""
        from PySide6.QtWidgets import QDialogButtonBox, QFormLayout, QProgressDialog
        from PySide6.QtCore import QDate

        # ── Date picker dialog ────────────────────────────────────────────────
        dlg = QDialog(self)
        dlg.setWindowTitle("Purge Shift Invoices")
        dlg.setFixedWidth(380)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(10)

        lay.addWidget(QLabel(
            "Delete (cancel) all POS shift invoices\n"
            "<b>before</b> the selected date.\n\n"
            "Stock will be restored for each invoice."
        ))

        form = QFormLayout()
        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDate(QDate.currentDate())
        date_edit.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Delete invoices before:", date_edit)

        # Warehouse filter
        wh_combo = QComboBox()
        wh_combo.addItem("All warehouses", "")
        try:
            from database.engine import get_session, init_db
            from database.models.items import Warehouse
            init_db()
            s = get_session()
            try:
                for wh in s.query(Warehouse).filter_by(is_active=True).order_by(Warehouse.name).all():
                    wh_combo.addItem(wh.name, wh.id)
            finally:
                s.close()
        except Exception:
            pass
        form.addRow("Warehouse:", wh_combo)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        before_date = date_edit.date().toString("yyyy-MM-dd")
        wh_id = wh_combo.currentData()

        # ── Count matching invoices ───────────────────────────────────────────
        from database.engine import get_session, init_db
        from database.models.invoices import SalesInvoice
        import sqlalchemy
        init_db()
        session = get_session()
        try:
            q = session.query(SalesInvoice).filter(
                SalesInvoice.source == "pos_shift",
                SalesInvoice.invoice_date <= before_date,
            )
            if wh_id:
                q = q.filter(SalesInvoice.warehouse_id == wh_id)
            ids = [inv.id for inv in q.all()]
        finally:
            session.close()

        if not ids:
            QMessageBox.information(self, "Purge", "No matching shift invoices found.")
            return

        if QMessageBox.question(
            self, "Confirm Purge",
            f"This will cancel <b>{len(ids)}</b> shift invoice(s) before {before_date}"
            f"{' for the selected warehouse' if wh_id else ''}.\n\n"
            "Stock will be restored. This cannot be undone.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return

        # ── Delete with progress ──────────────────────────────────────────────
        prog = QProgressDialog("Purging shift invoices…", "Cancel", 0, len(ids), self)
        prog.setWindowTitle("Purge")
        prog.setMinimumDuration(0)
        prog.setValue(0)

        ok_count = fail_count = 0
        errors = []
        from database.engine import get_session, init_db
        from database.models.invoices import SalesInvoice, SalesInvoiceItem
        init_db()
        for i, inv_id in enumerate(ids):
            if prog.wasCanceled():
                break
            prog.setValue(i)
            try:
                s = get_session()
                try:
                    s.query(SalesInvoiceItem).filter_by(invoice_id=inv_id).delete()
                    s.query(SalesInvoice).filter_by(id=inv_id).delete()
                    s.commit()
                    ok_count += 1
                except Exception as e:
                    s.rollback()
                    fail_count += 1
                    errors.append(str(e))
                finally:
                    s.close()
                # Also delete from Supabase so sync doesn't bring it back
                try:
                    from sync.service import is_configured, _headers, _url
                    import requests as _req
                    if is_configured():
                        _req.delete(
                            f"{_url('sales_invoice_items_central')}?invoice_id=eq.{inv_id}",
                            headers=_headers(), timeout=10,
                        )
                        _req.delete(
                            f"{_url('sales_invoices_central')}?id=eq.{inv_id}",
                            headers=_headers(), timeout=10,
                        )
                except Exception:
                    pass
            except Exception as e:
                fail_count += 1
                errors.append(str(e))
        prog.setValue(len(ids))

        self._load()
        msg = f"Purge complete.\n\n✔ {ok_count} invoices cancelled."
        if fail_count:
            sample = "\n".join(set(errors[:5]))
            msg += f"\n✘ {fail_count} failed:\n{sample}"
        QMessageBox.information(self, "Purge Complete", msg)

    def _ask_supervisor_pin(self) -> bool:
        """Prompt for a supervisor PIN. Checks admin passwords and power-user PINs."""
        from PySide6.QtWidgets import QInputDialog
        pin, ok = QInputDialog.getText(
            self, "Supervisor Required",
            "Enter supervisor password / PIN:",
            echo=QLineEdit.Password,
        )
        if not ok or not pin.strip():
            return False
        from database.engine import get_session, init_db
        from database.models.users import User
        import bcrypt
        init_db()
        session = get_session()
        try:
            supervisors = session.query(User).filter(
                User.is_active == True
            ).filter(
                (User.role == "admin") | (User.is_power_user == True)
            ).all()
            for u in supervisors:
                # Check 4-digit PIN first
                if u.pin and u.pin == pin.strip():
                    return True
                # Check full password
                try:
                    if u.password_hash and bcrypt.checkpw(
                        pin.strip().encode(), u.password_hash.encode()
                    ):
                        return True
                except Exception:
                    pass
        finally:
            session.close()
        QMessageBox.warning(self, "Access Denied", "Incorrect supervisor credentials.")
        return False

    def _action_duplicate(self):
        d = self._get_selected_data()
        if d:
            self.duplicate_requested.emit(d)

    def _action_print(self):
        d = self._get_selected_data()
        if d:
            _print_invoice(d, self)

    def _action_delete(self):
        d = self._get_selected_data()
        if not d:
            return
        if d["status"] == "cancelled":
            QMessageBox.information(self, "Delete", "Invoice is already cancelled.")
            return
        if QMessageBox.question(
            self, "Delete Invoice",
            f"Void invoice {d['invoice_number']}?\n\nStock will be restored.",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        ok, err = SalesInvoiceService.delete_invoice(self._selected_id)
        if ok:
            self._load()
            self._selected_id = ""
            for b in (self._edit_btn, self._dup_btn, self._print_btn, self._delete_btn):
                b.setEnabled(False)
            self._action_lbl.setText("Invoice voided")
        else:
            QMessageBox.critical(self, "Error", f"Failed:\n{err}")

    def refresh(self):
        self._load()

    def set_search(self, text: str):
        """Pre-fill the search box and filter (called from hub dialog)."""
        self._search.setText(text)
        self._filter()
