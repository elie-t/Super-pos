"""
Diagnose and fix duplicate/conflicting barcodes in the local SQLite DB.
Run this on the PC to see which barcodes are conflicting and remove the bad ones.

Usage:
    python fix_barcode_conflicts.py          # show conflicts only
    python fix_barcode_conflicts.py --fix    # actually remove the conflicting rows
"""
import sys
import os

# Add the project root to path
sys.path.insert(0, os.path.dirname(__file__))

from database.engine import get_session, init_db
from database.models.items import Item, ItemBarcode
from sqlalchemy import func

init_db()
session = get_session()

FIX = "--fix" in sys.argv

# Find all barcodes where the same value (case-insensitive) belongs to multiple items
from sqlalchemy import func as sa_func

all_barcodes = session.query(ItemBarcode).all()

# Group by lowercase barcode value
from collections import defaultdict
groups: dict[str, list] = defaultdict(list)
for bc in all_barcodes:
    groups[bc.barcode.strip().lower()].append(bc)

conflicts = {k: v for k, v in groups.items() if len(v) > 1}

if not conflicts:
    print("No conflicting barcodes found.")
    session.close()
    sys.exit(0)

print(f"Found {len(conflicts)} conflicting barcode value(s):\n")

for bc_val, rows in sorted(conflicts.items()):
    print(f"  Barcode '{bc_val}':")
    for bc in rows:
        item = session.get(Item, bc.item_id)
        item_name = item.name if item else "(missing item)"
        item_code = item.code if item else "?"
        print(f"    id={bc.id}  item_code={item_code}  item_name={item_name}  is_primary={bc.is_primary}  pack_qty={bc.pack_qty}")

if FIX:
    print("\n--- FIXING ---")
    print("For each conflict, keeping the FIRST barcode (by insertion order).")
    print("To keep a specific one, edit this script.\n")
    removed = 0
    for bc_val, rows in sorted(conflicts.items()):
        # Keep the first row (oldest / local), remove the rest
        keeper = rows[0]
        item = session.get(Item, keeper.item_id)
        print(f"  Keeping barcode '{bc_val}' → {item.name if item else '?'} (id={keeper.id})")
        for bc in rows[1:]:
            item2 = session.get(Item, bc.item_id)
            print(f"  Removing barcode id={bc.id} → {item2.name if item2 else '?'}")
            session.delete(bc)
            removed += 1
    session.commit()
    print(f"\nRemoved {removed} conflicting barcode row(s).")
else:
    print("\nRun with --fix to remove the duplicate rows.")
    print("Example: python fix_barcode_conflicts.py --fix")

session.close()
