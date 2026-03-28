"""Customer CRUD and statement service."""
from database.engine import get_session, init_db


class CustomerService:

    @staticmethod
    def list_customers(query: str = "", include_inactive: bool = False) -> list[dict]:
        init_db()
        session = get_session()
        try:
            from database.models.parties import Customer
            q = session.query(Customer)
            if not include_inactive:
                q = q.filter(Customer.is_active == True)
            if query:
                like = f"%{query}%"
                q = q.filter(
                    Customer.name.ilike(like)
                    | Customer.code.ilike(like)
                    | Customer.phone.ilike(like)
                )
            return [
                {
                    "id":           c.id,
                    "name":         c.name,
                    "code":         c.code or "",
                    "phone":        c.phone or "",
                    "phone2":       c.phone2 or "",
                    "email":        c.email or "",
                    "address":      c.address or "",
                    "classification": c.classification or "",
                    "credit_limit": c.credit_limit,
                    "balance":      c.balance,
                    "currency":     c.currency,
                    "notes":        c.notes or "",
                    "is_active":    c.is_active,
                    "is_cash_client": c.is_cash_client,
                }
                for c in q.order_by(Customer.name).all()
            ]
        finally:
            session.close()

    @staticmethod
    def save_customer(
        customer_id: str,
        name: str,
        code: str,
        phone: str,
        phone2: str,
        email: str,
        address: str,
        classification: str,
        credit_limit: float,
        currency: str,
        notes: str,
        is_active: bool,
    ) -> tuple[bool, str]:
        init_db()
        session = get_session()
        try:
            from database.models.parties import Customer
            from database.models.base import new_uuid

            if customer_id:
                c = session.query(Customer).filter_by(id=customer_id).first()
                if not c:
                    return False, "Customer not found"
            else:
                c = Customer(id=new_uuid())
                session.add(c)

            c.name           = name
            c.code           = code or None
            c.phone          = phone or None
            c.phone2         = phone2 or None
            c.email          = email or None
            c.address        = address or None
            c.classification = classification or None
            c.credit_limit   = credit_limit
            c.currency       = currency
            c.notes          = notes or None
            c.is_active      = is_active

            session.commit()
            return True, c.id
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            session.close()

    @staticmethod
    def get_statement(customer_id: str) -> dict:
        """All sales invoices for a customer plus running balance."""
        init_db()
        session = get_session()
        try:
            from database.models.parties import Customer
            from database.models.invoices import SalesInvoice
            from database.models.items import Warehouse

            c = session.query(Customer).filter_by(id=customer_id).first()
            if not c:
                return {}

            invoices = (
                session.query(SalesInvoice, Warehouse.name, Warehouse.number)
                .outerjoin(Warehouse, SalesInvoice.warehouse_id == Warehouse.id)
                .filter(
                    SalesInvoice.customer_id == customer_id,
                    SalesInvoice.invoice_type == "sale",
                    SalesInvoice.status != "cancelled",
                )
                .order_by(SalesInvoice.invoice_date.desc(),
                          SalesInvoice.created_at.desc())
                .all()
            )

            lines = []
            for inv, wh_name, wh_num in invoices:
                lines.append({
                    "id":             inv.id,
                    "invoice_number": inv.invoice_number,
                    "date":           inv.invoice_date or "",
                    "warehouse_name": wh_name or "",
                    "warehouse_num":  wh_num if wh_num is not None else "",
                    "total":          inv.total,
                    "amount_paid":    inv.amount_paid,
                    "balance":        inv.total - inv.amount_paid,
                    "currency":       inv.currency,
                    "payment_status": inv.payment_status,
                    "source":         inv.source,
                })

            return {
                "customer": {
                    "id":           c.id,
                    "name":         c.name,
                    "phone":        c.phone or "",
                    "balance":      c.balance,
                    "currency":     c.currency,
                    "credit_limit": c.credit_limit,
                },
                "invoices": lines,
            }
        finally:
            session.close()
