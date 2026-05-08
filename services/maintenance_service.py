"""Maintenance utilities — rebuild stock quantities from movement history."""
from database.engine import get_session, init_db


class MaintenanceService:

    @staticmethod
    def rebuild_stock_quantities() -> tuple[bool, str]:
        """
        Recalculate every ItemStock.quantity by summing all StockMovement rows
        for that (item_id, warehouse_id) pair.  Quantities are signed in
        StockMovement (positive = IN, negative = OUT) so a plain SUM gives the
        correct current level.

        Creates missing ItemStock rows and zeroes out any that have no movements.
        Returns (success, message).
        """
        init_db()
        session = get_session()
        try:
            from database.models.items import ItemStock
            from database.models.stock import StockMovement
            from database.models.base import new_uuid
            from sqlalchemy import func

            # Sum movements per (item_id, warehouse_id)
            rows = (
                session.query(
                    StockMovement.item_id,
                    StockMovement.warehouse_id,
                    func.sum(StockMovement.quantity).label("qty"),
                )
                .group_by(StockMovement.item_id, StockMovement.warehouse_id)
                .all()
            )

            updated = created = 0
            seen: set[tuple] = set()

            for item_id, warehouse_id, qty in rows:
                qty = max(0.0, float(qty or 0))
                key = (item_id, warehouse_id)
                seen.add(key)
                stock = session.query(ItemStock).filter_by(
                    item_id=item_id, warehouse_id=warehouse_id
                ).first()
                if stock:
                    stock.quantity = qty
                    updated += 1
                else:
                    session.add(ItemStock(
                        id=new_uuid(),
                        item_id=item_id,
                        warehouse_id=warehouse_id,
                        quantity=qty,
                    ))
                    created += 1

            # Zero out ItemStock rows that have no movements at all
            zeroed = 0
            for stock in session.query(ItemStock).all():
                if (stock.item_id, stock.warehouse_id) not in seen:
                    stock.quantity = 0.0
                    zeroed += 1

            session.commit()
            parts = []
            if updated:
                parts.append(f"{updated} updated")
            if created:
                parts.append(f"{created} created")
            if zeroed:
                parts.append(f"{zeroed} zeroed")
            return True, "Stock rebuilt — " + (", ".join(parts) or "nothing changed") + "."

        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            session.close()
