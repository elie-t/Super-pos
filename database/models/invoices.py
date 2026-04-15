"""
Sales and Purchase invoices + line items + held invoices.
"""
from sqlalchemy import String, Boolean, Float, Integer, ForeignKey, Text, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.models.base import Base, TimestampMixin, SyncMixin, new_uuid


# ── Sales Invoice ──────────────────────────────────────────────────────────────

class SalesInvoice(Base, TimestampMixin, SyncMixin):
    __tablename__ = "sales_invoices"

    id:             Mapped[str]        = mapped_column(String(36), primary_key=True, default=new_uuid)
    invoice_number: Mapped[str]        = mapped_column(String(30), unique=True, nullable=False, index=True)
    customer_id:    Mapped[str]        = mapped_column(String(36), ForeignKey("customers.id"), nullable=False)
    operator_id:    Mapped[str]        = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    warehouse_id:   Mapped[str]        = mapped_column(String(36), ForeignKey("warehouses.id"), nullable=False)

    invoice_date:   Mapped[str]        = mapped_column(String(20), nullable=False)   # ISO date string
    sale_time:      Mapped[str]        = mapped_column(String(5),  nullable=False, default="")  # HH:MM
    due_date:       Mapped[str | None]  = mapped_column(String(20), nullable=True)

    invoice_type:   Mapped[str]        = mapped_column(String(20), default="sale")   # sale | refund | proforma
    source:         Mapped[str]        = mapped_column(String(20), default="pos")    # pos | backoffice

    # Totals (in base currency USD)
    subtotal:       Mapped[float]      = mapped_column(Float, default=0.0)
    discount_value: Mapped[float]      = mapped_column(Float, default=0.0)
    vat_value:      Mapped[float]      = mapped_column(Float, default=0.0)
    total:          Mapped[float]      = mapped_column(Float, default=0.0)
    currency:       Mapped[str]        = mapped_column(String(5), default="USD")

    # Status
    status:         Mapped[str]        = mapped_column(String(20), default="draft")          # draft | finalized | cancelled
    payment_status: Mapped[str]        = mapped_column(String(20), default="unpaid")         # unpaid | partial | paid
    amount_paid:    Mapped[float]      = mapped_column(Float, default=0.0)

    # Reference to original invoice (for refunds)
    original_invoice_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sales_invoices.id"), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Set True after End-of-Shift export so the POS list shows a clean new shift
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    # Branch that created this invoice (empty = local branch, populated when pulled from central)
    branch_id: Mapped[str] = mapped_column(String(100), default="")

    customer:  Mapped["Customer"]          = relationship()  # type: ignore[name-defined]
    operator:  Mapped["User"]              = relationship()  # type: ignore[name-defined]
    warehouse: Mapped["Warehouse"]         = relationship()  # type: ignore[name-defined]
    items:     Mapped[list["SalesInvoiceItem"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    payments:  Mapped[list["Payment"]]     = relationship(back_populates="sales_invoice")   # type: ignore[name-defined]


class SalesInvoiceItem(Base, TimestampMixin):
    __tablename__ = "sales_invoice_items"

    id:          Mapped[str]   = mapped_column(String(36), primary_key=True, default=new_uuid)
    invoice_id:  Mapped[str]   = mapped_column(String(36), ForeignKey("sales_invoices.id"), nullable=False, index=True)
    item_id:     Mapped[str]   = mapped_column(String(36), ForeignKey("items.id"), nullable=False)
    barcode:     Mapped[str | None] = mapped_column(String(100), nullable=True)   # barcode used at scan time
    item_name:   Mapped[str]   = mapped_column(String(200), nullable=False)       # snapshot of name at sale time
    quantity:    Mapped[float] = mapped_column(Float, nullable=False)
    unit_price:  Mapped[float] = mapped_column(Float, nullable=False)
    currency:    Mapped[str]   = mapped_column(String(5), default="USD")
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    vat_pct:     Mapped[float] = mapped_column(Float, default=0.11)
    line_total:  Mapped[float] = mapped_column(Float, nullable=False)             # after discount + VAT

    invoice: Mapped["SalesInvoice"] = relationship(back_populates="items")
    item:    Mapped["Item"]         = relationship()  # type: ignore[name-defined]


# ── Purchase Invoice ───────────────────────────────────────────────────────────

class PurchaseInvoice(Base, TimestampMixin, SyncMixin):
    __tablename__ = "purchase_invoices"

    id:             Mapped[str]        = mapped_column(String(36), primary_key=True, default=new_uuid)
    invoice_number: Mapped[str]        = mapped_column(String(30), nullable=False, index=True)
    supplier_id:    Mapped[str]        = mapped_column(String(36), ForeignKey("suppliers.id"), nullable=False)
    operator_id:    Mapped[str]        = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    warehouse_id:   Mapped[str]        = mapped_column(String(36), ForeignKey("warehouses.id"), nullable=False)

    invoice_date:   Mapped[str]        = mapped_column(String(20), nullable=False)
    due_date:       Mapped[str | None]  = mapped_column(String(20), nullable=True)
    order_number:   Mapped[str | None]  = mapped_column(String(30), nullable=True)

    invoice_type:   Mapped[str]        = mapped_column(String(20), default="purchase")  # purchase | refund

    subtotal:       Mapped[float]      = mapped_column(Float, default=0.0)
    discount_value: Mapped[float]      = mapped_column(Float, default=0.0)
    vat_value:      Mapped[float]      = mapped_column(Float, default=0.0)
    total:          Mapped[float]      = mapped_column(Float, default=0.0)
    currency:       Mapped[str]        = mapped_column(String(5), default="USD")

    status:         Mapped[str]        = mapped_column(String(20), default="draft")    # draft | finalized | cancelled
    payment_status: Mapped[str]        = mapped_column(String(20), default="unpaid")
    amount_paid:    Mapped[float]      = mapped_column(Float, default=0.0)

    original_invoice_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("purchase_invoices.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    supplier:  Mapped["Supplier"]            = relationship()  # type: ignore[name-defined]
    operator:  Mapped["User"]                = relationship()  # type: ignore[name-defined]
    warehouse: Mapped["Warehouse"]           = relationship()  # type: ignore[name-defined]
    items:     Mapped[list["PurchaseInvoiceItem"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    payments:  Mapped[list["Payment"]]       = relationship(back_populates="purchase_invoice")  # type: ignore[name-defined]


class PurchaseInvoiceItem(Base, TimestampMixin):
    __tablename__ = "purchase_invoice_items"

    id:           Mapped[str]   = mapped_column(String(36), primary_key=True, default=new_uuid)
    invoice_id:   Mapped[str]   = mapped_column(String(36), ForeignKey("purchase_invoices.id"), nullable=False, index=True)
    item_id:      Mapped[str]   = mapped_column(String(36), ForeignKey("items.id"), nullable=False)
    item_name:    Mapped[str]   = mapped_column(String(200), nullable=False)
    quantity:     Mapped[float] = mapped_column(Float, nullable=False)
    pack_size:    Mapped[int]   = mapped_column(Integer, default=1)            # boxes vs pcs
    unit_cost:    Mapped[float] = mapped_column(Float, nullable=False)
    currency:     Mapped[str]   = mapped_column(String(5), default="USD")
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    vat_pct:      Mapped[float] = mapped_column(Float, default=0.11)
    line_total:   Mapped[float] = mapped_column(Float, nullable=False)

    invoice: Mapped["PurchaseInvoice"] = relationship(back_populates="items")
    item:    Mapped["Item"]            = relationship()  # type: ignore[name-defined]


# ── Online Order (from mobile shopping app) ───────────────────────────────────

class OnlineOrder(Base, TimestampMixin):
    """
    Incoming order from the mobile app.
    Pulled from Supabase by the sync worker → auto-creates a SalesInvoice.
    """
    __tablename__ = "online_orders"

    id:              Mapped[str]        = mapped_column(String(36), primary_key=True)  # same id as Supabase row
    customer_name:   Mapped[str]        = mapped_column(String(100), nullable=False)
    customer_phone:  Mapped[str]        = mapped_column(String(30), nullable=False)
    delivery_type:   Mapped[str]        = mapped_column(String(20), nullable=False)    # delivery | pickup
    address:         Mapped[str | None] = mapped_column(Text, nullable=True)
    notes:           Mapped[str | None] = mapped_column(Text, nullable=True)
    items_json:      Mapped[str]        = mapped_column(Text, nullable=False)          # [{item_id, qty, price}]
    total:           Mapped[float]      = mapped_column(Float, default=0.0)
    currency:        Mapped[str]        = mapped_column(String(5), default="LBP")
    status:          Mapped[str]        = mapped_column(String(20), default="new")     # new | confirmed | ready | delivered | cancelled
    payment_method:  Mapped[str]        = mapped_column(String(20), default="cash")   # cash | online
    invoice_id:      Mapped[str | None] = mapped_column(String(36), ForeignKey("sales_invoices.id"), nullable=True)
    ordered_at:      Mapped[str]        = mapped_column(String(30), nullable=False)


# ── Held Invoice (POS hold / resume) ──────────────────────────────────────────

class HeldInvoice(Base, TimestampMixin):
    __tablename__ = "held_invoices"

    id:          Mapped[str]        = mapped_column(String(36), primary_key=True, default=new_uuid)
    operator_id: Mapped[str]        = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    customer_id: Mapped[str | None]  = mapped_column(String(36), ForeignKey("customers.id"), nullable=True)
    label:       Mapped[str | None]  = mapped_column(String(100), nullable=True)   # e.g. "Table 3" or customer name
    items_json:  Mapped[str]         = mapped_column(Text, nullable=False)          # serialised cart rows
    total:       Mapped[float]       = mapped_column(Float, default=0.0)
    currency:    Mapped[str]         = mapped_column(String(5), default="USD")
    is_resumed:  Mapped[bool]        = mapped_column(Boolean, default=False)
