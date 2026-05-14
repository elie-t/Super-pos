"""
Recipe & costing service for restaurant mode.
"""
from database.engine import get_session, init_db


class RecipeService:

    @staticmethod
    def get_all(active_only: bool = True) -> list[dict]:
        init_db()
        session = get_session()
        try:
            from database.models.restaurant import Recipe
            q = session.query(Recipe)
            if active_only:
                q = q.filter(Recipe.is_active == True)
            recipes = q.order_by(Recipe.name).all()
            result = []
            for r in recipes:
                cost = RecipeService._calc_cost(r, session)
                result.append({
                    "id": r.id, "name": r.name,
                    "description": r.description or "",
                    "category": r.category or "",
                    "selling_price": r.selling_price,
                    "currency": r.currency,
                    "is_active": r.is_active,
                    "cost": cost,
                    "margin": RecipeService._margin(r.selling_price, cost),
                })
            return result
        finally:
            session.close()

    @staticmethod
    def get_detail(recipe_id: str) -> dict | None:
        init_db()
        session = get_session()
        try:
            from database.models.restaurant import Recipe
            r = session.get(Recipe, recipe_id)
            if not r:
                return None
            ingredients = []
            for ing in r.ingredients:
                from database.models.items import Item
                item = session.get(Item, ing.item_id)
                cost_per_unit = float(item.cost_price or 0) if item else 0.0
                line_cost = cost_per_unit * ing.quantity
                ingredients.append({
                    "id": ing.id,
                    "item_id": ing.item_id,
                    "item_name": item.name if item else "—",
                    "item_code": item.code if item else "",
                    "quantity": ing.quantity,
                    "unit": ing.unit,
                    "cost_per_unit": cost_per_unit,
                    "cost_currency": item.cost_currency if item else "USD",
                    "line_cost": line_cost,
                })
            total_cost = sum(i["line_cost"] for i in ingredients)
            return {
                "id": r.id, "name": r.name,
                "description": r.description or "",
                "category": r.category or "",
                "selling_price": r.selling_price,
                "currency": r.currency,
                "is_active": r.is_active,
                "ingredients": ingredients,
                "total_cost": total_cost,
                "margin": RecipeService._margin(r.selling_price, total_cost),
            }
        finally:
            session.close()

    @staticmethod
    def save(recipe_id: str, name: str, description: str, category: str,
             selling_price: float, currency: str,
             ingredients: list[dict]) -> tuple[bool, str]:
        """
        ingredients: list of {item_id, quantity, unit}
        Returns (ok, error_message)
        """
        init_db()
        session = get_session()
        try:
            from database.models.restaurant import Recipe, RecipeIngredient
            from database.models.base import new_uuid

            if recipe_id:
                r = session.get(Recipe, recipe_id)
                if not r:
                    return False, "Recipe not found."
            else:
                r = Recipe(id=new_uuid())
                session.add(r)

            r.name          = name.strip()
            r.description   = description.strip() or None
            r.category      = category.strip() or None
            r.selling_price = selling_price
            r.currency      = currency
            r.is_active     = True

            # Replace ingredients
            for ing in list(r.ingredients):
                session.delete(ing)
            session.flush()

            for row in ingredients:
                if not row.get("item_id") or row.get("quantity", 0) <= 0:
                    continue
                session.add(RecipeIngredient(
                    id=new_uuid(),
                    recipe_id=r.id,
                    item_id=row["item_id"],
                    quantity=float(row["quantity"]),
                    unit=row.get("unit", "PCS"),
                ))

            session.commit()
            return True, ""
        except Exception as exc:
            session.rollback()
            return False, str(exc)
        finally:
            session.close()

    @staticmethod
    def delete(recipe_id: str) -> tuple[bool, str]:
        init_db()
        session = get_session()
        try:
            from database.models.restaurant import Recipe
            r = session.get(Recipe, recipe_id)
            if r:
                session.delete(r)
                session.commit()
            return True, ""
        except Exception as exc:
            session.rollback()
            return False, str(exc)
        finally:
            session.close()

    @staticmethod
    def search_items(query: str, limit: int = 20) -> list[dict]:
        init_db()
        session = get_session()
        try:
            from database.models.items import Item
            from sqlalchemy import or_
            like = f"%{query}%"
            rows = (session.query(Item)
                    .filter(Item.is_active == True,
                            or_(Item.name.ilike(like), Item.code.ilike(like)))
                    .limit(limit).all())
            return [{"id": i.id, "name": i.name, "code": i.code,
                     "unit": i.unit, "cost_price": float(i.cost_price or 0),
                     "cost_currency": i.cost_currency or "USD"}
                    for i in rows]
        finally:
            session.close()

    @staticmethod
    def _calc_cost(recipe, session) -> float:
        total = 0.0
        for ing in recipe.ingredients:
            from database.models.items import Item
            item = session.get(Item, ing.item_id)
            if item:
                total += float(item.cost_price or 0) * ing.quantity
        return total

    @staticmethod
    def _margin(selling: float, cost: float) -> float:
        if selling <= 0:
            return 0.0
        return round((selling - cost) / selling * 100, 1)
