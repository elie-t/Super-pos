"""
Add barcode 'E' back to bread (and other items missing their shortcuts).
Edit the SHORTCUTS list below to match your local barcodes.

Usage:
    python fix_bread_barcode.py          # dry run (show what will be added)
    python fix_bread_barcode.py --fix    # actually add them
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database.engine import get_session, init_db
from database.models.items import Item, ItemBarcode
from database.models.base import new_uuid
from sqlalchemy import func as sa_func

# ── Edit this list: (barcode_value, item_name_contains) ──────────────────────
SHORTCUTS = [
    ("E", "bread"),
    ("W", "water"),
    # add more if needed: ("X", "item name"),
]
# ─────────────────────────────────────────────────────────────────────────────

FIX = "--fix" in sys.argv

init_db()
session = get_session()

for bc_value, name_contains in SHORTCUTS:
    # Find the item
    item = session.query(Item).filter(
        Item.name.ilike(f"%{name_contains}%"),
        Item.is_active == True,
    ).first()

    if not item:
        print(f"  [SKIP] No active item found with name containing '{name_contains}'")
        continue

    # Check if barcode already exists (case-insensitive)
    existing = session.query(ItemBarcode).filter(
        sa_func.lower(sa_func.trim(ItemBarcode.barcode)) == bc_value.lower()
    ).first()

    if existing:
        existing_item = session.get(Item, existing.item_id)
        print(f"  [SKIP] Barcode '{bc_value}' already exists → {existing_item.name if existing_item else '?'}")
        continue

    print(f"  [ADD] barcode='{bc_value}' → {item.name} (id={item.id})")
    if FIX:
        bc = ItemBarcode(
            id=new_uuid(),
            item_id=item.id,
            barcode=bc_value,
            is_primary=False,
            pack_qty=1,
        )
        session.add(bc)

if FIX:
    session.commit()
    print("\nDone. Barcodes added.")
else:
    print("\nDry run. Run with --fix to apply.")

session.close()
