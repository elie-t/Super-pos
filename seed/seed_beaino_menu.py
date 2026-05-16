"""
Seed script: Full Furn Beaino menu (all categories)
Source: https://order.furnbeaino.com / config/data.min.js

Run from the project root:
    python seed/seed_beaino_menu.py

What it does:
- Creates 8 categories with show_on_touch=True, show_on_home=True
- Creates ~44 unique items with USD prices and cover images
- Downloads images to data/images/items/
- Items shared across categories (e.g. Light) are created once under their
  primary category and skipped on subsequent categories
- Manakish (MNK*) items already seeded by seed_manakish.py are left untouched
- Safe to re-run: skips anything already in the DB by item code

Adjust USD prices in MENU_DATA below before running if needed.
"""
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from database.engine import init_db, SessionLocal
from database.models.items import Category, Item, ItemPrice, ItemBarcode
from database.models.base import new_uuid

IMG_DIR = os.path.join(ROOT, "data", "images", "items")
os.makedirs(IMG_DIR, exist_ok=True)

BASE_IMG = "https://beaino.weevi.com/static/content/uploads/ekomproducts/"

# ─────────────────────────────────────────────────────────────────────────────
# Menu data — edit price_usd values here to match your actual selling prices
# ─────────────────────────────────────────────────────────────────────────────
MENU_DATA = [
    # ── Pizza ──────────────────────────────────────────────────────────────────
    {
        "category": "Pizza",
        "sort_order": 2,
        "items": [
            {"code": "PIZ001", "name": "Barbecue Chicken",  "price_usd": 7.00, "img": "BBQ-Chicken-Pizza.jpg",
             "desc": "Smoky Barbecue Sauce topped with Grilled Chicken, Red Onions and Mixed Peppers"},
            {"code": "PIZ002", "name": "Pepperoni",          "price_usd": 6.50, "img": "Pepperoni.jpg",
             "desc": "Classic Pepperoni loaded on a Rich Tomato Sauce base with Melted Mozzarella"},
            {"code": "PIZ003", "name": "Classic Ham",        "price_usd": 5.50, "img": "Classic-Ham.jpg",
             "desc": "Premium Ham with Mozzarella Cheese on a Classic Tomato Sauce"},
            {"code": "PIZ004", "name": "Classic Turkey",     "price_usd": 5.50, "img": "Classic-Turkey.jpg",
             "desc": "Sliced Turkey Breast with Mozzarella on a Classic Tomato Sauce"},
            {"code": "PIZ005", "name": "Vegetarian",         "price_usd": 5.50, "img": "Vegetarian.jpg",
             "desc": "Fresh Garden Vegetables on a Tomato Sauce base with Mozzarella"},
            {"code": "PIZ006", "name": "Easy Cheesy",        "price_usd": 5.50, "img": "Easy-Cheesy.jpg",
             "desc": "A Triple Cheese Blend of Mozzarella, Cheddar and Akkawi on Tomato Sauce"},
        ],
    },
    # ── On The Side ────────────────────────────────────────────────────────────
    {
        "category": "On The Side",
        "sort_order": 3,
        "items": [
            {"code": "SID001", "name": "Cheesy Fries (Imported)",          "price_usd": 4.50, "img": "751~Cheesy-Fries.jpg",
             "desc": "Golden Imported Fries smothered in Creamy Cheese Sauce"},
            {"code": "SID002", "name": "French Fries (Imported)",          "price_usd": 3.00, "img": "Fries.jpg",
             "desc": "Crispy Golden Imported French Fries"},
            {"code": "SID003", "name": "Barbecue Dipped Chicken Strips",   "price_usd": 4.50, "img": "BBQ-Dipped-Chicken-Strips.jpg",
             "desc": "Tender Chicken Strips tossed in Smoky Barbecue Sauce"},
            {"code": "SID004", "name": "Mozzarella Sticks",                "price_usd": 4.00, "img": "Mozzarella-Sticks.jpg",
             "desc": "Crispy Breadcrumb-coated Mozzarella Sticks served with Marinara"},
            {"code": "SID005", "name": "Buffalo Dipped Chicken Strips",    "price_usd": 4.50, "img": "Buffalo-Dipped-Chicken-Strips.jpg",
             "desc": "Tender Chicken Strips tossed in Spicy Buffalo Sauce"},
            {"code": "SID006", "name": "Chicken Strips",                   "price_usd": 4.00, "img": "Chicken-Strips.jpg",
             "desc": "Lightly Seasoned Golden Fried Chicken Strips"},
            {"code": "SID007", "name": "Labneh Plate",                     "price_usd": 4.00, "img": "Labneh-Plate.jpg",
             "desc": "Creamy Homemade Labneh drizzled with Olive Oil and Dried Mint"},
            {"code": "SID008", "name": "Halloum Plate",                    "price_usd": 4.50, "img": "Halloum-Plate.jpg",
             "desc": "Grilled Halloumi Cheese served with Fresh Vegetables"},
            {"code": "SID009", "name": "Potato Wedges (Imported)",         "price_usd": 3.50, "img": "Potato-Wedges.jpg",
             "desc": "Thick-cut Seasoned Potato Wedges"},
            {"code": "SID010", "name": "French Fries (Local)",             "price_usd": 2.00, "img": "856~Fries.jpg",
             "desc": "Crispy Local French Fries"},
            {"code": "SID011", "name": "Cheesy Fries (Local)",             "price_usd": 4.00, "img": "218~Cheesy-Fries.jpg",
             "desc": "Local Fries smothered in Creamy Cheese Sauce"},
        ],
    },
    # ── Salads ─────────────────────────────────────────────────────────────────
    {
        "category": "Salads",
        "sort_order": 4,
        "items": [
            {"code": "SAL001", "name": "Astrochick",      "price_usd": 6.00, "img": "Astrochick.jpg",
             "desc": "Grilled Chicken, Croutons, Parmesan and Caesar Dressing on a bed of Romaine"},
            {"code": "SAL002", "name": "Fruity Halloumi", "price_usd": 5.50, "img": "Fruity-Halloumi.jpg",
             "desc": "Grilled Halloumi with Fresh Seasonal Fruits, Mixed Greens and a Honey-Lime Dressing"},
            {"code": "SAL003", "name": "Pasta Fiesta",    "price_usd": 6.00, "img": "Pasta-Fiesta.jpg",
             "desc": "Fusilli, Cherry Tomatoes, Olives, Feta and Fresh Basil in a Light Pesto Dressing"},
            {"code": "SAL004", "name": "Fab Crab",        "price_usd": 6.50, "img": "Fab-Crab.jpg",
             "desc": "Crab Sticks, Avocado, Cherry Tomatoes and Mixed Greens with a Citrus Dressing"},
            {"code": "SAL005", "name": "Tuna Luna",       "price_usd": 6.00, "img": "Tuna-Luna.jpg",
             "desc": "Tuna, Corn, Capers, Red Onion and Mixed Greens with a Lemon-Herb Vinaigrette"},
            {"code": "SAL006", "name": "Spring Fling",    "price_usd": 2.50, "img": "117~13.jpg",
             "desc": "Fresh Seasonal Greens, Cucumber, Cherry Tomatoes and a Light House Dressing"},
        ],
    },
    # ── Wraps ──────────────────────────────────────────────────────────────────
    {
        "category": "Wraps",
        "sort_order": 5,
        "items": [
            {"code": "WRP001", "name": "Crispy Chicken",    "price_usd": 4.50, "img": "197~Crispy-Chicken.jpg",
             "desc": "Crispy Fried Chicken with Lettuce, Tomato and Garlic Mayo in a Soft Wrap"},
            {"code": "WRP002", "name": "Ham & Cheese",      "price_usd": 3.50, "img": "Ham--Cheese.jpg",
             "desc": "Premium Ham and Melted Cheese Wrapped in Our Signature Dough"},
            {"code": "WRP003", "name": "Turkey & Cheese",   "price_usd": 3.75, "img": "Turkey--Cheese.jpg",
             "desc": "Sliced Turkey Breast and Melted Cheese Wrapped in Our Signature Dough"},
            {"code": "WRP004", "name": "Kafta & Cheese",    "price_usd": 4.75, "img": "Kafta--Cheese.jpg",
             "desc": "Spiced Ground Meat Kafta with Melted Cheese and Fresh Vegetables"},
            {"code": "WRP005", "name": "Soujouk & Cheese",  "price_usd": 5.00, "img": "Soujouk--Cheese.jpg",
             "desc": "Spicy Soujouk Sausage with Melted Cheese in Our Signature Dough"},
            {"code": "WRP006", "name": "Labneh Wrap",       "price_usd": 2.00, "img": "Labneh.jpg",
             "desc": "Creamy Labneh with Fresh Mint and Olive Oil in Our Signature Dough"},
            {"code": "WRP007", "name": "Chicken Aioli",     "price_usd": 4.50, "img": "Chicken-Aioli.jpg",
             "desc": "Grilled Chicken with Creamy Aioli, Lettuce and Tomato in a Soft Wrap"},
            {"code": "WRP008", "name": "Chicken Ranch",     "price_usd": 4.50, "img": "Chicken-Ranch.jpg",
             "desc": "Grilled Chicken with Ranch Dressing, Lettuce and Tomato in a Soft Wrap"},
            {"code": "WRP009", "name": "Spicy Chicken",     "price_usd": 4.50, "img": "Spicy-Chicken.jpg",
             "desc": "Spiced Grilled Chicken with Hot Sauce, Lettuce and Tomato in a Soft Wrap"},
            {"code": "WRP010", "name": "Guilt-Free Chicken","price_usd": 4.50, "img": "Guilt-Free-Chicken.jpg",
             "desc": "Grilled Chicken Breast, Mixed Greens, Cucumber and Light Yogurt Dressing"},
            {"code": "WRP011", "name": "Batata Wrap",       "price_usd": 1.75, "img": "Beaino-800x448p-20.jpg",
             "desc": "Crispy Potato Fries with Garlic Sauce Wrapped in Our Signature Dough"},
        ],
    },
    # ── Desserts ───────────────────────────────────────────────────────────────
    {
        "category": "Desserts",
        "sort_order": 6,
        "items": [
            {"code": "DES001", "name": "Lotus Chocolate Wrap",    "price_usd": 3.00, "img": "Lotus.jpg",
             "desc": "Our Signature Dough Filled with Lotus Biscoff Spread and Dark Chocolate"},
            {"code": "DES002", "name": "Salted Caramel Cheesecake","price_usd": 2.00, "img": "Salted-Caramel-.jpg",
             "desc": "Creamy Cheesecake on a Biscuit Base topped with Salted Caramel Sauce"},
            {"code": "DES003", "name": "Chocolate Wrap",          "price_usd": 3.00, "img": "Chocolate-Wrap.jpg",
             "desc": "Our Signature Dough Filled with Rich Dark Chocolate"},
            {"code": "DES004", "name": "Brownie",                 "price_usd": 3.75, "img": "Brownie.jpg",
             "desc": "Fudgy Chocolate Brownie served Warm"},
            {"code": "DES005", "name": "Panna Cotta",             "price_usd": 2.00, "img": "Panna-Cotta.jpg",
             "desc": "Classic Italian Panna Cotta with a Berry Coulis"},
            {"code": "DES006", "name": "Lava Love",               "price_usd": 3.75, "img": "Lava-Love.jpg",
             "desc": "Warm Chocolate Fondant with a Molten Centre, served with Vanilla Ice Cream"},
            {"code": "DES007", "name": "Strawberry Cheesecake",   "price_usd": 2.00, "img": "Strawberry-Cheesecake.jpg",
             "desc": "Creamy Cheesecake on a Biscuit Base topped with Fresh Strawberry Sauce"},
        ],
    },
    # ── Beverages ──────────────────────────────────────────────────────────────
    {
        "category": "Beverages",
        "sort_order": 7,
        "items": [
            {"code": "BEV001", "name": "Water",                "price_usd": 0.50, "img": "Water.jpg",
             "desc": "Still Water"},
            {"code": "BEV002", "name": "Sparkling Water",      "price_usd": 1.25, "img": "Sparkling-Water.jpg",
             "desc": "Sparkling Mineral Water"},
            {"code": "BEV003", "name": "Pepsi Bottle",         "price_usd": 1.00, "img": "Pepsi-Bottle.jpg",
             "desc": "Pepsi Cola"},
            {"code": "BEV004", "name": "Diet Pepsi Bottle",    "price_usd": 1.00, "img": "Diet-Pepsi-Bottle.jpg",
             "desc": "Diet Pepsi Cola"},
            {"code": "BEV005", "name": "7 up Bottle",          "price_usd": 1.00, "img": "7up-Bottle.jpg",
             "desc": "7 Up Lemon-Lime Soda"},
            {"code": "BEV006", "name": "Diet 7 up Bottle",     "price_usd": 1.00, "img": "Diet-7up-Bottle.jpg",
             "desc": "Diet 7 Up"},
            {"code": "BEV007", "name": "Mirinda Bottle",       "price_usd": 1.00, "img": "Mirinda-Bottle.jpg",
             "desc": "Mirinda Orange Soda"},
            {"code": "BEV008", "name": "Homemade Yogurt",      "price_usd": 1.25, "img": "Fresh-Yogurt.jpg",
             "desc": "Fresh Homemade Natural Yogurt"},
            {"code": "BEV009", "name": "Homemade Minted Yogurt","price_usd": 1.25, "img": "Minted.jpg",
             "desc": "Fresh Homemade Yogurt with Dried Mint"},
            {"code": "BEV010", "name": "Peach Ice Tea",        "price_usd": 1.25, "img": "Peach-Ice-Tea.jpg",
             "desc": "Refreshing Peach Flavored Iced Tea"},
            {"code": "BEV011", "name": "Lemon Ice Tea",        "price_usd": 1.25, "img": "Lemon-Ice-Tea.jpg",
             "desc": "Refreshing Lemon Flavored Iced Tea"},
            {"code": "BEV012", "name": "Fresh Orange Juice",   "price_usd": 1.50, "img": "Fresh-Orange.jpg",
             "desc": "Freshly Squeezed Orange Juice"},
            {"code": "BEV013", "name": "Pineapple Juice",      "price_usd": 1.00, "img": "Pineapple-Juice.jpg",
             "desc": "Tropical Pineapple Juice"},
            {"code": "BEV014", "name": "Apple Juice",          "price_usd": 1.00, "img": "Apple-Juice.jpg",
             "desc": "Fresh Apple Juice"},
        ],
    },
    # ── Lent-Exclusive Specials ────────────────────────────────────────────────
    {
        "category": "Lent Specials",
        "sort_order": 8,
        "items": [
            {"code": "LNT001", "name": "Tuna Manakish",  "price_usd": 3.00, "img": "Beaino-800x448p-19.jpg",
             "desc": "Flaked Tuna with Diced Tomatoes, Onions and Olives on Our Signature Dough"},
        ],
    },
]

# ─────────────────────────────────────────────────────────────────────────────

def _download_image(filename: str) -> str | None:
    dest = os.path.join(IMG_DIR, filename)
    if os.path.isfile(dest):
        return dest
    url = BASE_IMG + filename
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r, open(dest, "wb") as f:
            f.write(r.read())
        print(f"    [img] {filename}")
        return dest
    except Exception as e:
        print(f"    [img] FAILED {filename}: {e}")
        return None


def run():
    print("Initialising database …")
    init_db()

    session = SessionLocal()
    created_items = 0
    created_cats  = 0

    try:
        for cat_data in MENU_DATA:
            cat_name = cat_data["category"]

            # ── Category ──────────────────────────────────────────────────────
            cat = session.query(Category).filter_by(name=cat_name).first()
            if cat:
                print(f"\n[cat]  '{cat_name}' already exists — skipping creation.")
            else:
                cat = Category(
                    id=new_uuid(),
                    name=cat_name,
                    sort_order=cat_data.get("sort_order", 10),
                    is_active=True,
                    show_on_touch=True,
                    show_on_home=True,
                    show_in_daily=True,
                )
                session.add(cat)
                session.flush()
                print(f"\n[cat]  Created '{cat_name}'")
                created_cats += 1

            # ── Items ─────────────────────────────────────────────────────────
            for entry in cat_data["items"]:
                existing = session.query(Item).filter_by(code=entry["code"]).first()
                if existing:
                    continue

                photo_path = _download_image(entry["img"])

                item = Item(
                    id=new_uuid(),
                    code=entry["code"],
                    name=entry["name"],
                    category_id=cat.id,
                    unit="PCS",
                    pack_size=1,
                    cost_price=0.0,
                    cost_currency="USD",
                    vat_rate=0.0,
                    is_active=True,
                    is_pos_featured=True,
                    show_on_touch=True,
                    photo_url=photo_path,
                    notes=entry["desc"],
                )
                session.add(item)
                session.flush()

                session.add(ItemBarcode(
                    id=new_uuid(),
                    item_id=item.id,
                    barcode=entry["code"],
                    is_primary=True,
                    pack_qty=1,
                ))
                session.add(ItemPrice(
                    id=new_uuid(),
                    item_id=item.id,
                    price_type="retail",
                    amount=entry["price_usd"],
                    currency="USD",
                    is_default=True,
                    is_active=True,
                    pack_qty=1,
                ))
                print(f"  [ok]  {entry['code']} {entry['name']:<35} ${entry['price_usd']:.2f}")
                created_items += 1

        session.commit()
        print(f"\n{'─'*55}")
        print(f"Done!  {created_cats} categories and {created_items} items seeded.")
        print(f"Images saved to: {IMG_DIR}")
        print("To adjust prices: Super POS → Items → select item → Prices tab.")

    except Exception as e:
        session.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    run()
