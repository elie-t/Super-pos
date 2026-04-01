"""
reset_items_mac.py
==================
Clears all items, prices, barcodes and stock from the LOCAL database
so they can be re-pulled cleanly from Supabase central.

Run this on the MAC only, never on the PC.

Usage:
  python reset_items_mac.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database.engine import init_db, get_session
from database.models.items import Item, ItemBarcode, ItemPrice, ItemStock
from sqlalchemy import text

print("=" * 60)
print("  ITEM RESET — Mac local DB")
print("=" * 60)
print("\nThis will DELETE all local items, prices, barcodes and stock.")
print("They will be re-pulled from Supabase on next sync.\n")

answer = input("Type  YES  to confirm: ").strip()
if answer != "YES":
    print("Cancelled.")
    sys.exit(0)

init_db()
s = get_session()
try:
    s.execute(text("PRAGMA foreign_keys=OFF"))
    bc  = s.query(ItemBarcode).delete()
    pr  = s.query(ItemPrice).delete()
    st  = s.query(ItemStock).delete()
    it  = s.query(Item).delete()
    s.commit()
    s.execute(text("PRAGMA foreign_keys=ON"))
    print(f"\n  ✔  Barcodes deleted : {bc}")
    print(f"  ✔  Prices deleted   : {pr}")
    print(f"  ✔  Stock deleted    : {st}")
    print(f"  ✔  Items deleted    : {it}")
    print("\nNow delete .sync_state.json and restart the app.")
    print("Hit 'Force Push/Pull Now' to re-pull everything from Supabase.")
except Exception as e:
    s.rollback()
    print(f"\n  ✘  Error: {e}")
finally:
    s.close()
