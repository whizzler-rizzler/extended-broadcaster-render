-- Supabase Schema for Lighter Broadcaster
-- Run this in Supabase SQL Editor to create required tables

-- Account snapshots table - stores periodic account state
CREATE TABLE IF NOT EXISTS account_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_index INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    equity DECIMAL,
    margin DECIMAL,
    available_balance DECIMAL,
    pnl DECIMAL,
    positions_count INTEGER DEFAULT 0,
    orders_count INTEGER DEFAULT 0,
    raw_data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_account_snapshots_account ON account_snapshots(account_index);
CREATE INDEX idx_account_snapshots_timestamp ON account_snapshots(timestamp DESC);

-- Positions table - stores position history
CREATE TABLE IF NOT EXISTS positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_index INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    market VARCHAR(50),
    side VARCHAR(10),
    size DECIMAL,
    entry_price DECIMAL,
    mark_price DECIMAL,
    unrealized_pnl DECIMAL,
    raw_data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_positions_account ON positions(account_index);
CREATE INDEX idx_positions_timestamp ON positions(timestamp DESC);
CREATE INDEX idx_positions_market ON positions(market);

-- Orders table - stores order history
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_index INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    order_id VARCHAR(100),
    market VARCHAR(50),
    side VARCHAR(10),
    order_type VARCHAR(20),
    price DECIMAL,
    size DECIMAL,
    filled DECIMAL,
    status VARCHAR(20),
    raw_data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_orders_account ON orders(account_index);
CREATE INDEX idx_orders_timestamp ON orders(timestamp DESC);
CREATE INDEX idx_orders_order_id ON orders(order_id);
CREATE INDEX idx_orders_market ON orders(market);

-- Trades table - stores executed trade history
CREATE TABLE IF NOT EXISTS trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_index INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    trade_id VARCHAR(100),
    market VARCHAR(50),
    side VARCHAR(10),
    price DECIMAL,
    size DECIMAL,
    fee DECIMAL,
    raw_data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_trades_account ON trades(account_index);
CREATE INDEX idx_trades_timestamp ON trades(timestamp DESC);
CREATE INDEX idx_trades_trade_id ON trades(trade_id);
CREATE INDEX idx_trades_market ON trades(market);

-- Enable Row Level Security (optional, adjust as needed)
-- ALTER TABLE account_snapshots ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
