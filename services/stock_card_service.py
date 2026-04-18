"""Stock Card service — rich movement history for a single item."""
from datetime import datetime, timezone
from database.engine import get_session, init_db


class StockCardService:

    @staticmethod
    def find_item(query: str) -> dict | None:
        """Search by barcode (exact), code (exact), then name/code partial."""
        init_db()
        session = get_session()
        try:
            from database.models.items import Item, ItemBarcode
            # 1. Exact barcode (trim stored value to handle accidental spaces)
            from sqlalchemy import func as sa_func
            bc = session.query(ItemBarcode).filter(
                sa_func.trim(ItemBarcode.barcode).ilike(query)
            ).first()
            if bc:
                item = session.query(Item).filter_by(id=bc.item_id).first()
                if item:
                    return {"id": item.id, "code": item.code, "name": item.name, "barcode": query}
            # 2. Exact code
            item = session.query(Item).filter(Item.code == query).first()
            if item:
                bc2 = session.query(ItemBarcode).filter_by(item_id=item.id, is_primary=True).first()
                return {"id": item.id, "code": item.code, "name": item.name,
                        "barcode": bc2.barcode if bc2 else ""}
            # 3. Partial name / code
            item = session.query(Item).filter(
                Item.name.ilike(f"%{query}%") | Item.code.ilike(f"%{query}%")
            ).first()
            if item:
                bc2 = session.query(ItemBarcode).filter_by(item_id=item.id, is_primary=True).first()
                return {"id": item.id, "code": item.code, "name": item.name,
                        "barcode": bc2.barcode if bc2 else ""}
            return None
        finally:
            session.close()

    @staticmethod
    def get_stock_card(item_id: str, date_from: str, date_to: str,
                       warehouse_id: str = "") -> dict:
        """
        Returns a dict with opening_qty, opening_value, movements list, and totals.
        date_from / date_to: 'YYYY-MM-DD' strings (inclusive).
        """
        init_db()
        session = get_session()
        try:
            from database.models.stock import StockMovement
            from database.models.items import Warehouse
            from database.models.invoices import (
                SalesInvoice, SalesInvoiceItem,
                PurchaseInvoice, PurchaseInvoiceItem,
            )
            from database.models.parties import Customer, Supplier
            from database.models.users import User

            dt_from = datetime.strptime(date_from, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=timezone.utc)
            dt_to   = datetime.strptime(date_to, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc)

            base = session.query(StockMovement).filter(
                StockMovement.item_id == item_id
            )
            if warehouse_id:
                base = base.filter(StockMovement.warehouse_id == warehouse_id)

            # Opening: sum of all movements before date_from
            opening_rows = base.filter(StockMovement.created_at < dt_from).all()
            opening_qty_from_mvs = sum(r.quantity for r in opening_rows)
            opening_value = sum(abs(r.quantity) * r.unit_cost for r in opening_rows)

            # Period movements
            period_rows = base.filter(
                StockMovement.created_at >= dt_from,
                StockMovement.created_at <= dt_to,
            ).order_by(StockMovement.created_at).all()

            # Opening balance = sum of all movements before the period.
            # This is purely movement-based so it is never distorted by
            # an out-of-sync ItemStock value.
            opening_qty = opening_qty_from_mvs

            # Current stock: prefer live ItemStock for the top-bar display,
            # fall back to running total from movements.
            from database.models.items import ItemStock
            from sqlalchemy import func as _fn
            if warehouse_id:
                _s = session.query(ItemStock).filter_by(
                    item_id=item_id, warehouse_id=warehouse_id
                ).first()
                actual_stock = _s.quantity if _s else None
            else:
                actual_stock = session.query(_fn.sum(ItemStock.quantity)).filter_by(
                    item_id=item_id
                ).scalar()

            # ── Pre-fetch reference data ────────────────────────────────────
            sale_ids  = [r.reference_id for r in period_rows
                         if r.reference_type == "sales_invoice"   and r.reference_id]
            purch_ids = [r.reference_id for r in period_rows
                         if r.reference_type == "purchase_invoice" and r.reference_id]
            inv_sess_ids = [r.reference_id for r in period_rows
                            if r.reference_type == "inventory" and r.reference_id]

            # Sales invoices
            sales_inv = {}
            if sale_ids:
                for inv in session.query(SalesInvoice).filter(
                        SalesInvoice.id.in_(sale_ids)).all():
                    cust = session.query(Customer).filter_by(id=inv.customer_id).first()
                    op   = session.query(User).filter_by(id=inv.operator_id).first()
                    sales_inv[inv.id] = {
                        "inv_no":   inv.invoice_number,
                        "party":    cust.name if cust else "",
                        "cashier":  op.full_name if op else "",
                    }

            # Sales invoice line for this item
            sale_line = {}   # invoice_id → (unit_price, disc_pct, line_total)
            if sale_ids:
                for si in session.query(SalesInvoiceItem).filter(
                        SalesInvoiceItem.invoice_id.in_(sale_ids),
                        SalesInvoiceItem.item_id == item_id).all():
                    sale_line[si.invoice_id] = (si.unit_price, si.discount_pct, si.line_total)

            # Purchase invoices
            purch_inv = {}
            if purch_ids:
                for inv in session.query(PurchaseInvoice).filter(
                        PurchaseInvoice.id.in_(purch_ids)).all():
                    sup = session.query(Supplier).filter_by(id=inv.supplier_id).first()
                    op  = session.query(User).filter_by(id=inv.operator_id).first()
                    purch_inv[inv.id] = {
                        "inv_no":  inv.invoice_number,
                        "party":   sup.name if sup else "",
                        "cashier": op.full_name if op else "",
                    }

            # Purchase invoice line for this item
            purch_line = {}
            if purch_ids:
                for pi in session.query(PurchaseInvoiceItem).filter(
                        PurchaseInvoiceItem.invoice_id.in_(purch_ids),
                        PurchaseInvoiceItem.item_id == item_id).all():
                    purch_line[pi.invoice_id] = (pi.unit_cost, pi.discount_pct, pi.line_total)

            # Inventory sessions
            inv_sess_map: dict[str, str] = {}   # session_id → session_number
            if inv_sess_ids:
                try:
                    from database.models.inventory import InventorySession
                    for inv in session.query(InventorySession).filter(
                            InventorySession.id.in_(inv_sess_ids)).all():
                        inv_sess_map[inv.id] = inv.session_number or inv.id[:8]
                except Exception:
                    pass

            # Warehouse name cache
            wh_cache: dict[str, str] = {}
            def wh_name(wid: str) -> str:
                if wid not in wh_cache:
                    w = session.query(Warehouse).filter_by(id=wid).first()
                    wh_cache[wid] = w.name if w else "?"
                return wh_cache[wid]

            # ── Build rows ──────────────────────────────────────────────────
            movements  = []
            running    = opening_qty
            stock_in   = 0.0;  value_in  = 0.0
            stock_out  = 0.0;  value_out = 0.0

            for mv in period_rows:
                qty    = mv.quantity
                running += qty

                inv_no  = ""
                price   = 0.0
                disc    = 0.0
                total   = 0.0
                party   = ""
                cashier = ""
                label   = mv.movement_type.replace("_", " ").title()

                ref_id = mv.reference_id or ""

                if mv.reference_type == "sales_invoice" and ref_id in sales_inv:
                    d      = sales_inv[ref_id]
                    inv_no = d["inv_no"]
                    party  = d["party"]
                    cashier= d["cashier"]
                    label  = "Sales"
                    if ref_id in sale_line:
                        price, disc, total = sale_line[ref_id]
                        total = abs(total)

                elif mv.reference_type == "purchase_invoice" and ref_id in purch_inv:
                    d      = purch_inv[ref_id]
                    inv_no = d["inv_no"]
                    party  = d["party"]
                    cashier= d["cashier"]
                    label  = "Purchase"
                    if ref_id in purch_line:
                        price, disc, total = purch_line[ref_id]
                        total = abs(total)
                elif mv.reference_type == "inventory":
                    inv_no = inv_sess_map.get(ref_id, ref_id[:8] if ref_id else "")
                    label  = "Inventory"
                    price  = mv.unit_cost
                    if mv.operator_id:
                        op = session.query(User).filter_by(id=mv.operator_id).first()
                        cashier = op.full_name if op else ""
                else:
                    if mv.operator_id:
                        op = session.query(User).filter_by(id=mv.operator_id).first()
                        cashier = op.full_name if op else ""
                    price = mv.unit_cost

                # Totals
                if qty > 0:
                    stock_in  += qty
                    value_in  += total if total else qty * mv.unit_cost
                else:
                    stock_out += abs(qty)
                    value_out += total if total else abs(qty) * mv.unit_cost

                # If reference exists but invoice wasn't found (deleted/not synced),
                # show a short identifier so the row isn't completely anonymous
                display_inv_no = inv_no
                if not display_inv_no and ref_id and mv.reference_type in ("sales_invoice", "purchase_invoice"):
                    display_inv_no = f"[{ref_id[:8]}]"

                movements.append({
                    "date":          mv.created_at.strftime("%Y-%m-%d %H:%M") if mv.created_at else "",
                    "trans":         label,
                    "invoice_no":    display_inv_no,
                    "qty":           qty,
                    "price":         price,
                    "disc_pct":      disc,
                    "total":         total,
                    "warehouse":     wh_name(mv.warehouse_id),
                    "party":         party,
                    "cashier":       cashier,
                    "running_stock": running,
                    "movement_type": mv.movement_type,
                    "ref_type":      mv.reference_type or "",
                    "ref_id":        ref_id,
                    "inv_found":     bool(inv_no),   # True = invoice exists in DB
                })

            return {
                "opening_qty":   opening_qty,
                "opening_value": opening_value,
                "movements":     movements,
                "stock_in":      stock_in,
                "value_in":      value_in,
                "stock_out":     stock_out,
                "value_out":     value_out,
                "current_stock": running,
            }
        finally:
            session.close()
