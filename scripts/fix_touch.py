import sqlite3
db = sqlite3.connect('data/supermarket.db')

# Show items 37001-37100 and their category status
print("=== Items 37001-37100 ===")
rows = db.execute("""
    SELECT i.code, i.name, i.show_on_touch, i.category_id,
           c.name as cat_name, c.show_on_touch as cat_touch
    FROM items i
    LEFT JOIN categories c ON c.id = i.category_id
    WHERE CAST(i.code AS INTEGER) BETWEEN 37001 AND 37100
    ORDER BY CAST(i.code AS INTEGER)
""").fetchall()
print(f"Total: {len(rows)}")
for r in rows:
    print(f"  {r[0]}  touch={r[2]}  cat={r[4] or 'NO CATEGORY'}")

# Show all available categories
print("\n=== All categories ===")
cats = db.execute("SELECT id, name, show_on_touch FROM categories ORDER BY name").fetchall()
for c in cats:
    print(f"  {c[1]}  show_on_touch={c[2]}  id={c[0]}")

db.close()
