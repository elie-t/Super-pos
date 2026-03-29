"""
Inventory session models — physical stock count / inventory invoice.
Each session picks a warehouse, scans items with actual shelf qty,
and the service creates adjustment_in / adjustment_out movements.
"""
from sqlalchemy import String, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.models.base import Base, TimestampMixin, new_uuid


class InventorySession(Base, TimestampMixin):
    __tablename__ = "inventory_sessions"

    id:             Mapped[str]        = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_number: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    warehouse_id:   Mapped[str]        = mapped_column(String(36), ForeignKey("warehouses.id"), nullable=False)
    session_date:   Mapped[str | None] = mapped_column(String(20), nullable=True)
    status:         Mapped[str]        = mapped_column(String(20), default="open")   # open | locked
    operator_id:    Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    notes:          Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["InventorySessionItem"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class InventorySessionItem(Base, TimestampMixin):
    __tablename__ = "inventory_session_items"

    id:          Mapped[str]        = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id:  Mapped[str]        = mapped_column(String(36), ForeignKey("inventory_sessions.id"), nullable=False)
    item_id:     Mapped[str]        = mapped_column(String(36), ForeignKey("items.id"), nullable=False)
    item_name:   Mapped[str | None] = mapped_column(String(200), nullable=True)
    system_qty:  Mapped[float]      = mapped_column(Float, default=0.0)   # snapshot at scan time
    counted_qty: Mapped[float]      = mapped_column(Float, default=0.0)   # actual shelf qty
    diff_qty:    Mapped[float]      = mapped_column(Float, default=0.0)   # counted - system
    unit_cost:   Mapped[float]      = mapped_column(Float, default=0.0)

    session: Mapped["InventorySession"] = relationship(back_populates="items")
    item:    Mapped["Item"]             = relationship()  # type: ignore[name-defined]
