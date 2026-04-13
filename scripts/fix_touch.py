import sqlite3
db = sqlite3.connect('data/supermarket.db')

# Get local category IDs by name
cats = {r[0]: r[1] for r in db.execute("SELECT name, id FROM categories").fetchall()}
w  = cats.get("1WAFFLE")
c  = cats.get("2CREPE")
f  = cats.get("3FRAPPE/COFFEE")
a  = cats.get("ADD ONS")

print("Category IDs found:")
print(f"  1WAFFLE        = {w}")
print(f"  2CREPE         = {c}")
print(f"  3FRAPPE/COFFEE = {f}")
print(f"  ADD ONS        = {a}")

if not all([w, c, f, a]):
    print("ERROR: one or more categories missing!")
else:
    # Assign categories by code (from Supabase data)
    assignments = {
        "1WAFFLE":        ["37001","37002","37003","37004","37015","37017","37019","37020","37021","37022"],
        "2CREPE":         ["37005","37006","37007","37008"],
        "3FRAPPE/COFFEE": ["37009","37010","37011","37012","37013","37014","37016","37018","37023","37024",
                           "37025","37026","37027","37028","37029","37030","37031","37032","37037"],
        "ADD ONS":        ["37038","37039","37040","37041"],
    }
    cat_id_map = {"1WAFFLE": w, "2CREPE": c, "3FRAPPE/COFFEE": f, "ADD ONS": a}

    total = 0
    for cat_name, codes in assignments.items():
        ph = ','.join('?' * len(codes))
        r = db.execute(
            f"UPDATE items SET category_id=?, show_on_touch=1 WHERE code IN ({ph})",
            [cat_id_map[cat_name]] + codes
        )
        print(f"  {cat_name}: {r.rowcount} items assigned")
        total += r.rowcount

    # Enable show_on_touch on the 4 categories
    r2 = db.execute(
        "UPDATE categories SET show_on_touch=1 WHERE name IN ('1WAFFLE','2CREPE','3FRAPPE/COFFEE','ADD ONS')"
    )
    db.commit()
    print(f"\nTotal items assigned: {total}")
    print(f"Categories enabled: {r2.rowcount}")
    print("Done — restart the app")

db.close()
