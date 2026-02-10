import asyncio
import os
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL")

_db_pool = None

async def get_db_pool():
    global _db_pool
    if _db_pool is None:
        _db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _db_pool


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

                await conn.execute("""
                    INSERT INTO trade_positions (
                        id, account_id, account_index, account_name,
                        market, side, size, max_position_size, leverage,
                        open_price, realised_pnl, trade_pnl, funding_fees,
                        open_fees, close_fees, created_time, created_at,
                        epoch_start, epoch_number, fetched_at
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19, NOW())
                    ON CONFLICT (id) DO NOTHING
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
                )
                saved += 1
            except asyncpg.UniqueViolationError:
                pass
            except Exception as e:
                print(f"⚠️ [TradeHistory] Error saving position {pos.get('id')}: {e}")

    return saved


async def fetch_and_store_all_trades(accounts, fetch_fn):
    total_saved = 0
    total_fetched = 0

    for account in accounts:
        try:
            result = await fetch_fn(account, '/user/positions/history')
            if result and 'data' in result:
                positions = result['data']
                total_fetched += len(positions)
                account_idx = int(account.id.split('_')[1])
                saved = await save_positions_history(
                    account.id, account_idx, account.name, positions
                )
                total_saved += saved
            await asyncio.sleep(0.3)
        except Exception as e:
            print(f"⚠️ [TradeHistory] Error fetching trades for {account.name}: {e}")

    print(f"📊 [TradeHistory] Fetched {total_fetched} positions, saved {total_saved} new records")
    return total_saved


async def get_available_epochs() -> List[Dict]:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT epoch_number, epoch_start,
                   COUNT(*) as position_count,
                   COUNT(DISTINCT account_index) as account_count
            FROM trade_positions
            GROUP BY epoch_number, epoch_start
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
                "account_count": row['account_count'],
            })
        return epochs


async def get_epoch_stats(epoch_number: int, points_data: Optional[Dict] = None) -> Dict:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        combined = await conn.fetchrow("""
            SELECT
                COUNT(*) as total_positions,
                COUNT(DISTINCT account_index) as total_accounts,
                COUNT(DISTINCT market) as total_markets,
                COALESCE(SUM(ABS(size * open_price)), 0) as total_volume,
                COALESCE(SUM(ABS(open_fees) + ABS(close_fees)), 0) as total_fees,
                COALESCE(SUM(realised_pnl), 0) as total_pnl,
                COALESCE(SUM(trade_pnl), 0) as total_trade_pnl,
                COALESCE(SUM(funding_fees), 0) as total_funding_fees
            FROM trade_positions
            WHERE epoch_number = $1
        """, epoch_number)

        accounts = await conn.fetch("""
            SELECT
                account_index,
                account_id,
                account_name,
                COUNT(*) as positions,
                COUNT(DISTINCT market) as markets_traded,
                COALESCE(SUM(ABS(size * open_price)), 0) as volume,
                COALESCE(SUM(ABS(open_fees) + ABS(close_fees)), 0) as fees,
                COALESCE(SUM(realised_pnl), 0) as pnl,
                COALESCE(SUM(trade_pnl), 0) as trade_pnl,
                COALESCE(SUM(funding_fees), 0) as funding_fees,
                COALESCE(SUM(CASE WHEN open_fees = 0 THEN ABS(size * open_price) ELSE 0 END), 0) as maker_volume,
                COALESCE(SUM(CASE WHEN open_fees != 0 THEN ABS(size * open_price) ELSE 0 END), 0) as taker_volume,
                MIN(created_at) as first_trade,
                MAX(created_at) as last_trade
            FROM trade_positions
            WHERE epoch_number = $1
            GROUP BY account_index, account_id, account_name
            ORDER BY account_index
        """, epoch_number)

        account_stats = []
        for acc in accounts:
            volume = float(acc['volume'])
            fees = float(acc['fees'])
            maker_vol = float(acc['maker_volume'])
            taker_vol = float(acc['taker_volume'])
            total_vol = maker_vol + taker_vol if (maker_vol + taker_vol) > 0 else 1

            acc_points = 0
            if points_data and 'accounts' in points_data:
                acc_key = acc['account_id']
                if acc_key in points_data['accounts']:
                    acc_points = points_data['accounts'][acc_key].get('last_week_points', 0)

            pairs_data = await conn.fetch("""
                SELECT market,
                       COALESCE(SUM(ABS(size * open_price)), 0) as pair_volume
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

            first_trade = acc['first_trade']
            last_trade = acc['last_trade']
            avg_position_time = None
            if first_trade and last_trade and int(acc['positions']) > 1:
                total_seconds = (last_trade - first_trade).total_seconds()
                avg_seconds = total_seconds / (int(acc['positions']) - 1)
                if avg_seconds < 3600:
                    avg_position_time = f"{avg_seconds/60:.0f}m"
                elif avg_seconds < 86400:
                    avg_position_time = f"{avg_seconds/3600:.1f}h"
                else:
                    avg_position_time = f"{avg_seconds/86400:.1f}d"

            points_per_1m = (acc_points / volume * 1_000_000) if volume > 0 and acc_points > 0 else 0

            account_stats.append({
                "account_index": acc['account_index'],
                "account_id": acc['account_id'],
                "account_name": acc['account_name'],
                "total_volume": round(volume, 2),
                "total_fees": round(fees, 6),
                "positions": int(acc['positions']),
                "realised_pnl": round(float(acc['pnl']), 6),
                "trade_pnl": round(float(acc['trade_pnl']), 6),
                "funding_fees": round(float(acc['funding_fees']), 6),
                "points_earned": round(acc_points, 2),
                "points_per_1m": round(points_per_1m, 2),
                "avg_position_time": avg_position_time,
                "maker_volume": round(maker_vol, 2),
                "taker_volume": round(taker_vol, 2),
                "maker_pct": round(maker_vol / total_vol * 100, 1),
                "taker_pct": round(taker_vol / total_vol * 100, 1),
                "taker_fee_rate_bps": round(taker_fee_rate_bps, 2),
                "trading_pairs": trading_pairs,
            })

        total_volume = float(combined['total_volume'])
        total_fees = float(combined['total_fees'])

        total_points = 0
        if points_data:
            total_points = points_data.get('total_last_week_points', 0)

        cpp = (total_fees / total_points) if total_points > 0 else 0

        start, end = epoch_number_to_dates(epoch_number)

        return {
            "epoch_number": epoch_number,
            "epoch_label": f"Epoch {epoch_number} ({start.strftime('%b %d, %Y')} - {end.strftime('%b %d, %Y')})",
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "combined_stats": {
                "total_volume": round(total_volume, 2),
                "total_fees": round(total_fees, 6),
                "cost_per_point": round(cpp, 6),
                "total_positions": int(combined['total_positions']),
                "total_accounts": int(combined['total_accounts']),
                "total_markets": int(combined['total_markets']),
                "total_pnl": round(float(combined['total_pnl']), 6),
                "total_trade_pnl": round(float(combined['total_trade_pnl']), 6),
                "total_funding_fees": round(float(combined['total_funding_fees']), 6),
                "total_points": round(total_points, 2),
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
