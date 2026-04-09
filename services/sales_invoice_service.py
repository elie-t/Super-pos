"""Manual Sales Invoice service — back-office sales that deduct from warehouse stock."""
from dataclasses import dataclass, field
from database.engine import get_session, init_db


@dataclass
class SalesLineItem:
    item_id:     str
    code:        str
    barcode:     str
    description: str
    pack_qty:    int        # units per pack for the scanned barcode
    qty:         float      # total units
    price:       float      # unit selling price
    disc_pct:    float
    vat_pct:     float
    total:       float
    # Info
    stock_units: float = 0.0
    price_lbp:   float = 0.0
    subgroup:    str   = ""
    cost:        float = 0.0


class SalesInvoiceService:

    @staticmethod
    def next_invoice_number(warehouse_id: str = "") -> str:
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
            s = session.get(Setting, key)
            seq = int(s.value) if s else 1
            return str(wh_num * 10000 + seq)
        finally:
            session.close()

    @staticmethod
    def increment_invoice_number(warehouse_id: str = ""):
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
            s = session.get(Setting, key)
            if s:
                s.value = str(int(s.value) + 1)
                session.commit()
            else:
                from database.models.base import new_uuid
                session.add(Setting(key=key, value="2"))
                session.commit()
        finally:
            session.close()

    @staticmethod
    def lookup_item(query: str, warehouse_id: str = "",
                    search_by: str = "barcode", currency: str = "LBP") -> "SalesLineItem | None":
        """Find item by barcode/code/name, return a SalesLineItem with selling price."""
        init_db()
        session = get_session()
        try:
            from database.models.items import Item, ItemBarcode, ItemPrice, ItemStock, Category

            item = None
            barcode_str = ""

            if search_by == "barcode":
                bc = (
                    session.query(ItemBarcode)
                    .filter(ItemBarcode.barcode == query)
                    .first()
                )
                if bc:
                    item = session.query(Item).filter_by(id=bc.item_id, is_active=True).first()
                    barcode_str = bc.barcode
            else:
                item = (
                    session.query(Item)
                    .filter(Item.is_active == True)
                    .filter(Item.code.ilike(f"%{query}%") | Item.name.ilike(f"%{query}%"))
                    .first()
                )
                if item:
                    bc = session.query(ItemBarcode).filter_by(
                        item_id=item.id, is_primary=True
                    ).first()
                    barcode_str = bc.barcode if bc else ""

            if not item:
                return None

            # pack_qty: find any barcode of this item with pack_qty > 1
            box_bc = session.query(ItemBarcode).filter(
                ItemBarcode.item_id == item.id,
                ItemBarcode.pack_qty > 1,
            ).first()
            pack_qty = box_bc.pack_qty if box_bc else (item.pack_size if item.pack_size and item.pack_size > 1 else 1)

            # Category (subgroup)
            cat = session.query(Category).filter_by(id=item.category_id).first() if item.category_id else None
            subgroup = cat.name if cat else ""

            # Stock for the selected warehouse
            stock_units = 0.0
            if warehouse_id:
                stock = session.query(ItemStock).filter_by(
                    item_id=item.id, warehouse_id=warehouse_id
                ).first()
                stock_units = stock.quantity if stock else 0.0
            else:
                # sum all warehouses
                from sqlalchemy import func
                total = session.query(func.sum(ItemStock.quantity)).filter_by(
                    item_id=item.id
                ).scalar()
                stock_units = total or 0.0

            # Selling price — prefer 'individual' then 'retail' in requested currency
            price = 0.0
            price_lbp = 0.0
            prices = session.query(ItemPrice).filter_by(
                item_id=item.id, is_active=True
            ).all()

            def _find(ptype, cur):
                return next((p.amount for p in prices
                             if p.price_type == ptype and p.currency == cur), None)

            if currency == "LBP":
                price = (_find("individual", "LBP")
                         or _find("retail", "LBP")
                         or 0.0)
                price_lbp = price
            else:
                price = (_find("individual", "USD")
                         or _find("retail", "USD")
                         or 0.0)
                price_lbp = _find("individual", "LBP") or _find("retail", "LBP") or 0.0

            return SalesLineItem(
                item_id=item.id,
                code=item.code,
                barcode=barcode_str,
                description=item.name,
                pack_qty=pack_qty,
                qty=float(pack_qty),
                price=price,
                disc_pct=0.0,
                vat_pct=item.vat_rate * 100,
                total=price * pack_qty,
                stock_units=stock_units,
                price_lbp=price_lbp,
                subgroup=subgroup,
                cost=item.cost_price or 0.0,
            )
        finally:
            session.close()

    @staticmethod
    def save_invoice(
        customer_id: str, operator_id: str, warehouse_id: str,
        invoice_number: str, invoice_date: str,
        currency: str, lines: list[SalesLineItem],
        payment_mode: str, notes: str,
    ) -> tuple[bool, str]:
        init_db()
        session = get_session()
        try:
            from database.models.invoices import SalesInvoice, SalesInvoiceItem
            from database.models.stock import StockMovement
            from database.models.items import ItemStock
            from database.models.base import new_uuid

            subtotal = sum(l.total for l in lines)
            inv = SalesInvoice(
                id=new_uuid(),
                invoice_number=invoice_number,
                customer_id=customer_id,
                operator_id=operator_id,
                warehouse_id=warehouse_id,
                invoice_date=invoice_date,
                invoice_type="sale",
                source="manual",
                subtotal=subtotal,
                discount_value=0.0,
                vat_value=0.0,
                total=subtotal,
                currency=currency,
                status="finalized",
                payment_status="unpaid" if payment_mode == "account" else "paid",
                amount_paid=subtotal if payment_mode != "account" else 0.0,
                notes=notes or None,
                is_archived=False,
            )
            session.add(inv)
            session.flush()

            for line in lines:
                session.add(SalesInvoiceItem(
                    id=new_uuid(),
                    invoice_id=inv.id,
                    item_id=line.item_id,
                    item_name=line.description,
                    barcode=line.barcode,
                    quantity=line.qty,
                    unit_price=line.price,
                    currency=currency,
                    discount_pct=line.disc_pct,
                    vat_pct=line.vat_pct,
                    line_total=line.total,
                ))

                # Stock movement (sale = negative)
                session.add(StockMovement(
                    id=new_uuid(),
                    item_id=line.item_id,
                    warehouse_id=warehouse_id,
                    movement_type="sale",
                    quantity=-line.qty,
                    unit_cost=line.price,
                    cost_currency=currency,
                    reference_type="sales_invoice",
                    reference_id=inv.id,
                    operator_id=operator_id,
                ))

                # Deduct ItemStock cache
                stock = session.query(ItemStock).filter_by(
                    item_id=line.item_id, warehouse_id=warehouse_id
                ).first()
                if stock:
                    stock.quantity -= line.qty
                else:
                    stock = ItemStock(
                        id=new_uuid(),
                        item_id=line.item_id,
                        warehouse_id=warehouse_id,
                        quantity=-line.qty,
                    )
                    session.add(stock)

            session.commit()
            SalesInvoiceService.increment_invoice_number(warehouse_id)
            try:
                from sync.service import enqueue
                item_ids = [l.item_id for l in lines]
                enqueue("sales_invoice", inv.id, "create", {"item_ids": item_ids})
            except Exception:
                pass
            return True, inv.id
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            session.close()

    @staticmethod
    def search_items(query: str = "", warehouse_id: str = "", limit: int = 80) -> list[dict]:
        """Items matching query, sorted by sales frequency."""
        init_db()
        session = get_session()
        try:
            from database.models.items import Item, ItemBarcode, ItemPrice, ItemStock
            from database.models.stock import StockMovement
            from sqlalchemy import func

            usage_sub = (
                session.query(
                    StockMovement.item_id,
                    func.count(StockMovement.id).label("cnt"),
                )
                .filter(StockMovement.movement_type == "sale")
                .group_by(StockMovement.item_id)
                .subquery()
            )

            q = (
                session.query(Item, usage_sub.c.cnt)
                .outerjoin(usage_sub, Item.id == usage_sub.c.item_id)
                .filter(Item.is_active == True)
            )

            if query:
                like = f"%{query}%"
                bc_ids = (
                    session.query(ItemBarcode.item_id)
                    .filter(ItemBarcode.barcode.ilike(like))
                    .scalar_subquery()
                )
                q = q.filter(
                    Item.name.ilike(like)
                    | Item.code.ilike(like)
                    | Item.id.in_(bc_ids)
                )

            q = q.order_by(
                func.coalesce(usage_sub.c.cnt, 0).desc(),
                Item.name,
            ).limit(limit)

            rows = q.all()
            item_ids = [r.Item.id for r in rows]

            # primary barcodes
            bc_map = {}
            for bc in session.query(ItemBarcode).filter(
                ItemBarcode.item_id.in_(item_ids), ItemBarcode.is_primary == True
            ).all():
                bc_map[bc.item_id] = bc

            # stock per warehouse
            stock_map: dict[str, float] = {}
            if warehouse_id:
                for st in session.query(ItemStock).filter(
                    ItemStock.item_id.in_(item_ids),
                    ItemStock.warehouse_id == warehouse_id,
                ).all():
                    stock_map[st.item_id] = st.quantity
            else:
                for item_id, total in session.query(
                    ItemStock.item_id, func.sum(ItemStock.quantity)
                ).filter(ItemStock.item_id.in_(item_ids)).group_by(ItemStock.item_id).all():
                    stock_map[item_id] = total or 0.0

            # selling prices (LBP individual or retail)
            price_lbp_map: dict[str, float] = {}
            for p in session.query(ItemPrice).filter(
                ItemPrice.item_id.in_(item_ids),
                ItemPrice.is_active == True,
                ItemPrice.currency == "LBP",
            ).all():
                if p.item_id not in price_lbp_map or p.price_type == "individual":
                    price_lbp_map[p.item_id] = p.amount

            result = []
            for r, cnt in rows:
                bc = bc_map.get(r.id)
                result.append({
                    "item_id":  r.id,
                    "code":     r.code,
                    "name":     r.name,
                    "barcode":  bc.barcode if bc else "",
                    "pack_qty": (bc.pack_qty or 1) if bc else 1,
                    "price_lbp": price_lbp_map.get(r.id, 0.0),
                    "stock":    stock_map.get(r.id, 0.0),
                    "vat_pct":  r.vat_rate * 100,
                    "usage":    cnt or 0,
                })
            return result
        finally:
            session.close()

    @staticmethod
    def list_invoices(limit: int = 300, date_from: str = "", date_to: str = "") -> list[dict]:
        """All sales invoices (manual + pos_shift), newest first."""
        init_db()
        session = get_session()
        try:
            from database.models.invoices import SalesInvoice
            from database.models.parties import Customer
            from database.models.items import Warehouse
            from database.models.users import User

            q = (
                session.query(SalesInvoice, Customer.name, Warehouse.name,
                              Warehouse.number, User.full_name)
                .outerjoin(Customer,  SalesInvoice.customer_id  == Customer.id)
                .outerjoin(Warehouse, SalesInvoice.warehouse_id == Warehouse.id)
                .outerjoin(User,      SalesInvoice.operator_id  == User.id)
                .filter(SalesInvoice.invoice_type == "sale")
                .filter(SalesInvoice.source.in_(["manual", "pos_shift"]))
            )
            if date_from:
                q = q.filter(SalesInvoice.invoice_date >= date_from)
            if date_to:
                q = q.filter(SalesInvoice.invoice_date <= date_to)
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
                    "status":         inv.status,
                    "payment_status": inv.payment_status,
                    "lines":          len(inv.items),
                    "source":         inv.source,
                    "notes":          inv.notes or "",
                    "warehouse_name": wh_name or "",
                    "warehouse_num":  wh_num if wh_num is not None else "",
                    "cashier":        cashier or "",
                }
                for inv, cust_name, wh_name, wh_num, cashier in rows
            ]
        finally:
            session.close()

    @staticmethod
    def get_invoice(invoice_id: str) -> dict | None:
        """Load a full sales invoice with its line items."""
        init_db()
        session = get_session()
        try:
            from database.models.invoices import SalesInvoice, SalesInvoiceItem
            from database.models.parties import Customer
            from database.models.items import Warehouse
            from database.models.users import User

            inv = session.query(SalesInvoice).filter_by(id=invoice_id).first()
            if not inv:
                return None
            cust = session.query(Customer).filter_by(id=inv.customer_id).first() if inv.customer_id else None
            wh   = session.query(Warehouse).filter_by(id=inv.warehouse_id).first() if inv.warehouse_id else None
            op   = session.query(User).filter_by(id=inv.operator_id).first() if inv.operator_id else None
            lines = session.query(SalesInvoiceItem).filter_by(invoice_id=invoice_id).all()
            wh_num = wh.number if wh and wh.number is not None else ""
            return {
                "id":             inv.id,
                "invoice_number": inv.invoice_number,
                "source":         inv.source,
                "customer_id":    inv.customer_id or "",
                "customer_name":  cust.name if cust else "Walk-In",
                "warehouse_id":   inv.warehouse_id or "",
                "warehouse_name": wh.name if wh else "",
                "warehouse_num":  wh_num,
                "cashier":        op.full_name if op else "",
                "invoice_date":   inv.invoice_date or "",
                "currency":       inv.currency,
                "total":          inv.total,
                "subtotal":       inv.subtotal,
                "discount_value": inv.discount_value,
                "vat_value":      inv.vat_value,
                "payment_status": inv.payment_status,
                "amount_paid":    inv.amount_paid,
                "notes":          inv.notes or "",
                "lines": [
                    {
                        "item_id":       li.item_id,
                        "item_name":     li.item_name,
                        "barcode":       li.barcode or "",
                        "qty":           li.quantity,
                        "price":         li.unit_price,
                        "disc_pct":      li.discount_pct,
                        "vat_pct":       li.vat_pct,
                        "total":         li.line_total,
                        "currency":      li.currency,
                        "warehouse_num": wh_num,
                    }
                    for li in lines
                ],
            }
        finally:
            session.close()

    @staticmethod
    def delete_invoice(invoice_id: str, operator_id: str = "") -> tuple[bool, str]:
        """Cancel a sales invoice and restore stock."""
        init_db()
        session = get_session()
        try:
            from database.models.invoices import SalesInvoice, SalesInvoiceItem
            from database.models.stock import StockMovement
            from database.models.items import ItemStock
            from database.models.base import new_uuid

            inv = session.query(SalesInvoice).filter_by(id=invoice_id).first()
            if not inv:
                return False, "Invoice not found"
            if inv.status == "cancelled":
                return False, "Invoice is already cancelled"

            lines = session.query(SalesInvoiceItem).filter_by(invoice_id=invoice_id).all()
            for li in lines:
                session.add(StockMovement(
                    id=new_uuid(),
                    item_id=li.item_id,
                    warehouse_id=inv.warehouse_id,
                    movement_type="cancellation",
                    quantity=li.quantity,
                    unit_cost=li.unit_price,
                    cost_currency=inv.currency,
                    reference_type="sales_invoice",
                    reference_id=inv.id,
                    operator_id=operator_id or None,
                ))
                stock = session.query(ItemStock).filter_by(
                    item_id=li.item_id, warehouse_id=inv.warehouse_id
                ).first()
                if stock:
                    stock.quantity += li.quantity

            inv.status = "cancelled"
            inv.payment_status = "cancelled"
            session.commit()
            return True, ""
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            session.close()

    @staticmethod
    def list_customers(query: str = "") -> list[dict]:
        init_db()
        session = get_session()
        try:
            from database.models.parties import Customer
            q = session.query(Customer).filter(Customer.is_active == True)
            if query:
                like = f"%{query}%"
                q = q.filter(Customer.name.ilike(like) | Customer.phone.ilike(like))
            return [
                {"id": c.id, "name": c.name, "phone": c.phone or "", "balance": c.balance}
                for c in q.order_by(Customer.name).limit(60).all()
            ]
        finally:
            session.close()
