"""
Application-wide configuration.
Values here are defaults; runtime overrides come from the `settings` DB table.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

LOCAL_DB_PATH  = DATA_DIR / "supermarket.db"
LOCAL_DB_URL   = f"sqlite:///{LOCAL_DB_PATH}"

# Online DB — override via .env or settings table
ONLINE_DB_URL  = os.getenv("ONLINE_DB_URL", "")

# ── Business defaults ─────────────────────────────────────────────────────────
APP_NAME       = "SuperPOS"
APP_VERSION    = "1.0.0"

DEFAULT_VAT_RATE   = 0.11          # 11% — override in settings table
BASE_CURRENCY      = "USD"         # books kept in USD
DISPLAY_CURRENCIES = ["USD", "LBP"]

# LBP exchange rate default (overridden from settings table at runtime)
DEFAULT_LBP_RATE   = 89_500        # 1 USD = 89,500 LBP

# Price detection threshold during Excel import
LBP_PRICE_THRESHOLD = 1_000        # if Main_Price >= this → LBP, else USD

# ── POS defaults ──────────────────────────────────────────────────────────────
CASH_CUSTOMER_NAME = "Cash Customer"
DEFAULT_WAREHOUSE  = "Main Warehouse"

# ── Sync ──────────────────────────────────────────────────────────────────────
SYNC_INTERVAL_SEC  = 60            # background sync interval
SYNC_API_BASE_URL  = os.getenv("SYNC_API_BASE_URL", "")
SYNC_API_KEY       = os.getenv("SYNC_API_KEY", "")

# ── Branch role ───────────────────────────────────────────────────────────────
# True  → Main warehouse: manages items, prices, categories, purchases, transfers.
#         Pushes to Supabase products/items_central/app_categories.
# False → Branch POS: sells only. Pulls catalog, pushes sales invoices.
IS_MAIN_BRANCH = os.getenv("IS_MAIN_BRANCH", "false").lower() == "true"
