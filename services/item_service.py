"""
Item service — all business logic for the Stock module.
"""
from dataclasses import dataclass, field
from database.engine import get_session, init_db
from database.models.items import Item, ItemBarcode, ItemPrice, ItemStock, Category, Brand, Warehouse, Setting


@dataclass
class ItemRow:
    """Flat DTO used in list views — no lazy loading."""
    id: str
    code: str
    name: str
    barcode: str
    category: str
    cost: float
    cost_currency: str
    price: float
    price_currency: str
    stock: float
    is_active: bool
    is_pos_featured: bool
    is_featured: bool = False


@dataclass
class ItemDetail:
    id: str
    code: str
    name: str
    name_ar: str
    category_id: str
    category_name: str
    brand_id: str
    brand_name: str
    unit: str
    pack_size: int
    cost_price: float
    cost_currency: str
    vat_rate: float
    min_stock: float
    is_active: bool
    is_pos_featured: bool
    is_online: bool
    is_visible: bool
    notes: str
    show_on_touch: bool = False
    photo_url: str = ""
    barcodes: list = field(default_factory=list)   # list of (id, barcode, is_primary, pack_qty)
    prices: list   = field(default_factory=list)   # list of (id, type, amount, currency, is_default)
    stock_entries: list = field(default_factory=list)  # list of (warehouse, qty)


class ItemService:

    @staticmethod
    def search_items(query: str = "", category_id: str = "",
                     active_only: bool = False, limit: int = 500, offset: int = 0,
                     name_query: str = "", code_query: str = "", barcode_query: str = "") -> list[ItemRow]:
        init_db()
        session = get_session()
        try:
            q = session.query(
                Item.id, Item.code, Item.name,
                Item.cost_price, Item.cost_currency,
                Item.is_active, Item.is_pos_featured,
                Item.is_featured,
                Category.name.label("category_name"),
            ).outerjoin(Category, Item.category_id == Category.id)

            if active_only:
                q = q.filter(Item.is_active == True)
            if category_id:
                q = q.filter(Item.category_id == category_id)

            # Specific field filters take priority over the combined query
            if name_query:
                q = q.filter(Item.name.ilike(f"%{name_query}%"))
            elif code_query:
                q = q.filter(Item.code.ilike(f"%{code_query}%"))
            elif barcode_query:
                barcode_ids = session.query(ItemBarcode.item_id).filter(
                    ItemBarcode.barcode.ilike(f"{barcode_query}%")
                ).scalar_subquery()
                q = q.filter(Item.id.in_(barcode_ids))
            elif query:
                like = f"%{query}%"
                barcode_ids = session.query(ItemBarcode.item_id).filter(
                    ItemBarcode.barcode.ilike(like)
                ).scalar_subquery()
                q = q.filter(
                    Item.name.ilike(like) |
                    Item.code.ilike(like) |
                    Item.id.in_(barcode_ids)
                )

            q = q.order_by(Item.name).limit(limit).offset(offset)
            rows = q.all()

            # Fetch primary barcodes and default prices in bulk
            item_ids = [r.id for r in rows]
            barcodes = {}
            if item_ids:
                for b in session.query(ItemBarcode).filter(
                    ItemBarcode.item_id.in_(item_ids), ItemBarcode.is_primary == True
                ).all():
                    barcodes[b.item_id] = b.barcode

            prices = {}
            if item_ids:
                for p in session.query(ItemPrice).filter(
                    ItemPrice.item_id.in_(item_ids),
                    ItemPrice.is_default == True,
                    ItemPrice.price_type == "retail",
                ).all():
                    prices[p.item_id] = (p.amount, p.currency)

            result = []
            for r in rows:
                bc = barcodes.get(r.id, "")
                pr, pc = prices.get(r.id, (0.0, "USD"))
                result.append(ItemRow(
                    id=r.id, code=r.code, name=r.name,
                    barcode=bc, category=r.category_name or "",
                    cost=r.cost_price, cost_currency=r.cost_currency,
                    price=pr, price_currency=pc,
                    stock=0.0,
                    is_active=r.is_active, is_pos_featured=r.is_pos_featured,
                    is_featured=getattr(r, "is_featured", False) or False,
                ))
            return result
        finally:
            session.close()

    @staticmethod
    def get_item_detail(item_id: str) -> ItemDetail | None:
        init_db()
        session = get_session()
        try:
            item = session.query(Item).filter_by(id=item_id).first()
            if not item:
                return None
            cat = session.query(Category).filter_by(id=item.category_id).first() if item.category_id else None
            brand = session.query(Brand).filter_by(id=item.brand_id).first() if item.brand_id else None
            barcodes = [(b.id, b.barcode, b.is_primary, b.pack_qty)
                        for b in session.query(ItemBarcode).filter_by(item_id=item_id).all()]
            prices = [(p.id, p.price_type, p.amount, p.currency, p.is_default, getattr(p, "pack_qty", 1))
                      for p in session.query(ItemPrice).filter_by(item_id=item_id).all()]
            stock_entries = []
            for s in session.query(ItemStock).filter_by(item_id=item_id).all():
                wh = session.query(Warehouse).filter_by(id=s.warehouse_id).first()
                stock_entries.append((wh.name if wh else "?", s.quantity))

            return ItemDetail(
                id=item.id, code=item.code, name=item.name,
                name_ar=item.name_ar or "",
                category_id=item.category_id or "",
                category_name=cat.name if cat else "",
                brand_id=item.brand_id or "",
                brand_name=brand.name if brand else "",
                unit=item.unit, pack_size=item.pack_size,
                cost_price=item.cost_price, cost_currency=item.cost_currency,
                vat_rate=item.vat_rate, min_stock=item.min_stock,
                is_active=item.is_active, is_pos_featured=item.is_pos_featured,
                is_online=item.is_online, is_visible=item.is_visible,
                show_on_touch=getattr(item, "show_on_touch", False),
                photo_url=item.photo_url or "",
                notes=item.notes or "",
                barcodes=barcodes, prices=prices, stock_entries=stock_entries,
            )
        finally:
            session.close()

    @staticmethod
    def get_categories() -> list[tuple[str, str, str | None, bool, bool, str, bool, bool]]:
        """Returns list of (id, name, parent_id, show_in_daily, show_on_touch, photo_url, show_on_home, is_active)."""
        init_db()
        session = get_session()
        try:
            return [(c.id, c.name, c.parent_id, c.show_in_daily,
                     getattr(c, "show_on_touch", False), getattr(c, "photo_url", "") or "",
                     getattr(c, "show_on_home", False), getattr(c, "is_active", True))
                    for c in session.query(Category).order_by(Category.name).all()]
        finally:
            session.close()

    @staticmethod
    def get_brands() -> list[tuple[str, str]]:
        init_db()
        session = get_session()
        try:
            return [(b.id, b.name) for b in session.query(Brand).order_by(Brand.name).all()]
        finally:
            session.close()

    @staticmethod
    def get_warehouses() -> list[tuple[str, str, bool, int | None, str | None]]:
        """Returns (id, name, is_default, number, default_customer_id)."""
        init_db()
        session = get_session()
        try:
            return [(w.id, w.name, w.is_default, w.number, w.default_customer_id)
                    for w in session.query(Warehouse).order_by(Warehouse.name).all()]
        finally:
            session.close()

    @staticmethod
    def save_item(detail: ItemDetail) -> tuple[bool, str]:
        """Insert or update an item. Returns (success, error)."""
        init_db()
        session = get_session()
        try:
            item = session.query(Item).filter_by(id=detail.id).first()
            if not item:
                from database.models.base import new_uuid
                item = Item(id=detail.id if detail.id else new_uuid())
                session.add(item)

            item.code         = detail.code.strip()
            item.name         = detail.name.strip()
            item.name_ar      = detail.name_ar.strip() or None
            item.category_id  = detail.category_id or None
            item.brand_id     = detail.brand_id or None
            item.unit         = detail.unit
            item.pack_size    = detail.pack_size
            item.cost_price   = detail.cost_price
            item.cost_currency = detail.cost_currency
            item.vat_rate     = detail.vat_rate
            item.min_stock    = detail.min_stock
            item.is_active    = detail.is_active
            item.is_pos_featured = detail.is_pos_featured
            item.is_online    = detail.is_online
            item.is_visible   = detail.is_visible
            item.show_on_touch = detail.show_on_touch
            item.photo_url    = detail.photo_url or None
            item.notes        = detail.notes or None

            session.flush()

            # Update prices — find by id first, then by (type, pack_qty), then insert
            from database.models.base import new_uuid
            for price_tuple in detail.prices:
                pid, ptype, amount, currency, is_default = price_tuple[:5]
                p_pack_qty = price_tuple[5] if len(price_tuple) > 5 else 1
                price_obj = (
                    session.query(ItemPrice).filter_by(id=pid).first()
                    if pid else
                    session.query(ItemPrice).filter_by(
                        item_id=item.id, price_type=ptype, pack_qty=p_pack_qty
                    ).first()
                )
                if price_obj:
                    price_obj.amount   = amount
                    price_obj.currency = currency
                    price_obj.pack_qty = p_pack_qty
                else:
                    session.add(ItemPrice(
                        id=new_uuid(), item_id=item.id,
                        price_type=ptype, amount=amount,
                        currency=currency, is_default=is_default,
                        pack_qty=p_pack_qty,
                    ))

            # Update barcodes — (bc_id, barcode, is_primary, pack_qty)
            if detail.barcodes:
                from database.models.base import new_uuid
                submitted_ids = set()
                for bc_id, barcode, is_primary, pack_qty in detail.barcodes:
                    if not barcode.strip():
                        continue
                    if bc_id:
                        bc_obj = session.query(ItemBarcode).filter_by(id=bc_id).first()
                        if bc_obj:
                            bc_obj.barcode   = barcode.strip()
                            bc_obj.is_primary = is_primary
                            bc_obj.pack_qty  = pack_qty
                            submitted_ids.add(bc_id)
                            continue
                    # Check if barcode string already exists for this item
                    bc_obj = session.query(ItemBarcode).filter_by(
                        item_id=item.id, barcode=barcode.strip()
                    ).first()
                    if bc_obj:
                        bc_obj.is_primary = is_primary
                        bc_obj.pack_qty   = pack_qty
                        submitted_ids.add(bc_obj.id)
                    else:
                        new_id = new_uuid()
                        session.add(ItemBarcode(
                            id=new_id, item_id=item.id,
                            barcode=barcode.strip(),
                            is_primary=is_primary,
                            pack_qty=pack_qty,
                        ))
                        submitted_ids.add(new_id)

                # Remove barcodes that were deleted from the table
                for existing in session.query(ItemBarcode).filter_by(item_id=item.id).all():
                    if existing.id not in submitted_ids:
                        session.delete(existing)

            session.commit()

            # Enqueue sync to central (main branch only — branches don't push items)
            try:
                from config import IS_MAIN_BRANCH
                from sync.service import enqueue, is_configured
                if IS_MAIN_BRANCH and is_configured():
                    enqueue("item", item.id, "upsert", {})
            except Exception:
                pass

            return True, ""
        except Exception as exc:
            session.rollback()
            return False, str(exc)
        finally:
            session.close()

    @staticmethod
    def set_featured(item_id: str, featured: bool) -> tuple[bool, str]:
        init_db()
        session = get_session()
        try:
            item = session.query(Item).filter_by(id=item_id).first()
            if not item:
                return False, "Item not found."
            item.is_featured = featured
            session.commit()
            return True, ""
        except Exception as exc:
            session.rollback()
            return False, str(exc)
        finally:
            session.close()

    @staticmethod
    def toggle_active(item_id: str) -> tuple[bool, str]:
        init_db()
        session = get_session()
        try:
            item = session.query(Item).filter_by(id=item_id).first()
            if not item:
                return False, "Item not found."
            item.is_active = not item.is_active
            session.commit()
            return True, ""
        except Exception as exc:
            session.rollback()
            return False, str(exc)
        finally:
            session.close()

    @staticmethod
    def get_touch_categories() -> list[dict]:
        """Return active categories flagged show_on_touch, ordered by sort_order then name."""
        init_db()
        session = get_session()
        try:
            rows = (
                session.query(Category)
                .filter_by(is_active=True, show_on_touch=True)
                .order_by(Category.sort_order, Category.name)
                .all()
            )
            return [{"id": c.id, "name": c.name} for c in rows]
        finally:
            session.close()

    @staticmethod
    def get_touch_items(category_id: str) -> list[dict]:
        """Return active items in a category with their default LBP selling price."""
        from database.models.items import Item, ItemPrice
        init_db()
        session = get_session()
        try:
            items = (
                session.query(Item)
                .filter_by(category_id=category_id, is_active=True, show_on_touch=True)
                .order_by(Item.name)
                .all()
            )
            item_ids = [i.id for i in items]
            # Fetch default prices (prefer LBP retail, fallback to any retail)
            prices: dict[str, dict] = {}
            if item_ids:
                for p in (
                    session.query(ItemPrice)
                    .filter(
                        ItemPrice.item_id.in_(item_ids),
                        ItemPrice.is_active == True,
                        ItemPrice.price_type == "retail",
                    )
                    .all()
                ):
                    existing = prices.get(p.item_id)
                    if existing is None or p.is_default:
                        prices[p.item_id] = {"amount": p.amount, "currency": p.currency}
            result = []
            for item in items:
                p = prices.get(item.id, {"amount": 0.0, "currency": "USD"})
                result.append({
                    "item_id":  item.id,
                    "code":     item.code,
                    "name":     item.name,
                    "name_ar":  item.name_ar or "",
                    "price":    p["amount"],
                    "currency": p["currency"],
                })
            return result
        finally:
            session.close()

    @staticmethod
    def save_category(cat_id: str, name: str, parent_id: str = "",
                      show_in_daily: bool = False,
                      show_on_touch: bool = False,
                      photo_url: str = "",
                      show_on_home: bool = False,
                      is_active: bool = True) -> tuple[bool, str]:
        init_db()
        session = get_session()
        try:
            cat = session.query(Category).filter_by(id=cat_id).first() if cat_id else None
            if not cat:
                from database.models.base import new_uuid
                cat = Category(id=new_uuid())
                session.add(cat)
            cat.name          = name.strip()
            cat.parent_id     = parent_id or None
            cat.show_in_daily = show_in_daily
            cat.show_on_touch = show_on_touch
            cat.photo_url     = photo_url or None
            cat.show_on_home  = show_on_home
            cat.is_active     = is_active
            session.commit()

            sync_err = ""
            try:
                from config import IS_MAIN_BRANCH
                from sync.service import push_categories, is_configured
                if IS_MAIN_BRANCH and is_configured():
                    ok2, sync_err = push_categories()
            except Exception as e:
                sync_err = str(e)

            return True, sync_err  # (saved locally; sync error surfaced as warning)
        except Exception as exc:
            session.rollback()
            return False, str(exc)
        finally:
            session.close()

    @staticmethod
    def save_brand(brand_id: str, name: str) -> tuple[bool, str]:
        init_db()
        session = get_session()
        try:
            brand = session.query(Brand).filter_by(id=brand_id).first() if brand_id else None
            if not brand:
                from database.models.base import new_uuid
                brand = Brand(id=new_uuid())
                session.add(brand)
            brand.name = name.strip()
            session.commit()
            return True, ""
        except Exception as exc:
            session.rollback()
            return False, str(exc)
        finally:
            session.close()

    @staticmethod
    def save_warehouse(wh_id: str, name: str, location: str, is_default: bool,
                       number: int | None = None,
                       default_customer_id: str | None = None) -> tuple[bool, str]:
        init_db()
        session = get_session()
        try:
            wh = session.query(Warehouse).filter_by(id=wh_id).first() if wh_id else None
            if not wh:
                from database.models.base import new_uuid
                wh = Warehouse(id=new_uuid())
                session.add(wh)
            wh.name = name.strip()
            wh.location = location.strip() or None
            wh.number = number
            wh.default_customer_id = default_customer_id or None
            if is_default:
                session.query(Warehouse).filter(Warehouse.id != wh.id).update({"is_default": False})
            wh.is_default = is_default
            session.commit()
            return True, ""
        except Exception as exc:
            session.rollback()
            return False, str(exc)
        finally:
            session.close()

    @staticmethod
    def get_item_stock_movements(item_id: str, limit: int = 200):
        """Returns recent stock movements for the stock card."""
        init_db()
        session = get_session()
        try:
            from database.models.stock import StockMovement
            rows = session.query(StockMovement).filter_by(item_id=item_id)\
                .order_by(StockMovement.created_at.desc()).limit(limit).all()
            result = []
            for r in rows:
                wh = session.query(Warehouse).filter_by(id=r.warehouse_id).first()
                result.append({
                    "date": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
                    "type": r.movement_type,
                    "qty": r.quantity,
                    "warehouse": wh.name if wh else "?",
                    "reference": r.reference_type or "",
                    "notes": r.notes or "",
                })
            return result
        finally:
            session.close()

    @staticmethod
    def count_items(query: str = "", category_id: str = "",
                    name_query: str = "", code_query: str = "", barcode_query: str = "") -> int:
        init_db()
        session = get_session()
        try:
            q = session.query(Item)
            if category_id:
                q = q.filter(Item.category_id == category_id)
            if name_query:
                q = q.filter(Item.name.ilike(f"%{name_query}%"))
            elif code_query:
                q = q.filter(Item.code.ilike(f"%{code_query}%"))
            elif barcode_query:
                barcode_ids = session.query(ItemBarcode.item_id).filter(
                    ItemBarcode.barcode.ilike(f"{barcode_query}%")
                ).scalar_subquery()
                q = q.filter(Item.id.in_(barcode_ids))
            elif query:
                like = f"%{query}%"
                q = q.filter(Item.name.ilike(like) | Item.code.ilike(like))
            return q.count()
        finally:
            session.close()
