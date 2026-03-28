"""
Customers and Suppliers (collectively: parties).
"""
from sqlalchemy import String, Boolean, Float, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.models.base import Base, TimestampMixin, SyncMixin, new_uuid


class Supplier(Base, TimestampMixin, SyncMixin):
    __tablename__ = "suppliers"

    id:             Mapped[str]        = mapped_column(String(36), primary_key=True, default=new_uuid)
    name:           Mapped[str]        = mapped_column(String(200), nullable=False, index=True)
    code:           Mapped[str | None]  = mapped_column(String(30), unique=True, nullable=True)
    phone:          Mapped[str | None]  = mapped_column(String(50), nullable=True)
    phone2:         Mapped[str | None]  = mapped_column(String(50), nullable=True)
    email:          Mapped[str | None]  = mapped_column(String(100), nullable=True)
    address:        Mapped[str | None]  = mapped_column(Text, nullable=True)
    classification: Mapped[str | None]  = mapped_column(String(50), nullable=True)   # A, B, C …
    credit_limit:   Mapped[float]       = mapped_column(Float, default=0.0)
    balance:        Mapped[float]       = mapped_column(Float, default=0.0)           # positive = we owe them
    currency:       Mapped[str]         = mapped_column(String(5), default="USD")
    notes:          Mapped[str | None]  = mapped_column(Text, nullable=True)
    is_active:      Mapped[bool]        = mapped_column(Boolean, default=True)
    is_merged_into: Mapped[str | None]  = mapped_column(String(36), ForeignKey("suppliers.id"), nullable=True)


class Customer(Base, TimestampMixin, SyncMixin):
    __tablename__ = "customers"

    id:             Mapped[str]        = mapped_column(String(36), primary_key=True, default=new_uuid)
    name:           Mapped[str]        = mapped_column(String(200), nullable=False, index=True)
    code:           Mapped[str | None]  = mapped_column(String(30), unique=True, nullable=True)
    phone:          Mapped[str | None]  = mapped_column(String(50), nullable=True)
    phone2:         Mapped[str | None]  = mapped_column(String(50), nullable=True)
    email:          Mapped[str | None]  = mapped_column(String(100), nullable=True)
    address:        Mapped[str | None]  = mapped_column(Text, nullable=True)
    classification: Mapped[str | None]  = mapped_column(String(50), nullable=True)
    credit_limit:   Mapped[float]       = mapped_column(Float, default=0.0)
    balance:        Mapped[float]       = mapped_column(Float, default=0.0)           # positive = they owe us
    currency:       Mapped[str]         = mapped_column(String(5), default="USD")
    notes:          Mapped[str | None]  = mapped_column(Text, nullable=True)
    is_active:      Mapped[bool]        = mapped_column(Boolean, default=True)
    is_cash_client: Mapped[bool]        = mapped_column(Boolean, default=False)       # the default walk-in cash customer
    is_merged_into: Mapped[str | None]  = mapped_column(String(36), ForeignKey("customers.id"), nullable=True)
