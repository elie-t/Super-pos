"""Supplier service — CRUD and lookup for suppliers."""
from dataclasses import dataclass, field
from database.engine import get_session, init_db
from database.models.parties import Supplier


@dataclass
class SupplierRow:
    id: str
    name: str
    code: str
    phone: str
    balance: float
    currency: str
    is_active: bool


@dataclass
class SupplierDetail:
    id: str
    name: str
    code: str
    phone: str
    phone2: str
    email: str
    address: str
    classification: str
    credit_limit: float
    balance: float
    currency: str
    notes: str
    is_active: bool


class SupplierService:

    @staticmethod
    def search(query: str = "", limit: int = 300, offset: int = 0) -> list[SupplierRow]:
        init_db()
        session = get_session()
        try:
            q = session.query(Supplier)
            if query:
                like = f"%{query}%"
                q = q.filter(
                    Supplier.name.ilike(like) |
                    Supplier.code.ilike(like) |
                    Supplier.phone.ilike(like)
                )
            q = q.order_by(Supplier.name).limit(limit).offset(offset)
            return [
                SupplierRow(
                    id=s.id, name=s.name, code=s.code or "",
                    phone=s.phone or "", balance=s.balance,
                    currency=s.currency, is_active=s.is_active,
                )
                for s in q.all()
            ]
        finally:
            session.close()

    @staticmethod
    def get(supplier_id: str) -> SupplierDetail | None:
        init_db()
        session = get_session()
        try:
            s = session.query(Supplier).filter_by(id=supplier_id).first()
            if not s:
                return None
            return SupplierDetail(
                id=s.id, name=s.name, code=s.code or "",
                phone=s.phone or "", phone2=s.phone2 or "",
                email=s.email or "", address=s.address or "",
                classification=s.classification or "",
                credit_limit=s.credit_limit, balance=s.balance,
                currency=s.currency, notes=s.notes or "",
                is_active=s.is_active,
            )
        finally:
            session.close()

    @staticmethod
    def save(detail: SupplierDetail) -> tuple[bool, str]:
        init_db()
        session = get_session()
        try:
            sup = session.query(Supplier).filter_by(id=detail.id).first()
            if not sup:
                from database.models.base import new_uuid
                sup = Supplier(id=detail.id or new_uuid())
                session.add(sup)
            sup.name = detail.name.strip()
            sup.code = detail.code.strip() or None
            sup.phone = detail.phone.strip() or None
            sup.phone2 = detail.phone2.strip() or None
            sup.email = detail.email.strip() or None
            sup.address = detail.address.strip() or None
            sup.classification = detail.classification or None
            sup.credit_limit = detail.credit_limit
            sup.currency = detail.currency
            sup.notes = detail.notes or None
            sup.is_active = detail.is_active
            session.commit()
            return True, ""
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            session.close()

    @staticmethod
    def count(query: str = "") -> int:
        init_db()
        session = get_session()
        try:
            q = session.query(Supplier)
            if query:
                like = f"%{query}%"
                q = q.filter(Supplier.name.ilike(like) | Supplier.code.ilike(like))
            return q.count()
        finally:
            session.close()
