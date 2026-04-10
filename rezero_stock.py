"""
One-time script: reset all stock quantities to 0.
  - Local:   item_stock table → all quantities = 0
  - Supabase: stock_levels → delete all rows
  - Supabase: products.stock → set to 0

Run from the super_pos directory:
    python rezero_stock.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from database.engine import init_db, engine
from sqlalchemy import text

init_db()

print("=== Re-zeroing stock ===\n")

with engine.connect() as conn:
    r = conn.execute(text("UPDATE item_stock SET quantity=0"))
    print(f"  Local item_stock rows zeroed : {r.rowcount}")
    conn.commit()

# ── Supabase ──────────────────────────────────────────────────────────────────
try:
    from sync.service import is_configured, _url, _headers
    import requests

    if not is_configured():
        print("Supabase not configured — skipping remote reset.")
    else:
        print("Resetting Supabase…")

        # Delete all stock_levels rows
        r = requests.delete(
            f"{_url('stock_levels')}?item_id=neq.00000000-0000-0000-0000-000000000000",
            headers=_headers(), timeout=30,
        )
        print(f"  stock_levels deleted       : HTTP {r.status_code}")

        # Zero out products.stock
        r = requests.patch(
            f"{_url('products')}?id=neq.00000000-0000-0000-0000-000000000000",
            headers=_headers(),
            json={"stock": 0},
            timeout=30,
        )
        print(f"  products.stock → 0         : HTTP {r.status_code}")

except Exception as e:
    print(f"  Supabase error: {e}")

print("\nDone. All stock quantities are now 0.")
