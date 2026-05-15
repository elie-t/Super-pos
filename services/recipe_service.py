"""
Recipe & costing service — recipes are linked to items (one recipe per item).
"""
from database.engine import get_session, init_db

# ── Unit conversion ───────────────────────────────────────────────────────────
# All units normalised to a base: weight→kg, volume→L, count→PCS
_UNIT_BASE = {
    "kg": 1.0,        "g": 1e-3,       "mg": 1e-6,
    "L":  1.0,        "ml": 1e-3,
    "tsp": 4.929e-3,  "tbsp": 14.787e-3, "cup": 0.2366,
    "PCS": 1.0,
}
_WEIGHT  = {"kg", "g", "mg"}
_VOLUME  = {"L", "ml", "tsp", "tbsp", "cup"}
_COUNT   = {"PCS"}


def _unit_category(u: str) -> str:
    if u in _WEIGHT: return "weight"
    if u in _VOLUME: return "volume"
    return "count"


def calc_line_cost(cost_per_item_unit: float, item_unit: str,
                   recipe_qty: float, recipe_unit: str) -> float:
    """
    Return the cost for using recipe_qty (in recipe_unit) of an ingredient
    whose cost_price is expressed per item_unit.

    Example: flour costs $1/kg, recipe uses 200 g → 0.2 × $1 = $0.20
    Falls back to raw multiplication when units are unknown or incompatible.
    """
    ib = _UNIT_BASE.get(item_unit)
    rb = _UNIT_BASE.get(recipe_unit)
    if ib and rb and _unit_category(item_unit) == _unit_category(recipe_unit):
        qty_in_item_unit = (recipe_qty * rb) / ib
        return cost_per_item_unit * qty_in_item_unit
    return cost_per_item_unit * recipe_qty


class RecipeService:

    @staticmethod
    def get_for_item(item_id: str) -> dict | None:
        """Return recipe detail for an item, or None if no recipe exists."""
        init_db()
        session = get_session()
        try:
            from database.models.restaurant import Recipe
            r = session.query(Recipe).filter(Recipe.item_id == item_id).first()
            if not r:
                return None
            return RecipeService._build_detail(r, session)
        finally:
            session.close()

    @staticmethod
    def save_for_item(item_id: str, notes: str,
                      ingredients: list[dict]) -> tuple[float, str]:
        """
        Save (create/update) a recipe for an item.
        ingredients: list of {item_id, quantity, unit}
        Returns (calculated_cost, error_message).
        """
        init_db()
        session = get_session()
        try:
            from database.models.restaurant import Recipe, RecipeIngredient
            from database.models.base import new_uuid

            r = session.query(Recipe).filter(Recipe.item_id == item_id).first()
            if not r:
                r = Recipe(id=new_uuid(), item_id=item_id)
                session.add(r)

            r.notes = notes.strip() or None

            for ing in list(r.ingredients):
                session.delete(ing)
            session.flush()

            total_cost = 0.0
            for row in ingredients:
                if not row.get("item_id") or float(row.get("quantity", 0)) <= 0:
                    continue
                qty = float(row["quantity"])
                session.add(RecipeIngredient(
                    id=new_uuid(),
                    recipe_id=r.id,
                    item_id=row["item_id"],
                    quantity=qty,
                    unit=row.get("unit", "PCS"),
                ))
                from database.models.items import Item
                ing_item = session.get(Item, row["item_id"])
                if ing_item:
                    total_cost += calc_line_cost(
                        float(ing_item.cost_price or 0),
                        ing_item.unit or "PCS",
                        qty,
                        row.get("unit", "PCS"),
                    )

            session.commit()
            return total_cost, ""
        except Exception as exc:
            session.rollback()
            return 0.0, str(exc)
        finally:
            session.close()

    @staticmethod
    def delete_for_item(item_id: str):
        init_db()
        session = get_session()
        try:
            from database.models.restaurant import Recipe
            r = session.query(Recipe).filter(Recipe.item_id == item_id).first()
            if r:
                session.delete(r)
                session.commit()
        finally:
            session.close()

    @staticmethod
    def search_ingredients(query: str, limit: int = 20) -> list[dict]:
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
    def _build_detail(recipe, session) -> dict:
        from database.models.items import Item
        ingredients = []
        total_cost = 0.0
        for ing in recipe.ingredients:
            item = session.get(Item, ing.item_id)
            cpu = float(item.cost_price or 0) if item else 0.0
            lc  = calc_line_cost(cpu, item.unit or "PCS" if item else "PCS",
                                 ing.quantity, ing.unit)
            total_cost += lc
            ingredients.append({
                "id":           ing.id,
                "item_id":      ing.item_id,
                "item_name":    item.name if item else "—",
                "item_code":    item.code if item else "",
                "quantity":     ing.quantity,
                "unit":         ing.unit,
                "cost_per_unit": cpu,
                "cost_currency": item.cost_currency if item else "USD",
                "line_cost":    lc,
            })
        return {
            "id":           recipe.id,
            "item_id":      recipe.item_id,
            "notes":        recipe.notes or "",
            "ingredients":  ingredients,
            "total_cost":   total_cost,
        }
