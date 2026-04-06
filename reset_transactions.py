"""
reset_transactions.py
=====================
Deletes ALL transaction data while keeping the item catalog intact.

What is DELETED:
  - sales_invoices + sales_invoice_items
  - purchase_invoices + purchase_invoice_items
  - warehouse_transfers + warehouse_transfer_items
  - inventory_sessions + inventory_session_items
  - stock_movements
  - payments
  - held_invoices
  - sync_queue  (pending sync tasks referencing deleted records)
  - audit_logs
  - operator_sessions
  - Sequence-counter Settings (next_sale_number_*, next_purchase_number_*,
    next_transfer_number_*, next_inventory_number_*)

What is KEPT:
  - items, item_barcodes, item_prices, item_stock (quantities reset to 0)
  - categories, brands, warehouses, currencies
  - customers, suppliers, users
  - settings (all except sequence counters)

Usage:
  python reset_transactions.py

You will be asked to confirm before anything is deleted.
"""

import sys
import sqlite3
from pathlib import Path

# ── Locate the database ───────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DB_PATH  = BASE_DIR / "data" / "supermarket.db"

if not DB_PATH.exists():
    print(f"ERROR: Database not found at {DB_PATH}")
    sys.exit(1)

# ── Confirm ───────────────────────────────────────────────────────────────────
print("=" * 60)
print("  TRANSACTION RESET — Super POS")
print("=" * 60)
print(f"\nDatabase: {DB_PATH}\n")
print("This will permanently DELETE:")
print("  • All sales invoices and their items")
print("  • All purchase invoices and their items")
print("  • All warehouse transfers and their items")
print("  • All inventory sessions and their items")
print("  • All stock movements  (item quantities reset to 0)")
print("  • All payments, held invoices, audit logs")
print("  • All pending sync queue entries")
print("  • Invoice sequence counters (numbering restarts)\n")
print("This will KEEP:")
print("  • All items, barcodes, prices, categories, brands")
print("  • All warehouses, customers, suppliers, users")
print("  • All other settings\n")

answer = input("Type  YES  to confirm: ").strip()
if answer != "YES":
    print("Cancelled.")
    sys.exit(0)

# ── Execute ───────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys=OFF")
cur = conn.cursor()

TABLES_TO_DELETE = [
    # Order matters — children before parents
    "sales_invoice_items",
    "purchase_invoice_items",
    "warehouse_transfer_items",
    "inventory_session_items",
    "stock_movements",
    "payments",
    "held_invoices",
    "operator_sessions",
    "audit_logs",
    "sync_queue",
    "sales_invoices",
    "purchase_invoices",
    "warehouse_transfers",
    "inventory_sessions",
]

SEQUENCE_KEY_PATTERNS = [
    "next_sale_number",
    "next_purchase_number",
    "next_transfer_number",
    "next_inventory_number",
]

errors = []

print("\nDeleting transactions...")
for table in TABLES_TO_DELETE:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        cur.execute(f"DELETE FROM {table}")
        print(f"  ✔  {table:<35} ({count} rows deleted)")
    except Exception as e:
        print(f"  ✘  {table:<35} ERROR: {e}")
        errors.append((table, str(e)))

print("\nResetting item stock quantities to 0...")
try:
    cur.execute("SELECT COUNT(*) FROM item_stock WHERE quantity != 0")
    count = cur.fetchone()[0]
    cur.execute("UPDATE item_stock SET quantity = 0")
    print(f"  ✔  item_stock                        ({count} rows zeroed)")
except Exception as e:
    print(f"  ✘  item_stock                        ERROR: {e}")
    errors.append(("item_stock", str(e)))

print("\nResetting sequence counters...")
for pattern in SEQUENCE_KEY_PATTERNS:
    try:
        cur.execute(
            "SELECT COUNT(*) FROM settings WHERE key LIKE ?",
            (f"{pattern}%",)
        )
        count = cur.fetchone()[0]
        cur.execute(
            "DELETE FROM settings WHERE key LIKE ?",
            (f"{pattern}%",)
        )
        print(f"  ✔  settings LIKE '{pattern}%'  ({count} keys removed)")
    except Exception as e:
        print(f"  ✘  settings LIKE '{pattern}%'  ERROR: {e}")
        errors.append((pattern, str(e)))

conn.commit()
conn.execute("PRAGMA foreign_keys=ON")
conn.execute("VACUUM")
conn.close()

print("\n" + "=" * 60)
if errors:
    print(f"  Done with {len(errors)} error(s):")
    for t, e in errors:
        print(f"    {t}: {e}")
else:
    print("  Done. All transactions cleared successfully.")
print("=" * 60)

# ── Push reset to Supabase so other machines clean up their local copies ──────
print("\nPushing reset event to Supabase (so other machines sync the deletion)...")
try:
    # Need to load .env for Supabase credentials
    import os as _os
    from pathlib import Path as _Path
    _env = _Path(__file__).parent / ".env"
    if _env.exists():
        for _line in _env.read_text(encoding='utf-8', errors='ignore').splitlines():
            if "=" in _line and not _line.startswith("#"):
                _k, _, _v = _line.partition("=")
                _os.environ.setdefault(_k.strip(), _v.strip())

    from sync.service import push_branch_reset
    ok, err = push_branch_reset()
    if ok:
        print("  ✔  Supabase central tables cleared for this branch.")
    else:
        print(f"  ✘  Supabase push failed: {err}")
        print("     (Other machines will still remove deleted records on next sync)")
except Exception as _ex:
    print(f"  ✘  Could not push reset to Supabase: {_ex}")
    print("     (Other machines will still remove deleted records on next sync)")

print("\nYou can now start the program fresh.")
print("Item catalog is intact. Stock quantities are all 0.")
