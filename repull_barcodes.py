"""
Re-pull ALL barcodes from item_barcodes_central into the local SQLite DB.
Useful when local barcodes were lost or corrupted after a sync.

Fetches in pages of 1000. Skips barcodes whose item_id doesn't exist locally.

Usage:
    python repull_barcodes.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_KEY not set in .env")
    sys.exit(1)

HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "",
}

def fetch_all_barcodes():
    rows = []
    offset = 0
    page_size = 1000
    while True:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/item_barcodes_central"
            f"?order=id.asc&limit={page_size}&offset={offset}",
            headers=HEADERS,
            timeout=30,
        )
        if r.status_code != 200:
            print(f"ERROR fetching barcodes: HTTP {r.status_code} {r.text[:200]}")
            sys.exit(1)
        page = r.json()
        rows.extend(page)
        print(f"  Fetched {len(rows)} barcodes so far...")
        if len(page) < page_size:
            break
        offset += page_size
    return rows

from database.engine import get_session, init_db
from database.models.items import Item, ItemBarcode
from database.models.base import new_uuid

init_db()
session = get_session()

# Build set of local item IDs for fast lookup
local_item_ids = {str(r[0]) for r in session.query(Item.id).all()}
print(f"Local items: {len(local_item_ids)}")

print("Fetching all barcodes from Supabase...")
remote_barcodes = fetch_all_barcodes()
print(f"Total remote barcodes: {len(remote_barcodes)}")

added = updated = skipped = 0

try:
    for rb in remote_barcodes:
        item_id = rb.get("item_id")
        if item_id not in local_item_ids:
            skipped += 1
            continue

        bc = session.get(ItemBarcode, rb["id"])
        if not bc:
            bc = ItemBarcode(id=rb["id"], item_id=item_id)
            session.add(bc)
            added += 1
        else:
            updated += 1

        bc.barcode    = rb["barcode"]
        bc.is_primary = rb.get("is_primary", False)
        bc.pack_qty   = rb.get("pack_qty", 1)

    session.commit()
    print(f"\nDone: {added} added, {updated} updated, {skipped} skipped (item not local).")
except Exception as e:
    session.rollback()
    print(f"ERROR: {e}")
finally:
    session.close()
