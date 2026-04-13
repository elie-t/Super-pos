import sqlite3, json
db = sqlite3.connect('data/supermarket.db')

total    = db.execute('SELECT COUNT(*) FROM items').fetchone()[0]
active   = db.execute('SELECT COUNT(*) FROM items WHERE is_active=1').fetchone()[0]
with_cat = db.execute('SELECT COUNT(*) FROM items WHERE category_id IS NOT NULL').fetchone()[0]
touch    = db.execute('SELECT COUNT(*) FROM items WHERE show_on_touch=1').fetchone()[0]
no_price = db.execute('SELECT COUNT(*) FROM items WHERE id NOT IN (SELECT DISTINCT item_id FROM item_prices)').fetchone()[0]
no_bc    = db.execute('SELECT COUNT(*) FROM items WHERE id NOT IN (SELECT DISTINCT item_id FROM item_barcodes)').fetchone()[0]

state = json.load(open('.sync_state.json'))

print(f"Total items   : {total}")
print(f"Active        : {active}")
print(f"With category : {with_cat}")
print(f"Touch enabled : {touch}")
print(f"No prices     : {no_price}")
print(f"No barcodes   : {no_bc}")
print(f"Last pull     : {state.get('items_pull')}")
db.close()
