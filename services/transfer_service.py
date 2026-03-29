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
    def confirm_transfer(
        from_warehouse_id: str,
        to_warehouse_id: str,
        operator_id: str,
        transfer_date: str,
        notes: str,
        lines: list[dict],          # [{"item_id", "item_name", "barcode", "qty", "unit_cost"}]
        transfer_number: str = "",  # override auto-generated number if provided
    ) -> tuple[bool, str]:
        """
        Creates a WarehouseTransfer record + 2 StockMovements per line:
          - transfer_out  (negative qty) from source
          - transfer_in   (positive qty) to destination
        Updates ItemStock cache for both warehouses.
        Returns (success, transfer_id_or_error).
        """
        if not lines:
            return False, "No items to transfer."
        if from_warehouse_id == to_warehouse_id:
            return False, "Source and destination must be different warehouses."

        init_db()
        session = get_session()
        try:
            from database.models.stock import WarehouseTransfer, WarehouseTransferItem, StockMovement
            from database.models.items import ItemStock
            from database.models.base import new_uuid

            if not transfer_number:
                transfer_number = TransferService.next_transfer_number(from_warehouse_id)

            transfer = WarehouseTransfer(
                id=new_uuid(),
                transfer_number=transfer_number,
                from_warehouse_id=from_warehouse_id,
                to_warehouse_id=to_warehouse_id,
                transfer_date=transfer_date,
                status="confirmed",
                operator_id=operator_id,
                notes=notes or None,
            )
            session.add(transfer)
            session.flush()

            for line in lines:
                qty      = float(line["qty"])
                item_id  = line["item_id"]
                cost     = float(line.get("unit_cost", 0.0))

                # Transfer record item
                session.add(WarehouseTransferItem(
                    id=new_uuid(),
                    transfer_id=transfer.id,
                    item_id=item_id,
                    item_name=line.get("item_name", ""),
                    quantity=qty,
                    unit_cost=cost,
                ))

                # Stock movement OUT from source
                session.add(StockMovement(
                    id=new_uuid(),
                    item_id=item_id,
                    warehouse_id=from_warehouse_id,
                    movement_type="transfer_out",
                    quantity=-qty,
                    unit_cost=cost,
                    reference_type="transfer",
                    reference_id=transfer.id,
                    operator_id=operator_id,
                ))

                # Stock movement IN to destination
                session.add(StockMovement(
                    id=new_uuid(),
                    item_id=item_id,
                    warehouse_id=to_warehouse_id,
                    movement_type="transfer_in",
                    quantity=qty,
                    unit_cost=cost,
                    reference_type="transfer",
                    reference_id=transfer.id,
                    operator_id=operator_id,
                ))

                # Update ItemStock cache for source (deduct)
                src_stock = session.query(ItemStock).filter_by(
                    item_id=item_id, warehouse_id=from_warehouse_id
                ).first()
                if src_stock:
                    src_stock.quantity -= qty
                else:
                    session.add(ItemStock(
                        id=new_uuid(), item_id=item_id,
                        warehouse_id=from_warehouse_id, quantity=-qty,
                    ))

                # Update ItemStock cache for destination (add)
                dst_stock = session.query(ItemStock).filter_by(
                    item_id=item_id, warehouse_id=to_warehouse_id
                ).first()
                if dst_stock:
                    dst_stock.quantity += qty
                else:
                    session.add(ItemStock(
                        id=new_uuid(), item_id=item_id,
                        warehouse_id=to_warehouse_id, quantity=qty,
                    ))

            session.commit()
            TransferService.increment_transfer_number(from_warehouse_id)

            try:
                from sync.service import push_transfer
                push_transfer(transfer.id)
            except Exception:
                pass

            return True, transfer.id

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
