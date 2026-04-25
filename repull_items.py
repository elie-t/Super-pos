"""
Re-pull ALL items + prices + barcodes from Supabase central into local SQLite.
Uses cursor-based pagination to bypass the 1000-row cap.
Run this on the PC to get the full catalog.

Usage:
    python repull_items.py
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

def fetch_all(table: str, label: str) -> list[dict]:
    import time
    rows = []
    last_id = "00000000-0000-0000-0000-000000000000"
    while True:
        url = f"{SUPABASE_URL}/rest/v1/{table}?id=gt.{last_id}&order=id.asc&limit={PAGE}"
        page = None
        for attempt in range(1, 6):  # up to 5 retries
            try:
                r = requests.get(url, headers=HEADERS, timeout=60)
                if r.status_code != 200:
                    print(f"\n  [{label}] HTTP {r.status_code} (attempt {attempt}/5) — retrying...")
                    time.sleep(attempt * 3)
                    continue
                page = r.json()
                break
            except Exception as e:
                print(f"\n  [{label}] Network error (attempt {attempt}/5): {e} — retrying...")
                time.sleep(attempt * 3)
        if page is None:
            print(f"\nERROR: {label} failed after 5 attempts. Run the script again to resume.")
            sys.exit(1)
        if not page:
            break
        rows.extend(page)
        last_id = page[-1]["id"]
        print(f"  {label}: fetched {len(rows)}...", end="\r")
        if len(page) < PAGE:
            break
    print(f"  {label}: {len(rows)} total        ")
    return rows


from sqlalchemy import func as sa_func
from database.engine import get_session, init_db
from database.models.items import Item, ItemPrice, ItemBarcode, Category, Brand
from database.models.base import new_uuid

init_db()
session = get_session()

# ── Fetch everything ────────────────────────────────────────────────────────
print("Fetching from Supabase...")
remote_items    = fetch_all("items_central",        "Items")
remote_prices   = fetch_all("item_prices_central",  "Prices")
remote_barcodes = fetch_all("item_barcodes_central","Barcodes")

# Index prices and barcodes by item_id for fast lookup
prices_by_item:   dict[str, list] = {}
barcodes_by_item: dict[str, list] = {}
for p in remote_prices:
    prices_by_item.setdefault(p["item_id"], []).append(p)
for b in remote_barcodes:
    barcodes_by_item.setdefault(b["item_id"], []).append(b)

# ── Upsert into local SQLite ─────────────────────────────────────────────────
cats   = {c.name: c.id for c in session.query(Category).all()}
brands = {b.name: b.id for b in session.query(Brand).all()}

items_done = prices_done = barcodes_done = 0

try:
    for ri in remote_items:
        code_str = ri.get("code") or ri["id"][:12]
        item = session.get(Item, ri["id"])
        if not item:
            # Check for code collision — another local row already has this code
            existing = session.query(Item).filter_by(code=code_str).first()
            if existing:
                # Update the existing row in-place instead of inserting a duplicate
                item = existing
            else:
                item = Item(id=ri["id"])
                session.add(item)

        item.code            = code_str
        item.name            = ri.get("name") or ri.get("code") or ri["id"][:12]
        item.name_ar         = ri.get("name_ar") or ""
        item.unit            = ri.get("unit") or "PCS"
        item.cost_price      = ri.get("cost_price") or 0
        item.cost_currency   = ri.get("cost_currency") or "USD"
        item.vat_rate        = ri.get("vat_rate") or 0
        item.is_active       = ri.get("is_active", True)
        item.is_online       = ri.get("is_online", False)
        item.is_pos_featured = ri.get("is_pos_featured", False)
        item.photo_url       = ri.get("photo_url") or ""
        item.notes           = ri.get("notes") or ""
        item.category_id     = cats.get(ri.get("category") or "")
        item.brand_id        = brands.get(ri.get("brand") or "")
        items_done += 1

        for rp in prices_by_item.get(ri["id"], []):
            price = session.get(ItemPrice, rp["id"])
            if not price:
                price = ItemPrice(id=rp["id"], item_id=ri["id"])
                session.add(price)
            price.price_type = rp["price_type"]
            price.amount     = rp["amount"]
            price.currency   = rp["currency"]
            price.pack_qty   = int(rp.get("pack_qty") or 1)
            prices_done += 1

        local_item_id = item.id  # may differ from ri["id"] on code-collision merges
        for rb in barcodes_by_item.get(ri["id"], []):
            bc = session.get(ItemBarcode, rb["id"])
            if not bc:
                # Check for barcode value conflict (UNIQUE constraint on barcode column)
                conflict = session.query(ItemBarcode).filter(
                    sa_func.lower(ItemBarcode.barcode) == rb["barcode"].lower()
                ).first()
                if conflict:
                    conflict.item_id    = local_item_id
                    conflict.is_primary = rb.get("is_primary", False)
                    conflict.pack_qty   = rb.get("pack_qty", 1)
                    barcodes_done += 1
                    continue
                bc = ItemBarcode(id=rb["id"], item_id=local_item_id)
                session.add(bc)
            bc.barcode    = rb["barcode"]
            bc.is_primary = rb.get("is_primary", False)
            bc.pack_qty   = rb.get("pack_qty", 1)
            barcodes_done += 1

        if items_done % 500 == 0:
            session.commit()
            print(f"  Saved {items_done} items...", end="\r")

    session.commit()
    print(f"\nDone!")
    print(f"  Items:    {items_done}")
    print(f"  Prices:   {prices_done}")
    print(f"  Barcodes: {barcodes_done}")

    # Reset sync cursors so the next incremental pull starts from now
    from sync.service import _state_set
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    _state_set("items_pull",         now)
    _state_set("items_pull_last_id", "")
    _state_set("item_prices_pull",   now)
    print(f"  Sync cursors reset to {now}")

except Exception as e:
    session.rollback()
    print(f"ERROR: {e}")
    import traceback; traceback.print_exc()
finally:
    session.close()
