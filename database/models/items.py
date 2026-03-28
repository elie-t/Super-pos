"""
Product / item catalog: categories, brands, warehouses, items, barcodes, prices.
"""
from sqlalchemy import String, Boolean, Float, Integer, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.models.base import Base, TimestampMixin, SyncMixin, new_uuid


# ── Category (flat + self-referential for subcategories) ──────────────────────

class Category(Base, TimestampMixin, SyncMixin):
    __tablename__ = "categories"

    id:             Mapped[str]        = mapped_column(String(36), primary_key=True, default=new_uuid)
    name:           Mapped[str]        = mapped_column(String(100), nullable=False)
    parent_id:      Mapped[str | None] = mapped_column(String(36), ForeignKey("categories.id"), nullable=True)
    sort_order:     Mapped[int]        = mapped_column(Integer, default=0)
    is_active:      Mapped[bool]       = mapped_column(Boolean, default=True)
    show_in_daily:  Mapped[bool]       = mapped_column(Boolean, default=False)

    parent:   Mapped["Category | None"]     = relationship("Category", remote_side="Category.id", back_populates="children")
    children: Mapped[list["Category"]]      = relationship("Category", back_populates="parent")
    items:    Mapped[list["Item"]]          = relationship(back_populates="category")


# ── Brand ─────────────────────────────────────────────────────────────────────

class Brand(Base, TimestampMixin, SyncMixin):
    __tablename__ = "brands"

    id:       Mapped[str]  = mapped_column(String(36), primary_key=True, default=new_uuid)
    name:     Mapped[str]  = mapped_column(String(100), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    items: Mapped[list["Item"]] = relationship(back_populates="brand")


# ── Warehouse ─────────────────────────────────────────────────────────────────

class Warehouse(Base, TimestampMixin, SyncMixin):
    __tablename__ = "warehouses"

    id:                  Mapped[str]        = mapped_column(String(36), primary_key=True, default=new_uuid)
    number:              Mapped[int | None] = mapped_column(Integer, nullable=True)
    name:                Mapped[str]        = mapped_column(String(100), nullable=False, unique=True)
    location:            Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_default:          Mapped[bool]       = mapped_column(Boolean, default=False)
    is_active:           Mapped[bool]       = mapped_column(Boolean, default=True)
    default_customer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("customers.id"), nullable=True)

    stock_entries: Mapped[list["ItemStock"]] = relationship(back_populates="warehouse")


# ── Item (master product record) ──────────────────────────────────────────────

class Item(Base, TimestampMixin, SyncMixin):
    __tablename__ = "items"

    id:                  Mapped[str]       = mapped_column(String(36), primary_key=True, default=new_uuid)
    code:                Mapped[str]       = mapped_column(String(50), unique=True, nullable=False, index=True)
    name:                Mapped[str]       = mapped_column(String(200), nullable=False, index=True)
    name_ar:             Mapped[str | None] = mapped_column(String(200), nullable=True)
    category_id:         Mapped[str | None] = mapped_column(String(36), ForeignKey("categories.id"), nullable=True)
    brand_id:            Mapped[str | None] = mapped_column(String(36), ForeignKey("brands.id"), nullable=True)
    default_supplier_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("suppliers.id"), nullable=True, use_existing_column=False)

    # Units / packing
    unit:      Mapped[str]  = mapped_column(String(20), default="PCS")   # PCS, KG, L …
    pack_size: Mapped[int]  = mapped_column(Integer, default=1)          # pcs per box

    # Cost (always stored in USD; LBP cost = cost_usd * exchange_rate)
    cost_price:    Mapped[float]     = mapped_column(Float, default=0.0)
    cost_currency: Mapped[str]       = mapped_column(String(5), default="USD")

    # VAT
    vat_rate: Mapped[float] = mapped_column(Float, default=0.11)         # 0.11 = 11%

    # Minimum stock alert
    min_stock: Mapped[float] = mapped_column(Float, default=0.0)

    # Flags
    is_active:       Mapped[bool] = mapped_column(Boolean, default=True)   # item deactivated in system
    is_pos_featured: Mapped[bool] = mapped_column(Boolean, default=False)  # shows as quick button on POS
    is_online:       Mapped[bool] = mapped_column(Boolean, default=False)  # sync to mobile app
    is_visible:      Mapped[bool] = mapped_column(Boolean, default=True)   # visible in lists
    is_featured:     Mapped[bool] = mapped_column(Boolean, default=False)  # promoted/featured item
    photo_url:       Mapped[str | None] = mapped_column(Text, nullable=True)  # Supabase Storage public URL
    notes:           Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    category: Mapped["Category | None"]   = relationship(back_populates="items")
    brand:    Mapped["Brand | None"]      = relationship(back_populates="items")
    barcodes: Mapped[list["ItemBarcode"]] = relationship(back_populates="item", cascade="all, delete-orphan")
    prices:   Mapped[list["ItemPrice"]]   = relationship(back_populates="item", cascade="all, delete-orphan")
    stock_entries: Mapped[list["ItemStock"]] = relationship(back_populates="item", cascade="all, delete-orphan")

    @property
    def primary_barcode(self) -> str | None:
        primary = next((b for b in self.barcodes if b.is_primary), None)
        if primary:
            return primary.barcode
        return self.barcodes[0].barcode if self.barcodes else None

    @property
    def retail_price(self) -> "ItemPrice | None":
        return next((p for p in self.prices if p.price_type == "retail" and p.is_default), None)


# ── ItemBarcode ───────────────────────────────────────────────────────────────

class ItemBarcode(Base, TimestampMixin):
    __tablename__ = "item_barcodes"
    __table_args__ = (UniqueConstraint("barcode", name="uq_barcode"),)

    id:         Mapped[str]  = mapped_column(String(36), primary_key=True, default=new_uuid)
    item_id:    Mapped[str]  = mapped_column(String(36), ForeignKey("items.id"), nullable=False, index=True)
    barcode:    Mapped[str]  = mapped_column(String(100), nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    # pack_size override: a box barcode may represent 10 pcs
    pack_qty:   Mapped[int]  = mapped_column(Integer, default=1)

    item: Mapped["Item"] = relationship(back_populates="barcodes")


# ── ItemPrice ─────────────────────────────────────────────────────────────────

class ItemPrice(Base, TimestampMixin, SyncMixin):
    __tablename__ = "item_prices"

    id:         Mapped[str]   = mapped_column(String(36), primary_key=True, default=new_uuid)
    item_id:    Mapped[str]   = mapped_column(String(36), ForeignKey("items.id"), nullable=False, index=True)
    price_type: Mapped[str]   = mapped_column(String(30), default="retail")   # retail | wholesale | promo
    amount:     Mapped[float] = mapped_column(Float, nullable=False)
    currency:   Mapped[str]   = mapped_column(String(5), default="USD")       # USD | LBP
    is_default: Mapped[bool]  = mapped_column(Boolean, default=True)
    is_active:  Mapped[bool]  = mapped_column(Boolean, default=True)

    item: Mapped["Item"] = relationship(back_populates="prices")


# ── ItemStock (current qty per warehouse — derived from movements, cached here) ──

class ItemStock(Base, TimestampMixin):
    __tablename__ = "item_stock"
    __table_args__ = (UniqueConstraint("item_id", "warehouse_id", name="uq_item_warehouse"),)

    id:           Mapped[str]   = mapped_column(String(36), primary_key=True, default=new_uuid)
    item_id:      Mapped[str]   = mapped_column(String(36), ForeignKey("items.id"), nullable=False)
    warehouse_id: Mapped[str]   = mapped_column(String(36), ForeignKey("warehouses.id"), nullable=False)
    quantity:     Mapped[float] = mapped_column(Float, default=0.0)

    item:      Mapped["Item"]      = relationship(back_populates="stock_entries")
    warehouse: Mapped["Warehouse"] = relationship(back_populates="stock_entries")


# ── Currency ──────────────────────────────────────────────────────────────────

class Currency(Base, TimestampMixin):
    __tablename__ = "currencies"

    code:       Mapped[str]   = mapped_column(String(5), primary_key=True)   # USD, LBP, EUR …
    name:       Mapped[str]   = mapped_column(String(50), nullable=False)
    symbol:     Mapped[str]   = mapped_column(String(5),  nullable=False)
    rate_to_usd: Mapped[float] = mapped_column(Float, default=1.0)            # 1 USD = X of this currency
    is_base:    Mapped[bool]  = mapped_column(Boolean, default=False)
    is_active:  Mapped[bool]  = mapped_column(Boolean, default=True)


# ── Settings ──────────────────────────────────────────────────────────────────

class Setting(Base):
    __tablename__ = "settings"

    key:         Mapped[str]       = mapped_column(String(100), primary_key=True)
    value:       Mapped[str]       = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
