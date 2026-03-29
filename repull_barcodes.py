"""
Re-pull ALL barcodes from item_barcodes_central into the local SQLite DB.
Uses cursor-based pagination (id > last_id) to bypass Supabase's 1000-row cap.

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

PAGE = 1000

def fetch_all_barcodes():
    """Cursor-based pagination — avoids Supabase max_rows=1000 cap."""
    rows = []
    last_id = "00000000-0000-0000-0000-000000000000"
    while True:
        url = (
            f"{SUPABASE_URL}/rest/v1/item_barcodes_central"
            f"?id=gt.{last_id}&order=id.asc&limit={PAGE}"
        )
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            print(f"\nERROR: HTTP {r.status_code} {r.text[:300]}")
            sys.exit(1)
        page = r.json()
        if not page:
            break
        rows.extend(page)
        last_id = page[-1]["id"]
        print(f"  Fetched {len(rows)} barcodes...", end="\r")
        if len(page) < PAGE:
            break
    print()
    return rows


from database.engine import get_session, init_db
from database.models.items import Item, ItemBarcode

init_db()
session = get_session()

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
    print(f"Done: {added} added, {updated} updated, {skipped} skipped (item not local).")
except Exception as e:
    session.rollback()
    print(f"ERROR: {e}")
finally:
    session.close()
