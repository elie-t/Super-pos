"""
Diagnostic: check stock movements and shift invoices on this PC.
Run: python debug_stock.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from database.engine import init_db, engine
from sqlalchemy import text
init_db()

with engine.connect() as conn:
    print("=== Warehouses ===")
    for r in conn.execute(text("SELECT id, name FROM warehouses")).fetchall():
        print(f"  {r[0][:8]}.. {r[1]}")

    print("\n=== Shift invoices (pos_shift) ===")
    rows = conn.execute(text(
        "SELECT invoice_number, invoice_date, warehouse_id, branch_id "
        "FROM sales_invoices WHERE source='pos_shift' ORDER BY invoice_date DESC LIMIT 5"
    )).fetchall()
    for r in rows:
        print(f"  {r[0]} | {r[1]} | wh={str(r[2])[:8]} | branch={str(r[3])[:8]}")
    if not rows:
        print("  (none)")

    print("\n=== Stock movements (last 10) ===")
    rows = conn.execute(text(
        "SELECT movement_type, quantity, warehouse_id, reference_type, created_at "
        "FROM stock_movements ORDER BY created_at DESC LIMIT 10"
    )).fetchall()
    for r in rows:
        print(f"  {r[0]} qty={r[1]} wh={str(r[2])[:8]} ref={r[3]} at={r[4]}")
    if not rows:
        print("  (none)")

    print("\n=== applied_central_movements count ===")
    cnt = conn.execute(text("SELECT COUNT(*) FROM applied_central_movements")).scalar()
    print(f"  {cnt} rows")

    print("\n=== Movements for shift invoices ===")
    rows = conn.execute(text("""
        SELECT sm.quantity, sm.warehouse_id, sm.created_at
        FROM stock_movements sm
        JOIN sales_invoices si ON sm.reference_id = si.id
        WHERE si.source = 'pos_shift'
    """)).fetchall()
    print(f"  {len(rows)} movements linked to pos_shift invoices")
    for r in rows:
        print(f"  qty={r[0]} wh={str(r[1])[:8]} at={r[2]}")
