"""
Shared declarative base and mixin used by all models.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """Adds created_at / updated_at to any model."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SyncMixin:
    """Adds sync tracking fields to any model that syncs to the online DB."""
    sync_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    # local_version increments on every local edit
    local_version: Mapped[int] = mapped_column(default=1, nullable=False)
    # remote_version is set when the server confirms receipt
    remote_version: Mapped[int] = mapped_column(default=0, nullable=False)


def new_uuid() -> str:
    return str(uuid.uuid4())
