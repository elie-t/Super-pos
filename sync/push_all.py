"""
Manual full sync — pushes all is_online=True items to Supabase in one batch.
Called from the admin dashboard "Sync Now" button.
"""
from datetime import datetime, timezone
from sync.service import upsert_rows, is_configured

BATCH_SIZE = 500   # rows per HTTP request (safe for Supabase ~2 MB limit)


def push_all_online_items() -> tuple[int, int, list[str]]:
    """
    Push every item with is_online=True to Supabase in batches.
    Returns (success_count, fail_count, error_list).
    """
    if not is_configured():
        return 0, 0, ["Supabase not configured — check .env"]

    from database.engine import get_session, init_db
    from database.models.items import Item, Setting
    init_db()
    session = get_session()
    try:
        s = session.get(Setting, "lbp_rate")
        lbp_rate = int(s.value) if s and s.value else 90_000
        items = session.query(Item).filter_by(is_online=True, is_active=True).all()
        rows = [_build_row(item, lbp_rate) for item in items]
    finally:
        session.close()

    if not rows:
        return 0, 0, []

    ok_count = fail_count = 0
    errors: list[str] = []

    # Push the correct items first
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i: i + BATCH_SIZE]
        ok, err = upsert_rows("products", batch)
        if ok:
            ok_count += len(batch)
        else:
            fail_count += len(batch)
            errors.append(err)

    # PC is the sole owner of products — deactivate anything not in our catalog
    from config import IS_MAIN_BRANCH
    if IS_MAIN_BRANCH:
        _deactivate_stale_products({r["id"] for r in rows})

    return ok_count, fail_count, errors


def _deactivate_stale_products(valid_ids: set) -> None:
    """
    Fetch all active product IDs from Supabase and deactivate any that are
    not in valid_ids. Safe only when IS_MAIN_BRANCH=True (single catalog owner).
    """
    import requests
    from sync.service import _url, _headers, SUPABASE_URL, SUPABASE_KEY
    from datetime import datetime, timezone

    if not (SUPABASE_URL and SUPABASE_KEY):
        return
    try:
        # Fetch all active product IDs
        r = requests.get(
            f"{_url('products')}?is_active=eq.true&select=id",
            headers={**_headers(), "Prefer": ""},
            timeout=30,
        )
        if r.status_code != 200:
            return

        stale = [row["id"] for row in r.json() if row["id"] not in valid_ids]
        if not stale:
            return

        now = datetime.now(timezone.utc).isoformat()
        for i in range(0, len(stale), BATCH_SIZE):
            batch = [{"id": oid, "is_active": False, "updated_at": now}
                     for oid in stale[i: i + BATCH_SIZE]]
            upsert_rows("products", batch)
    except Exception:
        pass


def _build_row(item, lbp_rate: int = 0) -> dict:
    primary_bc = next((b.barcode for b in item.barcodes if b.is_primary), "")
    price_lbp = next(
        (p.amount for p in item.prices
         if p.price_type == "retail" and p.currency == "LBP"), 0.0
    ) or next(
        (p.amount for p in item.prices
         if p.price_type == "individual" and p.currency == "LBP"), 0.0
    )
    price_usd = next(
        (p.amount for p in item.prices
         if p.price_type == "retail" and p.currency == "USD"), 0.0
    ) or next(
        (p.amount for p in item.prices
         if p.price_type == "individual" and p.currency == "USD"), 0.0
    )
    # Convert USD price to LBP if no LBP price exists
    if not price_lbp and price_usd and lbp_rate:
        price_lbp = round(price_usd * lbp_rate / 1000) * 1000
    total_stock = sum(s.quantity for s in item.stock_entries)
    return {
        "id":          item.id,
        "code":        item.code,
        "name":        item.name,
        "name_ar":     item.name_ar or "",
        "category":    item.category.name if item.category else "",
        "brand":       item.brand.name if item.brand else "",
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
