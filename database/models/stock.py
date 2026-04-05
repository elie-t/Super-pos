"""
Stock movements — the source of truth for inventory.
Every qty change creates an immutable movement row.
"""
from sqlalchemy import String, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.models.base import Base, TimestampMixin, SyncMixin, new_uuid


MOVEMENT_TYPES = (
    "purchase",         # +  stock received from supplier
    "purchase_refund",  # -  returned to supplier
    "sale",             # -  sold to customer
    "sale_refund",      # +  returned by customer
    "transfer_in",      # +  arrived from another warehouse
    "transfer_out",     # -  sent to another warehouse
    "adjustment_in",    # +  manual positive adjustment
    "adjustment_out",   # -  manual negative adjustment / write-off
    "inventory",        # ±  inventory count correction
    "opening",          # +  opening balance on first setup
)


class StockMovement(Base, TimestampMixin, SyncMixin):
    __tablename__ = "stock_movements"

    id:              Mapped[str]        = mapped_column(String(36), primary_key=True, default=new_uuid)
    item_id:         Mapped[str]        = mapped_column(String(36), ForeignKey("items.id"), nullable=False, index=True)
    warehouse_id:    Mapped[str]        = mapped_column(String(36), ForeignKey("warehouses.id"), nullable=False, index=True)

    movement_type:   Mapped[str]        = mapped_column(String(30), nullable=False)   # see MOVEMENT_TYPES
    quantity:        Mapped[float]      = mapped_column(Float, nullable=False)         # positive = IN, negative = OUT
    unit_cost:       Mapped[float]      = mapped_column(Float, default=0.0)            # cost at time of movement
    cost_currency:   Mapped[str]        = mapped_column(String(5), default="USD")

    # Reference to the document that triggered this movement
    reference_type:  Mapped[str | None]  = mapped_column(String(30), nullable=True)   # sales_invoice | purchase_invoice | transfer | adjustment
    reference_id:    Mapped[str | None]  = mapped_column(String(36), nullable=True, index=True)

    operator_id:     Mapped[str | None]  = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    notes:           Mapped[str | None]  = mapped_column(Text, nullable=True)

    item:      Mapped["Item"]      = relationship()  # type: ignore[name-defined]
    warehouse: Mapped["Warehouse"] = relationship()  # type: ignore[name-defined]
    operator:  Mapped["User | None"] = relationship()  # type: ignore[name-defined]


class WarehouseTransfer(Base, TimestampMixin, SyncMixin):
    """Transfer of items between warehouses."""
    __tablename__ = "warehouse_transfers"

    id:                Mapped[str]        = mapped_column(String(36), primary_key=True, default=new_uuid)
    transfer_number:   Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    from_warehouse_id: Mapped[str]        = mapped_column(String(36), ForeignKey("warehouses.id"), nullable=False)
    to_warehouse_id:   Mapped[str]        = mapped_column(String(36), ForeignKey("warehouses.id"), nullable=False)
    transfer_date:     Mapped[str | None] = mapped_column(String(20), nullable=True)
    status:            Mapped[str]        = mapped_column(String(20), default="draft")  # draft | confirmed
    operator_id:       Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    notes:             Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["WarehouseTransferItem"]] = relationship(back_populates="transfer", cascade="all, delete-orphan")


class WarehouseTransferItem(Base, TimestampMixin):
    __tablename__ = "warehouse_transfer_items"

    id:          Mapped[str]        = mapped_column(String(36), primary_key=True, default=new_uuid)
    transfer_id: Mapped[str]        = mapped_column(String(36), ForeignKey("warehouse_transfers.id"), nullable=False)
    item_id:     Mapped[str]        = mapped_column(String(36), ForeignKey("items.id"), nullable=False)
    item_name:   Mapped[str | None] = mapped_column(String(200), nullable=True)
    quantity:    Mapped[float]      = mapped_column(Float, nullable=False)
    unit_cost:   Mapped[float]      = mapped_column(Float, nullable=True, default=0.0)

    transfer: Mapped["WarehouseTransfer"] = relationship(back_populates="items")
    item:     Mapped["Item"]              = relationship()  # type: ignore[name-defined]


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    id:          Mapped[str]        = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id:     Mapped[str | None]  = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    action:      Mapped[str]         = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str]         = mapped_column(String(50), nullable=False)
    entity_id:   Mapped[str | None]  = mapped_column(String(36), nullable=True)
    details:     Mapped[str | None]  = mapped_column(Text, nullable=True)   # JSON string

    user: Mapped["User | None"] = relationship()  # type: ignore[name-defined]
