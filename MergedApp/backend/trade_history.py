import asyncio
import os
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import asyncpg
import numpy as np

DATABASE_URL = os.getenv("DATABASE_URL")

_db_pool = None
_schema_ensured = False

async def get_db_pool():
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _db_pool


async def ensure_schema():
    global _schema_ensured
    if _schema_ensured:
        return
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            ALTER TABLE trade_positions ADD COLUMN IF NOT EXISTS closed_time BIGINT;
            ALTER TABLE trade_positions ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP;
            ALTER TABLE trade_positions ADD COLUMN IF NOT EXISTS exit_price NUMERIC;
            ALTER TABLE trade_positions ADD COLUMN IF NOT EXISTS exit_type VARCHAR(50);
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_orders (
                id BIGINT PRIMARY KEY,
                account_id VARCHAR(50),
                account_index INTEGER,
                account_name VARCHAR(100),
                market VARCHAR(50),
                side VARCHAR(10),
                order_type VARCHAR(20),
                status VARCHAR(20),
                price NUMERIC,
                average_price NUMERIC,
                qty NUMERIC,
                filled_qty NUMERIC,
                fee NUMERIC DEFAULT 0,
                is_maker BOOLEAN DEFAULT FALSE,
                created_time BIGINT,
                created_at TIMESTAMP,
                epoch_start DATE,
                epoch_number INTEGER,
                fetched_at TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_trade_orders_epoch ON trade_orders(epoch_number);
            CREATE INDEX IF NOT EXISTS idx_trade_orders_account ON trade_orders(account_index);
        """)
    _schema_ensured = True
    print("✅ [TradeHistory] Schema migration complete")


def get_epoch_start(dt: datetime) -> datetime:
    days_since_monday = dt.weekday()
    monday = dt - timedelta(days=days_since_monday)
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def get_epoch_number(dt: datetime) -> int:
    epoch_1_start = datetime(2025, 4, 28)
    dt_naive = dt.replace(tzinfo=None) if dt.tzinfo else dt
    delta = dt_naive - epoch_1_start
    week_num = delta.days // 7
    return max(1, week_num + 1)


def epoch_number_to_dates(epoch_num: int) -> tuple:
    epoch_1_start = datetime(2025, 4, 28)
    start = epoch_1_start + timedelta(weeks=epoch_num - 1)
    end = start + timedelta(days=6)
    return start, end


async def save_positions_history(account_id: str, account_index: int, account_name: str, positions: List[Dict]):
    if not positions or not DATABASE_URL:
        return 0

    await ensure_schema()

    pool = await get_db_pool()
    saved = 0

    async with pool.acquire() as conn:
        for pos in positions:
            try:
                pos_id = pos.get('id')
                if not pos_id:
                    continue

                created_time = pos.get('createdTime', 0)
                created_at = datetime.utcfromtimestamp(created_time / 1000)
                epoch_start = get_epoch_start(created_at)
                epoch_num = get_epoch_number(created_at)

                breakdown = pos.get('realisedPnlBreakdown', {})

                closed_time_ms = pos.get('closedTime')
                closed_time_val = int(closed_time_ms) if closed_time_ms else None
                closed_at_val = datetime.utcfromtimestamp(closed_time_val / 1000) if closed_time_val else None
                exit_price_val = float(pos.get('exitPrice', 0)) if pos.get('exitPrice') else None
                exit_type_val = pos.get('exitType') or None

                await conn.execute("""
                    INSERT INTO trade_positions (
                        id, account_id, account_index, account_name,
                        market, side, size, max_position_size, leverage,
                        open_price, realised_pnl, trade_pnl, funding_fees,
                        open_fees, close_fees, created_time, created_at,
                        epoch_start, epoch_number, fetched_at,
                        closed_time, closed_at, exit_price, exit_type
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19, NOW(), $20,$21,$22,$23)
                    ON CONFLICT (id) DO UPDATE SET
                        size = EXCLUDED.size,
                        max_position_size = GREATEST(EXCLUDED.max_position_size, trade_positions.max_position_size),
                        realised_pnl = EXCLUDED.realised_pnl,
                        trade_pnl = EXCLUDED.trade_pnl,
                        funding_fees = EXCLUDED.funding_fees,
                        open_fees = EXCLUDED.open_fees,
                        close_fees = EXCLUDED.close_fees,
                        closed_time = COALESCE(EXCLUDED.closed_time, trade_positions.closed_time),
                        closed_at = COALESCE(EXCLUDED.closed_at, trade_positions.closed_at),
                        exit_price = COALESCE(EXCLUDED.exit_price, trade_positions.exit_price),
                        exit_type = COALESCE(EXCLUDED.exit_type, trade_positions.exit_type),
                        fetched_at = NOW()
                """,
                    int(pos_id),
                    account_id,
                    account_index,
                    account_name,
                    pos.get('market', ''),
                    pos.get('side', ''),
                    float(pos.get('size', 0)),
                    float(pos.get('maxPositionSize', 0)),
                    float(pos.get('leverage', 0)),
                    float(pos.get('openPrice', 0)),
                    float(pos.get('realisedPnl', 0)),
                    float(breakdown.get('tradePnl', 0)),
                    float(breakdown.get('fundingFees', 0)),
                    float(breakdown.get('openFees', 0)),
                    float(breakdown.get('closeFees', 0)),
                    created_time,
                    created_at,
                    epoch_start.date(),
                    epoch_num,
                    closed_time_val,
                    closed_at_val,
                    exit_price_val,
                    exit_type_val,
                )
                saved += 1
            except asyncpg.UniqueViolationError:
                pass
            except Exception as e:
                print(f"⚠️ [TradeHistory] Error saving position {pos.get('id')}: {e}")

    return saved


async def save_orders_history(account_id: str, account_index: int, account_name: str, orders: List[Dict]):
    if not orders or not DATABASE_URL:
        return 0

    await ensure_schema()
    pool = await get_db_pool()
    saved = 0

    async with pool.acquire() as conn:
        for order in orders:
            try:
                order_id = order.get('id')
                if not order_id:
                    continue

                status = order.get('status', '')
                if status != 'FILLED':
                    continue

                filled_qty = float(order.get('filledQty', 0) or 0)
                if filled_qty <= 0:
                    continue

                created_time = order.get('createdTime', 0) or order.get('createdAt', 0)
                if not created_time:
                    continue
                created_at = datetime.utcfromtimestamp(created_time / 1000)
                epoch_start = get_epoch_start(created_at)
                epoch_num = get_epoch_number(created_at)

                avg_price = float(order.get('averagePrice', 0) or 0)
                fee_val = float(order.get('payedFee', 0) or order.get('fee', 0) or 0)
                is_maker = order.get('type', '') == 'LIMIT'

                await conn.execute("""
                    INSERT INTO trade_orders (
                        id, account_id, account_index, account_name,
                        market, side, order_type, status,
                        price, average_price, qty, filled_qty,
                        fee, is_maker, created_time, created_at,
                        epoch_start, epoch_number
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
                    ON CONFLICT (id) DO UPDATE SET
                        filled_qty = EXCLUDED.filled_qty,
                        average_price = EXCLUDED.average_price,
                        fee = EXCLUDED.fee,
                        status = EXCLUDED.status,
                        fetched_at = NOW()
                """,
                    int(order_id),
                    account_id,
                    account_index,
                    account_name,
                    order.get('market', ''),
                    order.get('side', ''),
                    order.get('type', ''),
                    status,
                    float(order.get('price', 0) or 0),
                    avg_price,
                    float(order.get('qty', 0) or 0),
                    filled_qty,
                    fee_val,
                    is_maker,
                    created_time,
                    created_at,
                    epoch_start.date(),
                    epoch_num,
                )
                saved += 1
            except asyncpg.UniqueViolationError:
                pass
            except Exception as e:
                print(f"⚠️ [TradeHistory] Error saving order {order.get('id')}: {e}")

    return saved


async def fetch_and_store_all_orders(accounts, fetch_fn):
    total_saved = 0
    total_fetched = 0
    PAGE_SIZE = 1000

    for account in accounts:
        try:
            account_idx = int(account.id.split('_')[1])
            offset = 0
            account_orders = 0

            while True:
                params = {"limit": PAGE_SIZE, "offset": offset}
                result = await fetch_fn(account, '/user/orders/history', params=params)
                if not result or 'data' not in result:
                    break

                orders = result['data']
                if not orders:
                    break

                account_orders += len(orders)
                total_fetched += len(orders)
                saved = await save_orders_history(
                    account.id, account_idx, account.name, orders
                )
                total_saved += saved

                if len(orders) < PAGE_SIZE:
                    break

                offset += PAGE_SIZE
                await asyncio.sleep(0.3)

            if account_orders > 0:
                print(f"📋 [TradeHistory] {account.name}: fetched {account_orders} orders")
            await asyncio.sleep(0.2)
        except Exception as e:
            print(f"⚠️ [TradeHistory] Error fetching orders for {account.name}: {e}")

    print(f"📋 [TradeHistory] Total: fetched {total_fetched} orders, saved {total_saved} new records")
    return total_saved


async def fetch_and_store_all_trades(accounts, fetch_fn):
    total_saved = 0
    total_fetched = 0
    PAGE_SIZE = 1000

    for account in accounts:
        try:
            account_idx = int(account.id.split('_')[1])
            offset = 0
            account_positions = 0

            while True:
                params = {"limit": PAGE_SIZE, "offset": offset}
                result = await fetch_fn(account, '/user/positions/history', params=params)
                if not result or 'data' not in result:
                    break

                positions = result['data']
                if not positions:
                    break

                account_positions += len(positions)
                total_fetched += len(positions)
                saved = await save_positions_history(
                    account.id, account_idx, account.name, positions
                )
                total_saved += saved

                if len(positions) < PAGE_SIZE:
                    break

                offset += PAGE_SIZE
                await asyncio.sleep(0.3)

            if account_positions > 0:
                print(f"📊 [TradeHistory] {account.name}: fetched {account_positions} positions")
            await asyncio.sleep(0.2)
        except Exception as e:
            print(f"⚠️ [TradeHistory] Error fetching trades for {account.name}: {e}")

    print(f"📊 [TradeHistory] Total: fetched {total_fetched} positions, saved {total_saved} new records")
    return total_saved


async def get_available_epochs() -> List[Dict]:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT
                COALESCE(p.epoch_number, o.epoch_number) as epoch_number,
                COALESCE(p.epoch_start, o.epoch_start) as epoch_start,
                COALESCE(p.position_count, 0) as position_count,
                COALESCE(o.order_count, 0) as order_count,
                GREATEST(COALESCE(p.account_count, 0), COALESCE(o.account_count, 0)) as account_count
            FROM (
                SELECT epoch_number, epoch_start, COUNT(*) as position_count,
                       COUNT(DISTINCT account_index) as account_count
                FROM trade_positions GROUP BY epoch_number, epoch_start
            ) p
            FULL OUTER JOIN (
                SELECT epoch_number, epoch_start, COUNT(*) as order_count,
                       COUNT(DISTINCT account_index) as account_count
                FROM trade_orders GROUP BY epoch_number, epoch_start
            ) o ON p.epoch_number = o.epoch_number
            ORDER BY epoch_number DESC
        """)
        epochs = []
        for row in rows:
            epoch_num = row['epoch_number']
            start, end = epoch_number_to_dates(epoch_num)
            epochs.append({
                "epoch_number": epoch_num,
                "start_date": start.strftime("%b %d, %Y"),
                "end_date": end.strftime("%b %d, %Y"),
                "label": f"Epoch {epoch_num} ({start.strftime('%b %d, %Y')} - {end.strftime('%b %d, %Y')})",
                "position_count": row['position_count'],
                "order_count": row['order_count'],
                "account_count": row['account_count'],
            })
        return epochs


def _format_duration(seconds: float) -> str:
    if seconds < 3600:
        return f"{seconds/60:.0f}m"
    elif seconds < 86400:
        return f"{seconds/3600:.1f}h"
    else:
        return f"{seconds/86400:.1f}d"


async def get_epoch_stats(epoch_number: int, points_data: Optional[Dict] = None, current_epoch: Optional[int] = None) -> Dict:
    is_current_epoch = (current_epoch is not None and epoch_number == current_epoch)
    is_last_completed_epoch = (current_epoch is not None and epoch_number == current_epoch - 1)
    points_pending = is_current_epoch
    points_available = is_last_completed_epoch

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        orders_exist = await conn.fetchval("SELECT COUNT(*) FROM trade_orders WHERE epoch_number = $1", epoch_number)
        use_orders = orders_exist > 0

        if use_orders:
            combined = await conn.fetchrow("""
                SELECT
                    (SELECT COUNT(*) FROM trade_positions WHERE epoch_number = $1) as total_positions,
                    (SELECT COUNT(*) FROM trade_orders WHERE epoch_number = $1) as total_orders,
                    COUNT(DISTINCT o.account_index) as total_accounts,
                    COUNT(DISTINCT o.market) as total_markets,
                    COALESCE(SUM(ABS(o.filled_qty * o.average_price)), 0) as total_volume,
                    COALESCE(SUM(ABS(o.fee)), 0) as total_fees,
                    COALESCE((SELECT SUM(realised_pnl) FROM trade_positions WHERE epoch_number = $1), 0) as total_pnl,
                    COALESCE((SELECT SUM(trade_pnl) FROM trade_positions WHERE epoch_number = $1), 0) as total_trade_pnl,
                    COALESCE((SELECT SUM(funding_fees) FROM trade_positions WHERE epoch_number = $1), 0) as total_funding_fees,
                    COALESCE((SELECT SUM(ABS(open_fees)) FROM trade_positions WHERE epoch_number = $1), 0) as total_open_fees,
                    COALESCE((SELECT SUM(ABS(close_fees)) FROM trade_positions WHERE epoch_number = $1), 0) as total_close_fees
                FROM trade_orders o
                WHERE o.epoch_number = $1
            """, epoch_number)
        else:
            combined = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_positions,
                    0 as total_orders,
                    COUNT(DISTINCT account_index) as total_accounts,
                    COUNT(DISTINCT market) as total_markets,
                    COALESCE(SUM(ABS(max_position_size * open_price)), 0) as total_volume,
                    COALESCE(SUM(ABS(open_fees) + ABS(close_fees)), 0) as total_fees,
                    COALESCE(SUM(realised_pnl), 0) as total_pnl,
                    COALESCE(SUM(trade_pnl), 0) as total_trade_pnl,
                    COALESCE(SUM(funding_fees), 0) as total_funding_fees,
                    COALESCE(SUM(ABS(open_fees)), 0) as total_open_fees,
                    COALESCE(SUM(ABS(close_fees)), 0) as total_close_fees
                FROM trade_positions
                WHERE epoch_number = $1
            """, epoch_number)

        if use_orders:
            accounts = await conn.fetch("""
                SELECT
                    o.account_index,
                    o.account_id,
                    o.account_name,
                    COUNT(DISTINCT o.id) as orders,
                    COUNT(DISTINCT o.market) as markets_traded,
                    COALESCE(SUM(ABS(o.filled_qty * o.average_price)), 0) as volume,
                    COALESCE(SUM(ABS(o.fee)), 0) as fees,
                    COALESCE(p.pnl, 0) as pnl,
                    COALESCE(p.trade_pnl, 0) as trade_pnl,
                    COALESCE(p.funding_fees, 0) as funding_fees,
                    COALESCE(p.open_fees, 0) as open_fees,
                    COALESCE(p.close_fees, 0) as close_fees,
                    COALESCE(SUM(CASE WHEN o.is_maker THEN ABS(o.filled_qty * o.average_price) ELSE 0 END), 0) as maker_volume,
                    COALESCE(SUM(CASE WHEN NOT o.is_maker THEN ABS(o.filled_qty * o.average_price) ELSE 0 END), 0) as taker_volume,
                    COALESCE(p.avg_duration_seconds, 0) as avg_duration_seconds,
                    COALESCE(p.positions, 0) as positions,
                    p.first_trade,
                    p.last_trade
                FROM trade_orders o
                LEFT JOIN (
                    SELECT account_index, account_id,
                        COUNT(*) as positions,
                        SUM(realised_pnl) as pnl,
                        SUM(trade_pnl) as trade_pnl,
                        SUM(funding_fees) as funding_fees,
                        SUM(ABS(open_fees)) as open_fees,
                        SUM(ABS(close_fees)) as close_fees,
                        AVG(CASE WHEN closed_time IS NOT NULL AND created_time > 0 THEN (closed_time - created_time) / 1000.0 END) as avg_duration_seconds,
                        MIN(created_at) as first_trade,
                        MAX(created_at) as last_trade
                    FROM trade_positions WHERE epoch_number = $1
                    GROUP BY account_index, account_id
                ) p ON o.account_index = p.account_index
                WHERE o.epoch_number = $1
                GROUP BY o.account_index, o.account_id, o.account_name,
                         p.pnl, p.trade_pnl, p.funding_fees, p.open_fees, p.close_fees,
                         p.avg_duration_seconds, p.positions, p.first_trade, p.last_trade
                ORDER BY o.account_index
            """, epoch_number)
        else:
            accounts = await conn.fetch("""
                SELECT
                    account_index,
                    account_id,
                    account_name,
                    COUNT(*) as positions,
                    0 as orders,
                    COUNT(DISTINCT market) as markets_traded,
                    COALESCE(SUM(ABS(max_position_size * open_price)), 0) as volume,
                    COALESCE(SUM(ABS(open_fees) + ABS(close_fees)), 0) as fees,
                    COALESCE(SUM(realised_pnl), 0) as pnl,
                    COALESCE(SUM(trade_pnl), 0) as trade_pnl,
                    COALESCE(SUM(funding_fees), 0) as funding_fees,
                    COALESCE(SUM(ABS(open_fees)), 0) as open_fees,
                    COALESCE(SUM(ABS(close_fees)), 0) as close_fees,
                    COALESCE(SUM(CASE WHEN open_fees = 0 THEN ABS(max_position_size * open_price) ELSE 0 END), 0) as maker_volume,
                    COALESCE(SUM(CASE WHEN open_fees != 0 THEN ABS(max_position_size * open_price) ELSE 0 END), 0) as taker_volume,
                    COALESCE(AVG(CASE WHEN closed_time IS NOT NULL AND created_time > 0 THEN (closed_time - created_time) / 1000.0 END), 0) as avg_duration_seconds,
                    MIN(created_at) as first_trade,
                    MAX(created_at) as last_trade
                FROM trade_positions
                WHERE epoch_number = $1
                GROUP BY account_index, account_id, account_name
                ORDER BY account_index
            """, epoch_number)

        account_stats = []
        cpp_values = []
        for acc in accounts:
            volume = float(acc['volume'])
            fees = float(acc['fees'])
            maker_vol = float(acc['maker_volume'])
            taker_vol = float(acc['taker_volume'])
            total_vol = maker_vol + taker_vol if (maker_vol + taker_vol) > 0 else 1

            acc_points = 0
            if is_last_completed_epoch and points_data and 'accounts' in points_data:
                acc_key = acc['account_id']
                if acc_key in points_data['accounts']:
                    acc_points = points_data['accounts'][acc_key].get('last_week_points', 0)
            elif is_current_epoch:
                acc_points = 0

            if use_orders:
                pairs_data = await conn.fetch("""
                    SELECT market,
                           COALESCE(SUM(ABS(filled_qty * average_price)), 0) as pair_volume
                    FROM trade_orders
                    WHERE epoch_number = $1 AND account_index = $2
                    GROUP BY market
                    ORDER BY pair_volume DESC
                """, epoch_number, acc['account_index'])
            else:
                pairs_data = await conn.fetch("""
                    SELECT market,
                           COALESCE(SUM(ABS(max_position_size * open_price)), 0) as pair_volume
                    FROM trade_positions
                    WHERE epoch_number = $1 AND account_index = $2
                    GROUP BY market
                    ORDER BY pair_volume DESC
                """, epoch_number, acc['account_index'])

            trading_pairs = []
            for pair in pairs_data:
                pair_vol = float(pair['pair_volume'])
                pct = (pair_vol / volume * 100) if volume > 0 else 0
                trading_pairs.append({
                    "market": pair['market'],
                    "volume": round(pair_vol, 2),
                    "percentage": round(pct, 1),
                })

            taker_fee_rate_bps = (fees / taker_vol * 10000) if taker_vol > 0 else 0

            num_positions = int(acc.get('positions', 0) or 0)
            num_orders = int(acc.get('orders', 0) or 0)
            avg_dur_sec = float(acc['avg_duration_seconds'])
            if avg_dur_sec > 0:
                avg_position_time = _format_duration(avg_dur_sec)
            else:
                first_trade = acc['first_trade']
                last_trade = acc['last_trade']
                if first_trade and last_trade and num_positions > 1:
                    total_seconds = (last_trade - first_trade).total_seconds()
                    avg_seconds = total_seconds / (num_positions - 1)
                    avg_position_time = _format_duration(avg_seconds)
                else:
                    avg_position_time = "N/A"

            points_per_1m = (acc_points / volume * 1_000_000) if volume > 0 and acc_points > 0 else 0

            acc_cpp = (fees / acc_points) if acc_points > 0 else None
            if acc_cpp is not None:
                cpp_values.append(acc_cpp)

            account_stats.append({
                "account_index": acc['account_index'],
                "account_id": acc['account_id'],
                "account_name": acc['account_name'],
                "total_volume": round(volume, 2),
                "total_fees": round(fees, 6),
                "positions": num_positions,
                "orders": num_orders,
                "realised_pnl": round(float(acc['pnl']), 6),
                "trade_pnl": round(float(acc['trade_pnl']), 6),
                "funding_fees": round(float(acc['funding_fees']), 6),
                "open_fees": round(float(acc['open_fees']), 6),
                "close_fees": round(float(acc['close_fees']), 6),
                "points_earned": round(acc_points, 2),
                "points_per_1m": round(points_per_1m, 2),
                "avg_position_time": avg_position_time,
                "maker_volume": round(maker_vol, 2),
                "taker_volume": round(taker_vol, 2),
                "maker_pct": round(maker_vol / total_vol * 100, 1),
                "taker_pct": round(taker_vol / total_vol * 100, 1),
                "taker_fee_rate_bps": round(taker_fee_rate_bps, 2),
                "cost_per_point": round(acc_cpp, 6) if acc_cpp else None,
                "trading_pairs": trading_pairs,
            })

        total_volume = float(combined['total_volume'])
        total_fees = float(combined['total_fees'])

        total_points = 0
        if is_last_completed_epoch and points_data:
            total_points = points_data.get('total_last_week_points', 0)

        cpp = (total_fees / total_points) if total_points > 0 else 0
        avg_cpp = (sum(cpp_values) / len(cpp_values)) if cpp_values else None

        start, end = epoch_number_to_dates(epoch_number)

        return {
            "epoch_number": epoch_number,
            "epoch_label": f"Epoch {epoch_number} ({start.strftime('%b %d, %Y')} - {end.strftime('%b %d, %Y')})",
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "is_current_epoch": is_current_epoch,
            "points_pending": points_pending,
            "points_available": points_available,
            "combined_stats": {
                "total_volume": round(total_volume, 2),
                "total_fees": round(total_fees, 6),
                "cost_per_point": round(cpp, 6),
                "avg_cpp": round(avg_cpp, 6) if avg_cpp else None,
                "total_positions": int(combined['total_positions']),
                "total_orders": int(combined.get('total_orders', 0)),
                "volume_source": "orders" if use_orders else "positions",
                "total_accounts": int(combined['total_accounts']),
                "total_markets": int(combined['total_markets']),
                "total_pnl": round(float(combined['total_pnl']), 6),
                "total_trade_pnl": round(float(combined['total_trade_pnl']), 6),
                "total_funding_fees": round(float(combined['total_funding_fees']), 6),
                "total_open_fees": round(float(combined['total_open_fees']), 6),
                "total_close_fees": round(float(combined['total_close_fees']), 6),
                "total_points": round(total_points, 2),
                "points_pending": points_pending,
                "points_available": points_available,
            },
            "accounts": account_stats,
        }


async def get_account_trades(epoch_number: int, account_index: int) -> List[Dict]:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, market, side, size, max_position_size, leverage,
                   open_price, realised_pnl, trade_pnl, funding_fees,
                   open_fees, close_fees, created_at
            FROM trade_positions
            WHERE epoch_number = $1 AND account_index = $2
            ORDER BY created_at DESC
        """, epoch_number, account_index)

        return [
            {
                "id": str(row['id']),
                "market": row['market'],
                "side": row['side'],
                "size": float(row['size']),
                "max_position_size": float(row['max_position_size']),
                "leverage": float(row['leverage']),
                "open_price": float(row['open_price']),
                "realised_pnl": float(row['realised_pnl']),
                "trade_pnl": float(row['trade_pnl']),
                "funding_fees": float(row['funding_fees']),
                "open_fees": float(row['open_fees']),
                "close_fees": float(row['close_fees']),
                "created_at": row['created_at'].isoformat(),
            }
            for row in rows
        ]


async def get_db_stats() -> Dict:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT COUNT(*) as total_records,
                   COUNT(DISTINCT account_index) as total_accounts,
                   COUNT(DISTINCT epoch_number) as total_epochs,
                   MIN(created_at) as earliest,
                   MAX(created_at) as latest,
                   MAX(fetched_at) as last_fetch
            FROM trade_positions
        """)
        return {
            "total_records": int(row['total_records']),
            "total_accounts": int(row['total_accounts']),
            "total_epochs": int(row['total_epochs']),
            "earliest": row['earliest'].isoformat() if row['earliest'] else None,
            "latest": row['latest'].isoformat() if row['latest'] else None,
            "last_fetch": row['last_fetch'].isoformat() if row['last_fetch'] else None,
        }


def _run_ols(X_norm, y, feature_names):
    n = len(y)
    X_i = np.column_stack([np.ones(n), X_norm])
    try:
        coeffs, _, _, _ = np.linalg.lstsq(X_i, y, rcond=None)
    except np.linalg.LinAlgError:
        return None
    y_pred = X_i @ coeffs
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    adj_r2 = 1 - (1 - r2) * (n - 1) / max(1, n - len(feature_names) - 1) if n > len(feature_names) + 1 else r2
    beta = coeffs[1:]
    abs_imp = np.abs(beta)
    total_imp = abs_imp.sum()
    imp_pct = (abs_imp / total_imp * 100) if total_imp > 0 else np.zeros(len(feature_names))
    features = []
    for i, name in enumerate(feature_names):
        features.append({
            "name": name,
            "coefficient": round(float(beta[i]), 6),
            "importance_pct": round(float(imp_pct[i]), 2),
        })
    features.sort(key=lambda x: x["importance_pct"], reverse=True)
    return {
        "r_squared": round(float(r2), 4),
        "adj_r_squared": round(float(adj_r2), 4),
        "intercept": round(float(coeffs[0]), 4),
        "features": features,
        "y_pred": y_pred,
    }


def _run_ridge(X_norm, y, feature_names, alpha=1.0):
    n, p = X_norm.shape
    y_mean = y.mean()
    y_centered = y - y_mean
    I = np.eye(p)
    try:
        beta = np.linalg.solve(X_norm.T @ X_norm + alpha * I, X_norm.T @ y_centered)
    except np.linalg.LinAlgError:
        return None
    y_pred = X_norm @ beta + y_mean
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y_mean) ** 2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    adj_r2 = 1 - (1 - r2) * (n - 1) / max(1, n - p - 1) if n > p + 1 else r2
    abs_imp = np.abs(beta)
    total_imp = abs_imp.sum()
    imp_pct = (abs_imp / total_imp * 100) if total_imp > 0 else np.zeros(p)
    features = []
    for i, name in enumerate(feature_names):
        features.append({
            "name": name,
            "coefficient": round(float(beta[i]), 6),
            "importance_pct": round(float(imp_pct[i]), 2),
        })
    features.sort(key=lambda x: x["importance_pct"], reverse=True)
    return {
        "r_squared": round(float(r2), 4),
        "adj_r_squared": round(float(adj_r2), 4),
        "alpha": alpha,
        "features": features,
        "y_pred": y_pred,
    }


def _per_feature_correlations(X_norm, y, feature_names):
    results = []
    for i, name in enumerate(feature_names):
        x_col = X_norm[:, i]
        corr = np.corrcoef(x_col, y)[0, 1] if np.std(x_col) > 0 else 0.0
        X_single = np.column_stack([np.ones(len(y)), x_col])
        try:
            coeffs, _, _, _ = np.linalg.lstsq(X_single, y, rcond=None)
            y_pred = X_single @ coeffs
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        except Exception:
            r2 = 0.0
        results.append({
            "name": name,
            "correlation": round(float(corr), 4),
            "r_squared": round(float(r2), 4),
            "direction": "positive" if corr >= 0 else "negative",
        })
    results.sort(key=lambda x: abs(x["correlation"]), reverse=True)
    return results


async def get_regression_analysis(points_data: Dict, current_epoch: int) -> Dict:
    last_completed_epoch = current_epoch - 1

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        has_orders = await conn.fetchval(
            "SELECT COUNT(*) FROM trade_orders WHERE epoch_number = $1", last_completed_epoch
        )
        if has_orders and has_orders > 0:
            accounts = await conn.fetch("""
                SELECT
                    o.account_index,
                    o.account_id,
                    o.account_name,
                    COUNT(DISTINCT o.id) as order_count,
                    COUNT(DISTINCT o.market) as markets_traded,
                    COALESCE(SUM(ABS(o.filled_qty * o.average_price)), 0) as volume,
                    COALESCE(SUM(ABS(o.fee)), 0) as fees,
                    COALESCE(SUM(CASE WHEN o.is_maker THEN ABS(o.filled_qty * o.average_price) ELSE 0 END), 0) as maker_volume,
                    COALESCE(SUM(CASE WHEN NOT o.is_maker THEN ABS(o.filled_qty * o.average_price) ELSE 0 END), 0) as taker_volume,
                    COALESCE(AVG(ABS(o.filled_qty * o.average_price)), 0) as avg_order_size,
                    COALESCE(p.avg_leverage, 0) as avg_leverage,
                    COALESCE(p.positions, 0) as positions,
                    COALESCE(p.realised_pnl, 0) as realised_pnl
                FROM trade_orders o
                LEFT JOIN (
                    SELECT account_index,
                        AVG(leverage) as avg_leverage,
                        COUNT(*) as positions,
                        SUM(realised_pnl) as realised_pnl
                    FROM trade_positions WHERE epoch_number = $1
                    GROUP BY account_index
                ) p ON o.account_index = p.account_index
                WHERE o.epoch_number = $1
                GROUP BY o.account_index, o.account_id, o.account_name,
                         p.avg_leverage, p.positions, p.realised_pnl
                ORDER BY o.account_index
            """, last_completed_epoch)
        else:
            accounts = await conn.fetch("""
                SELECT
                    account_index,
                    account_id,
                    account_name,
                    COUNT(*) as positions,
                    0 as order_count,
                    COUNT(DISTINCT market) as markets_traded,
                    COALESCE(SUM(ABS(max_position_size * open_price)), 0) as volume,
                    COALESCE(SUM(ABS(open_fees) + ABS(close_fees)), 0) as fees,
                    COALESCE(SUM(CASE WHEN open_fees = 0 THEN ABS(max_position_size * open_price) ELSE 0 END), 0) as maker_volume,
                    COALESCE(SUM(CASE WHEN open_fees != 0 THEN ABS(max_position_size * open_price) ELSE 0 END), 0) as taker_volume,
                    0 as avg_order_size,
                    COALESCE(AVG(leverage), 0) as avg_leverage,
                    COALESCE(SUM(realised_pnl), 0) as realised_pnl
                FROM trade_positions
                WHERE epoch_number = $1
                GROUP BY account_index, account_id, account_name
                ORDER BY account_index
            """, last_completed_epoch)

    if not accounts:
        return {"error": "No data for the last completed epoch", "epoch": last_completed_epoch}

    all_feature_names = [
        "volume", "total_fees", "taker_volume", "maker_volume",
        "maker_ratio", "order_count", "avg_order_size",
        "markets_traded", "avg_leverage", "fee_rate_bps",
    ]
    raw_rows = []
    targets = []
    account_labels = []
    account_details = []

    for acc in accounts:
        acc_key = acc['account_id']
        acc_points = 0.0
        if points_data and 'accounts' in points_data:
            if acc_key in points_data['accounts']:
                acc_points = points_data['accounts'][acc_key].get('last_week_points', 0)

        if acc_points <= 0:
            continue

        volume = float(acc['volume'])
        fees = float(acc['fees'])
        maker_vol = float(acc['maker_volume'])
        taker_vol = float(acc['taker_volume'])
        total_vol = maker_vol + taker_vol if (maker_vol + taker_vol) > 0 else 1
        maker_ratio = maker_vol / total_vol
        order_count = int(acc.get('order_count', 0) or 0)
        avg_order_size = float(acc.get('avg_order_size', 0) or 0)
        markets = int(acc['markets_traded'])
        avg_leverage = float(acc.get('avg_leverage', 0) or 0)
        fee_rate_bps = (fees / volume * 10000) if volume > 0 else 0

        row = [
            volume, fees, taker_vol, maker_vol,
            maker_ratio, order_count, avg_order_size,
            markets, avg_leverage, fee_rate_bps,
        ]
        raw_rows.append(row)
        targets.append(acc_points)
        account_labels.append(acc['account_name'])
        account_details.append({
            "name": acc['account_name'],
            "points": round(acc_points, 2),
            "volume": round(volume, 2),
            "fees": round(fees, 4),
            "orders": order_count,
        })

    n = len(raw_rows)
    if n < 3:
        return {
            "error": f"Not enough accounts with points data ({n} found, need at least 3)",
            "epoch": last_completed_epoch,
            "accounts_with_points": n,
        }

    X_all = np.array(raw_rows, dtype=np.float64)
    y = np.array(targets, dtype=np.float64)

    X_means = X_all.mean(axis=0)
    X_stds = X_all.std(axis=0)
    X_stds[X_stds == 0] = 1.0
    X_norm_all = (X_all - X_means) / X_stds

    correlations = _per_feature_correlations(X_norm_all, y, all_feature_names)

    models = []

    core_names = ["volume", "total_fees", "taker_volume", "maker_ratio"]
    core_idx = [all_feature_names.index(f) for f in core_names]
    X_core = X_norm_all[:, core_idx]
    result_core = _run_ols(X_core, y, core_names)
    if result_core:
        models.append({
            "name": "Core (Volume + Fees + Taker + Maker Ratio)",
            "type": "OLS",
            "feature_count": len(core_names),
            **{k: v for k, v in result_core.items() if k != "y_pred"},
        })

    result_full = _run_ols(X_norm_all, y, all_feature_names)
    if result_full:
        models.append({
            "name": "Full (All Factors)",
            "type": "OLS",
            "feature_count": len(all_feature_names),
            **{k: v for k, v in result_full.items() if k != "y_pred"},
        })

    best_alpha = 1.0
    best_ridge_r2 = -999
    for alpha in [0.01, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]:
        ridge = _run_ridge(X_norm_all, y, all_feature_names, alpha=alpha)
        if ridge and ridge["r_squared"] > best_ridge_r2:
            best_ridge_r2 = ridge["r_squared"]
            best_alpha = alpha
    best_ridge = _run_ridge(X_norm_all, y, all_feature_names, alpha=best_alpha)
    if best_ridge:
        models.append({
            "name": f"Ridge (alpha={best_alpha})",
            "type": "Ridge",
            "feature_count": len(all_feature_names),
            **{k: v for k, v in best_ridge.items() if k != "y_pred"},
        })

    top_corr_names = [c["name"] for c in correlations[:5] if abs(c["correlation"]) > 0.1]
    if len(top_corr_names) >= 2:
        top_idx = [all_feature_names.index(f) for f in top_corr_names]
        X_top = X_norm_all[:, top_idx]
        result_top = _run_ols(X_top, y, top_corr_names)
        if result_top:
            models.append({
                "name": f"Top Correlated ({len(top_corr_names)} factors)",
                "type": "OLS",
                "feature_count": len(top_corr_names),
                **{k: v for k, v in result_top.items() if k != "y_pred"},
            })

    fee_vol_names = ["total_fees", "volume"]
    fee_vol_idx = [all_feature_names.index(f) for f in fee_vol_names]
    X_fv = X_norm_all[:, fee_vol_idx]
    result_fv = _run_ols(X_fv, y, fee_vol_names)
    if result_fv:
        models.append({
            "name": "Minimal (Fees + Volume)",
            "type": "OLS",
            "feature_count": 2,
            **{k: v for k, v in result_fv.items() if k != "y_pred"},
        })

    models.sort(key=lambda m: m.get("adj_r_squared", m.get("r_squared", 0)), reverse=True)

    best_model = models[0] if models else None
    best_model_name = best_model["name"] if best_model else "N/A"

    return {
        "epoch": last_completed_epoch,
        "n_accounts": n,
        "data_source": "orders" if has_orders and has_orders > 0 else "positions",
        "best_model": best_model_name,
        "models": models,
        "correlations": correlations,
        "accounts_used": account_labels,
        "account_details": account_details,
    }
