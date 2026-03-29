"""Inventory Session (physical stock count) service."""
from database.engine import get_session, init_db


class InventorySessionService:

    @staticmethod
    def next_session_number(warehouse_id: str) -> str:
        """INV{wh_num * 10000 + seq}  e.g.  INV10001, INV20001"""
        init_db()
        session = get_session()
        try:
            from database.models.items import Setting, Warehouse
            wh = session.query(Warehouse).filter_by(id=warehouse_id).first()
            wh_num = wh.number if (wh and wh.number is not None) else 0
            key = f"next_inventory_number_wh{wh_num}"
            s = session.get(Setting, key)
            seq = int(s.value) if s else 1
            return f"INV{wh_num * 10000 + seq}"
        finally:
            session.close()

    # ── Save (create or update) ────────────────────────────────────────────────

    @staticmethod
    def save_session(
        session_id:   str,
        warehouse_id: str,
        operator_id:  str,
        session_date: str,
        notes:        str,
        lines:        list[dict],
        session_number: str = "",
    ) -> tuple[bool, str]:
        """
        Create a new inventory session or update an existing open one.

        Each line dict must have:
            item_id, item_name, counted_qty, system_qty, unit_cost

        On save:
          - Existing stock movements for this session are reversed first.
          - diff = counted_qty - system_qty
          - If diff > 0 → adjustment_in movement (+diff)
          - If diff < 0 → adjustment_out movement (diff, negative)
          - ItemStock is set to counted_qty directly.
        """
        if not lines:
            return False, "No items to save."

        init_db()
        db = get_session()
        try:
            from database.models.inventory import InventorySession, InventorySessionItem
            from database.models.items import ItemStock, Warehouse, Setting
            from database.models.stock import StockMovement
            from database.models.base import new_uuid

            if session_id:
                # ── Update existing ──────────────────────────────────────────
                inv = db.query(InventorySession).filter_by(id=session_id).first()
                if not inv:
                    return False, "Inventory session not found."
                if inv.status == "locked":
                    return False, "Session is locked and cannot be edited."

                # Reverse previous stock adjustments
                InventorySessionService._reverse_stock(
                    db, session_id, inv.warehouse_id,
                    inv.items, new_uuid, ItemStock, StockMovement
                )

                # Remove old lines
                for li in list(inv.items):
                    db.delete(li)
                db.flush()

                # Update header
                inv.warehouse_id = warehouse_id
                inv.session_date = session_date
                inv.operator_id  = operator_id or None
                inv.notes        = notes or None
                inv.status       = "open"
                db.flush()

            else:
                # ── Create new ───────────────────────────────────────────────
                wh = db.query(Warehouse).filter_by(id=warehouse_id).first()
                wh_num = wh.number if (wh and wh.number is not None) else 0
                seq_key = f"next_inventory_number_wh{wh_num}"
                s = db.get(Setting, seq_key)
                seq = int(s.value) if s else 1
                if not session_number:
                    session_number = f"INV{wh_num * 10000 + seq}"
                # Increment counter in same session
                if s:
                    s.value = str(seq + 1)
                else:
                    db.add(Setting(key=seq_key, value="2"))

                inv = InventorySession(
                    id=new_uuid(),
                    session_number=session_number,
                    warehouse_id=warehouse_id,
                    session_date=session_date,
                    status="open",
                    operator_id=operator_id or None,
                    notes=notes or None,
                )
                db.add(inv)
                db.flush()

            # Add new line items and apply stock movements
            for line in lines:
                item_id     = line["item_id"]
                counted_qty = float(line["counted_qty"])
                system_qty  = float(line["system_qty"])
                diff        = counted_qty - system_qty
                unit_cost   = float(line.get("unit_cost", 0.0))

                db.add(InventorySessionItem(
                    id=new_uuid(),
                    session_id=inv.id,
                    item_id=item_id,
                    item_name=line.get("item_name", ""),
                    system_qty=system_qty,
                    counted_qty=counted_qty,
                    diff_qty=diff,
                    unit_cost=unit_cost,
                ))

                # Stock movement
                if diff != 0:
                    mv_type = "adjustment_in" if diff > 0 else "adjustment_out"
                    db.add(StockMovement(
                        id=new_uuid(),
                        item_id=item_id,
                        warehouse_id=warehouse_id,
                        movement_type=mv_type,
                        quantity=diff,
                        unit_cost=unit_cost,
                        reference_type="inventory",
                        reference_id=inv.id,
                        operator_id=operator_id or None,
                    ))

                # Set ItemStock to actual counted qty
                stock = db.query(ItemStock).filter_by(
                    item_id=item_id, warehouse_id=warehouse_id
                ).first()
                if stock:
                    stock.quantity = counted_qty
                else:
                    db.add(ItemStock(
                        id=new_uuid(),
                        item_id=item_id,
                        warehouse_id=warehouse_id,
                        quantity=counted_qty,
                    ))

            db.commit()
            saved_id = inv.id

        except Exception as exc:
            db.rollback()
            return False, str(exc)
        finally:
            db.close()

        # Push to Supabase after session is fully closed
        try:
            from sync.service import push_inventory_session
            ok, err = push_inventory_session(saved_id)
            if not ok:
                print(f"[inventory] push failed: {err}")
        except Exception as e:
            print(f"[inventory] push exception: {e}")

        return True, saved_id

    # ── Reverse helper ─────────────────────────────────────────────────────────

    @staticmethod
    def _reverse_stock(db, session_id, warehouse_id, items,
                       new_uuid, ItemStock, StockMovement):
        """Delete stock movements and restore ItemStock to pre-session values."""
        for li in items:
            # Restore ItemStock: reverse the diff that was applied
            stock = db.query(ItemStock).filter_by(
                item_id=li.item_id, warehouse_id=warehouse_id
            ).first()
            if stock:
                # The session set stock to counted_qty; restore to system_qty
                stock.quantity = li.system_qty
            else:
                db.add(ItemStock(
                    id=new_uuid(),
                    item_id=li.item_id,
                    warehouse_id=warehouse_id,
                    quantity=li.system_qty,
                ))

            # Delete the movement records
            db.query(StockMovement).filter(
                StockMovement.reference_id == session_id,
                StockMovement.item_id == li.item_id,
            ).delete()

    # ── Lock / Unlock ──────────────────────────────────────────────────────────

    @staticmethod
    def lock_session(session_id: str) -> tuple[bool, str]:
        init_db()
        db = get_session()
        try:
            from database.models.inventory import InventorySession
            inv = db.query(InventorySession).filter_by(id=session_id).first()
            if not inv:
                return False, "Session not found."
            if inv.status == "locked":
                return True, session_id
            inv.status = "locked"
            db.commit()
            return True, session_id
        except Exception as exc:
            db.rollback()
            return False, str(exc)
        finally:
            db.close()

    @staticmethod
    def unlock_session(session_id: str) -> tuple[bool, str]:
        init_db()
        db = get_session()
        try:
            from database.models.inventory import InventorySession
            inv = db.query(InventorySession).filter_by(id=session_id).first()
            if not inv:
                return False, "Session not found."
            inv.status = "open"
            db.commit()
            return True, session_id
        except Exception as exc:
            db.rollback()
            return False, str(exc)
        finally:
            db.close()

    # ── List / Detail ──────────────────────────────────────────────────────────

    @staticmethod
    def list_sessions(limit: int = 200) -> list[dict]:
        init_db()
        db = get_session()
        try:
            from database.models.inventory import InventorySession
            from database.models.items import Warehouse
            rows = (
                db.query(InventorySession)
                .order_by(InventorySession.created_at.desc())
                .limit(limit)
                .all()
            )
            result = []
            for s in rows:
                wh = db.query(Warehouse).filter_by(id=s.warehouse_id).first()
                result.append({
                    "id":         s.id,
                    "number":     s.session_number or "—",
                    "date":       s.session_date or "",
                    "warehouse":  wh.name if wh else "?",
                    "item_count": len(s.items),
                    "status":     s.status,
                })
            return result
        finally:
            db.close()

    @staticmethod
    def get_session_detail(session_id: str) -> dict | None:
        init_db()
        db = get_session()
        try:
            from database.models.inventory import InventorySession
            from database.models.items import Warehouse, ItemBarcode
            inv = db.query(InventorySession).filter_by(id=session_id).first()
            if not inv:
                return None
            wh = db.query(Warehouse).filter_by(id=inv.warehouse_id).first()

            lines = []
            for li in inv.items:
                bc_obj = db.query(ItemBarcode).filter_by(
                    item_id=li.item_id, is_primary=True
                ).first()
                code = li.item.code if li.item else ""
                barcode = bc_obj.barcode if bc_obj else ""
                lines.append({
                    "item_id":     li.item_id,
                    "item_name":   li.item_name or "",
                    "code":        code,
                    "barcode":     barcode,
                    "system_qty":  li.system_qty,
                    "counted_qty": li.counted_qty,
                    "diff_qty":    li.diff_qty,
                    "unit_cost":   li.unit_cost or 0.0,
                })

            return {
                "id":           inv.id,
                "number":       inv.session_number or "—",
                "date":         inv.session_date or "",
                "warehouse_id": inv.warehouse_id,
                "warehouse":    wh.name if wh else "?",
                "status":       inv.status,
                "notes":        inv.notes or "",
                "lines":        lines,
            }
        finally:
            db.close()
