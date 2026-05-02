"""
Snapshot-based master data sync.

Main branch: generate_master_snapshot() serialises all items + prices +
barcodes + categories + brands to gzipped JSON and uploads the file to
Supabase Storage (bucket "master-data").

Branch machines: apply_master_snapshot() downloads the file, skips if
already up-to-date, then applies it atomically to the local SQLite DB
inside a single transaction with FK checks off.

The snapshot replaces the fragile cursor-based pull.  The old
pull_master_items / pull_item_prices_only functions are kept untouched
and serve as fallback when USE_SNAPSHOT_SYNC=false or when the snapshot
file does not exist yet.
"""
from __future__ import annotations

import gzip
import json
import sqlite3
from datetime import datetime, timezone

import requests

_BUCKET = "master-data"
_OBJECT = "snapshot.json.gz"


# ── internal helpers ──────────────────────────────────────────────────────────

def _base_url() -> str:
    from sync.service import SUPABASE_URL
    return f"{SUPABASE_URL}/storage/v1"


def _hdrs() -> dict:
    from sync.service import SUPABASE_KEY
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }


def _ensure_bucket() -> None:
    try:
        requests.post(
            f"{_base_url()}/bucket",
            headers={**_hdrs(), "Content-Type": "application/json"},
            json={"id": _BUCKET, "name": _BUCKET, "public": False},
            timeout=15,
        )
    except Exception:
        pass   # bucket already exists or network issue — upload will surface real errors


# ── public API ────────────────────────────────────────────────────────────────

def generate_master_snapshot() -> tuple[bool, str]:
    """
    Serialize the full item catalog from local SQLite and upload to Supabase
    Storage.  Called only on the main branch.  Returns (ok, error_str).
    """
    from sync.service import is_configured
    if not is_configured():
        return True, ""

    from database.engine import get_session, init_db
    from database.models.items import Brand, Category, Item, ItemBarcode, ItemPrice

    init_db()
    session = get_session()
    try:
        brands     = session.query(Brand).filter_by(is_active=True).all()
        categories = session.query(Category).filter_by(is_active=True).all()
        items      = session.query(Item).filter_by(is_active=True).all()
        item_ids   = [i.id for i in items]

        prices   = (session.query(ItemPrice)
                    .filter(ItemPrice.item_id.in_(item_ids)).all()) if item_ids else []
        barcodes = (session.query(ItemBarcode)
                    .filter(ItemBarcode.item_id.in_(item_ids)).all()) if item_ids else []

        def _ts(v) -> str:
            if v is None:
                return ""
            return v.isoformat() if hasattr(v, "isoformat") else str(v)

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "brands": [
                {"id": b.id, "name": b.name, "is_active": int(b.is_active),
                 "updated_at": _ts(b.updated_at)}
                for b in brands
            ],
            "categories": [
                {
                    "id": c.id, "name": c.name,
                    "parent_id":     c.parent_id    or "",
                    "sort_order":    c.sort_order,
                    "is_active":     int(c.is_active),
                    "show_in_daily": int(c.show_in_daily),
                    "show_on_touch": int(c.show_on_touch),
                    "show_on_home":  int(c.show_on_home),
                    "photo_url":     c.photo_url    or "",
                    "updated_at":    _ts(c.updated_at),
                }
                for c in categories
            ],
            "items": [
                {
                    "id": i.id, "code": i.code, "name": i.name,
                    "name_ar":       i.name_ar      or "",
                    "category_id":   i.category_id  or "",
                    "brand_id":      i.brand_id     or "",
                    "unit":          i.unit,
                    "pack_size":     i.pack_size,
                    "cost_price":    i.cost_price,
                    "cost_currency": i.cost_currency or "USD",
                    "vat_rate":      i.vat_rate,
                    "min_stock":     i.min_stock,
                    "is_active":        int(i.is_active),
                    "is_pos_featured":  int(i.is_pos_featured),
                    "is_online":        int(i.is_online),
                    "is_visible":       int(i.is_visible),
                    "is_featured":      int(i.is_featured),
                    "show_on_touch":    int(i.show_on_touch),
                    "photo_url":        i.photo_url  or "",
                    "notes":            i.notes      or "",
                    "updated_at":       _ts(i.updated_at),
                }
                for i in items
            ],
            "prices": [
                {
                    "id": p.id, "item_id": p.item_id,
                    "price_type": p.price_type,
                    "amount":     p.amount,
                    "currency":   p.currency,
                    "is_default": int(p.is_default),
                    "is_active":  int(p.is_active),
                    "pack_qty":   p.pack_qty,
                }
                for p in prices
            ],
            "barcodes": [
                {
                    "id": b.id, "item_id": b.item_id,
                    "barcode":    b.barcode,
                    "is_primary": int(b.is_primary),
                    "pack_qty":   b.pack_qty,
                }
                for b in barcodes
            ],
        }

        compressed = gzip.compress(
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            compresslevel=6,
        )

        _ensure_bucket()
        resp = requests.post(
            f"{_base_url()}/object/{_BUCKET}/{_OBJECT}",
            data=compressed,
            headers={
                **_hdrs(),
                "Content-Type": "application/octet-stream",
                "x-upsert":     "true",
            },
            timeout=60,
        )
        if resp.status_code not in (200, 201):
            return False, f"Upload {resp.status_code}: {resp.text[:300]}"
        return True, ""

    except Exception as exc:
        return False, str(exc)
    finally:
        session.close()


def apply_master_snapshot() -> tuple[int, str | None]:
    """
    Download the snapshot and apply it atomically to local SQLite.

    Return values:
      (count, None)  — count items applied (0 = already up-to-date)
      (-1,   None)   — snapshot file not found yet; caller should fallback
      (0,    str)    — error; caller should fallback
    """
    from sync.service import is_configured, _state_get, _state_set
    if not is_configured():
        return -1, None

    from config import LOCAL_DB_PATH

    try:
        resp = requests.get(
            f"{_base_url()}/object/{_BUCKET}/{_OBJECT}",
            headers=_hdrs(),
            timeout=60,
        )
        if resp.status_code == 404:
            return -1, None   # not generated yet
        if resp.status_code != 200:
            return 0, f"Download {resp.status_code}: {resp.text[:300]}"

        data         = json.loads(gzip.decompress(resp.content))
        generated_at = data.get("generated_at", "")
        last_applied = _state_get("snapshot_applied_at")

        if generated_at and generated_at <= last_applied:
            return 0, None   # already current

        brands     = data.get("brands",     [])
        categories = data.get("categories", [])
        items      = data.get("items",      [])
        prices     = data.get("prices",     [])
        barcodes   = data.get("barcodes",   [])
        now_str    = datetime.now(timezone.utc).isoformat()

        con = sqlite3.connect(str(LOCAL_DB_PATH))
        # High-performance pragmas for the raw connection
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA cache_size=-16000")
        
        cur = con.cursor()
        try:
            cur.execute("PRAGMA foreign_keys = OFF")
            con.execute("BEGIN")

            # ── Brands ────────────────────────────────────────────────────────
            if brands:
                brand_data = [
                    (b["id"], b["name"], b["is_active"], b.get("updated_at") or now_str, b.get("updated_at") or now_str)
                    for b in brands
                ]
                cur.executemany("""
                    INSERT INTO brands
                        (id, name, is_active,
                         created_at, updated_at, sync_status, local_version, remote_version)
                    VALUES (?,?,?,?,?,'synced',1,0)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name, is_active=excluded.is_active,
                        updated_at=excluded.updated_at
                """, brand_data)

            # ── Categories ────────────────────────────────────────────────────
            if categories:
                cat_data = [
                    (
                        c["id"], c["name"], c["parent_id"] or None,
                        c["sort_order"], c["is_active"],
                        c["show_in_daily"], c["show_on_touch"], c["show_on_home"],
                        c["photo_url"] or None, upd, upd
                    )
                    for c in categories
                    for upd in [c.get("updated_at") or now_str]
                ]
                cur.executemany("""
                    INSERT INTO categories
                        (id, name, parent_id, sort_order, is_active,
                         show_in_daily, show_on_touch, show_on_home, photo_url,
                         created_at, updated_at, sync_status, local_version, remote_version)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,'synced',1,0)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name, parent_id=excluded.parent_id,
                        sort_order=excluded.sort_order, is_active=excluded.is_active,
                        show_in_daily=excluded.show_in_daily,
                        show_on_touch=excluded.show_on_touch,
                        show_on_home=excluded.show_on_home,
                        photo_url=excluded.photo_url, updated_at=excluded.updated_at
                """, cat_data)

            # ── Items ─────────────────────────────────────────────────────────
            if items:
                item_data = [
                    (
                        i["id"], i["code"], i["name"], i["name_ar"] or None,
                        i["category_id"] or None, i["brand_id"] or None,
                        i["unit"], i["pack_size"],
                        i["cost_price"], i["cost_currency"] or "USD",
                        i["vat_rate"], i["min_stock"],
                        i["is_active"], i["is_pos_featured"], i["is_online"],
                        i["is_visible"], i["is_featured"], i["show_on_touch"],
                        i["photo_url"] or None, i["notes"] or None,
                        upd, upd
                    )
                    for i in items
                    for upd in [i.get("updated_at") or now_str]
                ]
                cur.executemany("""
                    INSERT INTO items
                        (id, code, name, name_ar, category_id, brand_id,
                         unit, pack_size, cost_price, cost_currency,
                         vat_rate, min_stock,
                         is_active, is_pos_featured, is_online,
                         is_visible, is_featured, show_on_touch,
                         photo_url, notes,
                         created_at, updated_at, sync_status, local_version, remote_version)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'synced',1,0)
                    ON CONFLICT(id) DO UPDATE SET
                        code=excluded.code, name=excluded.name,
                        name_ar=excluded.name_ar,
                        category_id=excluded.category_id,
                        brand_id=excluded.brand_id,
                        unit=excluded.unit, pack_size=excluded.pack_size,
                        cost_price=excluded.cost_price,
                        cost_currency=excluded.cost_currency,
                        vat_rate=excluded.vat_rate, min_stock=excluded.min_stock,
                        is_active=excluded.is_active,
                        is_pos_featured=excluded.is_pos_featured,
                        is_online=excluded.is_online,
                        is_visible=excluded.is_visible,
                        is_featured=excluded.is_featured,
                        show_on_touch=excluded.show_on_touch,
                        photo_url=excluded.photo_url, notes=excluded.notes,
                        updated_at=excluded.updated_at
                """, item_data)

            # ── Prices & Barcodes: delete + reinsert for all snapshot items ───
            item_ids = list({i["id"] for i in items})
            if item_ids:
                # Use a temp table for high-performance bulk deletion
                cur.execute("CREATE TEMPORARY TABLE temp_snap_ids (id TEXT PRIMARY KEY)")
                cur.executemany("INSERT INTO temp_snap_ids VALUES (?)", [(iid,) for iid in item_ids])
                
                if prices:
                    cur.execute("DELETE FROM item_prices WHERE item_id IN (SELECT id FROM temp_snap_ids)")
                    price_data = [
                        (p["id"], p["item_id"], p["price_type"], p["amount"], p["currency"],
                         p["is_default"], p["is_active"], p["pack_qty"], now_str, now_str)
                        for p in prices
                    ]
                    cur.executemany("""
                        INSERT OR IGNORE INTO item_prices
                            (id, item_id, price_type, amount, currency,
                             is_default, is_active, pack_qty,
                             created_at, updated_at, sync_status, local_version, remote_version)
                        VALUES (?,?,?,?,?,?,?,?,?,?,'synced',1,0)
                    """, price_data)

                if barcodes:
                    cur.execute("DELETE FROM item_barcodes WHERE item_id IN (SELECT id FROM temp_snap_ids)")
                    bc_data = [
                        (b["id"], b["item_id"], b["barcode"], b["is_primary"], b["pack_qty"], now_str, now_str)
                        for b in barcodes
                    ]
                    cur.executemany("""
                        INSERT OR IGNORE INTO item_barcodes
                            (id, item_id, barcode, is_primary, pack_qty,
                             created_at, updated_at)
                        VALUES (?,?,?,?,?,?,?)
                    """, bc_data)
                
                cur.execute("DROP TABLE temp_snap_ids")

            con.execute("COMMIT")

        except Exception:
            try:
                con.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            try:
                cur.execute("PRAGMA foreign_keys = ON")
            except Exception:
                pass
            con.close()

        _state_set("snapshot_applied_at", generated_at)
        return len(items), None

    except Exception as exc:
        return 0, str(exc)
