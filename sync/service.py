"""
Sync Service — pushes local data to Supabase, pulls master data down.

Uses the Supabase REST API (no extra library needed — plain requests).
Credentials come from .env / config.

Bidirectional sync:
  Push ↑  items_central, item_prices_central, item_barcodes_central,
          customers_central, sales_invoices_central, stock_levels,
          products (online catalog for mobile app)
  Pull ↓  items_central → local items
          item_prices_central → local item_prices
          item_barcodes_central → local item_barcodes
          customers_central → local customers
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
BRANCH_ID    = os.getenv("BRANCH_ID", "default")   # set to warehouse UUID in .env

# Stores timestamps of last successful pulls
_STATE_FILE = Path(__file__).parent.parent / ".sync_state.json"


def _state_get(key: str) -> str:
    try:
        val = json.loads(_STATE_FILE.read_text()).get(key, "2000-01-01T00:00:00Z")
        # Normalize to Z format to avoid + encoding issues in URLs
        return val.replace("+00:00", "Z")
    except Exception:
        return "2000-01-01T00:00:00Z"


def _state_set(key: str, value: str) -> None:
    try:
        # Always store in Z format
        value = value.replace("+00:00", "Z")
        data: dict = {}
        if _STATE_FILE.exists():
            data = json.loads(_STATE_FILE.read_text())
        data[key] = value
        _STATE_FILE.write_text(json.dumps(data))
    except Exception:
        pass


def _headers() -> dict:
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "resolution=merge-duplicates",   # upsert
    }


def _url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


# ── Push helpers ──────────────────────────────────────────────────────────────

def upsert_rows(table: str, rows: list[dict]) -> tuple[bool, str]:
    """Upsert a list of dicts into a Supabase table."""
    if not rows:
        return True, ""
    try:
        r = requests.post(
            _url(table),
            headers=_headers(),
            json=rows,
            timeout=15,
        )
        if r.status_code not in (200, 201):
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        return True, ""
    except Exception as e:
        return False, str(e)


def delete_row(table: str, row_id: str) -> tuple[bool, str]:
    try:
        r = requests.delete(
            f"{_url(table)}?id=eq.{row_id}",
            headers=_headers(),
            timeout=10,
        )
        if r.status_code not in (200, 204):
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        return True, ""
    except Exception as e:
        return False, str(e)


# ── Item sync ─────────────────────────────────────────────────────────────────

def push_item(item_id: str) -> tuple[bool, str]:
    """Push a single item (+ its online price + stock) to Supabase."""
    from database.engine import get_session, init_db
    from database.models.items import Item, ItemPrice, ItemStock

    init_db()
    session = get_session()
    try:
        item = session.get(Item, item_id)
        if not item:
            return True, ""

        # If not online, mark as inactive in products so app hides it
        if not item.is_online or not item.is_active:
            return upsert_rows("products", [{
                "id":        item.id,
                "code":      item.code,
                "name":      item.name,
                "is_active": False,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }])

        # Primary barcode
        primary_bc = next((b.barcode for b in item.barcodes if b.is_primary), "")

        # Individual price (LBP preferred)
        price_lbp = next(
            (p.amount for p in item.prices
             if p.price_type == "individual" and p.currency == "LBP"), 0.0
        )
        price_usd = next(
            (p.amount for p in item.prices
             if p.price_type == "individual" and p.currency == "USD"), 0.0
        )

        # Total stock across all warehouses
        total_stock = sum(s.quantity for s in item.stock_entries)

        cat_name   = item.category.name if item.category else ""
        brand_name = item.brand.name    if item.brand    else ""

        row = {
            "id":          item.id,
            "code":        item.code,
            "name":        item.name,
            "name_ar":     item.name_ar or "",
            "category":    cat_name,
            "brand":       brand_name,
            "barcode":     primary_bc,
            "price_lbp":   price_lbp,
            "price_usd":   price_usd,
            "stock":       total_stock,
            "unit":        item.unit,
            "is_featured": item.is_featured,
            "photo_url":   item.photo_url or "",
            "is_active":   True,
            "updated_at":  datetime.now(timezone.utc).isoformat(),
        }
        return upsert_rows("products", [row])
    finally:
        session.close()


def push_stock_update(item_id: str) -> tuple[bool, str]:
    """Update only the stock field for an item in Supabase."""
    from database.engine import get_session, init_db
    from database.models.items import Item

    init_db()
    session = get_session()
    try:
        item = session.get(Item, item_id)
        if not item or not item.is_online:
            return True, ""
        total_stock = sum(s.quantity for s in item.stock_entries)
        try:
            r = requests.patch(
                f"{_url('products')}?id=eq.{item_id}",
                headers=_headers(),
                json={"stock": total_stock, "updated_at": datetime.now(timezone.utc).isoformat()},
                timeout=10,
            )
            if r.status_code not in (200, 204):
                return False, f"HTTP {r.status_code}: {r.text[:200]}"
            return True, ""
        except Exception as e:
            return False, str(e)
    finally:
        session.close()


# ── Order pull ────────────────────────────────────────────────────────────────

def pull_new_orders() -> tuple[int, str]:
    """
    Fetch new orders from Supabase that haven't been imported yet.
    Returns (count_imported, error).
    """
    from database.engine import get_session, init_db
    from database.models.invoices import OnlineOrder

    if not is_configured():
        return 0, "Supabase not configured"

    init_db()
    session = get_session()
    try:
        # Fetch orders with status='new' from Supabase
        r = requests.get(
            f"{_url('orders')}?status=eq.new&order=created_at.asc",
            headers={**_headers(), "Prefer": ""},
            timeout=15,
        )
        if r.status_code != 200:
            return 0, f"HTTP {r.status_code}: {r.text[:200]}"

        orders = r.json()
        imported = 0

        for o in orders:
            order_id = o.get("id", "")
            # Skip if already imported
            existing = session.get(OnlineOrder, order_id)
            if existing:
                continue

            order = OnlineOrder(
                id             = order_id,
                customer_name  = o.get("customer_name", ""),
                customer_phone = o.get("customer_phone", ""),
                delivery_type  = o.get("delivery_type", "delivery"),
                address        = o.get("address", ""),
                notes          = o.get("notes", ""),
                items_json     = json.dumps(o.get("items", [])),
                total          = o.get("total", 0.0),
                currency       = o.get("currency", "LBP"),
                status         = "new",
                payment_method = o.get("payment_method", "cash"),
                ordered_at     = o.get("created_at", datetime.now(timezone.utc).isoformat()),
            )
            session.add(order)

            # Mark as 'confirmed' on Supabase so we don't pull it again
            requests.patch(
                f"{_url('orders')}?id=eq.{order_id}",
                headers=_headers(),
                json={"status": "confirmed"},
                timeout=10,
            )

            imported += 1

        session.commit()
        return imported, ""

    except Exception as e:
        session.rollback()
        return 0, str(e)
    finally:
        session.close()


# ── Sync queue drain ──────────────────────────────────────────────────────────

def drain_sync_queue(batch_size: int = 50) -> tuple[int, int]:
    """
    Process pending sync_queue rows.
    Returns (synced_count, failed_count).
    """
    from database.engine import get_session, init_db
    from database.models.sync import SyncQueue

    if not is_configured():
        return 0, 0

    init_db()
    session = get_session()
    synced = failed = 0

    try:
        rows = (
            session.query(SyncQueue)
            .filter(SyncQueue.sync_status == "pending", SyncQueue.retry_count < 3)
            .limit(batch_size)
            .all()
        )

        for row in rows:
            ok, err = _process_sync_row(row)
            if ok:
                row.sync_status = "synced"
                row.synced_at   = datetime.now(timezone.utc).isoformat()
                synced += 1
            else:
                row.retry_count += 1
                row.last_error   = err
                if row.retry_count >= 3:
                    row.sync_status = "failed"
                failed += 1

        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()

    return synced, failed


def _process_sync_row(row) -> tuple[bool, str]:
    """Route a sync_queue row to the right push function."""
    try:
        payload = json.loads(row.payload_json)
    except Exception:
        return False, "Invalid JSON payload"

    if row.entity_type == "item":
        # Push to both online catalog (products) and master data (items_central)
        ok1, err1 = push_item(row.entity_id)
        ok2, err2 = push_item_master(row.entity_id)
        if not ok1:
            return False, err1
        if not ok2:
            return False, err2
        return True, ""

    if row.entity_type == "item_stock":
        return push_stock_update(row.entity_id)

    if row.entity_type == "sales_invoice":
        try:
            item_ids = payload.get("item_ids", [])
            # Push invoice to central
            ok, err = push_invoice(row.entity_id)
            if not ok:
                return False, err
            # Update stock levels for each sold item
            for iid in item_ids:
                push_stock_update(iid)
                push_stock_level(iid)
            return True, ""
        except Exception as e:
            return False, str(e)

    if row.entity_type == "customer":
        return push_customer_master(row.entity_id)

    return True, ""   # unknown type — skip silently


# ── Master data push ───────────────────────────────────────────────────────────

def push_item_master(item_id: str) -> tuple[bool, str]:
    """Push full item data (not just online fields) to items_central."""
    from database.engine import get_session, init_db
    from database.models.items import Item

    if not is_configured():
        return True, ""

    init_db()
    session = get_session()
    try:
        item = session.get(Item, item_id)
        if not item or not item.is_active:
            return True, ""

        cat_name   = item.category.name if item.category else ""
        brand_name = item.brand.name    if item.brand    else ""
        now        = datetime.now(timezone.utc).isoformat()

        # Upsert item
        item_row = {
            "id": item.id, "code": item.code, "name": item.name,
            "name_ar": item.name_ar or "", "category": cat_name,
            "brand": brand_name, "unit": item.unit,
            "cost_price": item.cost_price, "cost_currency": item.cost_currency or "USD",
            "vat_rate": item.vat_rate, "is_active": item.is_active,
            "is_online": item.is_online, "is_pos_featured": item.is_pos_featured,
            "photo_url": item.photo_url or "", "notes": item.notes or "",
            "updated_at": now, "pushed_by": BRANCH_ID,
        }
        ok, err = upsert_rows("items_central", [item_row])
        if not ok:
            return False, err

        # Upsert prices
        price_rows = [
            {
                "id": p.id, "item_id": item.id,
                "price_type": p.price_type, "amount": p.amount,
                "currency": p.currency, "updated_at": now,
            }
            for p in item.prices
        ]
        if price_rows:
            ok, err = upsert_rows("item_prices_central", price_rows)
            if not ok:
                return False, err

        # Upsert barcodes
        bc_rows = [
            {
                "id": b.id, "item_id": item.id,
                "barcode": b.barcode, "is_primary": b.is_primary,
                "pack_qty": b.pack_qty or 1, "updated_at": now,
            }
            for b in item.barcodes
        ]
        if bc_rows:
            ok, err = upsert_rows("item_barcodes_central", bc_rows)
            if not ok:
                return False, err

        return True, ""
    finally:
        session.close()


def push_invoice(invoice_id: str) -> tuple[bool, str]:
    """Push a finalized sales invoice + line items to Supabase central."""
    from database.engine import get_session, init_db
    from database.models.invoices import SalesInvoice

    if not is_configured():
        return True, ""

    init_db()
    session = get_session()
    try:
        inv = session.get(SalesInvoice, invoice_id)
        if not inv:
            return True, ""

        customer_name = inv.customer.name if inv.customer else ""
        inv_row = {
            "id":             inv.id,
            "branch_id":      BRANCH_ID,
            "invoice_number": inv.invoice_number,
            "customer_id":    inv.customer_id,
            "customer_name":  customer_name,
            "operator_id":    inv.operator_id,
            "invoice_date":   inv.invoice_date,
            "total":          inv.total,
            "currency":       inv.currency,
            "status":         inv.status,
            "payment_status": inv.payment_status,
            "amount_paid":    inv.amount_paid,
            "notes":          inv.notes or "",
            "source":         inv.source or "manual",
            "invoice_type":   inv.invoice_type or "sale",
            "synced_at":      datetime.now(timezone.utc).isoformat(),
        }
        ok, err = upsert_rows("sales_invoices_central", [inv_row])
        if not ok:
            return False, err

        item_rows = [
            {
                "id":         li.id,
                "invoice_id": inv.id,
                "item_id":    li.item_id,
                "item_name":  li.item_name,
                "barcode":    li.barcode or "",
                "quantity":   li.quantity,
                "unit_price": li.unit_price,
                "currency":   li.currency,
                "line_total": li.line_total,
            }
            for li in inv.items
        ]
        if item_rows:
            ok, err = upsert_rows("sales_invoice_items_central", item_rows)
            if not ok:
                return False, err

        return True, ""
    finally:
        session.close()


def push_stock_level(item_id: str) -> tuple[bool, str]:
    """Update the stock_levels table for this item + branch."""
    from database.engine import get_session, init_db
    from database.models.items import Item

    if not is_configured() or not BRANCH_ID:
        return True, ""

    init_db()
    session = get_session()
    try:
        item = session.get(Item, item_id)
        if not item:
            return True, ""
        total_stock = sum(s.quantity for s in item.stock_entries)
        try:
            r = requests.post(
                _url("stock_levels"),
                headers=_headers(),
                json={
                    "item_id":    item_id,
                    "branch_id":  BRANCH_ID,
                    "quantity":   total_stock,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                timeout=10,
            )
            if r.status_code not in (200, 201):
                return False, f"HTTP {r.status_code}: {r.text[:200]}"
            return True, ""
        except Exception as e:
            return False, str(e)
    finally:
        session.close()


def push_all_stock_levels() -> tuple[bool, str]:
    """
    Push every (item, warehouse) stock row to stock_levels in Supabase.
    Uses branch_id = "{BRANCH_ID}|{warehouse_id}" as the unique composite key
    so each warehouse gets its own row without schema changes.
    """
    from database.engine import get_session, init_db
    from database.models.items import ItemStock

    if not is_configured() or not BRANCH_ID:
        return True, ""

    init_db()
    session = get_session()
    try:
        rows_all = session.query(ItemStock).all()
        if not rows_all:
            return True, ""
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            {
                "item_id":    s.item_id,
                "branch_id":  f"{BRANCH_ID}|{s.warehouse_id}",
                "quantity":   s.quantity,
                "updated_at": now,
            }
            for s in rows_all
        ]
        # Use POST with upsert; if that fails try DELETE+INSERT per row
        for i in range(0, len(rows), 500):
            r = requests.post(
                _url("stock_levels"),
                headers=_headers(),
                json=rows[i:i+500],
                timeout=30,
            )
            if r.status_code not in (200, 201):
                # Fallback: delete existing rows for this branch then re-insert
                requests.delete(
                    f"{_url('stock_levels')}?branch_id=like.{BRANCH_ID}|%",
                    headers=_headers(), timeout=15,
                )
                r2 = requests.post(
                    _url("stock_levels"),
                    headers={**_headers(), "Prefer": ""},
                    json=rows[i:i+500],
                    timeout=30,
                )
                if r2.status_code not in (200, 201):
                    return False, f"HTTP {r2.status_code}: {r2.text[:200]}"
        return True, ""
    finally:
        session.close()


def pull_all_stock_levels() -> tuple[int, str]:
    """
    Rebuild ItemStock for every (item_id, warehouse_id) by summing all local
    stock_movements. Guaranteed to be consistent with the movement history.
    """
    from database.engine import get_session, init_db
    from database.models.items import ItemStock
    from database.models.base import new_uuid
    import sqlalchemy

    init_db()
    session = get_session()
    try:
        rows = session.execute(sqlalchemy.text("""
            SELECT item_id, warehouse_id, SUM(quantity) AS total
            FROM stock_movements
            WHERE item_id IS NOT NULL AND item_id != ''
              AND warehouse_id IS NOT NULL AND warehouse_id != ''
            GROUP BY item_id, warehouse_id
        """)).fetchall()

        updated = 0
        for item_id, warehouse_id, total in rows:
            qty = float(total or 0)
            stock = session.query(ItemStock).filter_by(
                item_id=item_id, warehouse_id=warehouse_id
            ).first()
            if stock:
                if stock.quantity != qty:
                    stock.quantity = qty
                    updated += 1
            else:
                session.add(ItemStock(
                    id=new_uuid(),
                    item_id=item_id,
                    warehouse_id=warehouse_id,
                    quantity=qty,
                ))
                updated += 1

        session.commit()
        return updated, ""
    except Exception as e:
        session.rollback()
        return 0, str(e)
    finally:
        session.close()


def push_customer_master(customer_id: str) -> tuple[bool, str]:
    """Push a customer record to customers_central."""
    from database.engine import get_session, init_db
    from database.models.parties import Customer

    if not is_configured():
        return True, ""

    init_db()
    session = get_session()
    try:
        c = session.get(Customer, customer_id)
        if not c:
            return True, ""
        row = {
            "id": c.id, "name": c.name, "code": c.code or "",
            "phone": c.phone or "", "email": c.email or "",
            "address": c.address or "", "balance": c.balance,
            "currency": c.currency, "is_active": c.is_active,
            "is_cash_client": c.is_cash_client,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "pushed_by": BRANCH_ID,
        }
        return upsert_rows("customers_central", [row])
    finally:
        session.close()


# ── Master data pull ───────────────────────────────────────────────────────────

def pull_master_items() -> tuple[int, str]:
    """
    Pull item changes from items_central since last pull.
    Updates local SQLite items, prices, barcodes.
    Returns (updated_count, error).
    """
    from database.engine import get_session, init_db
    from database.models.items import Item, ItemPrice, ItemBarcode, Category, Brand
    from database.models.base import new_uuid

    if not is_configured():
        return 0, ""

    last_pull = _state_get("items_pull")
    last_id   = _state_get("items_pull_last_id")   # set only during initial full sync
    if not last_id or len(last_id) != 36 or "-" not in last_id:
        last_id = ""

    # ── Mode selection ────────────────────────────────────────────────────────
    # Full-sync mode  : last_id cursor is set — paginate all items by ID
    # Incremental mode: last_id empty — fetch only items updated since last_pull
    full_sync_mode = bool(last_id) or last_pull == "2000-01-01T00:00:00Z"

    PAGE = 500
    total_updated = 0
    latest_ts = last_pull

    init_db()
    session = get_session()

    try:
        from sqlalchemy import func as sa_func
        cats       = {c.name: c.id          for c in session.query(Category).all()}
        cat_touch  = {c.name: c.show_on_touch for c in session.query(Category).all()}
        brands = {b.name: b.id for b in session.query(Brand).all()}
        seen_codes: set[str] = set(r[0] for r in session.query(Item.code).all())

        while True:
            if full_sync_mode:
                # ID-cursor pagination — fast, no offset scanning
                if last_id:
                    url = (f"{_url('items_central')}?id=gt.{last_id}"
                           f"&order=id.asc&limit={PAGE}")
                else:
                    url = f"{_url('items_central')}?order=id.asc&limit={PAGE}"
            else:
                # Incremental — only items changed since last sync
                url = (f"{_url('items_central')}?updated_at=gt.{last_pull}"
                       f"&order=updated_at.asc,id.asc&limit={PAGE}")

            try:
                r = requests.get(url, headers={**_headers(), "Prefer": ""}, timeout=30)
            except Exception as e:
                return total_updated, str(e)

            if r.status_code != 200:
                return total_updated, f"HTTP {r.status_code}: {r.text[:200]}"

            remote_items = r.json()
            if not remote_items:
                break

            item_ids = [i["id"] for i in remote_items]
            ids_filter = ",".join(f'"{iid}"' for iid in item_ids)

            prices_by_item: dict[str, list] = {}
            rp = requests.get(
                f"{_url('item_prices_central')}?item_id=in.({ids_filter})",
                headers={**_headers(), "Prefer": ""}, timeout=20,
            )
            if rp.status_code == 200:
                for p in rp.json():
                    prices_by_item.setdefault(p["item_id"], []).append(p)

            barcodes_by_item: dict[str, list] = {}
            rb = requests.get(
                f"{_url('item_barcodes_central')}?item_id=in.({ids_filter})",
                headers={**_headers(), "Prefer": ""}, timeout=20,
            )
            if rb.status_code == 200:
                for b in rb.json():
                    barcodes_by_item.setdefault(b["item_id"], []).append(b)

            for ri in remote_items:
                if ri.get("pushed_by") == BRANCH_ID:
                    latest_ts = ri.get("updated_at", latest_ts)
                    continue

                item = session.get(Item, ri["id"])
                is_new = False
                if not item:
                    code_str = ri.get("code") or ri["id"][:12]
                    if code_str in seen_codes:
                        latest_ts = ri.get("updated_at", latest_ts)
                        total_updated += 1
                        continue
                    existing = session.query(Item).filter_by(code=code_str).first()
                    if existing:
                        seen_codes.add(code_str)
                        latest_ts = ri.get("updated_at", latest_ts)
                        total_updated += 1
                        continue
                    item = Item(id=ri["id"])
                    session.add(item)
                    seen_codes.add(code_str)
                    is_new = True

                item.code            = ri.get("code") or ri["id"][:12]
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

                cat_name   = ri.get("category") or ""
                brand_name = ri.get("brand") or ""
                item.category_id = cats.get(cat_name)
                item.brand_id    = brands.get(brand_name)

                # New items inherit show_on_touch from their category
                if is_new and cat_touch.get(cat_name):
                    item.show_on_touch = True

                seen_price_keys: set[tuple] = set()
                for rp_row in prices_by_item.get(ri["id"], []):
                    price = session.get(ItemPrice, rp_row["id"])
                    if not price:
                        price = session.query(ItemPrice).filter_by(
                            item_id=ri["id"],
                            price_type=rp_row["price_type"],
                            currency=rp_row["currency"],
                        ).first()
                    if not price:
                        price = ItemPrice(id=rp_row["id"], item_id=ri["id"])
                        session.add(price)
                    price.price_type = rp_row["price_type"]
                    price.amount     = rp_row["amount"]
                    price.currency   = rp_row["currency"]
                    seen_price_keys.add((rp_row["price_type"], rp_row["currency"]))

                if seen_price_keys:
                    for dup in session.query(ItemPrice).filter_by(item_id=ri["id"]).all():
                        if (dup.price_type, dup.currency) not in seen_price_keys:
                            session.delete(dup)

                for rb_row in barcodes_by_item.get(ri["id"], []):
                    bc = session.get(ItemBarcode, rb_row["id"])
                    if not bc:
                        conflict = session.query(ItemBarcode).filter(
                            sa_func.lower(ItemBarcode.barcode) == rb_row["barcode"].lower(),
                            ItemBarcode.item_id != ri["id"],
                        ).first()
                        if conflict:
                            continue
                        bc = ItemBarcode(id=rb_row["id"], item_id=ri["id"])
                        session.add(bc)
                    bc.barcode    = rb_row["barcode"]
                    bc.is_primary = rb_row.get("is_primary", False)
                    bc.pack_qty   = rb_row.get("pack_qty", 1)

                latest_ts = ri.get("updated_at", latest_ts)
                total_updated += 1

            session.commit()

            if full_sync_mode:
                last_id = remote_items[-1]["id"]
                _state_set("items_pull_last_id", last_id)
            else:
                # Incremental: save latest timestamp seen so next run starts here
                _state_set("items_pull", latest_ts)

            if len(remote_items) < PAGE:
                break  # Last page

        if full_sync_mode:
            # Full sync done — switch to incremental mode from now
            _state_set("items_pull", datetime.now(timezone.utc).isoformat())
            _state_set("items_pull_last_id", "")

        return total_updated, ""

    except Exception as e:
        session.rollback()
        return total_updated, str(e)
    finally:
        session.close()


def pull_master_customers() -> tuple[int, str]:
    """
    Pull customer changes from customers_central since last pull.
    Returns (updated_count, error).
    """
    from database.engine import get_session, init_db
    from database.models.parties import Customer

    if not is_configured():
        return 0, ""

    last_pull = _state_get("customers_pull")

    try:
        r = requests.get(
            f"{_url('customers_central')}?updated_at=gt.{last_pull}"
            f"&order=updated_at.asc&limit=500",
            headers={**_headers(), "Prefer": ""},
            timeout=20,
        )
        if r.status_code != 200:
            return 0, f"HTTP {r.status_code}: {r.text[:200]}"

        remote = r.json()
        if not remote:
            return 0, ""

        init_db()
        session = get_session()
        updated  = 0
        latest_ts = last_pull

        try:
            for rc in remote:
                if rc.get("pushed_by") == BRANCH_ID:
                    latest_ts = rc["updated_at"]
                    continue

                c = session.get(Customer, rc["id"])
                if not c:
                    c = Customer(id=rc["id"])
                    session.add(c)

                c.name           = rc["name"]
                c.code           = rc.get("code") or None
                c.phone          = rc.get("phone") or None
                c.email          = rc.get("email") or None
                c.address        = rc.get("address") or None
                c.balance        = rc.get("balance", 0)
                c.currency       = rc.get("currency", "USD")
                c.is_active      = rc.get("is_active", True)
                c.is_cash_client = rc.get("is_cash_client", False)

                latest_ts = rc["updated_at"]
                updated += 1

            session.commit()
            _state_set("customers_pull", latest_ts)
            return updated, ""

        except Exception as e:
            session.rollback()
            return 0, str(e)
        finally:
            session.close()

    except Exception as e:
        return 0, str(e)


# ── Stock movements push/pull ─────────────────────────────────────────────────

def push_stock_movements_for_invoice(reference_id: str) -> tuple[bool, str]:
    """
    Push all StockMovement rows for a given invoice/reference to Supabase.
    Called after purchase or sale is committed.
    Deletes old movements for this reference first so edited invoices don't
    leave stale rows that other branches would double-apply.
    """
    from database.engine import get_session, init_db
    from database.models.stock import StockMovement

    if not is_configured():
        return True, ""

    init_db()
    session = get_session()
    try:
        movements = session.query(StockMovement).filter_by(
            reference_id=reference_id
        ).all()
        if not movements:
            return True, ""

        rows = [
            {
                "id":             mv.id,
                "item_id":        mv.item_id,
                "warehouse_id":   mv.warehouse_id,
                "qty_change":     mv.quantity,   # positive=IN, negative=OUT
                "movement_type":  mv.movement_type,
                "reference_type": mv.reference_type or "",
                "reference_id":   mv.reference_id or "",
                "branch_id":      BRANCH_ID,
                "created_at":     mv.created_at or datetime.now(timezone.utc).isoformat(),
            }
            for mv in movements
        ]
    finally:
        session.close()

    # Delete old movements for this reference first (handles invoice edits —
    # old movement IDs are gone locally but may still exist in Supabase)
    try:
        requests.delete(
            f"{_url('stock_movements_central')}?reference_id=eq.{reference_id}&branch_id=eq.{BRANCH_ID}",
            headers=_headers(), timeout=15,
        )
    except Exception:
        pass

    return upsert_rows("stock_movements_central", rows)


def pull_stock_movements() -> tuple[int, str]:
    """
    Pull stock movements from OTHER branches since last pull.
    Applies qty changes to local ItemStock.
    Skips movements already applied or originating from this branch.
    Returns (applied_count, error).
    """
    from database.engine import get_session, init_db
    from database.models.items import ItemStock
    from database.models.base import new_uuid
    import sqlalchemy

    if not is_configured():
        return 0, ""

    last_pull = _state_get("movements_pull")

    try:
        r = requests.get(
            f"{_url('stock_movements_central')}"
            f"?created_at=gt.{last_pull}"
            f"&branch_id=neq.{BRANCH_ID}"
            f"&order=created_at.asc&limit=1000",
            headers={**_headers(), "Prefer": ""},
            timeout=20,
        )
        if r.status_code != 200:
            return 0, f"HTTP {r.status_code}: {r.text[:200]}"

        remote = r.json()
        if not remote:
            return 0, ""

        init_db()
        session = get_session()
        applied   = 0
        latest_ts = last_pull
        # Track new ItemStock rows added this batch to avoid UNIQUE conflicts
        stock_cache: dict[tuple, ItemStock] = {}

        try:
            for rm in remote:
                mv_id = rm["id"]

                # Skip if already applied
                already = session.execute(
                    sqlalchemy.text(
                        "SELECT 1 FROM applied_central_movements WHERE movement_id=:id"
                    ),
                    {"id": mv_id},
                ).fetchone()
                if already:
                    latest_ts = rm["created_at"]
                    continue

                item_id      = rm["item_id"]
                warehouse_id = rm["warehouse_id"]
                qty_change   = rm["qty_change"]

                # Only apply to local ItemStock if item + warehouse exist locally
                from database.models.items import Warehouse
                item_exists = session.execute(
                    sqlalchemy.text("SELECT 1 FROM items WHERE id=:id"), {"id": item_id}
                ).fetchone()
                wh_exists = session.get(Warehouse, warehouse_id)

                if not item_exists or not wh_exists:
                    # Item or warehouse not yet synced — skip WITHOUT marking applied
                    # so it will be retried on the next sync cycle
                    latest_ts = rm["created_at"]
                    continue

                cache_key = (item_id, warehouse_id)
                stock = stock_cache.get(cache_key)
                if stock is None:
                    stock = session.query(ItemStock).filter_by(
                        item_id=item_id, warehouse_id=warehouse_id
                    ).first()
                if stock:
                    stock.quantity += qty_change
                    stock_cache[cache_key] = stock
                else:
                    stock = ItemStock(
                        id=new_uuid(),
                        item_id=item_id,
                        warehouse_id=warehouse_id,
                        quantity=qty_change,
                    )
                    session.add(stock)
                    stock_cache[cache_key] = stock

                # Mark as applied (only reached when stock was actually updated)
                session.execute(
                    sqlalchemy.text(
                        "INSERT OR IGNORE INTO applied_central_movements"
                        " (movement_id, applied_at) VALUES (:id, :ts)"
                    ),
                    {"id": mv_id, "ts": datetime.now(timezone.utc).isoformat()},
                )

                latest_ts = rm["created_at"]
                applied += 1

            session.commit()
            _state_set("movements_pull", latest_ts)
            return applied, ""

        except Exception as e:
            session.rollback()
            return 0, str(e)
        finally:
            session.close()

    except Exception as e:
        return 0, str(e)


# ── User sync ─────────────────────────────────────────────────────────────────

def push_user(user_id: str) -> tuple[bool, str]:
    """Push a user record to users_central."""
    from database.engine import get_session, init_db
    from database.models.users import User

    if not is_configured():
        return True, ""

    init_db()
    session = get_session()
    try:
        u = session.get(User, user_id)
        if not u:
            return True, ""
        row = {
            "id":            u.id,
            "username":      u.username,
            "password_hash": u.password_hash,
            "full_name":     u.full_name,
            "role":          u.role,
            "warehouse_id":  u.warehouse_id or "",
            "is_active":     u.is_active,
            "updated_at":    datetime.now(timezone.utc).isoformat(),
            "pushed_by":     BRANCH_ID,
        }
        return upsert_rows("users_central", [row])
    finally:
        session.close()


def pull_users() -> tuple[int, str]:
    """Pull user changes from users_central since last pull."""
    from database.engine import get_session, init_db
    from database.models.users import User

    if not is_configured():
        return 0, ""

    last_pull = _state_get("users_pull")

    try:
        r = requests.get(
            f"{_url('users_central')}?updated_at=gt.{last_pull}"
            f"&order=updated_at.asc&limit=200",
            headers={**_headers(), "Prefer": ""},
            timeout=20,
        )
        if r.status_code != 200:
            return 0, f"HTTP {r.status_code}: {r.text[:200]}"

        remote = r.json()
        if not remote:
            return 0, ""

        init_db()
        session = get_session()
        updated   = 0
        latest_ts = last_pull

        try:
            for ru in remote:
                u = session.get(User, ru["id"])
                if not u:
                    u = User(id=ru["id"])
                    session.add(u)

                u.username      = ru["username"]
                u.password_hash = ru["password_hash"]
                u.full_name     = ru["full_name"]
                u.role          = ru["role"]
                u.is_active     = ru.get("is_active", True)

                # Only assign warehouse_id if it exists locally (avoids FK error)
                wh_id = ru.get("warehouse_id") or None
                if wh_id:
                    from database.models.items import Warehouse
                    u.warehouse_id = wh_id if session.get(Warehouse, wh_id) else None
                else:
                    u.warehouse_id = None

                latest_ts = ru["updated_at"]
                updated += 1

            session.commit()
            _state_set("users_pull", latest_ts)
            return updated, ""

        except Exception as e:
            session.rollback()
            return 0, str(e)
        finally:
            session.close()

    except Exception as e:
        return 0, str(e)


# ── Warehouse sync ────────────────────────────────────────────────────────────

def push_warehouses() -> tuple[bool, str]:
    """Push all warehouses to warehouses_central."""
    from database.engine import get_session, init_db
    from database.models.items import Warehouse

    if not is_configured():
        return True, ""

    init_db()
    session = get_session()
    try:
        rows = [
            {
                "id":                  w.id,
                "number":              w.number,
                "name":                w.name,
                "location":            w.location or "",
                "is_default":          w.is_default,
                "is_active":           w.is_active,
                "default_customer_id": w.default_customer_id or None,
                "updated_at":          datetime.now(timezone.utc).isoformat(),
            }
            for w in session.query(Warehouse).all()
        ]
        if not rows:
            return True, ""
        return upsert_rows("warehouses_central", rows)
    finally:
        session.close()


def pull_warehouses() -> tuple[int, str]:
    """Pull all warehouses from warehouses_central."""
    from database.engine import get_session, init_db
    from database.models.items import Warehouse

    if not is_configured():
        return 0, ""

    try:
        r = requests.get(
            f"{_url('warehouses_central')}?order=number.asc",
            headers={**_headers(), "Prefer": ""},
            timeout=15,
        )
        if r.status_code != 200:
            return 0, f"HTTP {r.status_code}: {r.text[:200]}"

        remote = r.json()
        if not remote:
            return 0, ""

        init_db()
        session = get_session()
        updated = 0
        try:
            for rw in remote:
                w = session.get(Warehouse, rw["id"])
                if not w:
                    w = Warehouse(id=rw["id"])
                    session.add(w)
                w.number              = rw.get("number")
                w.name                = rw["name"]
                w.location            = rw.get("location") or None
                w.is_default          = rw.get("is_default", False)
                w.is_active           = rw.get("is_active", True)
                w.default_customer_id = rw.get("default_customer_id") or None
                updated += 1
            session.commit()
            return updated, ""
        except Exception as e:
            session.rollback()
            return 0, str(e)
        finally:
            session.close()
    except Exception as e:
        return 0, str(e)


# ── Supplier sync ─────────────────────────────────────────────────────────────

def push_supplier(supplier_id: str) -> tuple[bool, str]:
    """Push a supplier record to suppliers_central."""
    from database.engine import get_session, init_db
    from database.models.parties import Supplier

    if not is_configured():
        return True, ""

    init_db()
    session = get_session()
    try:
        s = session.get(Supplier, supplier_id)
        if not s:
            return True, ""
        row = {
            "id":             s.id,
            "name":           s.name,
            "code":           s.code or "",
            "phone":          s.phone or "",
            "phone2":         s.phone2 or "",
            "email":          s.email or "",
            "address":        s.address or "",
            "classification": s.classification or "",
            "credit_limit":   s.credit_limit,
            "balance":        s.balance,
            "currency":       s.currency,
            "notes":          s.notes or "",
            "is_active":      s.is_active,
            "updated_at":     datetime.now(timezone.utc).isoformat(),
            "pushed_by":      BRANCH_ID,
        }
        return upsert_rows("suppliers_central", [row])
    finally:
        session.close()


def pull_suppliers() -> tuple[int, str]:
    """Pull supplier changes from suppliers_central since last pull."""
    from database.engine import get_session, init_db
    from database.models.parties import Supplier

    if not is_configured():
        return 0, ""

    last_pull = _state_get("suppliers_pull")

    try:
        r = requests.get(
            f"{_url('suppliers_central')}?updated_at=gt.{last_pull}"
            f"&order=updated_at.asc&limit=500",
            headers={**_headers(), "Prefer": ""},
            timeout=20,
        )
        if r.status_code != 200:
            return 0, f"HTTP {r.status_code}: {r.text[:200]}"

        remote = r.json()
        if not remote:
            return 0, ""

        init_db()
        session = get_session()
        updated   = 0
        latest_ts = last_pull

        try:
            for rs in remote:
                if rs.get("pushed_by") == BRANCH_ID:
                    latest_ts = rs["updated_at"]
                    continue

                s = session.get(Supplier, rs["id"])
                if not s:
                    s = Supplier(id=rs["id"])
                    session.add(s)

                s.name           = rs["name"]
                s.code           = rs.get("code") or None
                s.phone          = rs.get("phone") or None
                s.phone2         = rs.get("phone2") or None
                s.email          = rs.get("email") or None
                s.address        = rs.get("address") or None
                s.classification = rs.get("classification") or None
                s.credit_limit   = rs.get("credit_limit", 0)
                s.balance        = rs.get("balance", 0)
                s.currency       = rs.get("currency", "USD")
                s.notes          = rs.get("notes") or None
                s.is_active      = rs.get("is_active", True)

                latest_ts = rs["updated_at"]
                updated += 1

            session.commit()
            _state_set("suppliers_pull", latest_ts)
            return updated, ""

        except Exception as e:
            session.rollback()
            return 0, str(e)
        finally:
            session.close()

    except Exception as e:
        return 0, str(e)


# ── Sales invoice pull ────────────────────────────────────────────────────────

def pull_sales_invoices() -> tuple[int, str]:
    """
    Pull sales invoices from OTHER branches since last pull.
    Stores them locally for reporting/visibility.
    Returns (count, error).
    """
    from database.engine import get_session, init_db
    from database.models.invoices import SalesInvoice, SalesInvoiceItem

    if not is_configured():
        return 0, ""

    last_pull = _state_get("sales_invoices_pull")

    try:
        r = requests.get(
            f"{_url('sales_invoices_central')}"
            f"?synced_at=gt.{last_pull}"
            f"&branch_id=neq.{BRANCH_ID}"
            f"&order=synced_at.asc&limit=500",
            headers={**_headers(), "Prefer": ""},
            timeout=20,
        )
        if r.status_code != 200:
            return 0, f"HTTP {r.status_code}: {r.text[:200]}"

        remote = r.json()
        if not remote:
            return 0, ""

        inv_ids = [i["id"] for i in remote]
        ids_filter = ",".join(f'"{iid}"' for iid in inv_ids)

        rl = requests.get(
            f"{_url('sales_invoice_items_central')}?invoice_id=in.({ids_filter})",
            headers={**_headers(), "Prefer": ""},
            timeout=20,
        )
        lines_by_inv: dict[str, list] = {}
        if rl.status_code == 200:
            for li in rl.json():
                lines_by_inv.setdefault(li["invoice_id"], []).append(li)

        init_db()
        session = get_session()
        pulled    = 0
        latest_ts = last_pull

        try:
            import sqlalchemy
            from database.models.stock import StockMovement
            from database.models.base import new_uuid as _new_uuid
            session.execute(sqlalchemy.text("PRAGMA foreign_keys=OFF"))

            for ri in remote:
                inv = session.get(SalesInvoice, ri["id"])
                wh_id    = ri.get("warehouse_id") or ""
                src      = ri.get("source") or "manual"
                # pos_shift invoices are shift-summary records; their item-level
                # stock movements already arrive via pull_stock_movements(), so
                # we skip creating duplicate audit movements for them.
                is_shift = (src == "pos_shift")
                is_update = bool(inv)

                if is_update:
                    inv.payment_status = ri.get("payment_status", inv.payment_status)
                    inv.status         = ri.get("status", inv.status)
                    if ri.get("source"):
                        inv.source       = ri["source"]
                    if ri.get("invoice_type"):
                        inv.invoice_type = ri["invoice_type"]
                    if not is_shift:
                        # Reverse old audit movements + wipe old line items
                        session.query(StockMovement).filter(
                            StockMovement.reference_type == "sales_invoice",
                            StockMovement.reference_id   == ri["id"],
                        ).delete()
                        session.query(SalesInvoiceItem).filter_by(
                            invoice_id=ri["id"]
                        ).delete()
                        session.flush()
                else:
                    # Skip if invoice_number already taken by a local invoice
                    clash = session.query(SalesInvoice).filter_by(
                        invoice_number=ri["invoice_number"]
                    ).first()
                    if clash:
                        latest_ts = ri["synced_at"]
                        pulled += 1
                        continue

                    inv = SalesInvoice(
                        id=ri["id"],
                        invoice_number=ri["invoice_number"],
                        customer_id=ri.get("customer_id") or "",
                        operator_id=ri.get("operator_id") or "",
                        warehouse_id=wh_id,
                        invoice_date=ri["invoice_date"],
                        total=ri.get("total", 0),
                        currency=ri.get("currency", "USD"),
                        status=ri.get("status", "finalized"),
                        payment_status=ri.get("payment_status", "unpaid"),
                        amount_paid=ri.get("amount_paid", 0),
                        notes=ri.get("notes") or None,
                        source=src,
                        invoice_type=ri.get("invoice_type") or "sale",
                        branch_id=ri.get("branch_id") or "",
                    )
                    session.add(inv)
                    session.flush()

                # Add / re-add line items for all invoices.
                # For pos_shift: add items but skip stock movements
                # (movements already arrive via pull_stock_movements).
                for li in lines_by_inv.get(ri["id"], []):
                    item_id = li.get("item_id") or ""
                    qty     = float(li["quantity"])
                    price   = float(li.get("unit_price") or 0)
                    session.add(SalesInvoiceItem(
                        id=li["id"] if not is_update else _new_uuid(),
                        invoice_id=ri["id"],
                        item_id=item_id,
                        item_name=li["item_name"],
                        barcode=li.get("barcode") or "",
                        quantity=qty,
                        unit_price=price,
                        currency=li.get("currency", "USD"),
                        line_total=float(li.get("line_total") or 0),
                    ))
                    # Audit trail movement — only for non-shift invoices
                    if not is_shift and item_id and wh_id:
                        session.add(StockMovement(
                            id=_new_uuid(),
                            item_id=item_id,
                            warehouse_id=wh_id,
                            movement_type="sale",
                            quantity=-qty,
                            unit_cost=price,
                            reference_type="sales_invoice",
                            reference_id=ri["id"],
                        ))

                latest_ts = ri["synced_at"]
                pulled += 1

            session.commit()
            session.execute(sqlalchemy.text("PRAGMA foreign_keys=ON"))
            _state_set("sales_invoices_pull", latest_ts)
            return pulled, ""

        except Exception as e:
            session.rollback()
            return 0, str(e)
        finally:
            session.close()

    except Exception as e:
        return 0, str(e)


# ── Purchase invoice sync ─────────────────────────────────────────────────────

def push_purchase_invoice(invoice_id: str) -> tuple[bool, str]:
    """Push a purchase invoice + line items to purchase_invoices_central."""
    from database.engine import get_session, init_db
    from database.models.invoices import PurchaseInvoice

    if not is_configured():
        return True, ""

    init_db()
    session = get_session()
    try:
        inv = session.get(PurchaseInvoice, invoice_id)
        if not inv:
            return True, ""

        supplier_name = inv.supplier.name if inv.supplier else ""
        inv_row = {
            "id":             inv.id,
            "branch_id":      BRANCH_ID,
            "invoice_number": inv.invoice_number,
            "supplier_id":    inv.supplier_id or "",
            "supplier_name":  supplier_name,
            "operator_id":    inv.operator_id or "",
            "warehouse_id":   inv.warehouse_id or "",
            "invoice_date":   inv.invoice_date,
            "due_date":       inv.due_date or "",
            "order_number":   inv.order_number or "",
            "subtotal":       inv.subtotal,
            "total":          inv.total,
            "currency":       inv.currency,
            "status":         inv.status,
            "payment_status": inv.payment_status,
            "notes":          inv.notes or "",
            "synced_at":      datetime.now(timezone.utc).isoformat(),
        }
        ok, err = upsert_rows("purchase_invoices_central", [inv_row])
        if not ok:
            return False, err

        # Delete all existing lines for this invoice from Supabase first,
        # so removed lines don't survive and cause duplicates on re-pull.
        requests.delete(
            f"{_url('purchase_invoice_items_central')}?invoice_id=eq.{inv.id}",
            headers=_headers(), timeout=15,
        )

        item_rows = [
            {
                "id":         li.id,
                "invoice_id": inv.id,
                "item_id":    li.item_id,
                "item_name":  li.item_name,
                "quantity":   li.quantity,
                "pack_size":  li.pack_size or 1,
                "unit_cost":  li.unit_cost,
                "currency":   li.currency,
                "line_total": li.line_total,
            }
            for li in inv.items
        ]
        if item_rows:
            ok, err = upsert_rows("purchase_invoice_items_central", item_rows)
            if not ok:
                return False, err

        return True, ""
    finally:
        session.close()


def pull_purchase_invoices() -> tuple[int, str]:
    """
    Pull purchase invoices from OTHER branches since last pull.
    Stores them locally as read-only records (for visibility across branches).
    Returns (count, error).
    """
    from database.engine import get_session, init_db
    from database.models.invoices import PurchaseInvoice, PurchaseInvoiceItem
    from database.models.base import new_uuid

    if not is_configured():
        return 0, ""

    last_pull = _state_get("purchase_invoices_pull")

    try:
        r = requests.get(
            f"{_url('purchase_invoices_central')}"
            f"?synced_at=gt.{last_pull}"
            f"&branch_id=neq.{BRANCH_ID}"
            f"&order=synced_at.asc&limit=500",
            headers={**_headers(), "Prefer": ""},
            timeout=20,
        )
        if r.status_code != 200:
            return 0, f"HTTP {r.status_code}: {r.text[:200]}"

        remote = r.json()
        if not remote:
            return 0, ""

        inv_ids = [i["id"] for i in remote]
        ids_filter = ",".join(f'"{iid}"' for iid in inv_ids)

        # Fetch line items for these invoices
        rl = requests.get(
            f"{_url('purchase_invoice_items_central')}?invoice_id=in.({ids_filter})",
            headers={**_headers(), "Prefer": ""},
            timeout=20,
        )
        lines_by_inv: dict[str, list] = {}
        if rl.status_code == 200:
            for li in rl.json():
                lines_by_inv.setdefault(li["invoice_id"], []).append(li)

        init_db()
        session = get_session()
        pulled = 0
        latest_ts = last_pull

        try:
            # Disable FK checks so invoices from other branches can be stored
            # even if their supplier/operator/warehouse don't exist locally
            import sqlalchemy
            from database.models.stock import StockMovement
            from database.models.base import new_uuid as _new_uuid
            session.execute(sqlalchemy.text("PRAGMA foreign_keys=OFF"))

            for ri in remote:
                inv = session.get(PurchaseInvoice, ri["id"])
                wh_id = ri.get("warehouse_id") or ""
                is_update = bool(inv)

                if is_update:
                    # Update header fields
                    inv.payment_status = ri.get("payment_status", inv.payment_status)
                    inv.status         = ri.get("status", inv.status)
                    inv.notes          = ri.get("notes") or inv.notes
                    inv.total          = ri.get("total", inv.total)
                    inv.subtotal       = ri.get("subtotal", inv.subtotal)
                    # Reverse old audit movements then wipe old line items
                    session.query(StockMovement).filter(
                        StockMovement.reference_type == "purchase_invoice",
                        StockMovement.reference_id   == ri["id"],
                    ).delete()
                    session.query(PurchaseInvoiceItem).filter_by(
                        invoice_id=ri["id"]
                    ).delete()
                    session.flush()
                else:
                    inv = PurchaseInvoice(
                        id=ri["id"],
                        invoice_number=ri["invoice_number"],
                        supplier_id=ri.get("supplier_id") or None,
                        operator_id=ri.get("operator_id") or "",
                        warehouse_id=wh_id,
                        invoice_date=ri["invoice_date"],
                        due_date=ri.get("due_date") or None,
                        order_number=ri.get("order_number") or None,
                        invoice_type="purchase",
                        subtotal=ri.get("subtotal", 0),
                        total=ri.get("total", 0),
                        currency=ri.get("currency", "USD"),
                        status=ri.get("status", "finalized"),
                        payment_status=ri.get("payment_status", "unpaid"),
                        notes=ri.get("notes") or None,
                    )
                    session.add(inv)
                    session.flush()

                # Add / re-add line items and create audit trail movements
                for li in lines_by_inv.get(ri["id"], []):
                    item_id = li.get("item_id") or ""
                    qty     = float(li["quantity"])
                    cost    = float(li.get("unit_cost") or 0)
                    session.add(PurchaseInvoiceItem(
                        id=li["id"] if not is_update else _new_uuid(),
                        invoice_id=ri["id"],
                        item_id=item_id,
                        item_name=li["item_name"],
                        quantity=qty,
                        pack_size=li.get("pack_size", 1),
                        unit_cost=cost,
                        currency=li.get("currency", "USD"),
                        line_total=float(li.get("line_total") or 0),
                    ))
                    # Audit trail movement (stock card history) — ItemStock is
                    # already kept in sync by pull_stock_movements()
                    if item_id and wh_id:
                        session.add(StockMovement(
                            id=_new_uuid(),
                            item_id=item_id,
                            warehouse_id=wh_id,
                            movement_type="purchase",
                            quantity=qty,
                            unit_cost=cost,
                            reference_type="purchase_invoice",
                            reference_id=ri["id"],
                        ))

                latest_ts = ri["synced_at"]
                pulled += 1

            session.commit()
            session.execute(sqlalchemy.text("PRAGMA foreign_keys=ON"))
            _state_set("purchase_invoices_pull", latest_ts)
            return pulled, ""

        except Exception as e:
            session.execute(sqlalchemy.text("PRAGMA foreign_keys=ON"))
            session.rollback()
            return 0, str(e)
        finally:
            session.close()

    except Exception as e:
        return 0, str(e)


# ── Category sync ─────────────────────────────────────────────────────────────

def push_categories() -> tuple[bool, str]:
    """Push all categories (including subcategories) to categories_central."""
    from database.engine import get_session, init_db
    from database.models.items import Category

    if not is_configured():
        return True, ""

    init_db()
    session = get_session()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cats = session.query(Category).all()
        rows = [
            {
                "id":            c.id,
                "name":          c.name,
                "parent_id":     c.parent_id or None,
                "sort_order":    c.sort_order,
                "is_active":     c.is_active,
                "show_in_daily": c.show_in_daily,
                "updated_at":    now,
            }
            for c in cats
        ]
        if not rows:
            return True, ""
        ok, err = upsert_rows("categories_central", rows)
        if not ok:
            return False, err
        # Push image URLs to app_categories for the mobile app
        img_rows = [
            {"name": c.name, "image_url": c.photo_url or None,
             "show_on_home": bool(getattr(c, "show_on_home", False)), "updated_at": now}
            for c in cats if c.photo_url or getattr(c, "show_on_home", False)
        ]
        if img_rows:
            upsert_rows("app_categories", img_rows)
        # Remove entries for categories that no longer have an image
        live_names = {c.name for c in cats if c.photo_url or getattr(c, "show_on_home", False)}
        try:
            r_existing = requests.get(
                f"{_url('app_categories')}?select=name",
                headers={**_headers(), "Prefer": ""},
                timeout=10,
            )
            if r_existing.status_code == 200:
                for row in r_existing.json():
                    if row["name"] not in live_names:
                        requests.delete(
                            f"{_url('app_categories')}?name=eq.{row['name']}",
                            headers=_headers(),
                            timeout=10,
                        )
        except Exception:
            pass
        return True, ""
    finally:
        session.close()


def pull_categories() -> tuple[int, str]:
    """Pull all categories from categories_central (always full sync)."""
    from database.engine import get_session, init_db
    from database.models.items import Category

    if not is_configured():
        return 0, ""

    try:
        r = requests.get(
            f"{_url('categories_central')}?order=sort_order.asc",
            headers={**_headers(), "Prefer": ""},
            timeout=15,
        )
        if r.status_code != 200:
            return 0, f"HTTP {r.status_code}: {r.text[:200]}"

        remote = r.json()
        if not remote:
            return 0, ""

        init_db()
        session = get_session()
        updated = 0
        try:
            # First pass: upsert without parent_id to avoid FK issues
            for rc in remote:
                c = session.get(Category, rc["id"])
                if not c:
                    c = Category(id=rc["id"])
                    session.add(c)
                c.name          = rc["name"]
                c.sort_order    = rc.get("sort_order", 0)
                c.is_active     = rc.get("is_active", True)
                c.show_in_daily = rc.get("show_in_daily", False)
                c.parent_id     = None
                updated += 1
            session.flush()
            # Second pass: set parent_id now that all rows exist
            for rc in remote:
                if rc.get("parent_id"):
                    c = session.get(Category, rc["id"])
                    if c:
                        c.parent_id = rc["parent_id"]
            session.commit()
            return updated, ""
        except Exception as e:
            session.rollback()
            return 0, str(e)
        finally:
            session.close()
    except Exception as e:
        return 0, str(e)


# ── Warehouse transfer sync ───────────────────────────────────────────────────

def push_transfer(transfer_id: str) -> tuple[bool, str]:
    """Push a warehouse transfer + its items to Supabase central tables."""
    import sqlalchemy
    from database.engine import get_session, init_db
    from database.models.stock import WarehouseTransfer, WarehouseTransferItem

    if not is_configured():
        return True, ""

    init_db()
    session = get_session()
    try:
        t = session.get(WarehouseTransfer, transfer_id)
        if not t:
            return False, "Transfer not found"

        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id":                t.id,
            "transfer_number":   t.transfer_number or "",
            "from_warehouse_id": t.from_warehouse_id,
            "to_warehouse_id":   t.to_warehouse_id,
            "transfer_date":     t.transfer_date or "",
            "status":            t.status,
            "operator_id":       t.operator_id or None,
            "notes":             t.notes or "",
            "pushed_by":         BRANCH_ID,
            "synced_at":         now,
        }
        ok, err = upsert_rows("warehouse_transfers_central", [row])
        if not ok:
            return False, err

        # Query items directly — avoids ORM lazy-load issues
        items = session.query(WarehouseTransferItem).filter_by(
            transfer_id=transfer_id
        ).all()

        if items:
            item_rows = [
                {
                    "id":          ti.id,
                    "transfer_id": transfer_id,
                    "item_id":     ti.item_id,
                    "item_name":   ti.item_name or "",
                    "quantity":    ti.quantity,
                    "unit_cost":   ti.unit_cost or 0.0,
                    "synced_at":   now,
                }
                for ti in items
            ]
            ok, err = upsert_rows("warehouse_transfer_items_central", item_rows)
            if not ok:
                return False, err

        return True, ""
    finally:
        session.close()


def pull_transfers() -> tuple[int, str]:
    """Pull warehouse transfers from other branches."""
    import sqlalchemy
    from database.engine import get_session, init_db
    from database.models.stock import WarehouseTransfer, WarehouseTransferItem

    if not is_configured():
        return 0, ""

    last_pull = _state_get("transfers_pull")
    ts_filter = f"&synced_at=gt.{last_pull}" if last_pull else ""

    try:
        r = requests.get(
            f"{_url('warehouse_transfers_central')}?order=synced_at.asc{ts_filter}",
            headers={**_headers(), "Prefer": ""},
            timeout=15,
        )
        if r.status_code != 200:
            return 0, f"HTTP {r.status_code}: {r.text[:200]}"

        remote = r.json()
        if not remote:
            return 0, ""

        # Fetch all line items for these transfers
        transfer_ids = [rt["id"] for rt in remote]
        id_list = ",".join(f'"{i}"' for i in transfer_ids)
        r2 = requests.get(
            f"{_url('warehouse_transfer_items_central')}?transfer_id=in.({id_list})&limit=5000",
            headers={**_headers(), "Prefer": ""},
            timeout=15,
        )
        lines_by_transfer: dict[str, list] = {}
        if r2.status_code == 200:
            for li in r2.json():
                lines_by_transfer.setdefault(li["transfer_id"], []).append(li)

        init_db()
        session = get_session()
        pulled = 0
        latest_ts = last_pull
        stock_cache: dict[tuple, "ItemStock"] = {}  # (item_id, wh_id) → ItemStock
        try:
            session.execute(sqlalchemy.text("PRAGMA foreign_keys=OFF"))
            for rt in remote:
                if rt.get("pushed_by") == BRANCH_ID:
                    latest_ts = rt["synced_at"]
                    continue

                existing = session.get(WarehouseTransfer, rt["id"])
                if not existing:
                    t = WarehouseTransfer(
                        id=rt["id"],
                        transfer_number=rt.get("transfer_number") or None,
                        from_warehouse_id=rt["from_warehouse_id"],
                        to_warehouse_id=rt["to_warehouse_id"],
                        transfer_date=rt.get("transfer_date") or None,
                        status=rt.get("status", "open"),
                        operator_id=rt.get("operator_id") or None,
                        notes=rt.get("notes") or None,
                    )
                    session.add(t)
                    session.flush()
                    pulled += 1

                remote_items = lines_by_transfer.get(rt["id"], [])
                if remote_items:
                    from database.models.stock import StockMovement
                    from database.models.items import ItemStock
                    from database.models.base import new_uuid

                    from_wh = rt["from_warehouse_id"]
                    to_wh   = rt["to_warehouse_id"]

                    # Reverse old stock movements before replacing items
                    old_items = session.query(WarehouseTransferItem).filter_by(
                        transfer_id=rt["id"]
                    ).all()
                    for old_li in old_items:
                        # Restore source stock
                        src = session.query(ItemStock).filter_by(
                            item_id=old_li.item_id, warehouse_id=from_wh
                        ).first()
                        if src:
                            src.quantity += old_li.quantity
                        # Restore destination stock
                        dst = session.query(ItemStock).filter_by(
                            item_id=old_li.item_id, warehouse_id=to_wh
                        ).first()
                        if dst:
                            dst.quantity -= old_li.quantity
                        # Remove old movements
                        session.query(StockMovement).filter_by(
                            reference_id=rt["id"], item_id=old_li.item_id
                        ).delete()

                    # Full replace items
                    session.query(WarehouseTransferItem).filter_by(
                        transfer_id=rt["id"]
                    ).delete()
                    session.flush()

                    for li in remote_items:
                        item_id  = li.get("item_id") or ""
                        qty      = float(li["quantity"])
                        cost     = float(li.get("unit_cost") or 0.0)

                        session.add(WarehouseTransferItem(
                            id=li["id"],
                            transfer_id=rt["id"],
                            item_id=item_id,
                            item_name=li.get("item_name") or "",
                            quantity=qty,
                            unit_cost=cost,
                        ))

                        if item_id:
                            # transfer_out from source
                            session.add(StockMovement(
                                id=new_uuid(),
                                item_id=item_id,
                                warehouse_id=from_wh,
                                movement_type="transfer_out",
                                quantity=-qty,
                                unit_cost=cost,
                                reference_type="transfer",
                                reference_id=rt["id"],
                            ))
                            # transfer_in to destination
                            session.add(StockMovement(
                                id=new_uuid(),
                                item_id=item_id,
                                warehouse_id=to_wh,
                                movement_type="transfer_in",
                                quantity=qty,
                                unit_cost=cost,
                                reference_type="transfer",
                                reference_id=rt["id"],
                            ))

                            # Update ItemStock (cache avoids UNIQUE violation within batch)
                            src_key = (item_id, from_wh)
                            src = stock_cache.get(src_key) or session.query(ItemStock).filter_by(
                                item_id=item_id, warehouse_id=from_wh
                            ).first()
                            if src:
                                src.quantity -= qty
                            else:
                                src = ItemStock(id=new_uuid(), item_id=item_id,
                                                warehouse_id=from_wh, quantity=-qty)
                                session.add(src)
                            stock_cache[src_key] = src

                            dst_key = (item_id, to_wh)
                            dst = stock_cache.get(dst_key) or session.query(ItemStock).filter_by(
                                item_id=item_id, warehouse_id=to_wh
                            ).first()
                            if dst:
                                dst.quantity += qty
                            else:
                                dst = ItemStock(id=new_uuid(), item_id=item_id,
                                                warehouse_id=to_wh, quantity=qty)
                                session.add(dst)
                            stock_cache[dst_key] = dst

                latest_ts = rt["synced_at"]

            session.commit()
            session.execute(sqlalchemy.text("PRAGMA foreign_keys=ON"))
            if latest_ts:
                _state_set("transfers_pull", latest_ts)
            return pulled, ""

        except Exception as e:
            session.execute(sqlalchemy.text("PRAGMA foreign_keys=ON"))
            session.rollback()
            return 0, str(e)
        finally:
            session.close()
    except Exception as e:
        return 0, str(e)


# ── Inventory sessions sync ────────────────────────────────────────────────────

def push_inventory_session(session_id: str) -> tuple[bool, str]:
    """Push an inventory session + its items to Supabase central tables."""
    from database.engine import get_session as get_db, init_db
    from database.models.inventory import InventorySession, InventorySessionItem

    if not is_configured():
        return True, ""

    init_db()
    db = get_db()
    try:
        inv = db.get(InventorySession, session_id)
        if not inv:
            return False, "Inventory session not found"

        now = datetime.now(timezone.utc).isoformat()
        row = {
            "id":             inv.id,
            "session_number": inv.session_number or "",
            "warehouse_id":   inv.warehouse_id,
            "session_date":   inv.session_date or "",
            "status":         inv.status,
            "operator_id":    inv.operator_id or None,
            "notes":          inv.notes or "",
            "pushed_by":      BRANCH_ID,
            "synced_at":      now,
        }
        ok, err = upsert_rows("inventory_sessions_central", [row])
        if not ok:
            return False, err

        items = db.query(InventorySessionItem).filter_by(session_id=session_id).all()
        if items:
            item_rows = [
                {
                    "id":          li.id,
                    "session_id":  session_id,
                    "item_id":     li.item_id,
                    "item_name":   li.item_name or "",
                    "system_qty":  li.system_qty,
                    "counted_qty": li.counted_qty,
                    "diff_qty":    li.diff_qty,
                    "unit_cost":   li.unit_cost or 0.0,
                    "synced_at":   now,
                }
                for li in items
            ]
            ok, err = upsert_rows("inventory_session_items_central", item_rows)
            if not ok:
                return False, err

        return True, ""
    finally:
        db.close()


def delete_inventory_session_remote(session_id: str):
    """Delete an inventory session from Supabase central tables."""
    if not is_configured():
        return
    try:
        requests.delete(
            f"{_url('inventory_session_items_central')}?session_id=eq.{session_id}",
            headers=_headers(), timeout=10,
        )
        requests.delete(
            f"{_url('inventory_sessions_central')}?id=eq.{session_id}",
            headers=_headers(), timeout=10,
        )
    except Exception as e:
        print(f"[sync] delete_inventory_session_remote: {e}")


def pull_inventory_sessions() -> tuple[int, str]:
    """Pull inventory sessions from other branches."""
    import sqlalchemy
    from database.engine import get_session as get_db, init_db
    from database.models.inventory import InventorySession, InventorySessionItem

    if not is_configured():
        return 0, ""

    last_pull = _state_get("inventory_sessions_pull")
    ts_filter = f"&synced_at=gt.{last_pull}" if last_pull else ""

    try:
        r = requests.get(
            f"{_url('inventory_sessions_central')}?order=synced_at.asc{ts_filter}",
            headers={**_headers(), "Prefer": ""},
            timeout=15,
        )
        if r.status_code != 200:
            return 0, f"HTTP {r.status_code}: {r.text[:200]}"

        remote = r.json()
        if not remote:
            return 0, ""

        # Fetch all line items for these sessions
        session_ids = [rs["id"] for rs in remote]
        id_list = ",".join(f'"{i}"' for i in session_ids)
        r2 = requests.get(
            f"{_url('inventory_session_items_central')}?session_id=in.({id_list})&limit=5000",
            headers={**_headers(), "Prefer": ""},
            timeout=15,
        )
        lines_by_session: dict[str, list] = {}
        if r2.status_code == 200:
            for li in r2.json():
                lines_by_session.setdefault(li["session_id"], []).append(li)

        init_db()
        db = get_db()
        pulled = 0
        latest_ts = last_pull
        try:
            db.execute(sqlalchemy.text("PRAGMA foreign_keys=OFF"))
            for rs in remote:
                if rs.get("pushed_by") == BRANCH_ID:
                    latest_ts = rs["synced_at"]
                    continue

                existing = db.get(InventorySession, rs["id"])
                if not existing:
                    inv = InventorySession(
                        id=rs["id"],
                        session_number=rs.get("session_number") or None,
                        warehouse_id=rs["warehouse_id"],
                        session_date=rs.get("session_date") or None,
                        status=rs.get("status", "open"),
                        operator_id=rs.get("operator_id") or None,
                        notes=rs.get("notes") or None,
                    )
                    db.add(inv)
                    db.flush()
                    pulled += 1

                remote_items = lines_by_session.get(rs["id"], [])
                if remote_items:
                    wh_id = rs["warehouse_id"]
                    from database.models.stock import StockMovement
                    from database.models.items import ItemStock

                    # Reverse old stock adjustments before replacing items
                    old_items = db.query(InventorySessionItem).filter_by(
                        session_id=rs["id"]
                    ).all()
                    for old_li in old_items:
                        # Restore ItemStock to system_qty
                        old_stock = db.query(ItemStock).filter_by(
                            item_id=old_li.item_id, warehouse_id=wh_id
                        ).first()
                        if old_stock:
                            old_stock.quantity = old_li.system_qty
                        # Remove old movements for this session+item
                        db.query(StockMovement).filter_by(
                            reference_id=rs["id"], item_id=old_li.item_id
                        ).delete()

                    # Delete old items
                    db.query(InventorySessionItem).filter_by(
                        session_id=rs["id"]
                    ).delete()
                    db.flush()

                    # Insert new items, apply movements and update ItemStock
                    for li in remote_items:
                        item_id     = li.get("item_id") or ""
                        counted_qty = li.get("counted_qty") or 0.0
                        system_qty  = li.get("system_qty") or 0.0
                        diff        = li.get("diff_qty") or 0.0
                        unit_cost   = li.get("unit_cost") or 0.0

                        db.add(InventorySessionItem(
                            id=li["id"],
                            session_id=rs["id"],
                            item_id=item_id,
                            item_name=li.get("item_name") or "",
                            system_qty=system_qty,
                            counted_qty=counted_qty,
                            diff_qty=diff,
                            unit_cost=unit_cost,
                        ))

                        # Create local StockMovement so stock card shows it
                        if diff != 0 and item_id:
                            from database.models.base import new_uuid as _uuid
                            db.add(StockMovement(
                                id=_uuid(),
                                item_id=item_id,
                                warehouse_id=wh_id,
                                movement_type="adjustment_in" if diff > 0 else "adjustment_out",
                                quantity=diff,
                                unit_cost=unit_cost,
                                reference_type="inventory",
                                reference_id=rs["id"],
                            ))

                        # Set ItemStock to exact counted qty (absolute, not delta)
                        if item_id:
                            stock = db.query(ItemStock).filter_by(
                                item_id=item_id, warehouse_id=wh_id
                            ).first()
                            if stock:
                                stock.quantity = counted_qty
                            else:
                                from database.models.base import new_uuid as _uuid
                                db.add(ItemStock(
                                    id=_uuid(),
                                    item_id=item_id,
                                    warehouse_id=wh_id,
                                    quantity=counted_qty,
                                ))

                latest_ts = rs["synced_at"]

            db.commit()
            db.execute(sqlalchemy.text("PRAGMA foreign_keys=ON"))
            if latest_ts:
                _state_set("inventory_sessions_pull", latest_ts)
            return pulled, ""

        except Exception as e:
            db.execute(sqlalchemy.text("PRAGMA foreign_keys=ON"))
            db.rollback()
            return 0, str(e)
        finally:
            db.close()
    except Exception as e:
        return 0, str(e)


# ── Branch reset sync ─────────────────────────────────────────────────────────

def push_branch_reset() -> tuple[bool, str]:
    """
    Called after reset_transactions.py clears the local DB.
    Deletes this branch's transaction data from all Supabase central tables
    so other machines will remove their local copies on next sync.
    """
    if not is_configured():
        return True, ""
    try:
        hdrs = _headers()

        # Collect invoice IDs first (needed to delete line items — no cascade in REST)
        r = requests.get(
            f"{_url('sales_invoices_central')}?branch_id=eq.{BRANCH_ID}&select=id",
            headers={**hdrs, "Prefer": ""},
            timeout=20,
        )
        if r.status_code == 200:
            ids = [row["id"] for row in r.json()]
            if ids:
                ids_filter = ",".join(f'"{i}"' for i in ids)
                requests.delete(
                    f"{_url('sales_invoice_items_central')}?invoice_id=in.({ids_filter})",
                    headers=hdrs,
                    timeout=20,
                )

        requests.delete(
            f"{_url('sales_invoices_central')}?branch_id=eq.{BRANCH_ID}",
            headers=hdrs,
            timeout=20,
        )
        requests.delete(
            f"{_url('stock_movements_central')}?branch_id=eq.{BRANCH_ID}",
            headers=hdrs,
            timeout=20,
        )

        # Reset the state timestamps so a full re-pull doesn't re-create deleted records
        _state_set("sales_invoices_pull", "2000-01-01T00:00:00Z")
        _state_set("movements_pull",      "2000-01-01T00:00:00Z")

        return True, ""
    except Exception as e:
        return False, str(e)


def pull_invoice_deletes() -> tuple[int, str]:
    """
    Reconcile: find local sales invoices that came from other branches but no
    longer exist in central (e.g. the source branch ran a reset), and delete them.
    Runs once per sync cycle; processes up to 500 IDs per call.
    """
    import sqlalchemy as _sa
    from database.engine import get_session, init_db
    from database.models.invoices import SalesInvoice, SalesInvoiceItem
    from database.models.stock import StockMovement

    if not is_configured():
        return 0, ""

    init_db()
    session = get_session()
    try:
        # Find local invoices that were pulled from other branches
        rows = session.execute(
            _sa.text(
                "SELECT id FROM sales_invoices "
                "WHERE branch_id != '' AND branch_id != :bid "
                "LIMIT 500"
            ),
            {"bid": BRANCH_ID},
        ).fetchall()

        if not rows:
            return 0, ""

        local_ids = [r[0] for r in rows]
        ids_filter = ",".join(f'"{i}"' for i in local_ids)

        r = requests.get(
            f"{_url('sales_invoices_central')}?id=in.({ids_filter})&select=id",
            headers={**_headers(), "Prefer": ""},
            timeout=20,
        )
        if r.status_code != 200:
            return 0, f"HTTP {r.status_code}"

        central_ids = {row["id"] for row in r.json()}
        deleted_ids = [i for i in local_ids if i not in central_ids]

        if not deleted_ids:
            return 0, ""

        for inv_id in deleted_ids:
            session.query(StockMovement).filter_by(reference_id=inv_id).delete()
            session.query(SalesInvoiceItem).filter_by(invoice_id=inv_id).delete()
            session.query(SalesInvoice).filter_by(id=inv_id).delete()

        session.commit()
        return len(deleted_ids), ""

    except Exception as e:
        session.rollback()
        return 0, str(e)
    finally:
        session.close()

def pull_purchase_invoice_deletes() -> tuple[int, str]:
    """
    Reconcile: find local purchase invoices from other branches that no longer
    exist in Supabase (deleted by that branch) and remove them locally.
    Also removes own-branch invoices deleted from Supabase by another machine.
    """
    import sqlalchemy as _sa
    from database.engine import get_session, init_db
    from database.models.invoices import PurchaseInvoice, PurchaseInvoiceItem
    from database.models.stock import StockMovement

    if not is_configured():
        return 0, ""

    init_db()
    session = get_session()
    try:
        rows = session.execute(
            _sa.text("SELECT id FROM purchase_invoices LIMIT 500")
        ).fetchall()

        if not rows:
            return 0, ""

        local_ids = [r[0] for r in rows]
        ids_filter = ",".join(f'"{i}"' for i in local_ids)

        r = requests.get(
            f"{_url('purchase_invoices_central')}?id=in.({ids_filter})&select=id",
            headers={**_headers(), "Prefer": ""},
            timeout=20,
        )
        if r.status_code != 200:
            return 0, f"HTTP {r.status_code}"

        central_ids = {row["id"] for row in r.json()}
        deleted_ids = [i for i in local_ids if i not in central_ids]

        if not deleted_ids:
            return 0, ""

        for inv_id in deleted_ids:
            # Must delete stock movements first (orphaned movements cause wrong stock card)
            session.query(StockMovement).filter_by(
                reference_type="purchase_invoice", reference_id=inv_id
            ).delete()
            session.query(PurchaseInvoiceItem).filter_by(invoice_id=inv_id).delete()
            session.query(PurchaseInvoice).filter_by(id=inv_id).delete()

        session.commit()
        return len(deleted_ids), ""

    except Exception as e:
        session.rollback()
        return 0, str(e)
    finally:
        session.close()


def dedupe_stock_movements() -> int:
    """
    1. Remove StockMovement rows whose reference_id points to a purchase or
       sales invoice that no longer exists locally (orphaned by a delete).
    2. Remove duplicate rows sharing the same
       (reference_type, reference_id, item_id, movement_type) — keeps newest.
    Returns total rows removed.
    """
    import sqlalchemy as _sa
    from database.engine import get_session, init_db

    init_db()
    session = get_session()
    removed = 0
    try:
        # 1. Orphaned purchase-invoice movements
        r1 = session.execute(_sa.text("""
            DELETE FROM stock_movements
            WHERE reference_type = 'purchase_invoice'
              AND reference_id IS NOT NULL
              AND reference_id != ''
              AND reference_id NOT IN (SELECT id FROM purchase_invoices)
        """))
        removed += r1.rowcount

        # 2. Orphaned sales-invoice movements
        r2 = session.execute(_sa.text("""
            DELETE FROM stock_movements
            WHERE reference_type = 'sales_invoice'
              AND reference_id IS NOT NULL
              AND reference_id != ''
              AND reference_id NOT IN (SELECT id FROM sales_invoices)
        """))
        removed += r2.rowcount

        # 3. Duplicate movements (same invoice + item + type) — keep newest rowid
        r3 = session.execute(_sa.text("""
            DELETE FROM stock_movements
            WHERE rowid NOT IN (
                SELECT MAX(rowid)
                FROM stock_movements
                WHERE reference_id IS NOT NULL
                  AND reference_id != ''
                GROUP BY reference_type, reference_id, item_id, movement_type
            )
            AND reference_id IS NOT NULL
            AND reference_id != ''
        """))
        removed += r3.rowcount

        session.commit()
        return removed
    except Exception:
        session.rollback()
        return 0
    finally:
        session.close()


# ── Supabase Storage upload ───────────────────────────────────────────────────

def upload_to_storage(bucket: str, path: str, data: bytes, content_type: str = "image/jpeg") -> tuple[bool, str]:
    """
    Upload bytes to Supabase Storage.
    Returns (ok, public_url_or_error).
    """
    if not is_configured():
        return False, "Supabase not configured"
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}"
    headers = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  content_type,
        "x-upsert":      "true",
    }
    try:
        r = requests.post(url, headers=headers, data=data, timeout=30)
        if r.status_code not in (200, 201):
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        public_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"
        return True, public_url
    except Exception as e:
        return False, str(e)


# ── App Banners CRUD ──────────────────────────────────────────────────────────

def fetch_banners_remote() -> tuple[list, str]:
    """Fetch all rows from app_banners ordered by sort_order."""
    if not is_configured():
        return [], "Supabase not configured"
    try:
        r = requests.get(
            f"{_url('app_banners')}?order=sort_order.asc",
            headers={**_headers(), "Prefer": ""},
            timeout=10,
        )
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}: {r.text[:200]}"
        return r.json(), ""
    except Exception as e:
        return [], str(e)


def upsert_banner(banner: dict) -> tuple[bool, str]:
    """Insert or update a banner row."""
    return upsert_rows("app_banners", [banner])


def delete_banner(banner_id: str) -> tuple[bool, str]:
    """Delete a banner by id."""
    return delete_row("app_banners", banner_id)


# ── Online orders (app → POS) ─────────────────────────────────────────────────

def fetch_pending_online_orders(warehouse_id: str) -> list[dict]:
    """Return unacknowledged online orders placed for this branch (warehouse_id)."""
    if not is_configured() or not warehouse_id:
        return []
    pending_statuses = "or=(status.eq.new,status.eq.confirmed)"
    # Try with branch filter first
    try:
        r = requests.get(
            f"{_url('orders')}?branch_id=eq.{warehouse_id}"
            f"&{pending_statuses}&acknowledged_at=is.null&order=created_at.asc",
            headers={**_headers(), "Prefer": ""},
            timeout=8,
        )
        if r.status_code == 200:
            rows = r.json()
            if rows:
                return rows
    except Exception:
        pass
    # Fallback: fetch all unhandled orders (branch filter empty or column missing)
    try:
        r = requests.get(
            f"{_url('orders')}?{pending_statuses}&order=created_at.asc",
            headers={**_headers(), "Prefer": ""},
            timeout=8,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def acknowledge_online_order(order_id: str) -> bool:
    """Mark an online order as acknowledged (in-processing) so it stops alerting."""
    return update_online_order_status(order_id, "processing")


def update_online_order_status(order_id: str, status: str) -> bool:
    """Update the status of an online order in Supabase."""
    if not is_configured():
        return False
    try:
        now = datetime.now(timezone.utc).isoformat()
        payload: dict = {"status": status}
        if status == "processing":
            payload["acknowledged_at"] = now
        r = requests.patch(
            f"{_url('orders')}?id=eq.{order_id}",
            headers={**_headers(), "Prefer": "return=minimal"},
            json=payload,
            timeout=8,
        )
        return r.status_code in (200, 204)
    except Exception:
        return False


def fetch_branch_orders(warehouse_id: str, hours: int = 24) -> list[dict]:
    """Fetch all online orders for this branch from the last N hours."""
    if not is_configured() or not warehouse_id:
        return []
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    # Try with branch filter first
    try:
        r = requests.get(
            f"{_url('orders')}?branch_id=eq.{warehouse_id}"
            f"&created_at=gte.{since}&order=created_at.desc",
            headers={**_headers(), "Prefer": ""},
            timeout=10,
        )
        if r.status_code == 200:
            rows = r.json()
            if rows:           # found orders for this branch — return them
                return rows
    except Exception:
        pass
    # Fallback: no branch match (old orders with null branch_id, or column missing)
    try:
        r = requests.get(
            f"{_url('orders')}?created_at=gte.{since}&order=created_at.desc",
            headers={**_headers(), "Prefer": ""},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


# ── Enqueue helper (called from services) ────────────────────────────────────

def enqueue(entity_type: str, entity_id: str, action: str, payload: dict) -> None:
    """Add a row to sync_queue. Call after any local write that needs syncing."""
    from database.engine import get_session
    from database.models.sync import SyncQueue
    from database.models.base import new_uuid

    session = get_session()
    try:
        session.add(SyncQueue(
            id           = new_uuid(),
            entity_type  = entity_type,
            entity_id    = entity_id,
            action_type  = action,
            payload_json = json.dumps(payload),
            sync_status  = "pending",
        ))
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()
