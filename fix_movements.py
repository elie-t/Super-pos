"""
Fix duplicate stock movements and delete transfer movements.
Run on the MAIN PC: python fix_movements.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from database.engine import init_db, engine
from sqlalchemy import text
init_db()

print("=== Fixing stock movements ===\n")

with engine.connect() as conn:
    # 1. Delete all local stock movements (will be rebuilt cleanly by pull_stock_movements)
    r = conn.execute(text("DELETE FROM stock_movements"))
    print(f"  Local stock_movements deleted      : {r.rowcount}")

    # 2. Clear applied tracker so everything re-pulls
    r = conn.execute(text("DELETE FROM applied_central_movements"))
    print(f"  applied_central_movements cleared  : {r.rowcount}")

    conn.commit()

# 3. Delete transfer movements from Supabase stock_movements_central
try:
    from sync.service import is_configured, _url, _headers, _state_set
    import requests
    from datetime import datetime, timezone, timedelta

    if not is_configured():
        print("\nSupabase not configured — skipping remote cleanup.")
    else:
        print("\nCleaning Supabase…")

        r = requests.delete(
            f"{_url('stock_movements_central')}?movement_type=in.(transfer_in,transfer_out)",
            headers=_headers(), timeout=30,
        )
        print(f"  Transfer movements deleted from Supabase : HTTP {r.status_code}")

        # Reset movements cursor to 30 days ago for a clean re-pull
        _state_set("movements_pull",
                   (datetime.now(timezone.utc) - timedelta(days=30)).isoformat())
        print("  movements_pull cursor reset to 30 days ago")

except Exception as e:
    print(f"  Error: {e}")

print("\nDone. Now run Force Push/Pull to rebuild movements cleanly.")
