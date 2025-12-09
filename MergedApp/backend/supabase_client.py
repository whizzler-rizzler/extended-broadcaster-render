import os
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        self._client: Optional[Client] = None
        self._initialized = False
        self._url: Optional[str] = None
        self._key: Optional[str] = None
        self._saved_trade_ids: set = set()
    
    def initialize(self) -> bool:
        self._url = os.getenv("Supabase_Url")
        self._key = os.getenv("Supabase_service_role")
        
        if not self._url or not self._key:
            logger.warning("Supabase credentials not found, persistence disabled")
            return False
        
        try:
            self._client = create_client(self._url, self._key)
            self._initialized = True
            logger.info("Supabase client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Supabase: {e}")
            return False
    
    def _reconnect(self) -> bool:
        """Reconnect to Supabase if connection was lost."""
        if self._url and self._key:
            try:
                self._client = create_client(self._url, self._key)
                logger.info("Supabase client reconnected")
                return True
            except Exception as e:
                logger.error(f"Failed to reconnect to Supabase: {e}")
                return False
        return False
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized and self._client is not None
    
    def _insert_sync(self, table: str, data: Any, retry: bool = True):
        try:
            return self._client.table(table).insert(data).execute()
        except Exception as e:
            if retry and "disconnected" in str(e).lower():
                if self._reconnect():
                    return self._insert_sync(table, data, retry=False)
            raise
    
    def _select_sync(self, table: str, account_index: int, limit: int, exchange: Optional[str] = None):
        query = self._client.table(table).select("*").eq("account_index", account_index)
        if exchange:
            query = query.eq("exchange", exchange)
        return query.order("timestamp", desc=True).limit(limit).execute()
    
    async def save_account_snapshot(self, account_index: int, data: Dict[str, Any], exchange: str = "lighter") -> bool:
        if not self.is_initialized:
            return False
        
        try:
            raw_data = data.get("raw_data", {})
            accounts = raw_data.get("accounts", [])
            account_info = accounts[0] if accounts else {}
            
            snapshot = {
                "account_index": account_index,
                "exchange": exchange,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "equity": account_info.get("equity"),
                "margin": account_info.get("margin"),
                "available_balance": account_info.get("available_balance"),
                "pnl": account_info.get("pnl"),
                "positions_count": len(account_info.get("positions", [])),
                "orders_count": len(data.get("active_orders", [])),
                "raw_data": data
            }
            
            await asyncio.to_thread(self._insert_sync, "account_snapshots", snapshot)
            logger.debug(f"Saved snapshot for account {account_index} ({exchange})")
            return True
        except Exception as e:
            logger.error(f"Failed to save account snapshot: {e}")
            return False
    
    async def save_positions(self, account_index: int, positions: List[Dict], exchange: str = "lighter") -> bool:
        if not self.is_initialized or not positions:
            return False
        
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            records = []
            
            for pos in positions:
                records.append({
                    "account_index": account_index,
                    "exchange": exchange,
                    "timestamp": timestamp,
                    "market": pos.get("market_name") or pos.get("market"),
                    "side": pos.get("side"),
                    "size": pos.get("size"),
                    "entry_price": pos.get("entry_price"),
                    "mark_price": pos.get("mark_price"),
                    "unrealized_pnl": pos.get("unrealized_pnl"),
                    "raw_data": pos
                })
            
            if records:
                await asyncio.to_thread(self._insert_sync, "positions", records)
                logger.debug(f"Saved {len(records)} positions for account {account_index} ({exchange})")
            return True
        except Exception as e:
            logger.error(f"Failed to save positions: {e}")
            return False
    
    async def save_orders(self, account_index: int, orders: List[Dict], exchange: str = "lighter") -> bool:
        if not self.is_initialized or not orders:
            return False
        
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            records = []
            
            for order in orders:
                # Handle both 'size' and 'qty' field names
                size = order.get("size") or order.get("qty")
                filled = order.get("filled") or order.get("filledQty")
                
                records.append({
                    "account_index": account_index,
                    "exchange": exchange,
                    "timestamp": timestamp,
                    "order_id": order.get("id") or order.get("order_id"),
                    "market": order.get("market_name") or order.get("market"),
                    "side": order.get("side"),
                    "order_type": order.get("type") or order.get("order_type"),
                    "price": order.get("price"),
                    "size": size,
                    "filled": filled,
                    "status": order.get("status"),
                    "raw_data": order
                })
            
            if records:
                await asyncio.to_thread(self._insert_sync, "orders", records)
                logger.debug(f"Saved {len(records)} orders for account {account_index} ({exchange})")
            return True
        except Exception as e:
            logger.error(f"Failed to save orders: {e}")
            return False
    
    async def save_trade(self, account_index: int, trade: Dict, exchange: str = "lighter") -> bool:
        if not self.is_initialized:
            return False
        
        try:
            # Get trade_id and check for duplicates
            trade_id = str(trade.get("id") or trade.get("trade_id") or "")
            if not trade_id:
                logger.warning(f"Trade without ID, skipping: {trade}")
                return False
            
            # Skip if already saved (prevent duplicates)
            cache_key = f"{account_index}_{trade_id}"
            if cache_key in self._saved_trade_ids:
                logger.debug(f"Trade {trade_id} already saved, skipping duplicate")
                return False
            
            # Handle position size (qty, size, position)
            position_size = trade.get("qty") or trade.get("size") or trade.get("position")
            
            # Use original trade timestamp (closedAt, createdAt, timestamp, time)
            original_time = trade.get("closedAt") or trade.get("createdAt") or trade.get("timestamp") or trade.get("time")
            if original_time:
                if isinstance(original_time, (int, float)):
                    if original_time > 1e12:  # milliseconds
                        original_time = original_time / 1000
                    timestamp = datetime.fromtimestamp(original_time, tz=timezone.utc).isoformat()
                else:
                    timestamp = str(original_time)
            else:
                timestamp = datetime.now(timezone.utc).isoformat()
            
            exit_price = trade.get("exitPrice") or trade.get("exit_price") or trade.get("price")
            
            volume = None
            if position_size is not None and exit_price is not None:
                try:
                    volume = float(position_size) * float(exit_price)
                except (ValueError, TypeError):
                    volume = None
            
            record = {
                "account_index": account_index,
                "exchange": exchange,
                "timestamp": timestamp,
                "trade_id": trade_id,
                "market": trade.get("market_name") or trade.get("market"),
                "side": trade.get("side"),
                "exit_type": trade.get("exitType") or trade.get("exit_type") or "Trade",
                "position_size": position_size,
                "entry_price": trade.get("entryPrice") or trade.get("entry_price"),
                "exit_price": exit_price,
                "realized_pnl": trade.get("realizedPnl") or trade.get("realized_pnl") or trade.get("pnl"),
                "trade_pnl": trade.get("tradePnl") or trade.get("trade_pnl"),
                "funding_fees": trade.get("fundingFees") or trade.get("funding_fees"),
                "trading_fees": trade.get("tradingFees") or trade.get("trading_fees") or trade.get("fee"),
                "volume": volume,
                "raw_data": trade
            }
            
            await asyncio.to_thread(self._insert_sync, "trades", record)
            self._saved_trade_ids.add(cache_key)
            logger.info(f"Saved trade {trade_id} for account {account_index}: {trade.get('side')} {position_size} @ {record['exit_price']}")
            return True
        except Exception as e:
            logger.error(f"Failed to save trade: {e}")
            return False
    
    async def get_account_history(self, account_index: int, limit: int = 100, exchange: Optional[str] = None) -> List[Dict]:
        if not self.is_initialized:
            return []
        
        try:
            result = await asyncio.to_thread(self._select_sync, "account_snapshots", account_index, limit, exchange)
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Failed to get account history: {e}")
            return []
    
    async def get_recent_trades(self, account_index: int, limit: int = 50, exchange: Optional[str] = None) -> List[Dict]:
        if not self.is_initialized:
            return []
        
        try:
            result = await asyncio.to_thread(self._select_sync, "trades", account_index, limit, exchange)
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Failed to get recent trades: {e}")
            return []
    
    def _select_all_trades_sync(self, limit: int):
        return self._client.table("trades").select("*").order("timestamp", desc=True).limit(limit).execute()
    
    async def get_all_recent_trades(self, limit: int = 100) -> List[Dict]:
        if not self.is_initialized:
            return []
        
        try:
            result = await asyncio.to_thread(self._select_all_trades_sync, limit)
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Failed to get all recent trades: {e}")
            return []
    
    def _select_trades_since_sync(self, since: datetime, account_index: Optional[int] = None):
        query = self._client.table("trades").select("*").gte("timestamp", since.isoformat())
        if account_index is not None:
            query = query.eq("account_index", account_index)
        return query.order("timestamp", desc=True).execute()
    
    async def get_trades_stats(self, hours: int = 24, account_index: Optional[int] = None) -> Dict[str, Any]:
        if not self.is_initialized:
            return {"error": "Supabase not initialized"}
        
        try:
            since = datetime.now(timezone.utc) - timedelta(hours=hours)
            result = await asyncio.to_thread(self._select_trades_since_sync, since, account_index)
            trades = result.data if result.data else []
            
            total_pnl = 0.0
            total_volume = 0.0
            wins = 0
            losses = 0
            
            for trade in trades:
                pnl = trade.get("realized_pnl")
                vol = trade.get("volume")
                
                if pnl is not None:
                    try:
                        pnl_val = float(pnl)
                        total_pnl += pnl_val
                        if pnl_val > 0:
                            wins += 1
                        elif pnl_val < 0:
                            losses += 1
                    except (ValueError, TypeError):
                        pass
                
                if vol is not None:
                    try:
                        total_volume += float(vol)
                    except (ValueError, TypeError):
                        pass
            
            total_trades = len(trades)
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
            
            return {
                "period_hours": hours,
                "total_pnl": round(total_pnl, 2),
                "total_volume": round(total_volume, 2),
                "trades_count": total_trades,
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 2),
                "since": since.isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to get trades stats: {e}")
            return {"error": str(e)}
    
    async def get_period_stats(self, account_index: Optional[int] = None) -> Dict[str, Any]:
        stats_24h = await self.get_trades_stats(hours=24, account_index=account_index)
        stats_7d = await self.get_trades_stats(hours=24*7, account_index=account_index)
        stats_30d = await self.get_trades_stats(hours=24*30, account_index=account_index)
        
        return {
            "24h": stats_24h,
            "7d": stats_7d,
            "30d": stats_30d
        }
    
    def _select_trades_with_limit_sync(self, limit: int, account_index: Optional[int] = None):
        query = self._client.table("trades").select(
            "id, account_index, exchange, timestamp, trade_id, market, side, "
            "exit_type, position_size, entry_price, exit_price, realized_pnl, "
            "trade_pnl, funding_fees, trading_fees, volume"
        )
        if account_index is not None:
            query = query.eq("account_index", account_index)
        return query.order("timestamp", desc=True).limit(limit).execute()
    
    async def get_trades_list(self, limit: int = 100, account_index: Optional[int] = None) -> List[Dict]:
        if not self.is_initialized:
            return []
        
        try:
            result = await asyncio.to_thread(self._select_trades_with_limit_sync, limit, account_index)
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Failed to get trades list: {e}")
            return []


supabase_client = SupabaseClient()
