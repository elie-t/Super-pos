"""
SQLAlchemy engine and session factory for the local SQLite database.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from config import LOCAL_DB_URL
from database.models.base import Base

# SQLite-specific: enable WAL mode and foreign keys on every connection
engine = create_engine(
    LOCAL_DB_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session() -> Session:
    """Return a new DB session. Caller is responsible for closing it."""
    return SessionLocal()


def init_db() -> None:
    """Create all tables if they don't exist (used on first run)."""
    # Import all model modules so SQLAlchemy registers them before create_all
    import database.models.users        # noqa: F401
    import database.models.items        # noqa: F401
    import database.models.parties      # noqa: F401
    import database.models.invoices     # noqa: F401
    import database.models.stock        # noqa: F401
    import database.models.financials   # noqa: F401
    import database.models.sync         # noqa: F401
    import database.models.inventory    # noqa: F401
    Base.metadata.create_all(bind=engine)
    # Idempotent migrations for columns added after initial schema
    # NOTE: SQLite ALTER TABLE ADD COLUMN cannot have UNIQUE — uniqueness is
    # enforced at the application/model layer instead.
    with engine.connect() as conn:
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE warehouses ADD COLUMN number INTEGER"
            ))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE sales_invoices ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0"
            ))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE categories ADD COLUMN show_in_daily INTEGER NOT NULL DEFAULT 0"
            ))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE categories ADD COLUMN show_on_touch INTEGER NOT NULL DEFAULT 0"
            ))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE items ADD COLUMN show_on_touch INTEGER NOT NULL DEFAULT 0"
            ))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE warehouses ADD COLUMN default_customer_id TEXT REFERENCES customers(id)"
            ))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE warehouse_transfers ADD COLUMN transfer_number TEXT"
            ))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE warehouse_transfer_items ADD COLUMN item_name TEXT"
            ))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE warehouse_transfer_items ADD COLUMN unit_cost REAL NOT NULL DEFAULT 0"
            ))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE warehouse_transfers ADD COLUMN transfer_date TEXT"
            ))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE users ADD COLUMN warehouse_id TEXT REFERENCES warehouses(id)"
            ))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE items ADD COLUMN photo_url TEXT"
            ))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE item_barcodes ADD COLUMN pack_qty INTEGER NOT NULL DEFAULT 1"
            ))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE sales_invoice_items ADD COLUMN barcode TEXT"
            ))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                """CREATE TABLE IF NOT EXISTS applied_central_movements (
                    movement_id TEXT PRIMARY KEY,
                    applied_at  TEXT NOT NULL
                )"""
            ))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(__import__("sqlalchemy").text(
                "ALTER TABLE sales_invoices ADD COLUMN branch_id TEXT NOT NULL DEFAULT ''"
            ))
            conn.commit()
        except Exception:
            pass
