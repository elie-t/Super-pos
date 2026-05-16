"""
Seed script: Manakish bakery menu
Scraped from https://order.furnbeaino.com/categories/1648/manakish

Run from the project root:
    python seed/seed_manakish.py

- Creates a "Manakish" category (show_on_touch=True, show_on_home=True)
- Creates 9 items with USD prices and downloads cover images
- Images saved to:  data/images/items/
- photo_url stored as absolute path so touch mode tile shows the image
- Safe to re-run: skips items/categories that already exist by name
- Does NOT touch any supermarket data
"""
import os
import sys
import urllib.request

# ── resolve project root so we can run from anywhere ─────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from database.engine import init_db, SessionLocal
from database.models.items import Category, Item, ItemPrice, ItemBarcode
from database.models.base import new_uuid

# ── Image download directory ──────────────────────────────────────────────────
IMG_DIR = os.path.join(ROOT, "data", "images", "items")
os.makedirs(IMG_DIR, exist_ok=True)

# ── Menu data ─────────────────────────────────────────────────────────────────
# Prices are in USD.  Converted from the restaurant's LBP menu at 89,500 LBP/$.
# Adjust amounts below to match your actual selling prices before running.
MANAKISH_ITEMS = [
    {
        "code":       "MNK001",
        "name":       "Zaatar",
        "price_usd":  1.50,
        "image_url":  "https://beaino.weevi.com/static/content/uploads/ekomproducts/Zaatar.jpg",
        "image_file": "Zaatar.jpg",
        "description": (
            "Our Unique Blend of Zaatar – Dried Thyme, Sumac and Sesame Seeds – "
            "Mixed with Oil and Spread Generously over Our Signature Supple Dough"
        ),
    },
    {
        "code":       "MNK002",
        "name":       "Zaatar & Labneh",
        "price_usd":  2.00,
        "image_url":  "https://beaino.weevi.com/static/content/uploads/ekomproducts/Zaatar--Labneh.jpg",
        "image_file": "Zaatar-Labneh.jpg",
        "description": (
            "Our Unique Blend of Zaatar Tempered with Creamy Homemade Labneh "
            "Wrapped in Our Signature Dough"
        ),
    },
    {
        "code":       "MNK003",
        "name":       "Zaatar & Cheese",
        "price_usd":  2.50,
        "image_url":  "https://beaino.weevi.com/static/content/uploads/ekomproducts/Zaatar--Cheese.jpg",
        "image_file": "Zaatar-Cheese.jpg",
        "description": (
            "Our Unique Blend of Zaatar Complemented by Gooey White Cheese, "
            "Wrapped in Our Signature Dough"
        ),
    },
    {
        "code":       "MNK004",
        "name":       "Cheese",
        "price_usd":  3.00,
        "image_url":  "https://beaino.weevi.com/static/content/uploads/ekomproducts/Cheese.jpg",
        "image_file": "Cheese.jpg",
        "description": "Premium White Akkawi Cheese Melted on Our Signature Dough",
    },
    {
        "code":       "MNK005",
        "name":       "Halloum",
        "price_usd":  3.50,
        "image_url":  "https://beaino.weevi.com/static/content/uploads/ekomproducts/839~Halloum.jpg",
        "image_file": "Halloum.jpg",
        "description": "Soft, Savory White Cheese Spread Generously over Our Signature Dough",
    },
    {
        "code":       "MNK006",
        "name":       "Kashkawan",
        "price_usd":  3.50,
        "image_url":  "https://beaino.weevi.com/static/content/uploads/ekomproducts/Kashkawan.jpg",
        "image_file": "Kashkawan.jpg",
        "description": "Melted Kashkaval Yellow Cheese atop Our Signature Dough",
    },
    {
        "code":       "MNK007",
        "name":       "Shanklich",
        "price_usd":  3.00,
        "image_url":  "https://beaino.weevi.com/static/content/uploads/ekomproducts/Shanklish.jpg",
        "image_file": "Shanklich.jpg",
        "description": (
            "A Zesty Blend of Levantine White Cheese, Diced Tomatoes and Onions "
            "Elevated with Herbs, Spices and a Kick of Heat, Spread Richly over Our Signature Dough"
        ),
    },
    {
        "code":       "MNK008",
        "name":       "Lahm Baajin",
        "price_usd":  3.50,
        "image_url":  "https://beaino.weevi.com/static/content/uploads/ekomproducts/Lahm-Baajin.jpg",
        "image_file": "Lahm-Baajin.jpg",
        "description": (
            "Our Fragrant Blend of Freshly Ground Meat and Spices Spread over Our "
            "Signature Crispy Thin Dough, Finished with a Drizzle of Lemon"
        ),
    },
    {
        "code":       "MNK009",
        "name":       "Spinach",
        "price_usd":  1.50,
        "image_url":  "https://beaino.weevi.com/static/content/uploads/ekomproducts/Spinach.jpg",
        "image_file": "Spinach.jpg",
        "description": (
            "A Triangular Shaped Turnover Filled with Fresh Spinach Leaves, "
            "Onions and Tomatoes, Seasoned with Sumac"
        ),
    },
]


def _download_image(url: str, dest: str) -> bool:
    if os.path.isfile(dest):
        print(f"  [img] already exists: {os.path.basename(dest)}")
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r, open(dest, "wb") as f:
            f.write(r.read())
        print(f"  [img] downloaded: {os.path.basename(dest)}")
        return True
    except Exception as e:
        print(f"  [img] FAILED {os.path.basename(dest)}: {e}")
        return False


def run():
    print("Initialising database …")
    init_db()

    session = SessionLocal()
    try:
        # ── 1. Category ───────────────────────────────────────────────────────
        cat = session.query(Category).filter_by(name="Manakish").first()
        if cat:
            print(f"Category 'Manakish' already exists (id={cat.id}) — skipping creation.")
        else:
            cat = Category(
                id=new_uuid(),
                name="Manakish",
                sort_order=1,
                is_active=True,
                show_on_touch=True,
                show_on_home=True,
                show_in_daily=True,
            )
            session.add(cat)
            session.flush()
            print(f"Created category 'Manakish' (id={cat.id})")

        # ── 2. Items ──────────────────────────────────────────────────────────
        for entry in MANAKISH_ITEMS:
            existing = session.query(Item).filter_by(code=entry["code"]).first()
            if existing:
                print(f"  [skip] {entry['code']} {entry['name']} already in DB.")
                continue

            # Download image
            img_dest = os.path.join(IMG_DIR, entry["image_file"])
            _download_image(entry["image_url"], img_dest)
            photo_path = img_dest if os.path.isfile(img_dest) else None

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
                notes=entry["description"],
            )
            session.add(item)
            session.flush()

            # Barcode = same as code so POS scanner can find it
            session.add(ItemBarcode(
                id=new_uuid(),
                item_id=item.id,
                barcode=entry["code"],
                is_primary=True,
                pack_qty=1,
            ))

            # USD retail price
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

            print(f"  [ok]   {entry['code']} {entry['name']} — ${entry['price_usd']:.2f}")

        session.commit()
        print("\nDone! Manakish menu seeded successfully.")
        print(f"Images saved to: {IMG_DIR}")
        print("\nTo update prices: open Super POS → Items → select an MNK item → Prices tab.")

    except Exception as e:
        session.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    run()
