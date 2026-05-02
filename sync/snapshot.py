"""
Snapshot-based master data sync.

Main branch: generate_master_snapshot() serialises all items + prices +
barcodes + categories + brands to gzipped JSON and uploads the file to
Supabase Storage (bucket "master-data").

Branches: apply_master_snapshot() downloads the file and applies it to
the local SQLite database atomically (Wipe and Reload).
"""
import json
import gzip
import sqlite3
import requests
from datetime import datetime, timezone

_BUCKET = "master-data"
_OBJECT = "snapshot.json.gz"

def _base_url():
    from config import SUPABASE_URL
    return f"{SUPABASE_URL}/storage/v1"

def _hdrs():
    from config import SUPABASE_KEY
    return {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "apikey": SUPABASE_KEY,
    }

def generate_master_snapshot():
    """Main branch only: generate and upload the master data snapshot."""
    from database.engine import get_session, init_db
    from database.models.items import Item, ItemPrice, ItemBarcode, Category, Brand
    
    init_db()
    session = get_session()
    try:
        # Fetch all active data
        brands     = [dict(id=b.id, name=b.name, is_active=b.is_active, updated_at=b.updated_at.isoformat()) for b in session.query(Brand).all()]
        categories = [dict(id=c.id, name=c.name, parent_id=c.parent_id, sort_order=c.sort_order, is_active=c.is_active, show_in_daily=c.show_in_daily, show_on_touch=c.show_on_touch, show_on_home=c.show_on_home, photo_url=c.photo_url, updated_at=c.updated_at.isoformat()) for c in session.query(Category).all()]
        items      = [dict(id=i.id, code=i.code, name=i.name, name_ar=i.name_ar, category_id=i.category_id, brand_id=i.brand_id, unit=i.unit, pack_size=i.pack_size, cost_price=float(i.cost_price or 0), cost_currency=i.cost_currency, vat_rate=float(i.vat_rate or 0), min_stock=float(i.min_stock or 0), is_active=i.is_active, is_pos_featured=i.is_pos_featured, is_online=i.is_online, is_visible=i.is_visible, is_featured=i.is_featured, show_on_touch=i.show_on_touch, photo_url=i.photo_url, notes=i.notes, updated_at=i.updated_at.isoformat()) for i in session.query(Item).all()]
        prices     = [dict(id=p.id, item_id=p.item_id, price_type=p.price_type, amount=float(p.amount), currency=p.currency, is_default=p.is_default, is_active=p.is_active, pack_qty=p.pack_qty) for p in session.query(ItemPrice).all()]
        barcodes   = [dict(id=b.id, item_id=b.item_id, barcode=b.barcode, is_primary=b.is_primary, pack_qty=b.pack_qty) for b in session.query(ItemBarcode).all()]

        data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "brands":     brands,
            "categories": categories,
            "items":      items,
            "prices":     prices,
            "barcodes":   barcodes,
        }
        
        # Compress and upload
        payload = gzip.compress(json.dumps(data).encode("utf-8"))
        
        url = f"{_base_url()}/object/{_BUCKET}/{_OBJECT}"
        resp = requests.post(
            url,
            headers={**_hdrs(), "Content-Type": "application/gzip"},
            data=payload,
        )
        if resp.status_code != 200:
            # Try PUT if POST fails (exists)
            requests.put(url, headers=_hdrs(), data=payload)

    finally:
        session.close()


def apply_master_snapshot() -> tuple[int, str | None]:
    """
    Download the snapshot and apply it atomically to local SQLite.
    """
    from sync.service import is_configured, _state_get, _state_set
    if not is_configured():
        return -1, None

    from config import LOCAL_DB_PATH, DATA_DIR
    import time
    
    log_path = DATA_DIR / "sync_debug.log"
    def _log(msg):
        try:
            with open(log_path, "a") as f:
                f.write(f"[{datetime.now().isoformat()}] {msg}\n")
        except Exception:
            pass

    try:
        _log("Starting snapshot download...")
        start_t = time.time()
        
        resp = requests.get(
            f"{_base_url()}/object/{_BUCKET}/{_OBJECT}",
            headers=_hdrs(),
            timeout=120,
        )
        if resp.status_code == 404:
            _log("Snapshot not found (404)")
            return -1, None
        if resp.status_code != 200:
            _log(f"Download failed: {resp.status_code}")
            return 0, f"Download {resp.status_code}: {resp.text[:300]}"

        dl_t = time.time() - start_t
        _log(f"Download finished in {dl_t:.2f}s. Size: {len(resp.content)} bytes")

        # Save to disk for user verification
        snap_file = DATA_DIR / "last_snapshot.json.gz"
        try:
            with open(snap_file, "wb") as f:
                f.write(resp.content)
            _log(f"Snapshot saved to {snap_file}")
        except Exception as e:
            _log(f"Warning: Could not save snapshot file to disk: {e}")

        _log("Decompressing and parsing JSON...")
        data         = json.loads(gzip.decompress(resp.content))
        generated_at = data.get("generated_at", "")
        last_applied = _state_get("snapshot_applied_at")

        if generated_at and generated_at <= last_applied:
            _log("Snapshot already up-to-date")
            return 0, None

        brands     = data.get("brands",     [])
        categories = data.get("categories", [])
        items      = data.get("items",      [])
        prices     = data.get("prices",     [])
        barcodes   = data.get("barcodes",   [])
        now_str    = datetime.now(timezone.utc).isoformat()
        
        _log(f"Processing data: {len(items)} items, {len(prices)} prices...")

        con = sqlite3.connect(str(LOCAL_DB_PATH))
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=OFF")
        con.execute("PRAGMA cache_size=-64000")
        
        cur = con.cursor()
        try:
            cur.execute("PRAGMA foreign_keys = OFF")
            con.execute("BEGIN")

            # ── Brands ────────────────────────────────────────────────────────
            if brands:
                _log("Wiping and reloading Brands...")
                cur.execute("DELETE FROM brands")
                brand_data = [
                    (b["id"], b["name"], b["is_active"], b.get("updated_at") or now_str, b.get("updated_at") or now_str)
                    for b in brands
                ]
                cur.executemany("INSERT INTO brands (id, name, is_active, created_at, updated_at, sync_status, local_version, remote_version) VALUES (?,?,?,?,?,'synced',1,0)", brand_data)

            # ── Categories ────────────────────────────────────────────────────
            if categories:
                _log("Wiping and reloading Categories...")
                cur.execute("DELETE FROM categories")
                cat_data = [
                    (
                        c["id"], c["name"], c["parent_id"] or None,
                        c["sort_order"], c["is_active"],
                        c["show_in_daily"], c["show_on_touch"], c["show_on_home"],
                        c["photo_url"] or None, c.get("updated_at") or now_str, c.get("updated_at") or now_str
                    )
                    for c in categories
                ]
                cur.executemany("INSERT INTO categories (id, name, parent_id, sort_order, is_active, show_in_daily, show_on_touch, show_on_home, photo_url, created_at, updated_at, sync_status, local_version, remote_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,'synced',1,0)", cat_data)

            # ── Items ─────────────────────────────────────────────────────────
            if items:
                _log("Wiping and reloading Items...")
                cur.execute("DELETE FROM items")
                item_data = [
                    (
                        i["id"], i["code"], i["name"], i["name_ar"] or None,
                        i["category_id"] or None, i["brand_id"] or None,
                        i["unit"], i["pack_size"],
                        i["cost_price"], i["cost_currency"] or "USD",
                        i["vat_rate"], i["min_stock"],
                        i["is_active"], i["is_pos_featured"], i["is_online"],
                        i["is_visible"], i["is_featured"], i.get("show_on_touch", 0),
                        i["photo_url"] or None, i["notes"] or None,
                        i.get("updated_at") or now_str, i.get("updated_at") or now_str
                    )
                    for i in items
                ]
                for start in range(0, len(item_data), 2000):
                    cur.executemany("INSERT INTO items (id, code, name, name_ar, category_id, brand_id, unit, pack_size, cost_price, cost_currency, vat_rate, min_stock, is_active, is_pos_featured, is_online, is_visible, is_featured, show_on_touch, photo_url, notes, created_at, updated_at, sync_status, local_version, remote_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'synced',1,0)", item_data[start:start+2000])

            # ── Prices ────────────────────────────────────────────────────────
            if prices:
                _log("Wiping and reloading Prices...")
                cur.execute("DELETE FROM item_prices")
                price_data = [
                    (p["id"], p["item_id"], p["price_type"], p["amount"], p["currency"],
                     p["is_default"], p["is_active"], p["pack_qty"], now_str, now_str)
                    for p in prices
                ]
                for start in range(0, len(price_data), 2000):
                    cur.executemany("INSERT OR IGNORE INTO item_prices (id, item_id, price_type, amount, currency, is_default, is_active, pack_qty, created_at, updated_at, sync_status, local_version, remote_version) VALUES (?,?,?,?,?,?,?,?,?,?,'synced',1,0)", price_data[start:start+2000])

            # ── Barcodes ──────────────────────────────────────────────────────
            if barcodes:
                _log("Wiping and reloading Barcodes...")
                cur.execute("DELETE FROM item_barcodes")
                bc_data = [
                    (b["id"], b["item_id"], b["barcode"], b["is_primary"], b["pack_qty"], now_str, now_str)
                    for b in barcodes
                ]
                for start in range(0, len(bc_data), 2000):
                    cur.executemany("INSERT OR IGNORE INTO item_barcodes (id, item_id, barcode, is_primary, pack_qty, created_at, updated_at) VALUES (?,?,?,?,?,?,?)", bc_data[start:start+2000])

            _log("Committing transaction...")
            con.execute("COMMIT")
            _log("Sync complete!")

        except Exception as e:
            _log(f"Database error: {e}")
            try: con.execute("ROLLBACK")
            except Exception: pass
            raise e
        finally:
            try: cur.execute("PRAGMA foreign_keys = ON")
            except Exception: pass
            con.close()

        _state_set("snapshot_applied_at", generated_at)
        return len(items), None

    except Exception as exc:
        _log(f"Critical error: {exc}")
        return 0, str(exc)
