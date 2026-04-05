-- ============================================================
-- TannouryMarket — Supabase Schema
-- Run this once in Supabase → SQL Editor
-- ============================================================

-- ── Products (synced from POS items with is_online=true) ────
create table if not exists products (
    id          text primary key,
    code        text not null,
    name        text not null,
    name_ar     text default '',
    category    text default '',
    brand       text default '',
    barcode     text default '',
    price_lbp   numeric default 0,
    price_usd   numeric default 0,
    stock       numeric default 0,
    unit        text default 'PCS',
    is_featured boolean default false,
    photo_url   text default '',
    is_active   boolean default true,
    updated_at  timestamptz default now()
);

-- ── App customers (register via phone + OTP) ────────────────
create table if not exists app_customers (
    id           uuid primary key default gen_random_uuid(),
    phone        text unique not null,
    name         text default '',
    email        text default '',
    address      text default '',
    is_active    boolean default true,
    created_at   timestamptz default now()
);

-- ── Orders (placed by customers in the app) ─────────────────
create table if not exists orders (
    id              uuid primary key default gen_random_uuid(),
    customer_id     uuid references app_customers(id),
    customer_name   text not null,
    customer_phone  text not null,
    delivery_type   text not null check (delivery_type in ('delivery','pickup')),
    address         text default '',
    notes           text default '',
    items           jsonb not null default '[]',   -- [{id, name, qty, price_lbp}]
    total           numeric default 0,
    currency        text default 'LBP',
    status          text default 'new'
                    check (status in ('new','confirmed','preparing','ready','delivered','cancelled')),
    payment_method  text default 'cash' check (payment_method in ('cash','online')),
    created_at      timestamptz default now(),
    updated_at      timestamptz default now()
);

-- ── Order status history ─────────────────────────────────────
create table if not exists order_status_log (
    id         uuid primary key default gen_random_uuid(),
    order_id   uuid references orders(id) on delete cascade,
    status     text not null,
    note       text default '',
    created_at timestamptz default now()
);

-- ── Categories (for app browsing) ───────────────────────────
create table if not exists categories (
    id         text primary key,
    name       text not null,
    name_ar    text default '',
    sort_order int  default 0,
    is_active  boolean default true
);

-- ── RLS policies — service role bypasses all ────────────────
alter table products        enable row level security;
alter table app_customers   enable row level security;
alter table orders          enable row level security;
alter table order_status_log enable row level security;
alter table categories      enable row level security;

-- Allow anon read on products and categories (public catalog)
create policy "Public read products"
    on products for select using (is_active = true);

create policy "Public read categories"
    on categories for select using (is_active = true);

-- Customers can read/write their own orders
create policy "Customer own orders"
    on orders for all
    using (customer_phone = current_setting('request.jwt.claims', true)::json->>'phone');

-- ── Indexes ──────────────────────────────────────────────────
create index if not exists idx_products_category  on products(category);
create index if not exists idx_products_is_active on products(is_active);
create index if not exists idx_orders_status      on orders(status);
create index if not exists idx_orders_phone       on orders(customer_phone);

-- ── Storage bucket for product photos ───────────────────────
-- Run separately in Supabase → Storage → New bucket:
--   Name: product-images
--   Public: true
