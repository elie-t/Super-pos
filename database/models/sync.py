"""
Sync queue — every local write that needs to reach the online DB goes here.
"""
from sqlalchemy import String, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from database.models.base import Base, TimestampMixin, new_uuid


class SyncQueue(Base, TimestampMixin):
    __tablename__ = "sync_queue"

    id:           Mapped[str]        = mapped_column(String(36), primary_key=True, default=new_uuid)
    entity_type:  Mapped[str]        = mapped_column(String(50), nullable=False, index=True)   # item | sales_invoice | …
    entity_id:    Mapped[str]        = mapped_column(String(36), nullable=False, index=True)
    action_type:  Mapped[str]        = mapped_column(String(20), nullable=False)               # create | update | delete
    payload_json: Mapped[str]        = mapped_column(Text, nullable=False)                     # full serialised record
    sync_status:  Mapped[str]        = mapped_column(String(20), default="pending", index=True) # pending | synced | failed
    retry_count:  Mapped[int]        = mapped_column(Integer, default=0)
    last_error:   Mapped[str | None]  = mapped_column(Text, nullable=True)
    synced_at:    Mapped[str | None]  = mapped_column(String(30), nullable=True)
