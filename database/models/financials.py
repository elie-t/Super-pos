"""
Payments and receipts.
"""
from sqlalchemy import String, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.models.base import Base, TimestampMixin, SyncMixin, new_uuid


class Payment(Base, TimestampMixin, SyncMixin):
    """
    Covers both:
      - Customer payments (receipts for sales invoices)
      - Supplier payments (paying off purchase invoices)
    """
    __tablename__ = "payments"

    id:                  Mapped[str]        = mapped_column(String(36), primary_key=True, default=new_uuid)
    payment_type:        Mapped[str]        = mapped_column(String(20), nullable=False)   # customer | supplier
    party_id:            Mapped[str]        = mapped_column(String(36), nullable=False, index=True)   # customer_id or supplier_id

    sales_invoice_id:    Mapped[str | None]  = mapped_column(String(36), ForeignKey("sales_invoices.id"), nullable=True)
    purchase_invoice_id: Mapped[str | None]  = mapped_column(String(36), ForeignKey("purchase_invoices.id"), nullable=True)

    amount:              Mapped[float]      = mapped_column(Float, nullable=False)
    currency:            Mapped[str]        = mapped_column(String(5), default="USD")
    exchange_rate:       Mapped[float]      = mapped_column(Float, default=1.0)   # if paid in LBP
    amount_in_base:      Mapped[float]      = mapped_column(Float, nullable=False)  # USD equivalent

    payment_method:      Mapped[str]        = mapped_column(String(20), default="cash")   # cash | card | transfer | mixed
    payment_date:        Mapped[str]        = mapped_column(String(20), nullable=False)
    operator_id:         Mapped[str]        = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    reference:           Mapped[str | None]  = mapped_column(String(50), nullable=True)   # cheque / card ref
    notes:               Mapped[str | None]  = mapped_column(Text, nullable=True)

    sales_invoice:    Mapped["SalesInvoice | None"]    = relationship(back_populates="payments")     # type: ignore[name-defined]
    purchase_invoice: Mapped["PurchaseInvoice | None"] = relationship(back_populates="payments")    # type: ignore[name-defined]
    operator:         Mapped["User"]                   = relationship()                              # type: ignore[name-defined]
