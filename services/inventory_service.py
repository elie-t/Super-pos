"""
Inventory Service — queries current stock levels with flexible filtering.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class InventoryRow:
    item_id:        str
    code:           str
    name:           str
    barcode:        str
    pack_size:      int
    category:       str
    subgroup:       str       # parent category name
    brand:          str
    supplier:       str
    qty_pcs:        float
    cost:           float
    cost_currency:  str
    price:          float
    price_currency: str
    price_type:     str


class InventoryService:

    @staticmethod
    def get_lbp_rate() -> int:
        from database.engine import get_session, init_db
        from database.models.base import Setting
        init_db()
        session = get_session()
        try:
            s = session.get(Setting, "lbp_rate")
            return int(s.value) if s else 90_000
        except Exception:
            return 90_000
        finally:
            session.close()

    @staticmethod
    def get_filter_options():
        """Return (warehouses, categories, brands, suppliers) for combo population."""
        from database.engine import get_session, init_db
        from database.models.items import Category, Brand, Warehouse
        from database.models.parties import Supplier
        init_db()
        session = get_session()
        try:
            warehouses = [(w.id, w.name) for w in
                          session.query(Warehouse).filter_by(is_active=True).order_by(Warehouse.name).all()]
            # Groups = top-level categories (no parent)
            groups = [(c.id, c.name) for c in
                      session.query(Category).filter(Category.parent_id.is_(None))
                      .order_by(Category.name).all()]
            # Subgroups = categories that have a parent
            subgroups = [(c.id, c.name, c.parent_id) for c in
                         session.query(Category).filter(Category.parent_id.isnot(None))
                         .order_by(Category.name).all()]
            brands = [(b.id, b.name) for b in
                      session.query(Brand).order_by(Brand.name).all()]
            suppliers = [(s.id, s.name) for s in
                         session.query(Supplier).filter_by(is_active=True).order_by(Supplier.name).all()]
            return warehouses, groups, subgroups, brands, suppliers
        finally:
            session.close()

    @staticmethod
    def run_inventory(
        *,
        warehouse_id:    str   = "",
        barcode:         str   = "",
        name_contains:   str   = "",
        group_id:        str   = "",
        subgroup_id:     str   = "",
        brand_id:        str   = "",
        supplier_id:     str   = "",
        price_type:      str   = "individual",
        currency:        str   = "USD",
        active_filter:   str   = "active",   # active | inactive | all
        with_zeros:      bool  = False,
        unit_mode:       str   = "pcs",      # pcs | boxes
    ) -> list[InventoryRow]:
        from database.engine import get_session, init_db
        from database.models.items import Item, ItemBarcode, ItemPrice, ItemStock, Category, Brand
        from database.models.parties import Supplier
        from sqlalchemy import func as sa_func, and_, or_

        init_db()
        session = get_session()
        try:
            lbp_rate = InventoryService.get_lbp_rate()

            # ── Base query ────────────────────────────────────────────────────
            q = session.query(Item)

            # Active filter
            if active_filter == "active":
                q = q.filter(Item.is_active == True)
            elif active_filter == "inactive":
                q = q.filter(Item.is_active == False)

            # Name / barcode filter
            if barcode.strip():
                bc_sub = session.query(ItemBarcode.item_id).filter(
                    sa_func.lower(sa_func.trim(ItemBarcode.barcode)).ilike(barcode.strip().lower())
                ).subquery()
                q = q.filter(Item.id.in_(bc_sub))
            if name_contains.strip():
                pat = f"%{name_contains.strip()}%"
                q = q.filter(or_(Item.name.ilike(pat), Item.code.ilike(pat)))

            # Category / group filter
            if subgroup_id:
                q = q.filter(Item.category_id == subgroup_id)
            elif group_id:
                # group itself or any of its children
                child_ids = [r[0] for r in
                             session.query(Category.id)
                             .filter(Category.parent_id == group_id).all()]
                q = q.filter(or_(
                    Item.category_id == group_id,
                    Item.category_id.in_(child_ids),
                ))

            if brand_id:
                q = q.filter(Item.brand_id == brand_id)
            if supplier_id:
                q = q.filter(Item.default_supplier_id == supplier_id)

            items = q.order_by(Item.name).all()
            item_ids = [i.id for i in items]
            if not item_ids:
                return []

            # ── Bulk-load related data ─────────────────────────────────────
            # Primary barcodes
            bc_rows = session.query(ItemBarcode).filter(
                ItemBarcode.item_id.in_(item_ids),
                ItemBarcode.is_primary == True,
            ).all()
            primary_bc: dict[str, str] = {b.item_id: b.barcode for b in bc_rows}
            pack_bc: dict[str, int] = {b.item_id: b.pack_qty for b in bc_rows}

            # Prices for requested type
            price_rows = session.query(ItemPrice).filter(
                ItemPrice.item_id.in_(item_ids),
                ItemPrice.price_type == price_type,
            ).all()
            price_map: dict[str, tuple[float, str]] = {}
            for p in price_rows:
                price_map[p.item_id] = (p.amount, p.currency)

            # Stock per warehouse (or summed across all)
            if warehouse_id:
                stock_rows = session.query(ItemStock).filter(
                    ItemStock.item_id.in_(item_ids),
                    ItemStock.warehouse_id == warehouse_id,
                ).all()
            else:
                stock_rows = session.query(ItemStock).filter(
                    ItemStock.item_id.in_(item_ids),
                ).all()

            stock_map: dict[str, float] = {}
            for s in stock_rows:
                stock_map[s.item_id] = stock_map.get(s.item_id, 0.0) + s.quantity

            # Categories
            cat_ids = list({i.category_id for i in items if i.category_id})
            cats = {c.id: c for c in session.query(Category)
                    .filter(Category.id.in_(cat_ids)).all()} if cat_ids else {}

            # Brands
            brand_ids = list({i.brand_id for i in items if i.brand_id})
            brands = {b.id: b.name for b in session.query(Brand)
                      .filter(Brand.id.in_(brand_ids)).all()} if brand_ids else {}

            # Suppliers
            sup_ids = list({i.default_supplier_id for i in items if i.default_supplier_id})
            sups = {s.id: s.name for s in session.query(Supplier)
                    .filter(Supplier.id.in_(sup_ids)).all()} if sup_ids else {}

            # ── Build rows ────────────────────────────────────────────────────
            rows: list[InventoryRow] = []
            for item in items:
                qty_pcs = stock_map.get(item.id, 0.0)

                if not with_zeros and qty_pcs == 0.0:
                    continue

                # Category / subgroup
                cat_obj = cats.get(item.category_id)
                if cat_obj:
                    if cat_obj.parent_id:
                        subgroup_name = cat_obj.name
                        parent_cat = cats.get(cat_obj.parent_id)
                        group_name = parent_cat.name if parent_cat else ""
                    else:
                        group_name = cat_obj.name
                        subgroup_name = ""
                else:
                    group_name = subgroup_name = ""

                # Price
                p_amount, p_currency = price_map.get(item.id, (0.0, "USD"))

                # Convert to requested currency
                def to_currency(amount, src_currency):
                    if currency == src_currency:
                        return amount
                    if currency == "LBP" and src_currency == "USD":
                        return amount * lbp_rate
                    if currency == "USD" and src_currency == "LBP":
                        return amount / lbp_rate if lbp_rate else 0.0
                    return amount

                cost_disp = to_currency(item.cost_price or 0.0, item.cost_currency or "USD")
                price_disp = to_currency(p_amount, p_currency)

                rows.append(InventoryRow(
                    item_id        = item.id,
                    code           = item.code or "",
                    name           = item.name or "",
                    barcode        = primary_bc.get(item.id, ""),
                    pack_size      = pack_bc.get(item.id, item.pack_size or 1),
                    category       = group_name,
                    subgroup       = subgroup_name,
                    brand          = brands.get(item.brand_id, ""),
                    supplier       = sups.get(item.default_supplier_id, ""),
                    qty_pcs        = qty_pcs,
                    cost           = round(cost_disp, 2),
                    cost_currency  = currency,
                    price          = round(price_disp, 2),
                    price_currency = currency,
                    price_type     = price_type,
                ))

            return rows

        finally:
            session.close()
