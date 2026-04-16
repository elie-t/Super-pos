"""
Delivery Invoices Screen
========================
Shows delivery invoices pushed from the mobile Delivery App.
Lets the purchasing manager review and convert them to real purchase invoices.
"""
from __future__ import annotations

import threading
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QFrame, QHeaderView, QAbstractItemView,
    QMessageBox, QComboBox, QProgressDialog, QDialog, QDialogButtonBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor, QFont


# ── Background worker ──────────────────────────────────────────────────────────

class _PullWorker(QThread):
    done    = Signal(list, str)   # (invoices, error)

    def __init__(self, status: str, parent=None):
        super().__init__(parent)
        self._status = status

    def run(self):
        try:
            from sync.service import pull_delivery_invoices
            invoices, err = pull_delivery_invoices(self._status)
            self.done.emit(invoices, err)
        except Exception as e:
            self.done.emit([], str(e))


class _ConvertWorker(QThread):
    done = Signal(str, str)   # (purchase_invoice_id, error)

    def __init__(self, delivery: dict, parent=None):
        super().__init__(parent)
        self._delivery = delivery

    def run(self):
        try:
            inv_id = _convert_delivery_to_purchase(self._delivery)
            self.done.emit(inv_id, "")
        except Exception as e:
            self.done.emit("", str(e))


# ── View-items worker ──────────────────────────────────────────────────────────

class _ItemsWorker(QThread):
    done = Signal(list, str)   # (items, error)

    def __init__(self, invoice_id: str, parent=None):
        super().__init__(parent)
        self._invoice_id = invoice_id

    def run(self):
        try:
            from sync.service import pull_delivery_invoice_items
            items, err = pull_delivery_invoice_items(self._invoice_id)
            self.done.emit(items, err)
        except Exception as e:
            self.done.emit([], str(e))


# ── Delivery detail dialog ─────────────────────────────────────────────────────

class DeliveryDetailDialog(QDialog):
    """Shows full delivery invoice details before conversion."""

    def __init__(self, delivery: dict, parent=None):
        super().__init__(parent)
        self._delivery = delivery
        self._worker: _ItemsWorker | None = None
        self.setWindowTitle(f"Delivery Invoice — {delivery.get('invoice_number', '')}")
        self.resize(820, 540)
        self._build_ui()
        self._load_items()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 12)

        # Header info
        d = self._delivery
        currency = d.get("currency", "USD")
        total = float(d.get("total", 0))
        total_str = (
            f"{total:,.0f} L.L." if currency == "LBP" else f"$ {total:,.2f}"
        )

        info = QLabel(
            f"<b>Supplier:</b> {d.get('supplier_name') or '—'}  &nbsp;|&nbsp; "
            f"<b>Date:</b> {d.get('invoice_date', '')}  &nbsp;|&nbsp; "
            f"<b>Currency:</b> {currency}  &nbsp;|&nbsp; "
            f"<b>Total:</b> {total_str}  &nbsp;|&nbsp; "
            f"<b>Status:</b> {d.get('status', '').upper()}"
        )
        info.setStyleSheet("font-size:13px; padding:6px 4px;")
        info.setWordWrap(True)
        root.addWidget(info)

        if d.get("notes"):
            notes_lbl = QLabel(f"<i>Notes: {d['notes']}</i>")
            notes_lbl.setStyleSheet("font-size:12px; color:#666; padding:0 4px 4px;")
            root.addWidget(notes_lbl)

        # Items table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["#", "Item Name", "Barcode", "Qty", "Unit Cost", "Line Total"])
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(26)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2, 3, 4, 5):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setStyleSheet(
            "QHeaderView::section{background:#1b5e20;color:#fff;font-weight:700;"
            "border:none;padding:4px;}"
        )
        root.addWidget(self._table, stretch=1)

        self._loading_lbl = QLabel("Loading items…")
        self._loading_lbl.setAlignment(Qt.AlignCenter)
        self._loading_lbl.setStyleSheet("color:#888; font-size:13px;")
        root.addWidget(self._loading_lbl)

        # Total row
        self._total_lbl = QLabel()
        self._total_lbl.setAlignment(Qt.AlignRight)
        self._total_lbl.setStyleSheet("font-size:14px; font-weight:700; color:#1b5e20; padding:4px;")
        root.addWidget(self._total_lbl)

        # Close button
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _load_items(self):
        self._worker = _ItemsWorker(self._delivery["id"], self)
        self._worker.done.connect(self._on_items)
        self._worker.start()

    def _on_items(self, items: list, err: str):
        self._loading_lbl.hide()
        if err:
            self._loading_lbl.setText(f"Error: {err}")
            self._loading_lbl.show()
            return

        currency = self._delivery.get("currency", "USD")
        self._table.setRowCount(len(items))
        grand_total = 0.0

        for i, line in enumerate(items):
            unit_cost  = float(line.get("unit_cost", 0))
            line_total = float(line.get("line_total", 0))
            qty        = float(line.get("quantity", 0))
            grand_total += line_total

            def fmt(val):
                if currency == "LBP":
                    return f"{val:,.0f} L"
                return f"$ {val:,.2f}"

            cells = [
                (str(i + 1),                             Qt.AlignCenter),
                (line.get("item_name", ""),               Qt.AlignLeft | Qt.AlignVCenter),
                (line.get("barcode", "") or "—",          Qt.AlignCenter),
                (f"{qty:g}",                              Qt.AlignCenter),
                (fmt(unit_cost),                          Qt.AlignRight | Qt.AlignVCenter),
                (fmt(line_total),                         Qt.AlignRight | Qt.AlignVCenter),
            ]
            for col, (val, align) in enumerate(cells):
                cell = QTableWidgetItem(val)
                cell.setTextAlignment(align)
                self._table.setItem(i, col, cell)

        if currency == "LBP":
            total_str = f"Total: {grand_total:,.0f} L.L."
        else:
            total_str = f"Total: $ {grand_total:,.2f}"
        self._total_lbl.setText(total_str)


# ── Core conversion logic ──────────────────────────────────────────────────────

def _convert_delivery_to_purchase(delivery: dict) -> str:
    """
    Convert a delivery invoice dict (from Supabase) into a local PurchaseInvoice.
    Creates any missing items/barcodes/suppliers locally.
    Returns the new PurchaseInvoice.id.
    """
    from database.engine import get_session, init_db
    from database.models.invoices import PurchaseInvoice, PurchaseInvoiceItem
    from database.models.parties import Supplier
    from database.models.items import Item, ItemBarcode, Warehouse
    from database.models.users import User
    from database.models.base import new_uuid
    from services.purchase_service import PurchaseService
    from sync.service import pull_delivery_invoice_items, mark_delivery_converted
    from datetime import date

    # Pull line items from Supabase
    items, err = pull_delivery_invoice_items(delivery["id"])
    if err:
        raise RuntimeError(f"Failed to fetch items: {err}")

    init_db()
    session = get_session()
    try:
        # ── Supplier ──────────────────────────────────────────────────────────
        sup_name = (delivery.get("supplier_name") or "Unknown Supplier").strip()
        supplier = session.query(Supplier).filter(
            Supplier.name.ilike(sup_name)
        ).first()
        if not supplier:
            supplier = Supplier(
                id=new_uuid(), name=sup_name, is_active=True,
                currency=delivery.get("currency", "USD"),
            )
            session.add(supplier)
            session.flush()

        # ── Warehouse (use default, or the one matching branch_id) ────────────
        wh = session.query(Warehouse).filter_by(is_default=True).first()
        if not wh:
            wh = session.query(Warehouse).filter_by(is_active=True).first()
        if not wh:
            raise RuntimeError("No warehouse found in local database.")
        warehouse_id = wh.id

        # ── Operator (current active admin) ───────────────────────────────────
        operator = (
            session.query(User)
            .filter_by(is_active=True, role="admin")
            .first()
        ) or session.query(User).filter_by(is_active=True).first()
        operator_id = operator.id if operator else new_uuid()

        # ── Invoice number ────────────────────────────────────────────────────
        inv_number = PurchaseService.next_invoice_number(warehouse_id)

        # ── Create PurchaseInvoice (draft — operator reviews before finalizing) ─
        inv = PurchaseInvoice(
            id=new_uuid(),
            invoice_number=inv_number,
            supplier_id=supplier.id,
            operator_id=operator_id,
            warehouse_id=warehouse_id,
            invoice_date=date.today().isoformat(),
            invoice_type="purchase",
            status="draft",
            payment_status="unpaid",
            currency=delivery.get("currency", "USD"),
            subtotal=0.0, discount_value=0.0, vat_value=0.0,
            total=0.0, amount_paid=0.0,
            notes=f"Imported from delivery {delivery.get('invoice_number', '')} — {delivery.get('notes', '')}",
        )
        session.add(inv)
        session.flush()

        # ── Line items ────────────────────────────────────────────────────────
        subtotal = 0.0
        for line in items:
            item_id  = (line.get("item_id")  or "").strip()
            barcode  = (line.get("barcode")  or "").strip()
            item_name = (line.get("item_name") or "Unknown Item").strip()

            local_item: Item | None = None

            # 1. Try by item_id
            if item_id:
                local_item = session.get(Item, item_id)

            # 2. Try by barcode
            if not local_item and barcode:
                bc_row = session.query(ItemBarcode).filter_by(barcode=barcode).first()
                if bc_row:
                    local_item = session.get(Item, bc_row.item_id)

            # 3. Try by item name (partial)
            if not local_item and item_name and item_name != "Unknown Item":
                local_item = session.query(Item).filter(
                    Item.name.ilike(item_name)
                ).first()

            # 4. Create temp item
            if not local_item:
                code = f"IMP-{barcode[:12] if barcode else new_uuid()[:8]}"
                local_item = Item(
                    id=item_id or new_uuid(),
                    code=code,
                    name=item_name,
                    is_active=False,   # needs review
                    cost_price=float(line.get("unit_cost") or 0),
                    cost_currency=line.get("currency", "USD"),
                )
                session.add(local_item)
                session.flush()

                if barcode:
                    existing_bc = session.query(ItemBarcode).filter_by(barcode=barcode).first()
                    if not existing_bc:
                        session.add(ItemBarcode(
                            id=new_uuid(),
                            item_id=local_item.id,
                            barcode=barcode,
                            is_primary=True,
                            pack_qty=1,
                        ))

            qty       = float(line.get("quantity")  or 0)
            unit_cost = float(line.get("unit_cost") or 0)
            line_total = float(line.get("line_total") or qty * unit_cost)

            session.add(PurchaseInvoiceItem(
                id=new_uuid(),
                invoice_id=inv.id,
                item_id=local_item.id,
                item_name=local_item.name,
                quantity=qty,
                pack_size=int(line.get("pack_size") or 1),
                unit_cost=unit_cost,
                currency=line.get("currency", inv.currency),
                discount_pct=0.0,
                vat_pct=0.0,
                line_total=line_total,
            ))
            subtotal += line_total

        inv.subtotal = round(subtotal, 4)
        inv.total    = round(subtotal, 4)
        session.commit()

        # Bump invoice counter
        PurchaseService.increment_invoice_number(warehouse_id)

        # Mark as converted in Supabase (non-fatal if it fails)
        try:
            mark_delivery_converted(delivery["id"], inv_number)
        except Exception:
            pass

        return inv.id

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ── Main screen ────────────────────────────────────────────────────────────────

class DeliveryInvoicesScreen(QWidget):
    back             = Signal()
    invoice_selected = Signal(str)   # emits local PurchaseInvoice.id after conversion

    STATUS_COLOR = {
        "pending":   QColor("#e65100"),
        "converted": QColor("#2e7d32"),
        "rejected":  QColor("#c62828"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._invoices: list[dict] = []
        self._pull_worker: _PullWorker | None = None
        self._convert_worker: _ConvertWorker | None = None
        self._build_ui()
        self._load("pending")

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        bar = QFrame()
        bar.setFixedHeight(46)
        bar.setStyleSheet("background:#1b5e20;")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(12, 0, 12, 0)
        bar_lay.setSpacing(10)

        back_btn = QPushButton("←  Back")
        back_btn.setFixedHeight(30)
        back_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.15);color:#fff;"
            "border:1px solid rgba(255,255,255,0.3);border-radius:4px;padding:0 12px;font-size:12px;}"
            "QPushButton:hover{background:rgba(255,255,255,0.3);}"
        )
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.back.emit)
        bar_lay.addWidget(back_btn)

        title = QLabel("📦  Delivery Invoices")
        title.setStyleSheet("color:#fff; font-size:15px; font-weight:700; margin-left:6px;")
        bar_lay.addWidget(title)
        bar_lay.addStretch()

        # Status filter
        status_lbl = QLabel("Show:")
        status_lbl.setStyleSheet("color:rgba(255,255,255,0.8); font-size:12px;")
        bar_lay.addWidget(status_lbl)
        self._status_combo = QComboBox()
        self._status_combo.addItems(["Pending", "Converted", "All"])
        self._status_combo.setFixedHeight(28)
        self._status_combo.setStyleSheet(
            "QComboBox{background:#fff;border:none;border-radius:4px;padding:0 8px;font-size:12px;}"
        )
        self._status_combo.currentIndexChanged.connect(self._on_filter_changed)
        bar_lay.addWidget(self._status_combo)

        # Pull button
        self._pull_btn = QPushButton("🔄  Pull Latest")
        self._pull_btn.setFixedHeight(28)
        self._pull_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.15);color:#fff;"
            "border:1px solid rgba(255,255,255,0.3);border-radius:4px;padding:0 12px;font-size:12px;}"
            "QPushButton:hover{background:rgba(255,255,255,0.3);}"
        )
        self._pull_btn.setCursor(Qt.PointingHandCursor)
        self._pull_btn.clicked.connect(self._refresh)
        bar_lay.addWidget(self._pull_btn)

        root.addWidget(bar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels([
            "#", "Invoice No", "Date", "Branch / Warehouse", "Supplier", "Lines", "Total", "Status"
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(28)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        for c in (0, 1, 2, 5, 6, 7):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setStyleSheet(
            "QHeaderView::section{background:#1b5e20;color:#fff;font-weight:700;"
            "border:none;padding:4px;}"
        )
        self._table.selectionModel().selectionChanged.connect(self._on_selection)
        self._table.doubleClicked.connect(self._view_selected)
        root.addWidget(self._table, stretch=1)

        # Footer
        foot = QFrame()
        foot.setStyleSheet("background:#f0f4f0; border-top:1px solid #c8dfc8;")
        foot_lay = QHBoxLayout(foot)
        foot_lay.setContentsMargins(16, 8, 16, 8)
        foot_lay.setSpacing(10)

        self._status_lbl = QLabel("Ready.")
        self._status_lbl.setStyleSheet("font-size:12px; color:#555;")
        foot_lay.addWidget(self._status_lbl)
        foot_lay.addStretch()

        self._view_btn = QPushButton("🔍  View Details")
        self._view_btn.setFixedHeight(32)
        self._view_btn.setEnabled(False)
        self._view_btn.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#fff;border:none;border-radius:5px;"
            "font-size:13px;font-weight:700;padding:0 18px;}"
            "QPushButton:hover{background:#122540;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self._view_btn.setCursor(Qt.PointingHandCursor)
        self._view_btn.clicked.connect(self._view_selected)
        foot_lay.addWidget(self._view_btn)

        self._convert_btn = QPushButton("✅  Convert to Purchase Invoice")
        self._convert_btn.setFixedHeight(32)
        self._convert_btn.setEnabled(False)
        self._convert_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;border:none;border-radius:5px;"
            "font-size:13px;font-weight:700;padding:0 18px;}"
            "QPushButton:hover{background:#1b5e20;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self._convert_btn.setCursor(Qt.PointingHandCursor)
        self._convert_btn.clicked.connect(self._convert_selected)
        foot_lay.addWidget(self._convert_btn)

        root.addWidget(foot)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _on_filter_changed(self):
        mapping = {0: "pending", 1: "converted", 2: "all"}
        self._load(mapping[self._status_combo.currentIndex()])

    def _refresh(self):
        mapping = {0: "pending", 1: "converted", 2: "all"}
        self._load(mapping[self._status_combo.currentIndex()])

    def _load(self, status: str = "pending"):
        from sync.service import is_configured
        if not is_configured():
            self._status_lbl.setText("⚠  Sync not configured — set Supabase credentials in Settings.")
            return

        self._pull_btn.setEnabled(False)
        self._status_lbl.setText("Pulling from Supabase…")

        worker = _PullWorker(status, self)
        worker.done.connect(self._on_pull_done)
        worker.finished.connect(lambda: setattr(self, "_pull_worker", None))
        self._pull_worker = worker
        worker.start()

    def _on_pull_done(self, invoices: list[dict], err: str):
        self._pull_btn.setEnabled(True)
        if err:
            self._status_lbl.setText(f"Error: {err}")
            return

        self._invoices = invoices
        self._table.setRowCount(0)
        self._table.setRowCount(len(invoices))

        for i, inv in enumerate(invoices):
            status = inv.get("status", "pending")
            color  = self.STATUS_COLOR.get(status, QColor("#888"))
            notes  = inv.get("notes", "")
            # Derive warehouse name from notes or fall back to warehouse_id
            wh_name = inv.get("warehouse_id", "")[:8] if not notes else ""

            cells = [
                (str(i + 1),                               Qt.AlignCenter),
                (inv.get("invoice_number", ""),             Qt.AlignLeft | Qt.AlignVCenter),
                (inv.get("invoice_date", ""),               Qt.AlignCenter),
                (wh_name,                                   Qt.AlignLeft | Qt.AlignVCenter),
                (inv.get("supplier_name", ""),              Qt.AlignLeft | Qt.AlignVCenter),
                (str(len(inv.get("lines", []))),            Qt.AlignCenter),
                (f"{float(inv.get('total', 0)):,.2f} {inv.get('currency', '')}",
                                                            Qt.AlignRight | Qt.AlignVCenter),
                (status.upper(),                            Qt.AlignCenter),
            ]
            for col, (val, align) in enumerate(cells):
                cell = QTableWidgetItem(val)
                cell.setTextAlignment(align)
                if col == 7:
                    cell.setForeground(color)
                    cell.setFont(QFont("", -1, QFont.Bold))
                self._table.setItem(i, col, cell)

        self._status_lbl.setText(f"Loaded {len(invoices)} invoice(s).")
        self._view_btn.setEnabled(False)
        self._convert_btn.setEnabled(False)

    # ── Selection ─────────────────────────────────────────────────────────────

    def _on_selection(self):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._invoices):
            self._view_btn.setEnabled(False)
            self._convert_btn.setEnabled(False)
            return
        inv = self._invoices[row]
        is_pending = inv.get("status") == "pending"
        self._view_btn.setEnabled(True)
        self._convert_btn.setEnabled(is_pending)

    def _view_selected(self, *_):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._invoices):
            return
        dlg = DeliveryDetailDialog(self._invoices[row], self)
        dlg.exec()

    # ── Convert ───────────────────────────────────────────────────────────────

    def _convert_selected(self):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._invoices):
            return
        delivery = self._invoices[row]

        reply = QMessageBox.question(
            self, "Convert Delivery",
            f"Convert delivery  {delivery.get('invoice_number', '')}  to a Purchase Invoice?\n\n"
            "A draft purchase invoice will be created locally for your review.\n"
            "New/unknown items will be created as inactive (needs review).",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        self._convert_btn.setEnabled(False)
        self._pull_btn.setEnabled(False)
        self._status_lbl.setText("Converting…")

        worker = _ConvertWorker(delivery, self)
        worker.done.connect(self._on_convert_done)
        worker.finished.connect(lambda: setattr(self, "_convert_worker", None))
        self._convert_worker = worker
        worker.start()

    def refresh(self):
        """Called by PurchaseModule when the screen is revisited."""
        self._refresh()

    def _on_convert_done(self, inv_id: str, err: str):
        self._pull_btn.setEnabled(True)
        if err:
            self._status_lbl.setText(f"Error: {err}")
            QMessageBox.warning(self, "Conversion Failed", err)
            return

        self._status_lbl.setText("Conversion complete.")
        QMessageBox.information(
            self, "Converted",
            "Purchase invoice created as draft.\nOpening for review…",
        )
        self._refresh()
        if inv_id:
            self.invoice_selected.emit(inv_id)
