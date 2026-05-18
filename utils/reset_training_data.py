"""
Reset Training Data
-------------------
Run once after cashier training to wipe all test transactions and restore stock.

Usage:
    cd /path/to/super_pos
    python3 utils/reset_training_data.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.engine import get_session, init_db
from database.models.invoices import SalesInvoice, SalesInvoiceItem, HeldInvoice
from database.models.financials import Payment
from database.models.users import OperatorSession
from database.models.stock import StockMovement
from database.models.sync import SyncQueue
from database.models.items import ItemStock


def main():
    init_db()
    s = get_session()

    try:
        # ── Counts ────────────────────────────────────────────────────────────
        n_inv       = s.query(SalesInvoice).count()
        n_items     = s.query(SalesInvoiceItem).count()
        n_pay       = s.query(Payment).count()
        n_sessions  = s.query(OperatorSession).count()
        n_held      = s.query(HeldInvoice).count()
        n_movements = s.query(StockMovement).filter(
                          StockMovement.movement_type == "sale").count()
        n_sync      = s.query(SyncQueue).count()

        print("=" * 52)
        print("   RESET TRAINING DATA — what will be deleted")
        print("=" * 52)
        print(f"  Sales invoices          : {n_inv}")
        print(f"  Invoice line items      : {n_items}")
        print(f"  Payments                : {n_pay}")
        print(f"  Operator sessions       : {n_sessions}")
        print(f"  Held invoices           : {n_held}")
        print(f"  Sale stock movements    : {n_movements}  (stock will be restored)")
        print(f"  Sync queue entries      : {n_sync}")
        print("=" * 52)
        print()
        print("  Items, prices, users, warehouses, settings")
        print("  and purchase invoices are NOT touched.")
        print()

        confirm = input("  Type  YES  to proceed: ").strip()
        if confirm != "YES":
            print("  Cancelled.")
            return

        print()
        print("  Restoring stock quantities from sale movements...")
        # Reverse every sale movement in item_stock
        sale_movements = s.query(StockMovement).filter(
            StockMovement.movement_type == "sale"
        ).all()
        for mv in sale_movements:
            stock_row = s.query(ItemStock).filter_by(
                item_id=mv.item_id, warehouse_id=mv.warehouse_id
            ).first()
            if stock_row:
                # sale movements are negative; subtracting a negative = adding back
                stock_row.quantity -= mv.quantity

        # ── Delete in FK-safe order ────────────────────────────────────────────
        print("  Deleting sale stock movements...")
        s.query(StockMovement).filter(
            StockMovement.movement_type == "sale"
        ).delete(synchronize_session=False)

        print("  Deleting invoice line items...")
        s.query(SalesInvoiceItem).delete(synchronize_session=False)

        print("  Deleting payments...")
        s.query(Payment).delete(synchronize_session=False)

        print("  Deleting held invoices...")
        s.query(HeldInvoice).delete(synchronize_session=False)

        print("  Deleting sales invoices...")
        s.query(SalesInvoice).delete(synchronize_session=False)

        print("  Deleting operator sessions...")
        s.query(OperatorSession).delete(synchronize_session=False)

        print("  Clearing sync queue...")
        s.query(SyncQueue).delete(synchronize_session=False)

        s.commit()
        print()
        print("  Done. All training data removed and stock restored.")
        print("  You can now start real operations.")
        print()

    except Exception as e:
        s.rollback()
        print(f"\n  ERROR: {e}")
        raise
    finally:
        s.close()


if __name__ == "__main__":
    main()
