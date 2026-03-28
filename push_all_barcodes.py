"""
Push ALL barcodes (and items + prices) from local SQLite to Supabase central.
Run this on the MAC to do a full initial push of the entire catalog.

Usage:
    python push_all_barcodes.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
BRANCH_ID    = os.getenv("BRANCH_ID", "default")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_KEY not set in .env")
    sys.exit(1)

HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "resolution=merge-duplicates",
}

BATCH = 200   # rows per request

def upsert_batch(table: str, rows: list[dict]) -> str | None:
    """Returns error string or None on success."""
    if not rows:
        return None
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=HEADERS,
        json=rows,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        return f"HTTP {r.status_code}: {r.text[:300]}"
    return None

def push_in_batches(table: str, rows: list[dict], label: str):
    total = len(rows)
    done = 0
    for i in range(0, total, BATCH):
        batch = rows[i:i+BATCH]
        err = upsert_batch(table, batch)
        if err:
            print(f"  ERROR on {label} batch {i}-{i+len(batch)}: {err}")
            return False
        done += len(batch)
        print(f"  {label}: {done}/{total}", end="\r")
    print(f"  {label}: {total}/{total} ✓")
    return True


from database.engine import get_session, init_db
from database.models.items import Item, ItemPrice, ItemBarcode

init_db()
session = get_session()

now = datetime.now(timezone.utc).isoformat()

try:
    items    = session.query(Item).filter_by(is_active=True).all()
    prices   = session.query(ItemPrice).all()
    barcodes = session.query(ItemBarcode).all()

    print(f"Local DB: {len(items)} items, {len(prices)} prices, {len(barcodes)} barcodes")
    print("Pushing to Supabase...\n")

    # Items
    item_rows = []
    for item in items:
        cat_name   = item.category.name  if item.category else ""
        brand_name = item.brand.name     if item.brand    else ""
        item_rows.append({
            "id": item.id, "code": item.code or "", "name": item.name or "",
            "name_ar": item.name_ar or "", "unit": item.unit or "PCS",
            "cost_price": item.cost_price or 0, "cost_currency": item.cost_currency or "USD",
            "vat_rate": item.vat_rate or 0, "is_active": item.is_active,
            "is_online": item.is_online or False, "is_pos_featured": item.is_pos_featured or False,
            "photo_url": item.photo_url or "", "notes": item.notes or "",
            "category": cat_name, "brand": brand_name,
            "updated_at": now, "pushed_by": BRANCH_ID,
        })
    if not push_in_batches("items_central", item_rows, "Items"):
        sys.exit(1)

    # Prices
    price_rows = [
        {
            "id": p.id, "item_id": p.item_id,
            "price_type": p.price_type, "amount": p.amount,
            "currency": p.currency, "updated_at": now,
        }
        for p in prices
    ]
    if not push_in_batches("item_prices_central", price_rows, "Prices"):
        sys.exit(1)

    # Barcodes
    bc_rows = [
        {
            "id": b.id, "item_id": b.item_id,
            "barcode": b.barcode, "is_primary": b.is_primary,
            "pack_qty": b.pack_qty or 1, "updated_at": now,
        }
        for b in barcodes
    ]
    if not push_in_batches("item_barcodes_central", bc_rows, "Barcodes"):
        sys.exit(1)

    print("\nFull push complete!")

finally:
    session.close()
