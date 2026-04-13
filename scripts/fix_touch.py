import sqlite3
db = sqlite3.connect('data/supermarket.db')

# Show categories with show_on_touch=1
print("=== Touch categories ===")
cats = db.execute("SELECT id, name, show_on_touch FROM categories WHERE show_on_touch=1").fetchall()
for c in cats:
    print(f"  {c[1]}  (id={c[0]})")

if not cats:
    print("  NONE — enabling now...")
    r1 = db.execute("UPDATE items SET show_on_touch=1 WHERE CAST(code AS INTEGER) BETWEEN 37001 AND 37100")
    cat_ids = [r[0] for r in db.execute("SELECT DISTINCT category_id FROM items WHERE CAST(code AS INTEGER) BETWEEN 37001 AND 37100 AND category_id IS NOT NULL").fetchall()]
    if cat_ids:
        r2 = db.execute("UPDATE categories SET show_on_touch=1 WHERE id IN ({})".format(','.join('?'*len(cat_ids))), cat_ids)
        print(f"  Enabled {r2.rowcount} categories, {r1.rowcount} items")
    db.commit()
else:
    # Show how many touch items per category
    print("\n=== Items per touch category ===")
    for c in cats:
        n_all   = db.execute("SELECT COUNT(*) FROM items WHERE category_id=?", (c[0],)).fetchone()[0]
        n_touch = db.execute("SELECT COUNT(*) FROM items WHERE category_id=? AND show_on_touch=1", (c[0],)).fetchone()[0]
        print(f"  {c[1]}: {n_touch}/{n_all} items have show_on_touch=1")

    # Show touch items in range
    print("\n=== Items 37001-37100 with show_on_touch ===")
    rows = db.execute("SELECT code, name, show_on_touch, category_id FROM items WHERE CAST(code AS INTEGER) BETWEEN 37001 AND 37100 ORDER BY code").fetchall()
    print(f"  Total: {len(rows)}")
    for r in rows:
        cat_name = db.execute("SELECT name FROM categories WHERE id=?", (r[3],)).fetchone()
        print(f"  {r[0]}  touch={r[2]}  cat={cat_name[0] if cat_name else 'NO CATEGORY'}")

db.close()
