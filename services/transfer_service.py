"""Warehouse Transfer service."""
from database.engine import get_session, init_db


class TransferService:

    @staticmethod
    def next_transfer_number(from_warehouse_id: str) -> str:
        """Per-source-warehouse numbering: from_wh_num * 10000 + seq.
        E.g. warehouse #1 → T10001, T10002; warehouse #2 → T20001."""
        init_db()
        session = get_session()
        try:
            from database.models.items import Setting, Warehouse
            wh = session.query(Warehouse).filter_by(id=from_warehouse_id).first()
            wh_num = wh.number if (wh and wh.number is not None) else 0
            key = f"next_transfer_number_wh{wh_num}"
            s = session.get(Setting, key)
            seq = int(s.value) if s else 1
            return f"T{wh_num * 10000 + seq}"
        finally:
            session.close()

    @staticmethod
    def increment_transfer_number(from_warehouse_id: str):
        init_db()
        session = get_session()
        try:
            from database.models.items import Setting, Warehouse
            wh = session.query(Warehouse).filter_by(id=from_warehouse_id).first()
            wh_num = wh.number if (wh and wh.number is not None) else 0
            key = f"next_transfer_number_wh{wh_num}"
            s = session.get(Setting, key)
            if s:
                s.value = str(int(s.value) + 1)
            else:
                session.add(Setting(key=key, value="2"))
            session.commit()
        finally:
            session.close()

    @staticmethod
    def get_warehouses():
        """Returns list of (id, name, number)."""
        from services.item_service import ItemService
        return [(wid, wname, num) for wid, wname, _def, num, _cust in ItemService.get_warehouses()]

    @staticmethod
    def get_item_stock(item_id: str, warehouse_id: str) -> float:
        """Current stock of item in a specific warehouse."""
        init_db()
        session = get_session()
        try:
            from database.models.items import ItemStock
            s = session.query(ItemStock).filter_by(
                item_id=item_id, warehouse_id=warehouse_id
            ).first()
            return s.quantity if s else 0.0
        finally:
            session.close()

    @staticmethod
    def _apply_stock(session, transfer_id, from_wh, to_wh, lines, operator_id,
                     new_uuid, ItemStock, StockMovement):
        """Add stock movements and update ItemStock for a list of lines."""
        for line in lines:
            qty     = float(line["qty"])
            item_id = line["item_id"]
            cost    = float(line.get("unit_cost", 0.0))

            session.add(StockMovement(
                id=new_uuid(), item_id=item_id, warehouse_id=from_wh,
                movement_type="transfer_out", quantity=-qty, unit_cost=cost,
                reference_type="transfer", reference_id=transfer_id,
                operator_id=operator_id,
            ))
            session.add(StockMovement(
                id=new_uuid(), item_id=item_id, warehouse_id=to_wh,
                movement_type="transfer_in", quantity=qty, unit_cost=cost,
                reference_type="transfer", reference_id=transfer_id,
                operator_id=operator_id,
            ))

            src = session.query(ItemStock).filter_by(item_id=item_id, warehouse_id=from_wh).first()
            if src:
                src.quantity -= qty
            else:
                session.add(ItemStock(id=new_uuid(), item_id=item_id, warehouse_id=from_wh, quantity=-qty))

            dst = session.query(ItemStock).filter_by(item_id=item_id, warehouse_id=to_wh).first()
            if dst:
                dst.quantity += qty
            else:
                session.add(ItemStock(id=new_uuid(), item_id=item_id, warehouse_id=to_wh, quantity=qty))

    @staticmethod
    def _reverse_stock(session, transfer_id, from_wh, to_wh, items,
                       new_uuid, ItemStock, StockMovement):
        """Reverse all stock movements for a transfer (used before re-save or unlock)."""
        for li in items:
            qty     = li.quantity
            item_id = li.item_id

            session.query(StockMovement).filter_by(
                reference_id=transfer_id, item_id=item_id, movement_type="transfer_out",
            ).delete()
            session.query(StockMovement).filter_by(
                reference_id=transfer_id, item_id=item_id, movement_type="transfer_in",
            ).delete()

            src = session.query(ItemStock).filter_by(item_id=item_id, warehouse_id=from_wh).first()
            if src:
                src.quantity += qty
            else:
                session.add(ItemStock(id=new_uuid(), item_id=item_id, warehouse_id=from_wh, quantity=qty))

            dst = session.query(ItemStock).filter_by(item_id=item_id, warehouse_id=to_wh).first()
            if dst:
                dst.quantity -= qty
            else:
                session.add(ItemStock(id=new_uuid(), item_id=item_id, warehouse_id=to_wh, quantity=-qty))

    @staticmethod
    def save_transfer(
        from_warehouse_id: str,
        to_warehouse_id: str,
        operator_id: str,
        transfer_date: str,
        notes: str,
        lines: list[dict],
        transfer_number: str = "",
        transfer_id: str = "",      # pass existing ID to update
    ) -> tuple[bool, str]:
        """
        Create a new transfer or update an existing open one.
        Stock movements are applied immediately (status = "open").
        If updating, existing movements are reversed first then reapplied.
        """
        if not lines:
            return False, "No items to transfer."
        if from_warehouse_id == to_warehouse_id:
            return False, "Source and destination must be different warehouses."

        init_db()
        session = get_session()
        try:
            from database.models.stock import WarehouseTransfer, WarehouseTransferItem, StockMovement
            from database.models.items import ItemStock, Warehouse, Setting
            from database.models.base import new_uuid

            if transfer_id:
                # ── Update existing transfer ──────────────────────────────────
                t = session.query(WarehouseTransfer).filter_by(id=transfer_id).first()
                if not t:
                    return False, "Transfer not found."
                if t.status == "locked":
                    return False, "Transfer is locked and cannot be edited."

                # Reverse old stock movements
                TransferService._reverse_stock(
                    session, transfer_id,
                    t.from_warehouse_id, t.to_warehouse_id,
                    t.items, new_uuid, ItemStock, StockMovement,
                )

                # Remove old line items
                for li in list(t.items):
                    session.delete(li)
                session.flush()

                # Update header
                t.from_warehouse_id = from_warehouse_id
                t.to_warehouse_id   = to_warehouse_id
                t.transfer_date     = transfer_date
                t.operator_id       = operator_id
                t.notes             = notes or None
                t.status            = "open"
                session.flush()
            else:
                # ── Create new transfer ───────────────────────────────────────
                # Compute transfer number and increment counter in the same session
                wh = session.query(Warehouse).filter_by(id=from_warehouse_id).first()
                wh_num = wh.number if (wh and wh.number is not None) else 0
                seq_key = f"next_transfer_number_wh{wh_num}"
                s = session.get(Setting, seq_key)
                seq = int(s.value) if s else 1
                if not transfer_number:
                    transfer_number = f"T{wh_num * 10000 + seq}"
                # Increment in same session
                if s:
                    s.value = str(seq + 1)
                else:
                    session.add(Setting(key=seq_key, value="2"))

                t = WarehouseTransfer(
                    id=new_uuid(),
                    transfer_number=transfer_number,
                    from_warehouse_id=from_warehouse_id,
                    to_warehouse_id=to_warehouse_id,
                    transfer_date=transfer_date,
                    status="open",
                    operator_id=operator_id,
                    notes=notes or None,
                )
                session.add(t)
                session.flush()

            # Add new line items
            for line in lines:
                session.add(WarehouseTransferItem(
                    id=new_uuid(),
                    transfer_id=t.id,
                    item_id=line["item_id"],
                    item_name=line.get("item_name") or line.get("name", ""),
                    quantity=float(line["qty"]),
                    unit_cost=float(line.get("unit_cost", 0.0)),
                ))

            # Apply stock movements
            TransferService._apply_stock(
                session, t.id,
                from_warehouse_id, to_warehouse_id,
                lines, operator_id, new_uuid, ItemStock, StockMovement,
            )

            session.commit()
            saved_id = t.id

        except Exception as exc:
            session.rollback()
            return False, str(exc)
        finally:
            session.close()

        # Push AFTER session is fully closed
        try:
            from sync.service import push_transfer
            ok, err = push_transfer(saved_id)
            if not ok:
                print(f"[transfer] push failed: {err}")
        except Exception as e:
            print(f"[transfer] push exception: {e}")

        return True, saved_id

    @staticmethod
    def lock_transfer(transfer_id: str) -> tuple[bool, str]:
        """Lock an open transfer to prevent further edits."""
        init_db()
        session = get_session()
        try:
            from database.models.stock import WarehouseTransfer
            t = session.query(WarehouseTransfer).filter_by(id=transfer_id).first()
            if not t:
                return False, "Transfer not found."
            if t.status == "locked":
                return True, transfer_id   # already locked
            t.status = "locked"
            session.commit()
            return True, transfer_id
        except Exception as exc:
            session.rollback()
            return False, str(exc)
        finally:
            session.close()

    @staticmethod
    def unlock_transfer(transfer_id: str) -> tuple[bool, str]:
        """Unlock a locked transfer so it can be edited again."""
        init_db()
        session = get_session()
        try:
            from database.models.stock import WarehouseTransfer
            t = session.query(WarehouseTransfer).filter_by(id=transfer_id).first()
            if not t:
                return False, "Transfer not found."
            t.status = "open"
            session.commit()
            return True, transfer_id
        except Exception as exc:
            session.rollback()
            return False, str(exc)
        finally:
            session.close()

    @staticmethod
    def list_transfers(limit: int = 100) -> list[dict]:
        """Recent confirmed transfers for the history view."""
        init_db()
        session = get_session()
        try:
            from database.models.stock import WarehouseTransfer
            from database.models.items import Warehouse
            rows = session.query(WarehouseTransfer)\
                .order_by(WarehouseTransfer.created_at.desc()).limit(limit).all()
            result = []
            for t in rows:
                fw = session.query(Warehouse).filter_by(id=t.from_warehouse_id).first()
                tw = session.query(Warehouse).filter_by(id=t.to_warehouse_id).first()
                result.append({
                    "id":          t.id,
                    "number":      t.transfer_number or "—",
                    "date":        t.transfer_date or "",
                    "from_wh":     fw.name if fw else "?",
                    "to_wh":       tw.name if tw else "?",
                    "status":      t.status,
                    "item_count":  len(t.items),
                })
            return result
        finally:
            session.close()

    @staticmethod
    def get_transfer_detail(transfer_id: str) -> dict | None:
        """Full transfer with line items."""
        init_db()
        session = get_session()
        try:
            from database.models.stock import WarehouseTransfer
            from database.models.items import Warehouse, ItemBarcode
            t = session.query(WarehouseTransfer).filter_by(id=transfer_id).first()
            if not t:
                return None
            fw = session.query(Warehouse).filter_by(id=t.from_warehouse_id).first()
            tw = session.query(Warehouse).filter_by(id=t.to_warehouse_id).first()

            lines = []
            for li in t.items:
                bc_obj = session.query(ItemBarcode).filter_by(
                    item_id=li.item_id, is_primary=True
                ).first()
                code = li.item.code if li.item else ""
                barcode = bc_obj.barcode if bc_obj else ""
                lines.append({
                    "item_id":   li.item_id,
                    "item_name": li.item_name or "",
                    "code":      code,
                    "barcode":   barcode,
                    "qty":       li.quantity,
                    "unit_cost": li.unit_cost or 0.0,
                })

            return {
                "id":             t.id,
                "number":         t.transfer_number or "—",
                "date":           t.transfer_date or "",
                "from_wh_id":     t.from_warehouse_id,
                "to_wh_id":       t.to_warehouse_id,
                "from_wh":        fw.name if fw else "?",
                "to_wh":          tw.name if tw else "?",
                "status":         t.status,
                "notes":          t.notes or "",
                "lines":          lines,
            }
        finally:
            session.close()
