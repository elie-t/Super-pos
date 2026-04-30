"""
Daily Sales Service — reporting and end-of-shift export.
"""
import json
from datetime import datetime
from pathlib import Path

from database.engine import get_session, init_db
from database.models.invoices import SalesInvoice, SalesInvoiceItem
from database.models.items import Item, Category, Warehouse
from database.models.users import User
from database.models.financials import Payment


class DailySalesService:

    @staticmethod
    def get_report(date_from: str = "", date_to: str = "",
                   warehouse_id: str = "",
                   archived: bool = False) -> dict:
        """
        archived=False  → Daily Sales  (non-archived / open shift)
        archived=True   → Old Sales    (archived / closed shifts)

        date_from / date_to are optional filters on top of the archived flag.
        """
        init_db()
        session = get_session()
        try:
            q = session.query(SalesInvoice).filter(
                SalesInvoice.status       == "finalized",
                SalesInvoice.invoice_type == "sale",
                SalesInvoice.source       == "pos",
                SalesInvoice.is_archived  == archived,
            )
            if date_from:
                q = q.filter(SalesInvoice.invoice_date >= date_from)
            if date_to:
                q = q.filter(SalesInvoice.invoice_date <= date_to)
            if warehouse_id:
                q = q.filter(SalesInvoice.warehouse_id == warehouse_id)

            invoices = q.order_by(SalesInvoice.invoice_date.desc()).all()

            empty = {
                "summary": {
                    "invoice_count": 0,
                    "totals_by_currency": {},
                    "discount_total": 0.0,
                },
                "by_payment":  [],
                "by_category": [],
                "by_cashier":       [],
                "by_cashier_date":  [],
                "invoices":         [],
            }
            if not invoices:
                return empty

            invoice_ids = [inv.id for inv in invoices]

            # ── Summary: group totals by actual stored currency ────────────────
            totals_by_currency: dict[str, float] = {}
            discount_total = 0.0
            for inv in invoices:
                cur = inv.currency or "LBP"
                totals_by_currency[cur] = totals_by_currency.get(cur, 0.0) + inv.total
                discount_total += inv.discount_value

            # ── By payment method ──────────────────────────────────────────────
            payments = (
                session.query(Payment)
                .filter(Payment.sales_invoice_id.in_(invoice_ids))
                .all()
            )
            # Group payments by method AND currency
            pay_agg: dict[tuple, float] = {}
            for p in payments:
                key = (p.payment_method, p.currency)
                pay_agg[key] = pay_agg.get(key, 0.0) + p.amount
            by_payment = [
                {"method": m, "currency": c, "total": round(t, 2)}
                for (m, c), t in sorted(pay_agg.items())
            ]

            # ── By category ────────────────────────────────────────────────────
            line_items = (
                session.query(SalesInvoiceItem)
                .filter(SalesInvoiceItem.invoice_id.in_(invoice_ids))
                .all()
            )
            item_ids = list({li.item_id for li in line_items})
            cat_map: dict[str, str] = {}
            if item_ids:
                for item_id, cat_name in (
                    session.query(Item.id, Category.name)
                    .outerjoin(Category, Item.category_id == Category.id)
                    .filter(Item.id.in_(item_ids))
                    .all()
                ):
                    cat_map[item_id] = cat_name or "Uncategorised"

            # Which categories are flagged show_in_daily
            highlighted_cat_names: set[str] = set()
            for c in session.query(Category).filter_by(show_in_daily=True, is_active=True).all():
                highlighted_cat_names.add(c.name)

            # Aggregate per-category per-currency
            cat_agg: dict[str, dict] = {}
            for li in line_items:
                cat = cat_map.get(li.item_id, "Uncategorised")
                if cat not in cat_agg:
                    cat_agg[cat] = {"qty": 0.0, "total": 0.0}
                cat_agg[cat]["qty"]   += li.quantity
                cat_agg[cat]["total"] += li.line_total

            # Determine primary currency for % calculation
            grand = sum(v["total"] for v in cat_agg.values()) or 1.0
            # Find the most-used currency across invoices
            primary_cur = max(totals_by_currency, key=totals_by_currency.get) if totals_by_currency else "LBP"

            by_category = sorted(
                [
                    {
                        "category": cat,
                        "qty":      round(v["qty"], 2),
                        "total":    round(v["total"], 0),
                        "currency": primary_cur,
                        "pct":      round(v["total"] / grand * 100, 1),
                    }
                    for cat, v in cat_agg.items()
                ],
                key=lambda x: x["total"],
                reverse=True,
            )

            # ── By cashier ─────────────────────────────────────────────────────
            op_ids = list({inv.operator_id for inv in invoices})
            op_map: dict[str, str] = {}
            if op_ids:
                for u in session.query(User).filter(User.id.in_(op_ids)).all():
                    op_map[u.id] = u.full_name or u.username or "Unknown"

            cashier_agg: dict[str, dict] = {}
            for inv in invoices:
                name = op_map.get(inv.operator_id, "Unknown")
                cur  = inv.currency or "LBP"
                if name not in cashier_agg:
                    cashier_agg[name] = {"count": 0, "totals": {}}
                cashier_agg[name]["count"] += 1
                cashier_agg[name]["totals"][cur] = (
                    cashier_agg[name]["totals"].get(cur, 0.0) + inv.total
                )

            by_cashier = sorted(
                [
                    {
                        "cashier":  name,
                        "invoices": v["count"],
                        "totals":   {c: round(t, 0) for c, t in v["totals"].items()},
                    }
                    for name, v in cashier_agg.items()
                ],
                key=lambda x: sum(x["totals"].values()),
                reverse=True,
            )

            # ── By cashier × date (date + cashier → totals) ────────────────────
            cashier_date_agg: dict[tuple, dict] = {}
            for inv in invoices:
                name = op_map.get(inv.operator_id, "Unknown")
                cur  = inv.currency or "LBP"
                key  = (inv.invoice_date or "", name)
                if key not in cashier_date_agg:
                    cashier_date_agg[key] = {"count": 0, "totals": {}}
                cashier_date_agg[key]["count"] += 1
                cashier_date_agg[key]["totals"][cur] = (
                    cashier_date_agg[key]["totals"].get(cur, 0.0) + inv.total
                )

            by_cashier_date = sorted(
                [
                    {
                        "date":     k[0],
                        "cashier":  k[1],
                        "invoices": v["count"],
                        "totals":   {c: round(t, 0) for c, t in v["totals"].items()},
                    }
                    for k, v in cashier_date_agg.items()
                ],
                key=lambda x: (x["date"], x["cashier"]),
            )

            # ── Raw invoice list (for export) ──────────────────────────────────
            inv_items_map: dict[str, list] = {}
            for li in line_items:
                inv_items_map.setdefault(li.invoice_id, []).append(li)

            invoice_list = [
                {
                    "id":             inv.id,
                    "invoice_number": inv.invoice_number,
                    "invoice_date":   inv.invoice_date,
                    "operator":       op_map.get(inv.operator_id, "?"),
                    "total":          inv.total,
                    "currency":       inv.currency,
                    "payment_status": inv.payment_status,
                    "items": [
                        {
                            "item_id":    li.item_id,
                            "item_name":  li.item_name,
                            "barcode":    li.barcode or "",
                            "qty":        li.quantity,
                            "unit_price": li.unit_price,
                            "currency":   li.currency,
                            "line_total": li.line_total,
                        }
                        for li in inv_items_map.get(inv.id, [])
                    ],
                }
                for inv in invoices
            ]

            # Highlighted category totals for the summary cards
            highlighted = [
                {"name": cat, "total": round(v["total"], 0), "currency": primary_cur}
                for cat, v in cat_agg.items()
                if cat in highlighted_cat_names
            ]

            return {
                "summary": {
                    "invoice_count":      len(invoices),
                    "totals_by_currency": {c: round(t, 0) for c, t in totals_by_currency.items()},
                    "discount_total":     round(discount_total, 0),
                    "primary_currency":   primary_cur,
                },
                "by_payment":       by_payment,
                "by_category":      by_category,
                "highlighted_cats": highlighted,
                "by_cashier":       by_cashier,
                "by_cashier_date":  by_cashier_date,
                "invoices":         invoice_list,
            }
        finally:
            session.close()

    @staticmethod
    def close_shift(warehouse_id: str = "") -> tuple[int, str]:
        """
        1. Export all non-archived finalized POS invoices to a JSON shift file.
        2. Create one consolidated SalesInvoice (source='pos_shift') PER DAY,
           grouping invoices by invoice_date so multi-day shifts produce one
           invoice per day each dated correctly.
           Stock is NOT re-deducted (POS already did it per-sale).
        3. Mark all POS invoices as archived.
        Returns (count_archived, filepath).
        """
        from collections import defaultdict
        from database.models.base import new_uuid
        from database.models.parties import Customer

        report = DailySalesService.get_report(archived=False, warehouse_id=warehouse_id)

        export_dir = Path.home() / "Documents" / "TannouryMarket" / "shifts"
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath  = export_dir / f"shift_{timestamp}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({
                "exported_at":  datetime.now().isoformat(),
                "warehouse_id": warehouse_id,
                "report":       report,
            }, f, ensure_ascii=False, indent=2)

        init_db()
        session = get_session()
        try:
            # ── Fetch all open POS invoices ───────────────────────────────────
            q = session.query(SalesInvoice).filter(
                SalesInvoice.status       == "finalized",
                SalesInvoice.invoice_type == "sale",
                SalesInvoice.source       == "pos",
                SalesInvoice.is_archived  == False,
            )
            if warehouse_id:
                q = q.filter(SalesInvoice.warehouse_id == warehouse_id)
            open_invoices = q.all()
            count = len(open_invoices)

            if not open_invoices:
                return 0, str(filepath)

            invoice_ids = [inv.id for inv in open_invoices]

            # ── Fetch all line items, indexed by invoice_id ───────────────────
            all_lines = (
                session.query(SalesInvoiceItem)
                .filter(SalesInvoiceItem.invoice_id.in_(invoice_ids))
                .all()
            )
            lines_by_invoice: dict[str, list] = defaultdict(list)
            for li in all_lines:
                lines_by_invoice[li.invoice_id].append(li)

            # ── Group invoices by their date ──────────────────────────────────
            today_str = datetime.now().strftime("%Y-%m-%d")
            by_date: dict[str, list] = defaultdict(list)
            for inv in open_invoices:
                by_date[inv.invoice_date or today_str].append(inv)

            walk_in = session.query(Customer).filter_by(is_cash_client=True).first()
            wh_id   = warehouse_id or open_invoices[0].warehouse_id or ""

            created_shift_ids: list[tuple[str, list[str]]] = []

            # ── One shift invoice per day ─────────────────────────────────────
            for date_key in sorted(by_date.keys()):
                day_invoices = by_date[date_key]
                date_tag     = date_key.replace("-", "")

                # Aggregate line items for this day
                agg: dict[str, dict] = {}
                for inv in day_invoices:
                    for li in lines_by_invoice.get(inv.id, []):
                        if li.item_id not in agg:
                            agg[li.item_id] = {
                                "name":       li.item_name,
                                "qty":        0.0,
                                "line_total": 0.0,
                                "currency":   li.currency,
                                "disc":       li.discount_pct,
                                "vat":        li.vat_pct,
                            }
                        agg[li.item_id]["qty"]        += li.quantity
                        agg[li.item_id]["line_total"] += li.line_total

                # Count ALL invoices whose number starts with SH-{date}- regardless
                # of source or how they arrived (local creation vs. synced from
                # another branch).  Counting only source='pos_shift' misses
                # invoices that were synced in with a different source/date format,
                # causing the sequence to collide with an existing number.
                existing = session.query(SalesInvoice).filter(
                    SalesInvoice.invoice_number.like(f"SH-{date_tag}-%"),
                ).count()
                shift_number = f"SH-{date_tag}-{existing + 1:03d}"
                # Guarantee uniqueness even if the count is still off (e.g. two
                # concurrent shift closes, or an orphaned record with that number).
                while session.query(SalesInvoice).filter_by(
                    invoice_number=shift_number
                ).first():
                    existing += 1
                    shift_number = f"SH-{date_tag}-{existing + 1:03d}"

                op_id       = day_invoices[0].operator_id or ""
                customer_id = walk_in.id if walk_in else day_invoices[0].customer_id

                shift_total    = sum(inv.total          for inv in day_invoices)
                shift_subtotal = sum(inv.subtotal       for inv in day_invoices)
                shift_disc     = sum(inv.discount_value for inv in day_invoices)
                shift_vat      = sum(inv.vat_value      for inv in day_invoices)
                shift_paid     = sum(inv.amount_paid    for inv in day_invoices)

                cur_totals: dict[str, float] = {}
                for inv in day_invoices:
                    cur_totals[inv.currency] = cur_totals.get(inv.currency, 0) + inv.total
                shift_currency = max(cur_totals, key=cur_totals.get) if cur_totals else "LBP"

                shift_pay_status = (
                    "paid"    if shift_paid >= shift_total else
                    "partial" if shift_paid > 0 else
                    "unpaid"
                )

                shift_inv = SalesInvoice(
                    id             = new_uuid(),
                    invoice_number = shift_number,
                    customer_id    = customer_id,
                    operator_id    = op_id,
                    warehouse_id   = wh_id,
                    invoice_date   = date_key,
                    invoice_type   = "sale",
                    source         = "pos_shift",
                    subtotal       = shift_subtotal,
                    discount_value = shift_disc,
                    vat_value      = shift_vat,
                    total          = shift_total,
                    currency       = shift_currency,
                    status         = "finalized",
                    payment_status = shift_pay_status,
                    amount_paid    = shift_paid,
                    notes          = f"Shift close: {len(day_invoices)} POS invoices · {timestamp}",
                    is_archived    = False,
                )
                session.add(shift_inv)
                session.flush()  # makes this invoice visible to the next iteration's count

                for item_id, d in agg.items():
                    # Skip items not present in the local items table — they
                    # may exist on other branches but haven't synced here yet.
                    # The FK constraint would fail without this guard.
                    if not session.get(Item, item_id):
                        continue
                    qty        = d["qty"]
                    line_total = d["line_total"]
                    unit_price = (line_total / qty) if qty else 0.0
                    session.add(SalesInvoiceItem(
                        id           = new_uuid(),
                        invoice_id   = shift_inv.id,
                        item_id      = item_id,
                        item_name    = d["name"],
                        quantity     = qty,
                        unit_price   = round(unit_price, 4),
                        currency     = d["currency"],
                        discount_pct = d["disc"],
                        vat_pct      = d["vat"],
                        line_total   = round(line_total, 4),
                    ))

                created_shift_ids.append((shift_inv.id, list(agg.keys())))

            # ── Archive all POS invoices ───────────────────────────────────────
            for inv in open_invoices:
                inv.is_archived = True

            session.commit()

            # ── Enqueue all shift invoices for sync ───────────────────────────
            for shift_id, item_ids in created_shift_ids:
                try:
                    from sync.service import enqueue
                    enqueue("sales_invoice", shift_id, "create", {"item_ids": item_ids})
                except Exception:
                    pass

            # ── Cloud cleanup: delete individual pos, keep shift invoices only ─
            try:
                from sync.service import (
                    is_configured, _url, _headers, BRANCH_ID
                )
                import requests as _req

                if is_configured() and invoice_ids:
                    ids_csv = ",".join(invoice_ids)
                    _req.delete(
                        f"{_url('stock_movements_central')}?reference_id=in.({ids_csv})&branch_id=eq.{BRANCH_ID}",
                        headers=_headers(), timeout=20,
                    )
                    _req.delete(
                        f"{_url('sales_invoice_items_central')}?invoice_id=in.({ids_csv})",
                        headers=_headers(), timeout=20,
                    )
                    _req.delete(
                        f"{_url('sales_invoices_central')}?id=in.({ids_csv})&branch_id=eq.{BRANCH_ID}",
                        headers=_headers(), timeout=20,
                    )
            except Exception:
                pass  # Cloud cleanup is best-effort; local state is already correct

            return count, str(filepath)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def get_warehouses() -> list[tuple[str, str]]:
        init_db()
        session = get_session()
        try:
            return [
                (w.id, w.name)
                for w in session.query(Warehouse).order_by(Warehouse.name).all()
            ]
        finally:
            session.close()
