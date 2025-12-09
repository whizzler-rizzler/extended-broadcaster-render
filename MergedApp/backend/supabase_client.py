import os
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from supabase import create_client, Client

logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        self._client: Optional[Client] = None
        self._initialized = False
        self._url: Optional[str] = None
        self._key: Optional[str] = None
    
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
            # Handle both 'size' and 'qty' field names (Extended API uses 'qty')
            size = trade.get("size") or trade.get("qty")
            value = trade.get("value")
            
            record = {
                "account_index": account_index,
                "exchange": exchange,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "trade_id": trade.get("id") or trade.get("trade_id"),
                "market": trade.get("market_name") or trade.get("market"),
                "side": trade.get("side"),
                "price": trade.get("price"),
                "size": size,
                "value": value,
                "fee": trade.get("fee"),
                "raw_data": trade
            }
            
            await asyncio.to_thread(self._insert_sync, "trades", record)
            logger.debug(f"Saved trade for account {account_index} ({exchange}): size={size}, value={value}")
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


supabase_client = SupabaseClient()
