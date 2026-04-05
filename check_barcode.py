"""
Check what a barcode maps to, and what barcodes an item has.
Usage:
    python check_barcode.py e
    python check_barcode.py w
    python check_barcode.py "bread"     # search by item name
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database.engine import get_session, init_db
from database.models.items import Item, ItemBarcode
from sqlalchemy import func as sa_func

init_db()
session = get_session()

query = sys.argv[1] if len(sys.argv) > 1 else "e"

# 1. What does this barcode map to?
print(f"\n=== Barcode lookup for '{query}' ===")
matches = session.query(ItemBarcode).filter(
    sa_func.lower(sa_func.trim(ItemBarcode.barcode)) == query.strip().lower()
).all()
if matches:
    for bc in matches:
        item = session.get(Item, bc.item_id)
        print(f"  barcode='{bc.barcode}'  item_id={bc.item_id}  item_name={item.name if item else '(missing)'}  is_active={item.is_active if item else '?'}  is_primary={bc.is_primary}")
else:
    print(f"  No barcode found for '{query}'")

# 2. Search items by name containing query
print(f"\n=== Items with name containing '{query}' ===")
items = session.query(Item).filter(Item.name.ilike(f"%{query}%")).all()
if items:
    for item in items:
        barcodes = session.query(ItemBarcode).filter_by(item_id=item.id).all()
        bc_list = [(b.barcode, b.is_primary, b.pack_qty) for b in barcodes]
        print(f"  [{item.code}] {item.name}  is_active={item.is_active}  barcodes={bc_list}")
else:
    print(f"  No items found with name containing '{query}'")

session.close()
