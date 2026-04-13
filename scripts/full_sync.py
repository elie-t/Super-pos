"""
Full item sync from Supabase — standalone, small batches, no sync service.
Usage: venv/Scripts/python scripts/full_sync.py
"""
import sys, sqlite3, json, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests, urllib3
urllib3.disable_warnings()

from dotenv import load_dotenv
load_dotenv()

URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_SERVICE_KEY")
HEADERS = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Prefer": ""}

DB_PATH = "data/supermarket.db"
BATCH = 100   # small to avoid huge responses


def get(table, params=None):
    r = requests.get(f"{URL}/rest/v1/{table}",
                     headers=HEADERS, params=params or {}, timeout=60, verify=False)
    r.raise_for_status()
    return r.json()


def main():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")

    # Load local lookup maps
    cats   = {r[0]: r[1] for r in db.execute("SELECT name, id FROM categories").fetchall()}
    brands = {r[0]: r[1] for r in db.execute("SELECT name, id FROM brands").fetchall()}

    # Count remote items
    r = requests.get(f"{URL}/rest/v1/items_central?select=id&limit=1",
                     headers={**HEADERS, "Range-Unit": "items", "Range": "0-0",
                              "Prefer": "count=exact"}, verify=False)
    total_remote = int(r.headers.get("content-range", "0/0").split("/")[-1])
    print(f"Supabase has {total_remote} items. Local has "
          f"{db.execute('SELECT COUNT(*) FROM items').fetchone()[0]}.")
    print(f"Fetching in batches of {BATCH}...\n")

    offset = 0
    imported = 0

    while True:
        rows = get("items_central", {
            "select": "id,code,name,name_ar,category,brand,unit,cost_price,"
                      "cost_currency,vat_rate,is_active,is_pos_featured,is_online,"
                      "show_on_touch,photo_url,notes,pack_size",
            "order": "id.asc",
            "limit": BATCH,
            "offset": offset,
        })
        if not rows:
            break

        ids = [r["id"] for r in rows]
        ids_csv = ",".join(ids)

        # Fetch prices for this batch
        prices = get("item_prices_central", {"item_id": f"in.({ids_csv})"})
        prices_by_item = {}
        for p in prices:
            prices_by_item.setdefault(p["item_id"], []).append(p)

        # Fetch barcodes for this batch
        barcodes = get("item_barcodes_central", {"item_id": f"in.({ids_csv})"})
        barcodes_by_item = {}
        for b in barcodes:
            barcodes_by_item.setdefault(b["item_id"], []).append(b)

        for ri in rows:
            item_id   = ri["id"]
            cat_name  = ri.get("category") or ""
            brand_name = ri.get("brand") or ""
            cat_id    = cats.get(cat_name)
            brand_id  = brands.get(brand_name)

            # Upsert item
            db.execute("""
                INSERT INTO items (id, code, name, name_ar, category_id, brand_id,
                    unit, pack_size, cost_price, cost_currency, vat_rate, is_active,
                    is_pos_featured, is_online, show_on_touch, photo_url, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    code=excluded.code, name=excluded.name, name_ar=excluded.name_ar,
                    category_id=excluded.category_id, brand_id=excluded.brand_id,
                    unit=excluded.unit, pack_size=excluded.pack_size,
                    cost_price=excluded.cost_price, cost_currency=excluded.cost_currency,
                    vat_rate=excluded.vat_rate, is_active=excluded.is_active,
                    is_pos_featured=excluded.is_pos_featured, is_online=excluded.is_online,
                    show_on_touch=excluded.show_on_touch, photo_url=excluded.photo_url,
                    notes=excluded.notes
            """, (item_id, ri.get("code",""), ri.get("name",""), ri.get("name_ar",""),
                  cat_id, brand_id, ri.get("unit","PCS"), ri.get("pack_size",1),
                  ri.get("cost_price",0), ri.get("cost_currency","USD"),
                  ri.get("vat_rate",0), 1 if ri.get("is_active",True) else 0,
                  1 if ri.get("is_pos_featured") else 0,
                  1 if ri.get("is_online") else 0,
                  1 if ri.get("show_on_touch") else 0,
                  ri.get("photo_url",""), ri.get("notes","")))

            # Upsert prices
            for p in prices_by_item.get(item_id, []):
                db.execute("""
                    INSERT INTO item_prices (id, item_id, price_type, amount, currency,
                        is_default, is_active, pack_qty)
                    VALUES (?,?,?,?,?,1,1,?)
                    ON CONFLICT(id) DO UPDATE SET
                        price_type=excluded.price_type, amount=excluded.amount,
                        currency=excluded.currency, pack_qty=excluded.pack_qty
                """, (p["id"], item_id, p["price_type"], p["amount"],
                      p.get("currency","USD"), p.get("pack_qty",1)))

            # Upsert barcodes
            for b in barcodes_by_item.get(item_id, []):
                existing_conflict = db.execute(
                    "SELECT item_id FROM item_barcodes WHERE barcode=? AND item_id!=?",
                    (b["barcode"], item_id)).fetchone()
                if existing_conflict:
                    continue
                db.execute("""
                    INSERT INTO item_barcodes (id, item_id, barcode, is_primary, pack_qty)
                    VALUES (?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                        barcode=excluded.barcode, is_primary=excluded.is_primary,
                        pack_qty=excluded.pack_qty
                """, (b["id"], item_id, b["barcode"],
                      1 if b.get("is_primary") else 0, b.get("pack_qty",1)))

        db.commit()
        imported += len(rows)
        offset += BATCH
        print(f"  {imported}/{total_remote} items synced...")

        if len(rows) < BATCH:
            break

    count = db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    db.close()
    print(f"\nDone. Local DB now has {count} items.")


if __name__ == "__main__":
    main()
