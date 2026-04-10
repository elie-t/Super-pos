"""
One-time script: delete ALL purchase invoices from local SQLite + Supabase.
Also removes purchase-type stock movements so the stock card is clean.

Run from the super_pos directory:
    python purge_purchases.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from database.engine import init_db, engine
from sqlalchemy import text

init_db()

print("=== Purging purchase invoices ===\n")

with engine.connect() as conn:
    conn.execute(text("PRAGMA foreign_keys=OFF"))

    r1 = conn.execute(text("DELETE FROM purchase_invoice_items"))
    print(f"  Local purchase_invoice_items deleted : {r1.rowcount}")

    r2 = conn.execute(text("DELETE FROM purchase_invoices"))
    print(f"  Local purchase_invoices deleted      : {r2.rowcount}")

    r3 = conn.execute(text(
        "DELETE FROM stock_movements WHERE reference_type='purchase_invoice'"
    ))
    print(f"  Local stock_movements (purchase) del : {r3.rowcount}")

    # Also clean applied_central_movements for any orphaned purchase movements
    r4 = conn.execute(text(
        "DELETE FROM applied_central_movements "
        "WHERE movement_id NOT IN (SELECT id FROM stock_movements)"
    ))
    print(f"  Orphan applied_central_movements del : {r4.rowcount}")

    conn.execute(text("PRAGMA foreign_keys=ON"))
    conn.commit()

print()

# ── Supabase ──────────────────────────────────────────────────────────────────
try:
    from sync.service import is_configured, _url, _headers
    import requests

    if not is_configured():
        print("Supabase not configured — skipping remote delete.")
    else:
        print("Deleting from Supabase…")

        r = requests.delete(
            f"{_url('purchase_invoice_items_central')}?id=neq.00000000-0000-0000-0000-000000000000",
            headers=_headers(), timeout=30,
        )
        print(f"  purchase_invoice_items_central : HTTP {r.status_code}")

        r = requests.delete(
            f"{_url('purchase_invoices_central')}?id=neq.00000000-0000-0000-0000-000000000000",
            headers=_headers(), timeout=30,
        )
        print(f"  purchase_invoices_central      : HTTP {r.status_code}")

except Exception as e:
    print(f"  Supabase error: {e}")

print("\nDone.")
