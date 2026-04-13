"""
Full item sync from Supabase — runs pull_master_items in a tight loop
until all items are downloaded. Much faster than waiting for the 60s timer.

Usage:
    python scripts/full_sync.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.engine import init_db
init_db()

# Reset cursor to full-sync mode
from sync.service import _state_set, _state_get
_state_set("items_pull", "2000-01-01T00:00:00Z")
_state_set("items_pull_last_id", "")

print("Starting full sync...")
total = 0
batch = 0
while True:
    from sync.service import pull_master_items
    n, err = pull_master_items()
    batch += 1
    total += n
    last_id = _state_get("items_pull_last_id") or ""
    print(f"  Batch {batch:>3}: +{n} items  (total={total})  cursor={last_id[:8] if last_id else 'done'}")
    if err:
        print(f"  ERROR: {err}")
        break
    if n == 0:
        print(f"\nSync complete — {total} items processed.")
        break

# Verify
import sqlite3
db = sqlite3.connect('data/supermarket.db')
count = db.execute('SELECT COUNT(*) FROM items').fetchone()[0]
db.close()
print(f"Local DB now has {count} items.")
