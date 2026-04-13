import sqlite3
db = sqlite3.connect('data/supermarket.db')
r1 = db.execute("UPDATE items SET show_on_touch=1 WHERE CAST(code AS INTEGER) BETWEEN 37001 AND 37100")
cat_ids = [r[0] for r in db.execute("SELECT DISTINCT category_id FROM items WHERE CAST(code AS INTEGER) BETWEEN 37001 AND 37100 AND category_id IS NOT NULL").fetchall()]
if cat_ids:
    r2 = db.execute("UPDATE categories SET show_on_touch=1 WHERE id IN ({})".format(','.join('?'*len(cat_ids))), cat_ids)
    print('Categories:', r2.rowcount)
db.commit()
print('Items:', r1.rowcount)
db.close()
