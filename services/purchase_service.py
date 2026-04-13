"""Purchase invoice service."""
from dataclasses import dataclass, field
from database.engine import get_session, init_db


@dataclass
class PurchaseInvoiceRow:
    id: str
    invoice_number: str
    supplier_name: str
    invoice_date: str
    total: float
    currency: str
    status: str
    payment_status: str


@dataclass
class PurchaseLineItem:
    item_id: str
    code: str
    barcode: str
    description: str
    pack_qty: int        # units per box for the scanned barcode
    box_qty: float
    pcs_qty: float
    price: float
    disc_pct: float
    vat_pct: float
    total: float
    # Info panel data
    stock_units: float = 0.0
    stock_packs: float = 0.0
    last_cost: float = 0.0
    last_cost_currency: str = "USD"
    avg_cost: float = 0.0
    subgroup: str = ""
    brand: str = ""
    sales_prices: list = field(default_factory=list)


class PurchaseService:

    @staticmethod
    def next_invoice_number(warehouse_id: str = "") -> str:
        """Returns the next invoice number for the given warehouse.
        Format: wh_num * 10000 + seq  (e.g. warehouse 2 → 20001, 20002…)
        Falls back to global sequence when no warehouse or no number assigned."""
        init_db()
        session = get_session()
        try:
            from database.models.items import Setting, Warehouse
            wh_num = None
            if warehouse_id:
                wh = session.query(Warehouse).filter_by(id=warehouse_id).first()
                wh_num = wh.number if wh else None

            if wh_num is not None:
                key = f"next_purchase_number_wh{wh_num}"
                s = session.get(Setting, key)
                seq = int(s.value) if s else 1
                return str(wh_num * 10000 + seq)
            else:
                s = session.get(Setting, "next_purchase_number")
                num = int(s.value) if s else 1
                return f"PI{num:05d}"
        finally:
            session.close()

    @staticmethod
    def increment_invoice_number(warehouse_id: str = ""):
        init_db()
        session = get_session()
        try:
            from database.models.items import Setting, Warehouse
            wh_num = None
            if warehouse_id:
                wh = session.query(Warehouse).filter_by(id=warehouse_id).first()
                wh_num = wh.number if wh else None

            if wh_num is not None:
                key = f"next_purchase_number_wh{wh_num}"
                s = session.get(Setting, key)
                if s:
                    s.value = str(int(s.value) + 1)
                else:
                    from database.models.items import Setting as S
                    session.add(S(key=key, value="2"))
            else:
                s = session.get(Setting, "next_purchase_number")
                if s:
                    s.value = str(int(s.value) + 1)
            session.commit()
        finally:
            session.close()

    @staticmethod
    def lookup_item(query: str, search_by: str = "barcode") -> PurchaseLineItem | None:
        """Find an item by barcode, code, name or ref and return a line item DTO."""
        init_db()
        session = get_session()
        try:
            from database.models.items import Item, ItemBarcode, ItemPrice, ItemStock, Category
            from database.models.stock import StockMovement

            item = None
            matched_bc = None   # the exact barcode row that was scanned
            if search_by == "barcode":
                bc = session.query(ItemBarcode).filter(
                    ItemBarcode.barcode.ilike(query.strip())
                ).first()
                if bc:
                    item = session.query(Item).filter_by(id=bc.item_id).first()
                    matched_bc = bc
            elif search_by == "code":
                item = session.query(Item).filter(Item.code.ilike(query.strip())).first()
            else:
                item = session.query(Item).filter(Item.name.ilike(f"%{query.strip()}%")).first()

            if not item:
                return None

            # Primary barcode (for display); if we matched by barcode, show that one
            if matched_bc:
                barcode = matched_bc.barcode
            else:
                bc_obj = session.query(ItemBarcode).filter_by(item_id=item.id, is_primary=True).first()
                barcode = bc_obj.barcode if bc_obj else ""

            # Category
            cat = session.query(Category).filter_by(id=item.category_id).first() if item.category_id else None

            # Stock
            from database.models.items import ItemStock, Warehouse
            stock = session.query(ItemStock).filter_by(item_id=item.id).first()
            stock_units = stock.quantity if stock else 0.0
            stock_packs = round(stock_units / item.pack_size, 2) if item.pack_size > 1 else stock_units

            # Last cost from movements
            last_mv = session.query(StockMovement).filter_by(
                item_id=item.id, movement_type="purchase"
            ).order_by(StockMovement.created_at.desc()).first()
            last_cost = last_mv.unit_cost if last_mv else item.cost_price
            # Determine currency of last cost from the purchase invoice it came from
            last_cost_currency = "USD"
            if last_mv and last_mv.reference_id:
                from database.models.invoices import PurchaseInvoice
                ref_inv = session.query(PurchaseInvoice).filter_by(id=last_mv.reference_id).first()
                if ref_inv:
                    last_cost_currency = ref_inv.currency or "USD"

            # Selling prices
            prices = session.query(ItemPrice).filter_by(item_id=item.id).all()
            sales_prices = [(p.price_type, p.amount, p.currency) for p in prices]

            # pack_qty: item-level check — does this item have any box barcode?
            # Always stop at Box if the item has a barcode with pack_qty > 1,
            # regardless of which specific barcode was scanned.
            box_bc = session.query(ItemBarcode).filter(
                ItemBarcode.item_id == item.id,
                ItemBarcode.pack_qty > 1,
            ).first()
            pack_qty = box_bc.pack_qty if box_bc else (item.pack_size if item.pack_size and item.pack_size > 1 else 1)

            return PurchaseLineItem(
                item_id=item.id,
                code=item.code,
                barcode=barcode,
                description=item.name,
                pack_qty=pack_qty,
                box_qty=0,
                pcs_qty=1,
                price=last_cost,
                disc_pct=0.0,
                vat_pct=item.vat_rate * 100,
                total=last_cost,
                stock_units=stock_units,
                stock_packs=stock_packs,
                last_cost=last_cost,
                last_cost_currency=last_cost_currency,
                avg_cost=item.cost_price,
                subgroup=cat.name if cat else "",
                brand="",
                sales_prices=sales_prices,
            )
        finally:
            session.close()

    @staticmethod
    def get_invoice(invoice_id: str) -> dict | None:
        """Load a full invoice with all line items for display/edit."""
        init_db()
        session = get_session()
        try:
            from database.models.invoices import PurchaseInvoice, PurchaseInvoiceItem
            from database.models.items import Item, ItemBarcode
            from database.models.parties import Supplier

            inv = session.query(PurchaseInvoice).filter_by(id=invoice_id).first()
            if not inv:
                return None

            sup = session.query(Supplier).filter_by(id=inv.supplier_id).first() if inv.supplier_id else None

            lines = []
            for li in session.query(PurchaseInvoiceItem).filter_by(invoice_id=inv.id).all():
                item = session.query(Item).filter_by(id=li.item_id).first()
                bc = session.query(ItemBarcode).filter_by(
                    item_id=li.item_id, is_primary=True
                ).first()
                lines.append({
                    "item_id":     li.item_id,
                    "code":        item.code if item else "",
                    "barcode":     bc.barcode if bc else "",
                    "description": li.item_name,
                    "pack_qty":    li.pack_size or 1,
                    "box":         li.pack_size or 0,
                    "pcs":         li.quantity,
                    "price":       li.unit_cost,
                    "disc":        li.discount_pct,
                    "vat":         li.vat_pct * 100,
                    "total":       li.line_total,
                    "last_cost":   li.unit_cost,
                    "vat_pct":     li.vat_pct * 100,
                })

            return {
                "id":             inv.id,
                "invoice_number": inv.invoice_number,
                "supplier_id":    inv.supplier_id or "",
                "supplier_name":  sup.name if sup else "",
                "supplier":       sup,
                "date":           inv.invoice_date or "",
                "currency":       inv.currency,
                "warehouse_id":   inv.warehouse_id or "",
                "order_number":   inv.order_number or "",
                "notes":          inv.notes or "",
                "payment_status": inv.payment_status,
                "lines":          lines,
            }
        finally:
            session.close()

    @staticmethod
    def save_invoice(
        supplier_id: str, operator_id: str, warehouse_id: str,
        invoice_number: str, invoice_date: str, due_date: str, order_number: str,
        currency: str, lines: list[PurchaseLineItem],
        payment_mode: str, notes: str,
        invoice_id: str | None = None,
    ) -> tuple[bool, str]:
        init_db()
        session = get_session()
        try:
            from database.models.invoices import PurchaseInvoice, PurchaseInvoiceItem
            from database.models.stock import StockMovement
            from database.models.items import ItemStock
            from database.models.base import new_uuid
            from datetime import datetime, timezone

            subtotal = sum(l.total for l in lines)

            # ── Edit existing invoice ──────────────────────────────────────────
            if invoice_id:
                inv = session.get(PurchaseInvoice, invoice_id)
                if inv:
                    # Reverse old stock movements and wipe old line items
                    old_lines = session.query(PurchaseInvoiceItem).filter_by(invoice_id=invoice_id).all()
                    for old_li in old_lines:
                        mv = session.query(StockMovement).filter_by(
                            reference_type="purchase_invoice",
                            reference_id=invoice_id,
                            item_id=old_li.item_id,
                        ).first()
                        if mv:
                            # Reverse stock
                            stock = session.query(ItemStock).filter_by(
                                item_id=old_li.item_id,
                                warehouse_id=inv.warehouse_id,
                            ).first()
                            if stock:
                                stock.quantity = max(0.0, stock.quantity - old_li.quantity)
                        session.delete(old_li)
                    session.query(StockMovement).filter_by(
                        reference_type="purchase_invoice",
                        reference_id=invoice_id,
                    ).delete()
                    session.flush()
                    # Update header fields
                    inv.supplier_id    = supplier_id
                    inv.operator_id    = operator_id
                    inv.warehouse_id   = warehouse_id
                    inv.invoice_date   = invoice_date
                    inv.due_date       = due_date
                    inv.order_number   = order_number or None
                    inv.subtotal       = subtotal
                    inv.total          = subtotal
                    inv.currency       = currency
                    inv.notes          = notes or None
                    session.flush()
                else:
                    invoice_id = None  # fall through to create new

            # ── Create new invoice ─────────────────────────────────────────────
            if not invoice_id:
                inv = PurchaseInvoice(
                    id=new_uuid(),
                    invoice_number=invoice_number,
                    supplier_id=supplier_id,
                    operator_id=operator_id,
                    warehouse_id=warehouse_id,
                    invoice_date=invoice_date,
                    due_date=due_date,
                    order_number=order_number or None,
                    invoice_type="purchase",
                    subtotal=subtotal,
                    total=subtotal,
                    currency=currency,
                    status="finalized",
                    payment_status="unpaid" if payment_mode == "account" else "paid",
                    notes=notes or None,
                )
                session.add(inv)
                session.flush()

            for line in lines:
                # When buying by box, line.price is per-box price.
                # Store unit_cost per piece so last_cost is correct on next purchase.
                unit_cost = (
                    line.price / line.pack_qty
                    if (line.pack_qty > 1 and line.box_qty > 0 and line.pack_qty)
                    else line.price
                )
                li = PurchaseInvoiceItem(
                    id=new_uuid(),
                    invoice_id=inv.id,
                    item_id=line.item_id,
                    item_name=line.description,
                    quantity=line.pcs_qty,
                    pack_size=int(line.box_qty) if line.box_qty else 1,
                    unit_cost=unit_cost,
                    currency=currency,
                    discount_pct=line.disc_pct,
                    vat_pct=line.vat_pct / 100.0,
                    line_total=line.total,
                )
                session.add(li)

                # Stock movement
                mv = StockMovement(
                    id=new_uuid(),
                    item_id=line.item_id,
                    warehouse_id=warehouse_id,
                    movement_type="purchase",
                    quantity=line.pcs_qty,
                    unit_cost=unit_cost,
                    cost_currency=currency,
                    reference_type="purchase_invoice",
                    reference_id=inv.id,
                    operator_id=operator_id,
                )
                session.add(mv)

                # Update ItemStock cache
                stock = session.query(ItemStock).filter_by(
                    item_id=line.item_id, warehouse_id=warehouse_id
                ).first()
                if stock:
                    stock.quantity += line.pcs_qty
                else:
                    stock = ItemStock(
                        id=new_uuid(),
                        item_id=line.item_id,
                        warehouse_id=warehouse_id,
                        quantity=line.pcs_qty,
                    )
                    session.add(stock)

            session.commit()
            PurchaseService.increment_invoice_number(warehouse_id)

            # Sync to central
            try:
                from sync.service import (
                    push_stock_movements_for_invoice,
                    push_purchase_invoice,
                    is_configured,
                )
                if is_configured():
                    push_stock_movements_for_invoice(inv.id)
                    push_purchase_invoice(inv.id)
            except Exception:
                pass

            return True, inv.id
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            session.close()

    @staticmethod
    def search_items_by_usage(query: str = "", limit: int = 80) -> list[dict]:
        """Items matching query, sorted by purchase frequency (most used first)."""
        init_db()
        session = get_session()
        try:
            from database.models.items import Item, ItemBarcode, ItemPrice, Category
            from database.models.stock import StockMovement
            from sqlalchemy import func

            usage_sub = (
                session.query(
                    StockMovement.item_id,
                    func.count(StockMovement.id).label("cnt"),
                )
                .filter(StockMovement.movement_type == "purchase")
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

            # bulk-fetch primary barcodes and last costs
            item_ids = [r.Item.id for r in rows]
            bc_map = {}
            for bc in session.query(ItemBarcode).filter(
                ItemBarcode.item_id.in_(item_ids), ItemBarcode.is_primary == True
            ).all():
                bc_map[bc.item_id] = bc

            result = []
            for r, cnt in rows:
                bc = bc_map.get(r.id)
                result.append({
                    "item_id":   r.id,
                    "code":      r.code,
                    "name":      r.name,
                    "barcode":   bc.barcode if bc else "",
                    "pack_qty":  (bc.pack_qty or 1) if bc else 1,
                    "cost":      r.cost_price,
                    "vat_pct":   r.vat_rate * 100,
                    "usage":     cnt or 0,
                })
            return result
        finally:
            session.close()

    @staticmethod
    def list_invoices(limit: int = 300) -> list[dict]:
        """All purchase invoices, newest first."""
        init_db()
        session = get_session()
        try:
            from database.models.invoices import PurchaseInvoice
            from database.models.parties import Supplier
            rows = (
                session.query(PurchaseInvoice, Supplier.name)
                .outerjoin(Supplier, PurchaseInvoice.supplier_id == Supplier.id)
                .order_by(PurchaseInvoice.invoice_date.desc(),
                          PurchaseInvoice.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id":             inv.id,
                    "invoice_number": inv.invoice_number,
                    "supplier":       sup_name or "—",
                    "date":           inv.invoice_date or "",
                    "total":          inv.total,
                    "currency":       inv.currency,
                    "payment_status": inv.payment_status,
                    "lines":          len(inv.items),
                }
                for inv, sup_name in rows
            ]
        finally:
            session.close()

    @staticmethod
    def mark_paid(invoice_id: str) -> tuple[bool, str]:
        """Set payment_status = 'paid' on a purchase invoice."""
        init_db()
        session = get_session()
        try:
            from database.models.invoices import PurchaseInvoice
            inv = session.get(PurchaseInvoice, invoice_id)
            if not inv:
                return False, "Invoice not found."
            inv.payment_status = "paid"
            session.commit()
            return True, ""
        except Exception as exc:
            session.rollback()
            return False, str(exc)
        finally:
            session.close()

    @staticmethod
    def mark_unpaid(invoice_id: str) -> tuple[bool, str]:
        """Set payment_status = 'unpaid' on a purchase invoice."""
        init_db()
        session = get_session()
        try:
            from database.models.invoices import PurchaseInvoice
            inv = session.get(PurchaseInvoice, invoice_id)
            if not inv:
                return False, "Invoice not found."
            inv.payment_status = "unpaid"
            session.commit()
            return True, ""
        except Exception as exc:
            session.rollback()
            return False, str(exc)
        finally:
            session.close()

    @staticmethod
    def delete_invoice(invoice_id: str) -> tuple[bool, str]:
        """Delete a purchase invoice and all its lines from local DB and Supabase."""
        init_db()
        session = get_session()
        try:
            from database.models.invoices import PurchaseInvoice, PurchaseInvoiceItem
            session.query(PurchaseInvoiceItem).filter_by(invoice_id=invoice_id).delete()
            inv = session.get(PurchaseInvoice, invoice_id)
            if not inv:
                return False, "Invoice not found."
            session.delete(inv)
            session.commit()
        except Exception as exc:
            session.rollback()
            return False, str(exc)
        finally:
            session.close()

        # Delete from Supabase
        try:
            from sync.service import _headers, _url, is_configured
            import requests
            if is_configured():
                requests.delete(
                    f"{_url('purchase_invoice_items_central')}?invoice_id=eq.{invoice_id}",
                    headers=_headers(), timeout=15,
                )
                requests.delete(
                    f"{_url('purchase_invoices_central')}?id=eq.{invoice_id}",
                    headers=_headers(), timeout=15,
                )
        except Exception:
            pass  # Local delete succeeded; Supabase failure is non-fatal

        return True, ""

    @staticmethod
    def get_invoice_pricing_data(invoice_id: str) -> list[dict]:
        """Items from a saved invoice + their current selling prices for the pricing review."""
        init_db()
        session = get_session()
        try:
            from database.models.invoices import PurchaseInvoice, PurchaseInvoiceItem
            from database.models.items import Item, ItemPrice

            inv = session.query(PurchaseInvoice).filter_by(id=invoice_id).first()
            if not inv:
                return []

            result = []
            for li in session.query(PurchaseInvoiceItem).filter_by(invoice_id=invoice_id).all():
                item = session.query(Item).filter_by(id=li.item_id).first()
                prices = session.query(ItemPrice).filter_by(item_id=li.item_id).all()
                price_map = {
                    p.price_type: {"id": p.id, "amount": p.amount, "currency": p.currency}
                    for p in prices
                }
                cost_usd = li.unit_cost if inv.currency == "USD" else li.unit_cost / 89500.0
                result.append({
                    "item_id":      li.item_id,
                    "code":         item.code if item else "",
                    "description":  li.item_name,
                    "cost":         li.unit_cost,
                    "inv_currency": inv.currency,
                    "cost_usd":     cost_usd,
                    "prices":       price_map,
                })
            return result
        finally:
            session.close()

    @staticmethod
    def save_pricing_updates(updates: list[dict]) -> tuple[bool, str]:
        """
        Save selling price changes from the pricing review dialog.
        updates = [{"item_id": str, "price_type": str, "amount": float, "currency": str}]
        """
        init_db()
        session = get_session()
        try:
            from database.models.items import ItemPrice
            from database.models.base import new_uuid

            for upd in updates:
                # Prefer lookup by exact price_id (avoids duplicate-row ambiguity)
                pid = upd.get("price_id", "")
                if pid:
                    p = session.query(ItemPrice).filter_by(id=pid).first()
                else:
                    p = session.query(ItemPrice).filter_by(
                        item_id=upd["item_id"], price_type=upd["price_type"]
                    ).first()
                if p:
                    p.amount   = upd["amount"]
                    p.currency = upd["currency"]
                else:
                    session.add(ItemPrice(
                        id=new_uuid(),
                        item_id=upd["item_id"],
                        price_type=upd["price_type"],
                        amount=upd["amount"],
                        currency=upd["currency"],
                        is_default=True,
                    ))
            session.commit()
            return True, ""
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            session.close()

    @staticmethod
    def get_supplier_balance(supplier_id: str) -> dict:
        """Return balance info for the supplier balance panel."""
        init_db()
        session = get_session()
        try:
            from database.models.parties import Supplier
            sup = session.query(Supplier).filter_by(id=supplier_id).first()
            if not sup:
                return {}
            return {
                "balance": sup.balance,
                "currency": sup.currency,
            }
        finally:
            session.close()
