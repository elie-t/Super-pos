"""
Users / operators and session management.
"""
from sqlalchemy import String, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.models.base import Base, TimestampMixin, SyncMixin, new_uuid


class User(Base, TimestampMixin, SyncMixin):
    __tablename__ = "users"

    id:            Mapped[str]  = mapped_column(String(36), primary_key=True, default=new_uuid)
    username:      Mapped[str]  = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str]  = mapped_column(String(128), nullable=False)
    full_name:     Mapped[str]  = mapped_column(String(100), nullable=False)
    role:          Mapped[str]  = mapped_column(String(20),  nullable=False)   # admin | manager | cashier
    is_active:     Mapped[bool] = mapped_column(Boolean, default=True)
    is_power_user: Mapped[bool] = mapped_column(Boolean, default=False)
    pin:           Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Branch assignment — cashiers are locked to this warehouse when opening POS
    warehouse_id:  Mapped[str | None] = mapped_column(
        String(36), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )

    sessions: Mapped[list["OperatorSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class OperatorSession(Base, TimestampMixin):
    """Tracks login / logout events and the active cashier drawer."""
    __tablename__ = "operator_sessions"

    id:         Mapped[str]       = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id:    Mapped[str]       = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    started_at: Mapped[str]       = mapped_column(String(30), nullable=False)
    ended_at:   Mapped[str | None] = mapped_column(String(30), nullable=True)
    notes:      Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")
