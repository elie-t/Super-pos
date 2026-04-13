"""
Full item sync from Supabase — wipes local items and re-imports from scratch.
Usage: venv/Scripts/python scripts/full_sync.py
"""
import sys, sqlite3, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests, urllib3
urllib3.disable_warnings()

# Monkey-patch to disable SSL verification globally (Windows cert issue)
_orig_request = requests.Session.request
def _no_verify(self, method, url, **kwargs):
    kwargs["verify"] = False
    return _orig_request(self, method, url, **kwargs)
requests.Session.request = _no_verify

from dotenv import load_dotenv
load_dotenv()

URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_SERVICE_KEY")
HEADERS = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}

DB_PATH = "data/supermarket.db"
BATCH = 200


def get(table, params=None):
    r = requests.get(f"{URL}/rest/v1/{table}",
                     headers=HEADERS, params=params or {}, timeout=60)
    r.raise_for_status()
    return r.json()


def main():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=OFF")

    # Load local lookup maps
    cats   = {r[0]: r[1] for r in db.execute("SELECT name, id FROM categories").fetchall()}
    brands = {r[0]: r[1] for r in db.execute("SELECT name, id FROM brands").fetchall()}

    # Count remote items
    r = requests.get(f"{URL}/rest/v1/items_central?select=id&limit=1",
                     headers={**HEADERS, "Range-Unit": "items", "Range": "0-0",
                              "Prefer": "count=exact"})
    total_remote = int(r.headers.get("content-range", "0/0").split("/")[-1])
    print(f"Supabase has {total_remote} items.")
    print(f"Wiping local items, prices, barcodes...")

    db.execute("DELETE FROM item_barcodes")
    db.execute("DELETE FROM item_prices")
    db.execute("DELETE FROM items")
    db.commit()
    print("Wiped. Starting import...\n")

    offset = 0
    imported = 0

    while True:
        rows = get("items_central", {
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
            item_id    = ri["id"]
            cat_name   = ri.get("category") or ""
            brand_name = ri.get("brand") or ""
            cat_id     = cats.get(cat_name)
            brand_id   = brands.get(brand_name)

            db.execute("""
                INSERT OR IGNORE INTO items
                    (id, code, name, name_ar, category_id, brand_id,
                     unit, pack_size, cost_price, cost_currency, vat_rate, min_stock,
                     is_active, is_pos_featured, is_online, is_visible, is_featured,
                     show_on_touch, photo_url, notes,
                     sync_status, local_version, remote_version)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (item_id, ri.get("code",""), ri.get("name",""), ri.get("name_ar",""),
                  cat_id, brand_id,
                  ri.get("unit","PCS"), 1,
                  ri.get("cost_price") or 0, ri.get("cost_currency","USD"),
                  ri.get("vat_rate") or 0, 0,
                  1 if ri.get("is_active", True) else 0,
                  1 if ri.get("is_pos_featured") else 0,
                  1 if ri.get("is_online") else 0,
                  1, 0,
                  1 if ri.get("show_on_touch") else 0,
                  ri.get("photo_url") or "", ri.get("notes") or "",
                  "synced", 1, 1))

            for p in prices_by_item.get(item_id, []):
                db.execute("""
                    INSERT OR IGNORE INTO item_prices
                        (id, item_id, price_type, amount, currency,
                         is_default, is_active, pack_qty,
                         sync_status, local_version, remote_version)
                    VALUES (?,?,?,?,?,1,1,?,?,?,?)
                """, (p["id"], item_id, p["price_type"], p["amount"],
                      p.get("currency","USD"), p.get("pack_qty",1),
                      "synced", 1, 1))

            for b in barcodes_by_item.get(item_id, []):
                db.execute("""
                    INSERT OR IGNORE INTO item_barcodes
                        (id, item_id, barcode, is_primary, pack_qty)
                    VALUES (?,?,?,?,?)
                """, (b["id"], item_id, b["barcode"],
                      1 if b.get("is_primary") else 0, b.get("pack_qty",1)))

        db.commit()
        imported += len(rows)
        offset   += BATCH
        print(f"  {imported}/{total_remote} items imported...")

        if len(rows) < BATCH:
            break

    db.execute("PRAGMA foreign_keys=ON")
    count = db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    db.close()
    print(f"\nDone. Local DB now has {count} items.")


if __name__ == "__main__":
    main()
