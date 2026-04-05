```python
class ItemService:

    @staticmethod
    def search_items(query: str = "", category_id: str = "",
                      active_only: bool = False, limit: int = 500, offset: int = 0,
                      name_query: str = "", code_query: str = "", barcode_query: str = "") -> list[ItemRow]:
        init_db()
        session = get_session()
        try:
            q = session.query(
                Item.id, Item.code, Item.name,
                Item.cost_price, Item.cost_currency,
                Item.is_active, Item.is_pos_featured,
                Category.name.label("category_name"),
            ).outerjoin(Category, Item.category_id == Category.id)

            if active_only:
                q = q.filter(Item.is_active == True)
            if category_id:
                q = q.filter(Item.category_id == category_id)

            # Specific field filters take priority over the combined query
            if name_query:
                q = q.filter(Item.name.ilike(f"%{name_query}%"))
            elif code_query:
                q = q.filter(Item.code.ilike(f"%{code_query}%"))
            elif barcode_query:
                barcode_ids = session.query(ItemBarcode.item_id).filter(
                    ItemBarcode.barcode.ilike(f"{barcode_query}%")
                ).scalar_subquery()
                q = q.filter(Item.id.in_(barcode_ids))
            elif query:
                like = f"%{query}%"
                barcode_ids = session.query(ItemBarcode.item_id).filter(
                    ItemBarcode.barcode.ilike(like)
                ).scalar_subquery()
                q = q.filter(
                    Item.name.ilike(like) |
                    Item.code.ilike(like) |
                    Item.id.in_(barcode_ids)
                )

            q = q.limit(limit).offset(offset)
            items = q.all()
            item_rows = []
            for item in items:
                item_row = ItemRow(
                    item.id,
                    item.code,
                    item.name,
                    item.cost_price,
                    item.cost_currency,
                    item.is_active,
                    item.is_pos_featured,
                    category_name=item.category_name,
                )
                item_rows.append(item_row)
            return item_rows
        finally:
            session.close()
```