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

-- Sales invoices from all branches (append-only, no conflicts)
CREATE TABLE IF NOT EXISTS sales_invoices_central (
    id              TEXT PRIMARY KEY,
    branch_id       TEXT NOT NULL,
    invoice_number  TEXT NOT NULL,
    customer_id     TEXT,
    customer_name   TEXT DEFAULT '',
    operator_id     TEXT,
    invoice_date    TEXT NOT NULL,
    total           FLOAT DEFAULT 0,
    currency        TEXT DEFAULT 'LBP',
    status          TEXT DEFAULT 'finalized',
    payment_status  TEXT DEFAULT 'paid',
    amount_paid     FLOAT DEFAULT 0,
    notes           TEXT,
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
ALTER TABLE stock_movements_central DISABLE ROW LEVEL SECURITY;

-- Indexes for pull performance
CREATE INDEX IF NOT EXISTS idx_items_central_updated    ON items_central(updated_at);
CREATE INDEX IF NOT EXISTS idx_customers_central_updated ON customers_central(updated_at);
CREATE INDEX IF NOT EXISTS idx_invoices_branch          ON sales_invoices_central(branch_id);
CREATE INDEX IF NOT EXISTS idx_prices_item              ON item_prices_central(item_id);
CREATE INDEX IF NOT EXISTS idx_barcodes_item            ON item_barcodes_central(item_id);

-- Disable RLS for service_role (POS uses service key)
ALTER TABLE items_central             DISABLE ROW LEVEL SECURITY;
ALTER TABLE item_prices_central       DISABLE ROW LEVEL SECURITY;
ALTER TABLE item_barcodes_central     DISABLE ROW LEVEL SECURITY;
ALTER TABLE customers_central         DISABLE ROW LEVEL SECURITY;
ALTER TABLE sales_invoices_central    DISABLE ROW LEVEL SECURITY;
ALTER TABLE sales_invoice_items_central DISABLE ROW LEVEL SECURITY;
ALTER TABLE stock_levels              DISABLE ROW LEVEL SECURITY;
