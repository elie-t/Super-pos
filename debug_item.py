"""
Debug a specific item's stock state. Run: python debug_item.py 99000751
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

code = sys.argv[1] if len(sys.argv) > 1 else "99000751"

from database.engine import init_db, engine
from sqlalchemy import text
init_db()

with engine.connect() as conn:
    # 1. Find the item
    row = conn.execute(text("SELECT id, code, name FROM items WHERE code=:c"), {"c": code}).fetchone()
    if not row:
        print(f"Item code '{code}' NOT FOUND locally")
        sys.exit(1)
    item_id, item_code, item_name = row
    print(f"Item: [{item_code}] {item_name}  id={item_id}")

    # 2. Item stock
    stocks = conn.execute(text(
        "SELECT ist.quantity, w.name FROM item_stock ist "
        "JOIN warehouses w ON w.id=ist.warehouse_id "
        "WHERE ist.item_id=:id"
    ), {"id": item_id}).fetchall()
    print(f"\nItem stock:")
    for qty, wh in stocks:
        print(f"  {wh}: {qty}")
    if not stocks:
        print("  (none)")

    # 3. All stock movements
    mvs = conn.execute(text(
        "SELECT sm.movement_type, sm.quantity, sm.reference_type, sm.reference_id, sm.created_at, w.name "
        "FROM stock_movements sm "
        "LEFT JOIN warehouses w ON w.id=sm.warehouse_id "
        "WHERE sm.item_id=:id ORDER BY sm.created_at DESC LIMIT 20"
    ), {"id": item_id}).fetchall()
    print(f"\nStock movements ({len(mvs)}):")
    for mt, qty, rt, rid, created, wh in mvs:
        print(f"  created_at={created}  type={mt} qty={qty} ref={rt} wh={wh}")
    if not mvs:
        print("  (none)")

    # 4. Sales invoice items for this item
    sii = conn.execute(text(
        "SELECT sii.quantity, si.invoice_number, si.invoice_date, si.source, si.id "
        "FROM sales_invoice_items sii "
        "JOIN sales_invoices si ON si.id=sii.invoice_id "
        "WHERE sii.item_id=:id ORDER BY si.invoice_date DESC LIMIT 10"
    ), {"id": item_id}).fetchall()
    print(f"\nSales invoice lines ({len(sii)}):")
    for qty, inv_no, inv_date, src, inv_id in sii:
        has_mv = conn.execute(text(
            "SELECT COUNT(*) FROM stock_movements WHERE reference_type='sales_invoice' AND reference_id=:ref"
        ), {"ref": inv_id}).scalar()
        print(f"  inv={inv_no} date={inv_date} qty={qty} src={src}  movements_for_inv={has_mv}")
    if not sii:
        print("  (none)")

print()

# 5. Check Supabase for movements
try:
    from sync.service import is_configured, _url, _headers, BRANCH_ID
    import requests

    if not is_configured():
        print("Supabase not configured — skipping remote check.")
    else:
        print(f"=== Supabase check (BRANCH_ID={BRANCH_ID[:8]}..) ===")

        # Find item in items_central
        rc = requests.get(
            f"{_url('items_central')}?code=eq.{code}&select=id,code,name,pushed_by",
            headers={**_headers(), "Prefer": ""},
            timeout=15,
        )
        if rc.status_code == 200:
            central_items = rc.json()
            print(f"items_central entries for code={code}: {len(central_items)}")
            for ci in central_items:
                print(f"  id={ci['id'][:8]}.. pushed_by={str(ci.get('pushed_by',''))[:8]}")

            # Check movements for each remote item ID
            for ci in central_items:
                rm = requests.get(
                    f"{_url('stock_movements_central')}?item_id=eq.{ci['id']}&select=id,qty_change,movement_type,branch_id,created_at",
                    headers={**_headers(), "Prefer": ""},
                    timeout=15,
                )
                if rm.status_code == 200:
                    mvs2 = rm.json()
                    print(f"  Supabase movements for item {ci['id'][:8]}..: {len(mvs2)}")
                    for m in mvs2:
                        print(f"    qty={m.get('qty_change')} branch={str(m.get('branch_id',''))[:8]} at={m.get('created_at','')[:19]}")

        # applied_central_movements check
        with engine.connect() as conn2:
            applied_count = conn2.execute(text("SELECT COUNT(*) FROM applied_central_movements")).scalar()
            print(f"\napplied_central_movements total: {applied_count}")

except Exception as e:
    print(f"Supabase check error: {e}")
