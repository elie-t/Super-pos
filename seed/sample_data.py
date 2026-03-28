"""
Seeds the essential reference data that must exist before any import or operation:
  - currencies (USD, LBP)
  - default warehouse
  - admin user
  - cash customer
  - app settings

Run this ONCE after first database init:
    python seed/sample_data.py
"""
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import bcrypt as _bcrypt
from database.engine import init_db, get_session
from database.models.items import Currency, Warehouse, Setting
from database.models.parties import Customer
from database.models.users import User


DEFAULT_SETTINGS = {
    "vat_rate":            ("0.11",        "VAT rate applied to items (e.g. 0.11 = 11%)"),
    "base_currency":       ("USD",         "Base currency for all books"),
    "lbp_rate":            ("89500",       "Current LBP rate per 1 USD"),
    "shop_name":           ("My Supermarket", "Shop display name on receipts"),
    "shop_address":        ("",            "Shop address on receipts"),
    "shop_phone":          ("",            "Shop phone on receipts"),
    "receipt_footer":      ("Thank you!", "Footer text on POS receipt"),
    "invoice_prefix_sale": ("SI",          "Prefix for sale invoice numbers"),
    "invoice_prefix_purchase": ("PI",      "Prefix for purchase invoice numbers"),
    "next_sale_number":    ("1",           "Auto-increment counter for sale invoices"),
    "next_purchase_number":("1",           "Auto-increment counter for purchase invoices"),
    "sync_enabled":        ("0",           "Enable background sync to online DB (0/1)"),
}


def seed():
    init_db()
    session = get_session()

    try:
        # ── Currencies ────────────────────────────────────────────────────────
        usd = session.get(Currency, "USD")
        if not usd:
            session.add(Currency(code="USD", name="US Dollar",    symbol="$",   rate_to_usd=1.0,     is_base=True,  is_active=True))
        lbp = session.get(Currency, "LBP")
        if not lbp:
            session.add(Currency(code="LBP", name="Lebanese Pound", symbol="L.L", rate_to_usd=89500.0, is_base=False, is_active=True))

        # ── Default warehouse ─────────────────────────────────────────────────
        wh = session.query(Warehouse).filter_by(name="Main Warehouse").first()
        if not wh:
            session.add(Warehouse(
                id=str(uuid.uuid4()),
                name="Main Warehouse",
                location="Shop floor",
                is_default=True,
                is_active=True,
            ))
            print("  Created: Main Warehouse")

        # ── Admin user ────────────────────────────────────────────────────────
        admin = session.query(User).filter_by(username="admin").first()
        if not admin:
            session.add(User(
                id=str(uuid.uuid4()),
                username="admin",
                password_hash=_bcrypt.hashpw(b"admin123", _bcrypt.gensalt()).decode(),
                full_name="Administrator",
                role="admin",
                is_active=True,
            ))
            print("  Created: admin / admin123  ← CHANGE THIS PASSWORD!")

        # ── Cash customer (walk-in) ────────────────────────────────────────────
        cash = session.query(Customer).filter_by(is_cash_client=True).first()
        if not cash:
            session.add(Customer(
                id=str(uuid.uuid4()),
                name="Cash Customer",
                code="CASH",
                is_active=True,
                is_cash_client=True,
            ))
            print("  Created: Cash Customer")

        # ── Settings ──────────────────────────────────────────────────────────
        for key, (value, description) in DEFAULT_SETTINGS.items():
            if not session.get(Setting, key):
                session.add(Setting(key=key, value=value, description=description))

        session.commit()
        print("\n✓ Sample data seeded successfully.")

    except Exception as exc:
        session.rollback()
        print(f"\n✗ Seed failed: {exc}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed()
