"""POS (Point-of-Sale) service — item lookup, sale saving, hold/recall."""
import json
from dataclasses import dataclass, field
from database.engine import get_session, init_db


@dataclass
class PosLineItem:
    item_id:     str
    code:        str
    barcode:     str
    description: str
    qty:         float
    unit_price:  float
    disc_pct:    float
    vat_pct:     float
    total:       float
    currency:    str = "USD"
    price_type:  str = "retail"
    stock_qty:   float = 0.0


class PosService:

    # ── Vegetable / bulk placeholder item ─────────────────────────────────────

    @staticmethod
    def get_or_create_vege_item() -> str:
        """Return the item_id of the Vegetables placeholder, creating it if needed."""
        init_db()
        session = get_session()
        try:
            from database.models.items import Item, ItemBarcode
            from database.models.base import new_uuid

            # Check by code first, then by barcode "V"
            item = session.query(Item).filter_by(code="VEGE").first()
            if not item:
                bc = session.query(ItemBarcode).filter_by(barcode="V").first()
                if bc:
                    item = session.query(Item).filter_by(id=bc.item_id).first()

            if item:
                return item.id

            # Create item
            item_id = new_uuid()
            session.add(Item(
                id=item_id,
                code="VEGE",
                name="Vegetables",
                unit="kg",
                vat_rate=0.0,
                is_active=True,
            ))
            session.flush()

            # Add "V" barcode only if not already present
            if not session.query(ItemBarcode).filter_by(barcode="V").first():
                session.add(ItemBarcode(
                    id=new_uuid(),
                    item_id=item_id,
                    barcode="V",
                    pack_qty=1,
                    is_primary=True,
                ))
            session.commit()
            return item_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── Item lookup ───────────────────────────────────────────────────────────

    @staticmethod
    def lookup_item(query: str, search_by: str = "barcode",
                    currency: str = "USD", price_type: str = "retail") -> PosLineItem | None:
        """Find an item and return its selling price as a POS line-item DTO."""
        init_db()
        session = get_session()
        try:
            from database.models.items import Item, ItemBarcode, ItemPrice, ItemStock

            item = None
            scanned_bc = None

            if search_by == "barcode":
                from sqlalchemy import func as sa_func
                q_stripped = query.strip()
                scanned_bc = session.query(ItemBarcode).filter(
                    sa_func.trim(ItemBarcode.barcode).ilike(q_stripped)
                ).first()
                if scanned_bc:
                    item = session.query(Item).filter_by(id=scanned_bc.item_id).first()
            elif search_by == "code":
                item = session.query(Item).filter(Item.code.ilike(query.strip())).first()
            else:
                item = session.query(Item).filter(
                    Item.name.ilike(f"%{query.strip()}%")
                ).filter(Item.is_active == True).first()

            if not item:
                return None

            # Primary barcode
            bc_obj = session.query(ItemBarcode).filter_by(
                item_id=item.id, is_primary=True
            ).first()

            # Selling price — prefer requested type, fallback to retail, then any
            price_obj = (
                session.query(ItemPrice).filter_by(
                    item_id=item.id, price_type=price_type, currency=currency
                ).first()
                or session.query(ItemPrice).filter_by(
                    item_id=item.id, price_type=price_type
                ).first()
                or session.query(ItemPrice).filter_by(
                    item_id=item.id, price_type="retail"
                ).first()
                or session.query(ItemPrice).filter_by(item_id=item.id).first()
            )
            unit_price = price_obj.amount if price_obj else 0.0
            price_currency = price_obj.currency if price_obj else currency

            # Pack qty — if the scanned barcode represents a multi-pack,
            # set qty to pack_qty so (qty × unit_price) gives the pack total.
            pack_qty = float(scanned_bc.pack_qty) if scanned_bc and scanned_bc.pack_qty > 1 else 1.0

            # Stock
            stock = session.query(ItemStock).filter_by(item_id=item.id).first()
            stock_qty = stock.quantity if stock else 0.0

            return PosLineItem(
                item_id    = item.id,
                code       = item.code,
                barcode    = bc_obj.barcode if bc_obj else (scanned_bc.barcode if scanned_bc else ""),
                description= item.name,
                qty        = pack_qty,
                unit_price = unit_price,
                disc_pct   = 0.0,
                vat_pct    = item.vat_rate * 100,
                total      = unit_price * pack_qty,
                currency   = price_currency,
                price_type = price_type,
                stock_qty  = stock_qty,
            )
        finally:
            session.close()

    # ── Walk-in customer ──────────────────────────────────────────────────────

    @staticmethod
    def get_walk_in_customer_id(warehouse_id: str = "") -> str:
        """Return the default customer for this warehouse, falling back to the
        global is_cash_client customer (creating it if needed)."""
        init_db()
        session = get_session()
        try:
            from database.models.items import Warehouse
            from database.models.parties import Customer
            from database.models.base import new_uuid

            # Prefer warehouse-specific default customer (only if it exists locally)
            if warehouse_id:
                wh = session.query(Warehouse).filter_by(id=warehouse_id).first()
                if wh and wh.default_customer_id:
                    cust = session.query(Customer).filter_by(
                        id=wh.default_customer_id, is_active=True
                    ).first()
                    if cust:
                        return cust.id

            # Fall back to global cash client
            c = session.query(Customer).filter_by(is_cash_client=True).first()
            if c:
                return c.id
            # Create a default walk-in customer
            c = Customer(
                id=new_uuid(),
                name="Walk-In",
                is_cash_client=True,
                is_active=True,
                currency="USD",
                balance=0.0,
            )
            session.add(c)
            session.commit()
            return c.id
        finally:
            session.close()

    # ── Invoice numbering ──────────────────────────────────────────────────────

    @staticmethod
    def next_sale_number(warehouse_id: str = "") -> str:
        """Return the next invoice number for this warehouse.
        Format: wh_number * 10000 + sequence  (e.g. 10001, 30005).
        """
        init_db()
        session = get_session()
        try:
            from database.models.items import Setting, Warehouse
            wh_num = 0
            if warehouse_id:
                wh = session.query(Warehouse).filter_by(id=warehouse_id).first()
                if wh and wh.number is not None:
                    wh_num = wh.number
            key = f"next_sale_number_wh{wh_num}"
            s   = session.get(Setting, key)
            seq = int(s.value) if s else 1
            return str(wh_num * 10000 + seq)
        finally:
            session.close()

    @staticmethod
    def increment_sale_number(warehouse_id: str = ""):
        init_db()
        session = get_session()
        try:
            from database.models.items import Setting, Warehouse
            wh_num = 0
            if warehouse_id:
                wh = session.query(Warehouse).filter_by(id=warehouse_id).first()
                if wh and wh.number is not None:
                    wh_num = wh.number
            key = f"next_sale_number_wh{wh_num}"
            s   = session.get(Setting, key)
            if s:
                s.value = str(int(s.value) + 1)
            else:
                session.add(Setting(key=key, value="2"))
            session.commit()
        finally:
            session.close()

    # ── Save sale ─────────────────────────────────────────────────────────────

    @staticmethod
    def save_sale(
        customer_id: str,
        operator_id: str,
        warehouse_id: str,
        lines: list[PosLineItem],
        currency: str,
        payment_method: str,   # "cash" | "card" | "account"
        amount_paid: float,
        discount_value: float = 0.0,
        notes: str = "",
    ) -> tuple[bool, str]:
        init_db()
        session = get_session()
        try:
            from database.models.invoices import SalesInvoice, SalesInvoiceItem
            from database.models.stock import StockMovement
            from database.models.items import ItemStock
            from database.models.base import new_uuid
            from datetime import date

            subtotal = sum(
                l.qty * l.unit_price * (1 - l.disc_pct / 100)
                for l in lines
            )
            vat_value = sum(
                l.qty * l.unit_price * (1 - l.disc_pct / 100) * (l.vat_pct / 100)
                for l in lines
            )
            total = subtotal + vat_value - discount_value

            payment_status = "paid" if amount_paid >= total else (
                "partial" if amount_paid > 0 else "unpaid"
            )

            sale_no = PosService.next_sale_number(warehouse_id)

            inv = SalesInvoice(
                id             = new_uuid(),
                invoice_number = sale_no,
                customer_id    = customer_id,
                operator_id    = operator_id,
                warehouse_id   = warehouse_id,
                invoice_date   = date.today().isoformat(),
                invoice_type   = "sale",
                source         = "pos",
                subtotal       = subtotal,
                discount_value = discount_value,
                vat_value      = vat_value,
                total          = total,
                currency       = currency,
                status         = "finalized",
                payment_status = payment_status,
                amount_paid    = amount_paid,
                notes          = notes or None,
            )
            session.add(inv)
            session.flush()

            stock_cache: dict = {}  # (item_id, wh_id) → ItemStock object
            for line in lines:
                line_net = line.qty * line.unit_price * (1 - line.disc_pct / 100)
                line_total = line_net * (1 + line.vat_pct / 100)
                li = SalesInvoiceItem(
                    id           = new_uuid(),
                    invoice_id   = inv.id,
                    item_id      = line.item_id,
                    barcode      = line.barcode,
                    item_name    = line.description,
                    quantity     = line.qty,
                    unit_price   = line.unit_price,
                    currency     = line.currency,
                    discount_pct = line.disc_pct,
                    vat_pct      = line.vat_pct / 100.0,
                    line_total   = line_total,
                )
                session.add(li)

                # Vege/bulk placeholder — no stock tracking
                if line.code == "VEGE":
                    continue

                # Stock movement (deduct)
                mv = StockMovement(
                    id             = new_uuid(),
                    item_id        = line.item_id,
                    warehouse_id   = warehouse_id,
                    movement_type  = "sale",
                    quantity       = -line.qty,
                    unit_cost      = line.unit_price,
                    cost_currency  = line.currency,
                    reference_type = "sales_invoice",
                    reference_id   = inv.id,
                    operator_id    = operator_id,
                )
                session.add(mv)

                # Update stock cache — use dict to handle same item appearing multiple times
                key = (line.item_id, warehouse_id)
                if key in stock_cache:
                    stock_cache[key].quantity -= line.qty
                else:
                    stock = session.query(ItemStock).filter_by(
                        item_id=line.item_id, warehouse_id=warehouse_id
                    ).first()
                    if stock:
                        stock.quantity -= line.qty
                    else:
                        stock = ItemStock(
                            id=new_uuid(), item_id=line.item_id,
                            warehouse_id=warehouse_id, quantity=-line.qty,
                        )
                        session.add(stock)
                    stock_cache[key] = stock

            session.commit()
            PosService.increment_sale_number(warehouse_id)

            # Sync to central (best-effort — never block a sale)
            try:
                from sync.service import enqueue, push_stock_movements_for_invoice, is_configured
                item_ids = list({l.item_id for l in lines})
                enqueue("sales_invoice", inv.id, "create", {"item_ids": item_ids})
                if is_configured():
                    push_stock_movements_for_invoice(inv.id)
            except Exception:
                pass

            return True, inv.id
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            session.close()

    # ── Hold / Recall ─────────────────────────────────────────────────────────

    @staticmethod
    def hold_sale(operator_id: str, customer_name: str,
                  lines_json: str, total: float, currency: str,
                  label: str = "") -> tuple[bool, str]:
        init_db()
        session = get_session()
        try:
            from database.models.invoices import HeldInvoice
            from database.models.base import new_uuid

            h = HeldInvoice(
                id=new_uuid(), operator_id=operator_id,
                label=label or customer_name or "Hold",
                items_json=lines_json,
                total=total, currency=currency,
                is_resumed=False,
            )
            session.add(h)
            session.commit()
            return True, h.id
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            session.close()

    @staticmethod
    def list_held_sales() -> list[dict]:
        init_db()
        session = get_session()
        try:
            from database.models.invoices import HeldInvoice
            rows = session.query(HeldInvoice).filter_by(is_resumed=False).order_by(
                HeldInvoice.created_at.desc()
            ).all()
            return [
                {"id": r.id, "label": r.label or "—",
                 "total": r.total, "currency": r.currency,
                 "created_at": str(r.created_at)[:16],
                 "items_json": r.items_json}
                for r in rows
            ]
        finally:
            session.close()

    @staticmethod
    def delete_held_sale(held_id: str):
        init_db()
        session = get_session()
        try:
            from database.models.invoices import HeldInvoice
            h = session.query(HeldInvoice).filter_by(id=held_id).first()
            if h:
                session.delete(h)
                session.commit()
        finally:
            session.close()

    # ── Sales list ────────────────────────────────────────────────────────────

    @staticmethod
    def list_sales(
        limit: int = 300,
        warehouse_id: str = "",
        operator_id: str = "",
    ) -> list[dict]:
        """Return recent POS sales invoices for this branch/cashier, newest first."""
        init_db()
        session = get_session()
        try:
            from database.models.invoices import SalesInvoice, SalesInvoiceItem
            from database.models.parties import Customer
            q = (
                session.query(SalesInvoice, Customer.name)
                .outerjoin(Customer, SalesInvoice.customer_id == Customer.id)
                .filter(
                    SalesInvoice.source == "pos",
                    SalesInvoice.is_archived == False,
                    SalesInvoice.status != "cancelled",
                )
            )
            if warehouse_id:
                q = q.filter(SalesInvoice.warehouse_id == warehouse_id)
            if operator_id:
                q = q.filter(SalesInvoice.operator_id == operator_id)
            rows = (
                q.order_by(SalesInvoice.invoice_date.desc(),
                           SalesInvoice.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id":             inv.id,
                    "invoice_number": inv.invoice_number,
                    "customer":       cust_name or "Walk-In",
                    "date":           inv.invoice_date or "",
                    "total":          inv.total,
                    "currency":       inv.currency,
                    "payment_status": inv.payment_status,
                    "amount_paid":    inv.amount_paid,
                    "warehouse_id":   inv.warehouse_id or "",
                    "lines":          len(inv.items),
                }
                for inv, cust_name in rows
            ]
        finally:
            session.close()

    @staticmethod
    def list_archived_sales(limit: int = 500, date_from: str = "", date_to: str = "") -> list[dict]:
        """Return archived (post-shift) POS sales invoices."""
        init_db()
        session = get_session()
        try:
            from database.models.invoices import SalesInvoice
            from database.models.parties import Customer
            q = (
                session.query(SalesInvoice, Customer.name)
                .outerjoin(Customer, SalesInvoice.customer_id == Customer.id)
                .filter(
                    SalesInvoice.source == "pos",
                    SalesInvoice.is_archived == True,
                )
            )
            if date_from:
                q = q.filter(SalesInvoice.invoice_date >= date_from)
            if date_to:
                q = q.filter(SalesInvoice.invoice_date <= date_to)
            rows = q.order_by(SalesInvoice.invoice_date.desc(),
                              SalesInvoice.created_at.desc()).limit(limit).all()
            return [
                {
                    "id":             inv.id,
                    "invoice_number": inv.invoice_number,
                    "customer":       cust_name or "Walk-In",
                    "date":           inv.invoice_date or "",
                    "total":          inv.total,
                    "currency":       inv.currency,
                    "payment_status": inv.payment_status,
                    "amount_paid":    inv.amount_paid,
                    "lines":          len(inv.items),
                }
                for inv, cust_name in rows
            ]
        finally:
            session.close()

    @staticmethod
    def get_sale_lines(invoice_id: str) -> list[dict]:
        """Return line items for a POS invoice."""
        init_db()
        session = get_session()
        try:
            from database.models.invoices import SalesInvoiceItem
            items = session.query(SalesInvoiceItem).filter_by(invoice_id=invoice_id).all()
            return [
                {
                    "item_id":     li.item_id,
                    "barcode":     li.barcode or "",
                    "description": li.item_name,
                    "qty":         li.quantity,
                    "unit_price":  li.unit_price,
                    "disc_pct":    li.discount_pct,
                    "vat_pct":     li.vat_pct * 100,
                    "total":       li.line_total,
                    "currency":    li.currency,
                }
                for li in items
            ]
        finally:
            session.close()

    @staticmethod
    def cancel_invoice(invoice_id: str, warehouse_id: str, operator_id: str) -> tuple[bool, str]:
        """Cancel a POS invoice: mark cancelled and reverse stock deductions."""
        init_db()
        session = get_session()
        try:
            from database.models.invoices import SalesInvoice, SalesInvoiceItem
            from database.models.items import ItemStock
            from database.models.stock import StockMovement
            from database.models.base import new_uuid

            inv = session.query(SalesInvoice).filter_by(id=invoice_id).first()
            if not inv:
                return False, "Invoice not found."
            if inv.status == "cancelled":
                return False, "Already cancelled."

            lines = session.query(SalesInvoiceItem).filter_by(invoice_id=invoice_id).all()

            for li in lines:
                # Reverse stock movement
                session.add(StockMovement(
                    id=new_uuid(),
                    item_id=li.item_id,
                    warehouse_id=warehouse_id or inv.warehouse_id,
                    movement_type="cancellation",
                    quantity=li.quantity,   # positive = restore
                    unit_cost=li.unit_price,
                    cost_currency=li.currency,
                    reference_type="sales_invoice",
                    reference_id=inv.id,
                    operator_id=operator_id,
                ))
                # Restore ItemStock cache
                stock = session.query(ItemStock).filter_by(
                    item_id=li.item_id,
                    warehouse_id=warehouse_id or inv.warehouse_id,
                ).first()
                if stock:
                    stock.quantity += li.quantity

            inv.status = "cancelled"
            inv.payment_status = "cancelled"
            session.commit()
            return True, inv.invoice_number
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            session.close()

    # ── Receipt data ──────────────────────────────────────────────────────────

    @staticmethod
    def get_invoice_for_print(invoice_id: str) -> dict | None:
        """Return everything needed to render a receipt for a POS invoice."""
        init_db()
        session = get_session()
        try:
            from database.models.invoices import SalesInvoice, SalesInvoiceItem
            from database.models.parties import Customer
            from database.models.users import User
            from database.models.items import Warehouse, Setting

            inv = session.query(SalesInvoice).filter_by(id=invoice_id).first()
            if not inv:
                return None

            customer = session.get(Customer, inv.customer_id)
            operator = session.get(User, inv.operator_id)
            warehouse = session.get(Warehouse, inv.warehouse_id)

            def setting(key, default=""):
                s = session.get(Setting, key)
                return s.value if s else default

            lines = session.query(SalesInvoiceItem).filter_by(invoice_id=invoice_id).all()

            return {
                "invoice_number": inv.invoice_number,
                "date":           inv.invoice_date or "",
                "created_at":     inv.created_at or "",
                "customer":       customer.name if customer else "Walk-In",
                "cashier":        operator.full_name if operator else "",
                "warehouse":      warehouse.name if warehouse else "",
                "subtotal":       inv.subtotal,
                "discount":       inv.discount_value,
                "vat":            inv.vat_value,
                "total":          inv.total,
                "amount_paid":    inv.amount_paid,
                "currency":       inv.currency,
                "payment_status": inv.payment_status,
                "shop_name":      setting("shop_name", "TannouryMarket"),
                "shop_address":   setting("shop_address", ""),
                "shop_phone":     setting("shop_phone", ""),
                "receipt_footer": setting("receipt_footer", "Thank you!"),
                "lines": [
                    {
                        "description": li.item_name,
                        "qty":         li.quantity,
                        "unit_price":  li.unit_price,
                        "disc_pct":    li.discount_pct,
                        "vat_pct":     li.vat_pct * 100,
                        "total":       li.line_total,
                        "currency":    li.currency,
                    }
                    for li in lines
                ],
            }
        finally:
            session.close()

    # ── Customer search ───────────────────────────────────────────────────────

    @staticmethod
    def search_customers(query: str, limit: int = 20) -> list[dict]:
        init_db()
        session = get_session()
        try:
            from database.models.parties import Customer
            like = f"%{query}%"
            rows = session.query(Customer).filter(
                Customer.name.ilike(like), Customer.is_active == True
            ).limit(limit).all()
            return [{"id": r.id, "name": r.name,
                     "phone": getattr(r, "phone", "") or "",
                     "balance": r.balance, "currency": r.currency}
                    for r in rows]
        finally:
            session.close()
