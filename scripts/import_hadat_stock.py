"""
scripts/import_hadat_stock.py
=============================
Import a stock Excel file into one Super POS inventory session.

Usage:
    python scripts/import_hadat_stock.py [--file PATH] [--warehouse-id ID] [--yes]

Options:
    --file          Path to xlsx (default: ~/Downloads/hadat stock 12042026.xlsx)
    --warehouse-id  UUID of target warehouse (skips interactive picker)
    --yes           Skip confirmation prompt before writing to DB
"""
import argparse
import sys
from pathlib import Path
from datetime import date

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))


def clean_str(raw) -> str:
    if not raw:
        return ""
    return str(raw).strip().replace("\xa0", "").strip()


def list_warehouses() -> list[dict]:
    from database.engine import init_db, get_session
    from database.models.items import Warehouse
    init_db()
    db = get_session()
    try:
        rows = db.query(Warehouse).filter_by(is_active=True).order_by(Warehouse.name).all()
        return [{"id": w.id, "name": w.name, "is_default": getattr(w, "is_default", False)} for w in rows]
    finally:
        db.close()


def pick_warehouse(warehouse_id_arg) -> str:
    warehouses = list_warehouses()
    if not warehouses:
        print("ERROR: No active warehouses found in DB.")
        sys.exit(1)

    if warehouse_id_arg:
        ids = [w["id"] for w in warehouses]
        if warehouse_id_arg not in ids:
            print(f"ERROR: warehouse-id '{warehouse_id_arg}' not found. Available:")
            for w in warehouses:
                print(f"  {w['id']}  {w['name']}")
            sys.exit(1)
        return warehouse_id_arg

    print("\nAvailable warehouses:")
    for i, w in enumerate(warehouses, 1):
        default_tag = " [DEFAULT]" if w["is_default"] else ""
        print(f"  {i}. {w['name']}{default_tag}  (id: {w['id']})")
    print()
    while True:
        choice = input(f"Select warehouse [1-{len(warehouses)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(warehouses):
            return warehouses[int(choice) - 1]["id"]
        print("  Invalid choice, try again.")


def get_operator_id():
    from database.engine import get_session
    db = get_session()
    try:
        from database.models.users import User
        admin = db.query(User).filter_by(role="admin", is_active=True).first()
        if admin:
            print(f"  Using operator: {admin.full_name} ({admin.username})")
            return admin.id
        print("  No admin user found — operator_id will be None.")
        return None
    except Exception:
        return None
    finally:
        db.close()


def load_excel_rows(xlsx_path: str) -> list:
    from seed.import_items import load_xlsx
    return load_xlsx(xlsx_path)


def build_lookup_maps(warehouse_id: str) -> tuple:
    from database.engine import get_session
    from database.models.items import Item, ItemBarcode, ItemStock
    db = get_session()
    try:
        code_to_item = {}
        item_id_to_name = {}
        for item in db.query(Item).all():
            if item.code:
                code_to_item[item.code.strip()] = {"id": item.id, "name": item.name}
                item_id_to_name[item.id] = item.name

        barcode_to_item = {}
        for bc in db.query(ItemBarcode).all():
            bc_clean = clean_str(bc.barcode)
            if bc_clean:
                barcode_to_item[bc_clean] = {
                    "id": bc.item_id,
                    "name": item_id_to_name.get(bc.item_id, ""),
                }

        item_current_stock = {}
        for s in db.query(ItemStock).filter_by(warehouse_id=warehouse_id).all():
            item_current_stock[s.item_id] = s.quantity

        return code_to_item, barcode_to_item, item_current_stock
    finally:
        db.close()


def match_rows(excel_rows, code_to_item, barcode_to_item, item_current_stock):
    lines = []
    unmatched = []
    seen_item_ids = set()

    for row in excel_rows:
        xl_code_raw  = row[1]
        xl_barcode_raw = row[2]
        xl_name      = clean_str(row[4]) if len(row) > 4 else ""
        xl_qty_raw   = row[5] if len(row) > 5 else None
        xl_cost_raw  = row[6] if len(row) > 6 else None

        # Normalise code: Excel stores as int or float
        try:
            xl_code = str(int(float(xl_code_raw))) if xl_code_raw is not None else ""
        except (ValueError, TypeError):
            xl_code = clean_str(xl_code_raw)

        xl_barcode = clean_str(xl_barcode_raw)
        xl_qty  = float(xl_qty_raw)  if xl_qty_raw  is not None else 0.0
        xl_cost = float(xl_cost_raw) if xl_cost_raw is not None else 0.0

        match = code_to_item.get(xl_code) or barcode_to_item.get(xl_barcode)

        if not match:
            unmatched.append({
                "code": xl_code,
                "barcode": xl_barcode,
                "name": xl_name,
                "qty": xl_qty,
            })
            continue

        item_id = match["id"]
        if item_id in seen_item_ids:
            continue
        seen_item_ids.add(item_id)

        system_qty = item_current_stock.get(item_id, 0.0)

        lines.append({
            "item_id":     item_id,
            "item_name":   match.get("name") or xl_name,
            "counted_qty": xl_qty,
            "system_qty":  system_qty,
            "unit_cost":   xl_cost,
        })

    return lines, unmatched


def main():
    parser = argparse.ArgumentParser(
        description="Import an Excel stock file into a Super POS inventory session."
    )
    parser.add_argument(
        "--file",
        default=str(Path.home() / "Downloads" / "hadat stock 12042026.xlsx"),
        help="Path to the Excel stock file",
    )
    parser.add_argument(
        "--warehouse-id",
        default=None,
        dest="warehouse_id",
        help="UUID of the target warehouse (skips interactive prompt)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt before writing to DB",
    )
    args = parser.parse_args()

    xlsx_path = Path(args.file)
    if not xlsx_path.exists():
        print(f"ERROR: File not found: {xlsx_path}")
        sys.exit(1)

    warehouse_id = pick_warehouse(args.warehouse_id)

    print("\nLooking up operator...")
    operator_id = get_operator_id()

    print(f"\nReading: {xlsx_path}")
    excel_rows = load_excel_rows(str(xlsx_path))
    print(f"  Excel rows (excluding header): {len(excel_rows)}")

    print("Building item lookup maps from DB...")
    code_to_item, barcode_to_item, item_current_stock = build_lookup_maps(warehouse_id)
    print(f"  DB items indexed by code  : {len(code_to_item)}")
    print(f"  DB barcodes indexed       : {len(barcode_to_item)}")

    print("Matching Excel rows to DB items...")
    lines, unmatched = match_rows(excel_rows, code_to_item, barcode_to_item, item_current_stock)

    print(f"\n--- Match Report ---")
    print(f"  Total Excel rows : {len(excel_rows)}")
    print(f"  Matched          : {len(lines)}")
    print(f"  Unmatched        : {len(unmatched)}")
    if unmatched:
        print("\n  Unmatched items (will NOT be imported):")
        for u in unmatched:
            print(f"    Code={u['code']:>12}  Barcode={u['barcode']:<20}  Qty={u['qty']:>8.2f}  {u['name']}")

    if not lines:
        print("\nNo items matched — nothing to import. Exiting.")
        sys.exit(0)

    if not args.yes:
        print(f"\nThis will create 1 inventory session with {len(lines)} lines.")
        print(f"  Warehouse : {warehouse_id}")
        print(f"  Date      : {date.today().isoformat()}")
        answer = input("\nProceed? [y/N] ").strip().lower()
        if answer != "y":
            print("Cancelled.")
            sys.exit(0)

    from services.inventory_session_service import InventorySessionService

    session_number = InventorySessionService.next_session_number(warehouse_id)
    print(f"\nCreating inventory session {session_number}...")

    ok, result = InventorySessionService.save_session(
        session_id="",
        warehouse_id=warehouse_id,
        operator_id=operator_id,
        session_date=date.today().isoformat(),
        notes=f"Imported from {xlsx_path.name}",
        lines=lines,
        session_number=session_number,
    )

    if ok:
        print(f"\nSUCCESS.")
        print(f"  Session number : {session_number}")
        print(f"  Session ID     : {result}")
        print(f"  Lines saved    : {len(lines)}")
    else:
        print(f"\nFAILED: {result}")
        sys.exit(1)


if __name__ == "__main__":
    main()
