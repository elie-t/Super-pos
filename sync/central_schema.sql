-- =============================================================================
-- Central Supabase schema for multi-branch POS sync
-- Run this ONCE in Supabase → SQL Editor
-- =============================================================================

-- Items master (full data, all branches pull this)
CREATE TABLE IF NOT EXISTS items_central (
    id              TEXT PRIMARY KEY,
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    name_ar         TEXT DEFAULT '',
    category        TEXT DEFAULT '',
    brand           TEXT DEFAULT '',
    unit            TEXT DEFAULT 'PCS',
    cost_price      FLOAT DEFAULT 0,
    cost_currency   TEXT DEFAULT 'USD',
    vat_rate        FLOAT DEFAULT 0,
    is_active       BOOLEAN DEFAULT TRUE,
    is_online       BOOLEAN DEFAULT FALSE,
    is_pos_featured BOOLEAN DEFAULT FALSE,
    show_on_touch   BOOLEAN DEFAULT FALSE,
    photo_url       TEXT DEFAULT '',
    notes           TEXT DEFAULT '',
    updated_at      TIMESTAMPTZ DEFAULT now(),
    pushed_by       TEXT DEFAULT ''  -- branch_id that last pushed
);

-- Item prices (per type: individual / retail / wholesale / semi_wholesale)
CREATE TABLE IF NOT EXISTS item_prices_central (
    id         TEXT PRIMARY KEY,
    item_id    TEXT NOT NULL REFERENCES items_central(id) ON DELETE CASCADE,
    price_type TEXT NOT NULL,
    amount     FLOAT NOT NULL DEFAULT 0,
    currency   TEXT DEFAULT 'LBP',
    pack_qty   INT DEFAULT 1,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Item barcodes
CREATE TABLE IF NOT EXISTS item_barcodes_central (
    id         TEXT PRIMARY KEY,
    item_id    TEXT NOT NULL REFERENCES items_central(id) ON DELETE CASCADE,
    barcode    TEXT NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    pack_qty   INT DEFAULT 1,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Customers (shared across all branches)
CREATE TABLE IF NOT EXISTS customers_central (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    code           TEXT,
    phone          TEXT,
    email          TEXT,
    address        TEXT,
    balance        FLOAT DEFAULT 0,
    currency       TEXT DEFAULT 'USD',
    is_active      BOOLEAN DEFAULT TRUE,
    is_cash_client BOOLEAN DEFAULT FALSE,
    updated_at     TIMESTAMPTZ DEFAULT now(),
    pushed_by      TEXT DEFAULT ''
);

-- Suppliers (shared across all branches)
CREATE TABLE IF NOT EXISTS suppliers_central (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    code           TEXT,
    phone          TEXT,
    phone2         TEXT,
    email          TEXT,
    address        TEXT,
    classification TEXT,
    credit_limit   FLOAT DEFAULT 0,
    balance        FLOAT DEFAULT 0,
    currency       TEXT DEFAULT 'USD',
    notes          TEXT,
    is_active      BOOLEAN DEFAULT TRUE,
    updated_at     TIMESTAMPTZ DEFAULT now(),
    pushed_by      TEXT DEFAULT ''
);

-- Users (shared login across branches)
CREATE TABLE IF NOT EXISTS users_central (
    id             TEXT PRIMARY KEY,
    username       TEXT NOT NULL,
    password_hash  TEXT,
    full_name      TEXT,
    role           TEXT,
    warehouse_id   TEXT,
    is_active      BOOLEAN DEFAULT TRUE,
    updated_at     TIMESTAMPTZ DEFAULT now(),
    pushed_by      TEXT DEFAULT ''
);

-- Sales invoices from all branches (append-only, no conflicts)
CREATE TABLE IF NOT EXISTS sales_invoices_central (
    id              TEXT PRIMARY KEY,
    branch_id       TEXT NOT NULL,
    invoice_number  TEXT NOT NULL,
    customer_id     TEXT,
    customer_name   TEXT DEFAULT '',
    operator_id     TEXT,
    warehouse_id    TEXT DEFAULT '',
    invoice_date    TEXT NOT NULL,
    total           FLOAT DEFAULT 0,
    currency        TEXT DEFAULT 'LBP',
    status          TEXT DEFAULT 'finalized',
    payment_status  TEXT DEFAULT 'paid',
    amount_paid     FLOAT DEFAULT 0,
    notes           TEXT,
    source          TEXT DEFAULT 'manual',   -- manual | pos | pos_shift
    invoice_type    TEXT DEFAULT 'sale',     -- sale | return
    synced_at       TIMESTAMPTZ DEFAULT now()
);

-- Sales invoice line items
CREATE TABLE IF NOT EXISTS sales_invoice_items_central (
    id           TEXT PRIMARY KEY,
    invoice_id   TEXT NOT NULL REFERENCES sales_invoices_central(id) ON DELETE CASCADE,
    item_id      TEXT,
    item_name    TEXT NOT NULL,
    barcode      TEXT,
    quantity     FLOAT NOT NULL,
    unit_price   FLOAT NOT NULL,
    currency     TEXT DEFAULT 'LBP',
    line_total   FLOAT NOT NULL
);

-- Purchase invoices (restock)
CREATE TABLE IF NOT EXISTS purchase_invoices_central (
    id              TEXT PRIMARY KEY,
    branch_id       TEXT NOT NULL,
    invoice_number  TEXT NOT NULL,
    supplier_id     TEXT,
    supplier_name   TEXT DEFAULT '',
    operator_id     TEXT,
    warehouse_id    TEXT DEFAULT '',
    invoice_date    TEXT NOT NULL,
    due_date        TEXT,
    order_number    TEXT,
    subtotal        FLOAT DEFAULT 0,
    total           FLOAT DEFAULT 0,
    currency        TEXT DEFAULT 'USD',
    status          TEXT DEFAULT 'finalized',
    payment_status  TEXT DEFAULT 'unpaid',
    notes           TEXT,
    synced_at       TIMESTAMPTZ DEFAULT now()
);

-- Purchase invoice items
CREATE TABLE IF NOT EXISTS purchase_invoice_items_central (
    id           TEXT PRIMARY KEY,
    invoice_id   TEXT NOT NULL REFERENCES purchase_invoices_central(id) ON DELETE CASCADE,
    item_id      TEXT,
    item_name    TEXT NOT NULL,
    quantity     FLOAT NOT NULL,
    pack_size    INT DEFAULT 1,
    unit_cost    FLOAT NOT NULL,
    currency     TEXT DEFAULT 'USD',
    line_total   FLOAT NOT NULL,
    sort_order   INT DEFAULT 0
);

-- Stock levels per item per branch (for cross-branch visibility)
CREATE TABLE IF NOT EXISTS stock_levels (
    item_id    TEXT NOT NULL,
    branch_id  TEXT NOT NULL,
    quantity   FLOAT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (item_id, branch_id)
);

-- Stock movements from all branches (purchase, sale, transfer, adjustment)
CREATE TABLE IF NOT EXISTS stock_movements_central (
    id             TEXT PRIMARY KEY,
    item_id        TEXT NOT NULL,
    warehouse_id   TEXT NOT NULL,
    qty_change     FLOAT NOT NULL,        -- positive = IN, negative = OUT
    movement_type  TEXT NOT NULL,
    reference_type TEXT DEFAULT '',
    reference_id   TEXT DEFAULT '',
    branch_id      TEXT NOT NULL,
    created_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_smov_warehouse  ON stock_movements_central(warehouse_id, created_at);
CREATE INDEX IF NOT EXISTS idx_smov_branch     ON stock_movements_central(branch_id, created_at);

-- Categories (shared across all branches, includes subcategories via parent_id)
CREATE TABLE IF NOT EXISTS categories_central (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    parent_id     TEXT REFERENCES categories_central(id) ON DELETE SET NULL,
    sort_order    INT DEFAULT 0,
    is_active     BOOLEAN DEFAULT TRUE,
    show_in_daily BOOLEAN DEFAULT FALSE,
    updated_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_categories_parent ON categories_central(parent_id);

-- Warehouse transfers from all branches
CREATE TABLE IF NOT EXISTS warehouse_transfers_central (
    id                TEXT PRIMARY KEY,
    transfer_number   TEXT DEFAULT '',
    from_warehouse_id TEXT NOT NULL,
    to_warehouse_id   TEXT NOT NULL,
    transfer_date     TEXT DEFAULT '',
    status            TEXT DEFAULT 'confirmed',
    operator_id       TEXT,
    notes             TEXT DEFAULT '',
    pushed_by         TEXT DEFAULT '',
    synced_at         TIMESTAMPTZ DEFAULT now()
);

-- Warehouse transfer line items
CREATE TABLE IF NOT EXISTS warehouse_transfer_items_central (
    id          TEXT PRIMARY KEY,
    transfer_id TEXT NOT NULL REFERENCES warehouse_transfers_central(id) ON DELETE CASCADE,
    item_id     TEXT NOT NULL,
    item_name   TEXT DEFAULT '',
    quantity    FLOAT NOT NULL,
    unit_cost   FLOAT DEFAULT 0,
    synced_at   TIMESTAMPTZ DEFAULT now()
);

-- Inventory sessions (counting)
CREATE TABLE IF NOT EXISTS inventory_sessions_central (
    id              TEXT PRIMARY KEY,
    session_number  TEXT DEFAULT '',
    warehouse_id    TEXT NOT NULL,
    session_date    TEXT NOT NULL,
    status          TEXT DEFAULT 'closed',
    operator_id     TEXT,
    notes           TEXT,
    pushed_by       TEXT DEFAULT '',
    synced_at       TIMESTAMPTZ DEFAULT now()
);

-- Inventory session items
CREATE TABLE IF NOT EXISTS inventory_session_items_central (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES inventory_sessions_central(id) ON DELETE CASCADE,
    item_id      TEXT NOT NULL,
    item_name    TEXT DEFAULT '',
    system_qty   FLOAT DEFAULT 0,
    counted_qty  FLOAT DEFAULT 0,
    diff_qty     FLOAT DEFAULT 0,
    unit_cost    FLOAT DEFAULT 0,
    synced_at    TIMESTAMPTZ DEFAULT now()
);

-- Disable RLS for service_role (POS uses service key)
ALTER TABLE items_central             DISABLE ROW LEVEL SECURITY;
ALTER TABLE item_prices_central       DISABLE ROW LEVEL SECURITY;
ALTER TABLE item_barcodes_central     DISABLE ROW LEVEL SECURITY;
ALTER TABLE customers_central         DISABLE ROW LEVEL SECURITY;
ALTER TABLE suppliers_central         DISABLE ROW LEVEL SECURITY;
ALTER TABLE users_central             DISABLE ROW LEVEL SECURITY;
ALTER TABLE sales_invoices_central    DISABLE ROW LEVEL SECURITY;
ALTER TABLE sales_invoice_items_central DISABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_invoices_central   DISABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_invoice_items_central DISABLE ROW LEVEL SECURITY;
ALTER TABLE stock_levels              DISABLE ROW LEVEL SECURITY;
ALTER TABLE stock_movements_central   DISABLE ROW LEVEL SECURITY;
ALTER TABLE categories_central         DISABLE ROW LEVEL SECURITY;
ALTER TABLE warehouse_transfers_central DISABLE ROW LEVEL SECURITY;
ALTER TABLE warehouse_transfer_items_central DISABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_sessions_central DISABLE ROW LEVEL SECURITY;
ALTER TABLE inventory_session_items_central DISABLE ROW LEVEL SECURITY;

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_items_updated    ON items_central(updated_at);
CREATE INDEX IF NOT EXISTS idx_invoices_synced  ON sales_invoices_central(synced_at);
CREATE INDEX IF NOT EXISTS idx_invoices_branch  ON sales_invoices_central(branch_id);
CREATE INDEX IF NOT EXISTS idx_purchase_synced  ON purchase_invoices_central(synced_at);
CREATE INDEX IF NOT EXISTS idx_transfers_synced ON warehouse_transfers_central(synced_at);
CREATE INDEX IF NOT EXISTS idx_inventory_synced ON inventory_sessions_central(synced_at);
