from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import aiohttp
import asyncio
import os
from typing import Dict, Any, Set, List, Optional
import json
import time
from datetime import datetime
from dataclasses import dataclass, field
from supabase_client import supabase_client

app = FastAPI(title="Extended API Multi-Account Broadcaster")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============= ACCOUNT CONFIGURATION =============
@dataclass
class AccountConfig:
    id: str
    name: str
    api_key: str
    base_url: str = "https://api.starknet.extended.exchange/api/v1"
    proxy_url: str = None  # Optional proxy URL per account

@dataclass 
class AccountCache:
    positions: Any = None
    balance: Any = None
    trades: Any = None
    orders: Any = None
    last_update: Dict[str, float] = field(default_factory=lambda: {
        "positions": 0,
        "balance": 0,
        "trades": 0,
        "orders": 0,
    })

# Load account configurations from environment variables
def load_accounts() -> List[AccountConfig]:
    accounts = []
    
    # Account identifier codes for Extended_N_XXXXXX_API_KEY format
    ACCOUNT_CODES = {
        1: "aE42d3",
        2: "61658C",
        3: "74eF87",
        4: "1112E1",
        5: "fe69Ac",
        6: "05A739",
        7: "1eE2a4",
        8: "7B8f14",
        9: "1A04d3",
        10: "0f08fC",
    }
    
    # Try Extended_N_XXXXXX_API_KEY format first (user's format)
    for i in range(1, 11):
        code = ACCOUNT_CODES.get(i, "")
        api_key = os.getenv(f"Extended_{i}_{code}_API_KEY")
        if api_key:
            # Get raw proxy value - format is IP:PORT:Username:Password
            proxy_var = f"Extended_{i}_PROXY_{i}_URL"
            raw_proxy = os.getenv(proxy_var)
            
            proxy_url = None
            if raw_proxy:
                # Convert from IP:PORT:Username:Password to http://username:password@ip:port
                parts = raw_proxy.strip().split(':')
                if len(parts) == 4:
                    ip, port, username, password = parts
                    proxy_url = f"http://{username}:{password}@{ip}:{port}"
                    print(f"✅ Account {i} proxy: {ip}:{port} (user: {username})")
                else:
                    print(f"⚠️ Account {i} proxy invalid: expected IP:PORT:User:Pass, got {len(parts)} parts")
            else:
                print(f"⚠️ Account {i}: no proxy ({proxy_var} not set)")
            
            accounts.append(AccountConfig(
                id=f"account_{i}",
                name=f"Extended {i} ({code})",
                api_key=api_key,
                base_url="https://api.starknet.extended.exchange/api/v1",
                proxy_url=proxy_url
            ))
            proxy_info = f" (via proxy)" if proxy_url else " (no proxy)"
            print(f"✅ Loaded Account {i}: Extended_{i}_{code}{proxy_info}")
    
    # Fallback: Try ACCOUNT_N_API_KEY format
    if not accounts:
        for i in range(1, 11):
            api_key = os.getenv(f"ACCOUNT_{i}_API_KEY")
            if api_key:
                name = os.getenv(f"ACCOUNT_{i}_NAME", f"Account {i}")
                base_url = os.getenv(f"ACCOUNT_{i}_BASE_URL", "https://api.starknet.extended.exchange/api/v1")
                accounts.append(AccountConfig(
                    id=f"account_{i}",
                    name=name,
                    api_key=api_key,
                    base_url=base_url.rstrip("/")
                ))
                print(f"✅ Loaded Account {i}: {name}")
    
    # Final fallback: old single-account format
    if not accounts:
        api_key = os.getenv("EXTENDED_API_KEY")
        if api_key:
            accounts.append(AccountConfig(
                id="account_1",
                name="Main Account",
                api_key=api_key,
                base_url=os.getenv("EXTENDED_API_BASE_URL", "https://api.starknet.extended.exchange/api/v1").rstrip("/")
            ))
            print(f"✅ Loaded single account (legacy mode)")
    
    return accounts

ACCOUNTS = load_accounts()

if not ACCOUNTS:
    raise ValueError("No account API keys configured! Set ACCOUNT_1_API_KEY or EXTENDED_API_KEY")

print(f"🎯 Total accounts configured: {len(ACCOUNTS)}")

# ============= BROADCASTER GLOBAL STATE =============
# Cache for each account - keyed by account ID
BROADCASTER_CACHES: Dict[str, AccountCache] = {
    account.id: AccountCache() for account in ACCOUNTS
}

# Set of connected WebSocket clients
BROADCAST_CLIENTS: Set[WebSocket] = set()

# Poller state tracking
TRADES_POLL_COUNTER = 0


# ============= UTILITY FUNCTIONS =============
def data_changed(old_data: Any, new_data: Any) -> bool:
    """Compare two data structures to detect changes."""
    if old_data is None and new_data is not None:
        return True
    if old_data is not None and new_data is None:
        return True
    return json.dumps(old_data, sort_keys=True) != json.dumps(new_data, sort_keys=True)


async def fetch_account_api(account: AccountConfig, endpoint: str) -> Dict[str, Any] | None:
    """Fetch data from Extended API for a specific account, using proxy if configured."""
    try:
        async with aiohttp.ClientSession() as session:
            request_kwargs = {
                "headers": {
                    "X-Api-Key": account.api_key,
                    "User-Agent": "extended-broadcaster/3.0-multiacccount",
                    "Content-Type": "application/json",
                },
                "timeout": aiohttp.ClientTimeout(total=15.0)
            }
            
            # Add proxy if configured - this routes the request through the proxy IP
            if account.proxy_url:
                request_kwargs["proxy"] = account.proxy_url
            
            url = f"{account.base_url}{endpoint}"
            
            async with session.get(url, **request_kwargs) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    proxy_info = f" (proxy: {account.proxy_url[:25]}...)" if account.proxy_url else ""
                    print(f"⚠️ [{account.name}][{endpoint}] HTTP {response.status}{proxy_info}")
                    return None
    except Exception as e:
        proxy_info = f" via proxy" if account.proxy_url else ""
        print(f"❌ [{account.name}][{endpoint}]{proxy_info} Error: {e}")
        return None


async def broadcast_to_clients(message: Dict[str, Any]):
    """Broadcast a message to all connected WebSocket clients."""
    if not BROADCAST_CLIENTS:
        return
    
    disconnected = set()
    message_json = json.dumps(message)
    
    for client in BROADCAST_CLIENTS:
        try:
            await client.send_text(message_json)
        except Exception as e:
            disconnected.add(client)
    
    for client in disconnected:
        BROADCAST_CLIENTS.discard(client)
        print(f"🗑️ [Broadcast] Removed disconnected client (remaining: {len(BROADCAST_CLIENTS)})")


# ============= BACKGROUND POLLERS =============
async def poll_account_fast_data(account: AccountConfig):
    """Poll positions and balance for a single account (4x per second)."""
    cache = BROADCASTER_CACHES[account.id]
    
    positions_task = fetch_account_api(account, "/user/positions")
    balance_task = fetch_account_api(account, "/user/balance")
    
    new_positions, new_balance = await asyncio.gather(
        positions_task, balance_task, return_exceptions=True
    )
    
    changes = []
    
    if not isinstance(new_positions, Exception) and new_positions is not None:
        if data_changed(cache.positions, new_positions):
            cache.positions = new_positions
            cache.last_update["positions"] = time.time()
            changes.append("positions")
    
    if not isinstance(new_balance, Exception) and new_balance is not None:
        if data_changed(cache.balance, new_balance):
            cache.balance = new_balance
            cache.last_update["balance"] = time.time()
            changes.append("balance")
    
    if changes:
        print(f"📊 [{account.name}] Changes: {', '.join(changes)} - broadcasting")
        await broadcast_to_clients({
            "type": "account_update",
            "account_id": account.id,
            "account_name": account.name,
            "positions": cache.positions if "positions" in changes else None,
            "balance": cache.balance if "balance" in changes else None,
            "timestamp": time.time()
        })
        
        # Save to Supabase (async, non-blocking)
        if supabase_client.is_initialized:
            account_idx = int(account.id.split('_')[1])
            
            # Save account snapshot with balance
            if "balance" in changes and cache.balance:
                balance_data = cache.balance.get('data', cache.balance) if isinstance(cache.balance, dict) else cache.balance
                snapshot_data = {
                    "raw_data": {"accounts": [balance_data] if isinstance(balance_data, dict) else balance_data},
                    "active_orders": cache.orders or []
                }
                asyncio.create_task(supabase_client.save_account_snapshot(account_idx, snapshot_data, exchange="extended"))
            
            # Save positions
            if "positions" in changes and cache.positions:
                positions_list = cache.positions.get('data', cache.positions) if isinstance(cache.positions, dict) else cache.positions
                if isinstance(positions_list, list):
                    asyncio.create_task(supabase_client.save_positions(account_idx, positions_list, exchange="extended"))


async def poll_account_trades(account: AccountConfig):
    """Poll closed positions (with PnL) for a single account."""
    cache = BROADCASTER_CACHES[account.id]
    new_trades = await fetch_account_api(account, "/user/positions-history")
    
    if new_trades is not None and data_changed(cache.trades, new_trades):
        cache.trades = new_trades
        cache.last_update["trades"] = time.time()
        print(f"📜 [{account.name}] Trades changed - broadcasting")
        await broadcast_to_clients({
            "type": "trades_update",
            "account_id": account.id,
            "account_name": account.name,
            "trades": new_trades,
            "timestamp": time.time()
        })
        
        # Save trades to Supabase
        if supabase_client.is_initialized:
            account_idx = int(account.id.split('_')[1])
            trades_list = new_trades.get('data', new_trades) if isinstance(new_trades, dict) else new_trades
            if isinstance(trades_list, list):
                for trade in trades_list:
                    asyncio.create_task(supabase_client.save_trade(account_idx, trade, exchange="extended"))


async def poll_account_orders(account: AccountConfig):
    """Poll orders for a single account (2x per second)."""
    cache = BROADCASTER_CACHES[account.id]
    new_orders = await fetch_account_api(account, "/user/orders?status=ACTIVE")
    
    if new_orders is not None and data_changed(cache.orders, new_orders):
        cache.orders = new_orders
        cache.last_update["orders"] = time.time()
        print(f"📋 [{account.name}] Orders changed - broadcasting")
        await broadcast_to_clients({
            "type": "orders_update",
            "account_id": account.id,
            "account_name": account.name,
            "orders": new_orders,
            "timestamp": time.time()
        })
        
        # Save orders to Supabase
        if supabase_client.is_initialized:
            account_idx = int(account.id.split('_')[1])
            orders_list = new_orders.get('data', new_orders) if isinstance(new_orders, dict) else new_orders
            if isinstance(orders_list, list):
                asyncio.create_task(supabase_client.save_orders(account_idx, orders_list, exchange="extended"))


async def poll_all_accounts_fast():
    """Poll fast data (positions + balance) for all accounts in parallel."""
    await asyncio.gather(*[
        poll_account_fast_data(account) for account in ACCOUNTS
    ], return_exceptions=True)


async def poll_all_accounts_trades():
    """Poll trades for all accounts in parallel."""
    await asyncio.gather(*[
        poll_account_trades(account) for account in ACCOUNTS
    ], return_exceptions=True)


async def poll_all_accounts_orders():
    """Poll orders for all accounts in parallel."""
    await asyncio.gather(*[
        poll_account_orders(account) for account in ACCOUNTS
    ], return_exceptions=True)


async def background_poller():
    """
    Main background task that continuously polls Extended API for all accounts.
    
    With proxies per account, rate limiting is avoided.
    - Fast loop (250ms): positions + balance + orders (4x/sec per account)
    - Trades loop (1000ms): trades (1x/sec per account)
    """
    global TRADES_POLL_COUNTER
    
    # Count accounts with proxies
    proxied_accounts = sum(1 for a in ACCOUNTS if a.proxy_url)
    print(f"🚀 [Broadcaster] Background poller started for {len(ACCOUNTS)} accounts")
    print(f"🔒 Accounts with proxy: {proxied_accounts}/{len(ACCOUNTS)}")
    print(f"⚡ Polling rates: positions/balance/orders 4x/s, trades 1x/s")
    
    while True:
        try:
            # Fast polling: positions + balance + orders for all accounts (every 250ms = 4x/sec)
            await poll_all_accounts_fast()
            await poll_all_accounts_orders()
            
            # Trades polling: every 4 cycles (1 second)
            TRADES_POLL_COUNTER += 1
            if TRADES_POLL_COUNTER >= 4:
                await poll_all_accounts_trades()
                TRADES_POLL_COUNTER = 0
            
            await asyncio.sleep(0.25)
            
        except Exception as e:
            print(f"❌ [Broadcaster] Poller error: {e}")
            await asyncio.sleep(0.5)


# ============= STARTUP EVENT =============
@app.on_event("startup")
async def startup_broadcaster():
    print(f"⚡ [Startup] Initializing multi-account broadcaster for {len(ACCOUNTS)} accounts...")
    
    # Initialize Supabase persistence
    if supabase_client.initialize():
        print("✅ [Startup] Supabase persistence enabled")
    else:
        print("⚠️ [Startup] Supabase persistence disabled (no credentials)")
    
    asyncio.create_task(background_poller())
    print("✅ [Startup] Broadcaster initialized")


# ============= REST API ENDPOINTS =============
@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "extended-multi-account-broadcaster",
        "accounts_configured": len(ACCOUNTS),
        "broadcaster": {
            "connected_clients": len(BROADCAST_CLIENTS),
            "accounts": [
                {
                    "id": account.id,
                    "name": account.name,
                    "cache_initialized": all([
                        BROADCASTER_CACHES[account.id].positions is not None,
                        BROADCASTER_CACHES[account.id].balance is not None,
                    ])
                }
                for account in ACCOUNTS
            ]
        }
    }


@app.get("/api/cached-accounts")
async def get_cached_accounts():
    """
    Return cached data for ALL accounts.
    
    ✅ NO rate limits - served from memory
    ✅ Frontend can call 100x/s if needed
    ✅ Zero Extended API calls
    """
    current_time = time.time()
    
    accounts_data = {}
    for account in ACCOUNTS:
        cache = BROADCASTER_CACHES[account.id]
        accounts_data[account.id] = {
            "id": account.id,
            "name": account.name,
            "positions": cache.positions,
            "balance": cache.balance,
            "trades": cache.trades,
            "orders": cache.orders,
            "cache_age_ms": {
                "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
                "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
                "trades": int((current_time - cache.last_update["trades"]) * 1000) if cache.last_update["trades"] > 0 else None,
                "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
            },
            "last_update": cache.last_update.copy()
        }
    
    return {
        "accounts": accounts_data,
        "total_accounts": len(ACCOUNTS),
        "timestamp": current_time
    }


@app.get("/api/cached-account")
async def get_cached_account():
    """
    Return cached data for the first/primary account (backward compatibility).
    """
    if not ACCOUNTS:
        raise HTTPException(status_code=404, detail="No accounts configured")
    
    account = ACCOUNTS[0]
    cache = BROADCASTER_CACHES[account.id]
    current_time = time.time()
    
    return {
        "account_id": account.id,
        "account_name": account.name,
        "positions": cache.positions,
        "balance": cache.balance,
        "trades": cache.trades,
        "orders": cache.orders,
        "cache_age_ms": {
            "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
            "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
            "trades": int((current_time - cache.last_update["trades"]) * 1000) if cache.last_update["trades"] > 0 else None,
            "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
        }
    }


@app.get("/api/cached-account/{account_id}")
async def get_cached_account_by_id(account_id: str):
    """Return cached data for a specific account by ID."""
    if account_id not in BROADCASTER_CACHES:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    
    account = next((a for a in ACCOUNTS if a.id == account_id), None)
    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    
    cache = BROADCASTER_CACHES[account_id]
    current_time = time.time()
    
    return {
        "account_id": account.id,
        "account_name": account.name,
        "positions": cache.positions,
        "balance": cache.balance,
        "trades": cache.trades,
        "orders": cache.orders,
        "cache_age_ms": {
            "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
            "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
            "trades": int((current_time - cache.last_update["trades"]) * 1000) if cache.last_update["trades"] > 0 else None,
            "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
        }
    }


@app.get("/api/broadcaster/stats")
async def broadcaster_stats():
    """Get broadcaster statistics and monitoring info."""
    current_time = time.time()
    
    accounts_stats = []
    for account in ACCOUNTS:
        cache = BROADCASTER_CACHES[account.id]
        accounts_stats.append({
            "id": account.id,
            "name": account.name,
            "positions_initialized": cache.positions is not None,
            "balance_initialized": cache.balance is not None,
            "trades_initialized": cache.trades is not None,
            "orders_initialized": cache.orders is not None,
            "positions_age_seconds": int(current_time - cache.last_update["positions"]) if cache.last_update["positions"] > 0 else None,
            "balance_age_seconds": int(current_time - cache.last_update["balance"]) if cache.last_update["balance"] > 0 else None,
        })
    
    return {
        "broadcaster": {
            "connected_clients": len(BROADCAST_CLIENTS),
            "accounts_configured": len(ACCOUNTS),
            "extended_api_rate": f"~{len(ACCOUNTS) * 6} req/s total ({len(ACCOUNTS)} accounts x 6 endpoints)",
        },
        "accounts": accounts_stats,
        "timestamp": current_time
    }


# ============= WEBSOCKET BROADCAST ENDPOINT =============
@app.websocket("/ws/broadcast")
async def websocket_broadcast(websocket: WebSocket):
    """WebSocket endpoint for broadcasting real-time updates for all accounts."""
    await websocket.accept()
    print(f"✅ [WS] New client connected (total: {len(BROADCAST_CLIENTS) + 1})")
    
    BROADCAST_CLIENTS.add(websocket)
    
    try:
        # Send immediate snapshot of all accounts
        accounts_snapshot = {}
        for account in ACCOUNTS:
            cache = BROADCASTER_CACHES[account.id]
            accounts_snapshot[account.id] = {
                "id": account.id,
                "name": account.name,
                "positions": cache.positions,
                "balance": cache.balance,
                "trades": cache.trades,
                "orders": cache.orders,
            }
        
        snapshot = {
            "type": "snapshot",
            "accounts": accounts_snapshot,
            "total_accounts": len(ACCOUNTS),
            "timestamp": time.time()
        }
        await websocket.send_json(snapshot)
        print(f"📸 [WS] Sent snapshot for {len(ACCOUNTS)} accounts to client")
        
        while True:
            try:
                await asyncio.sleep(30)
                await websocket.send_json({"type": "ping", "timestamp": time.time()})
            except WebSocketDisconnect:
                break
            except Exception as e:
                print(f"⚠️ [WS] Error in keep-alive: {e}")
                break
                
    except WebSocketDisconnect:
        print(f"👋 [WS] Client disconnected gracefully")
    except Exception as e:
        print(f"❌ [WS] Connection error: {e}")
    finally:
        BROADCAST_CLIENTS.discard(websocket)
        print(f"🗑️ [WS] Client removed (remaining: {len(BROADCAST_CLIENTS)})")


# ============= SUPABASE HISTORY ENDPOINTS =============
@app.get("/api/account/{account_id}/history")
async def get_account_history(account_id: int, limit: int = 100):
    """Get historical snapshots from Supabase."""
    if not supabase_client.is_initialized:
        raise HTTPException(status_code=503, detail="Supabase persistence not enabled")
    
    history = await supabase_client.get_account_history(account_id, limit, exchange="extended")
    return {"account_id": account_id, "history": history, "count": len(history)}


@app.get("/api/trades/recent")
async def get_recent_trades(account_id: Optional[int] = None, limit: int = 100):
    """Get recent trades from Supabase."""
    if not supabase_client.is_initialized:
        raise HTTPException(status_code=503, detail="Supabase persistence not enabled")
    
    if account_id is not None:
        trades = await supabase_client.get_recent_trades(account_id, limit, exchange="extended")
    else:
        trades = await supabase_client.get_all_recent_trades(limit)
    
    return {"account_id": account_id, "trades": trades, "count": len(trades)}


# Legacy endpoints removed - use /api/cached-accounts instead


# ============= STATISTICS ENDPOINTS =============
@app.get("/api/stats/periods")
async def get_stats_periods(account_id: Optional[int] = None):
    """
    Get trading statistics for 24h, 7d, and 30d periods.
    Each period includes: total_pnl, total_volume, trades_count, wins, losses, win_rate
    """
    if not supabase_client.is_initialized:
        raise HTTPException(status_code=503, detail="Supabase persistence not enabled")
    
    stats = await supabase_client.get_period_stats(account_index=account_id)
    return {
        "account_id": account_id,
        "stats": stats,
        "timestamp": time.time()
    }


@app.get("/api/stats/summary")
async def get_stats_summary():
    """
    Get summary statistics for all accounts.
    Includes: current equity (from cache), PnL for 24h/7d/30d, total volume.
    """
    if not supabase_client.is_initialized:
        raise HTTPException(status_code=503, detail="Supabase persistence not enabled")
    
    total_equity = 0.0
    accounts_equity = {}
    
    for account in ACCOUNTS:
        cache = BROADCASTER_CACHES[account.id]
        if cache.balance:
            balance_data = cache.balance.get('data', cache.balance) if isinstance(cache.balance, dict) else cache.balance
            if isinstance(balance_data, dict):
                equity = balance_data.get('equity') or balance_data.get('totalEquity') or 0
            elif isinstance(balance_data, list) and len(balance_data) > 0:
                equity = balance_data[0].get('equity') or balance_data[0].get('totalEquity') or 0
            else:
                equity = 0
            try:
                equity_val = float(equity)
                total_equity += equity_val
                accounts_equity[account.id] = equity_val
            except (ValueError, TypeError):
                accounts_equity[account.id] = 0
    
    stats = await supabase_client.get_period_stats()
    
    return {
        "total_equity": round(total_equity, 2),
        "accounts_equity": accounts_equity,
        "pnl_24h": stats.get("24h", {}).get("total_pnl", 0),
        "pnl_7d": stats.get("7d", {}).get("total_pnl", 0),
        "pnl_30d": stats.get("30d", {}).get("total_pnl", 0),
        "volume_24h": stats.get("24h", {}).get("total_volume", 0),
        "volume_7d": stats.get("7d", {}).get("total_volume", 0),
        "volume_30d": stats.get("30d", {}).get("total_volume", 0),
        "trades_24h": stats.get("24h", {}).get("trades_count", 0),
        "trades_7d": stats.get("7d", {}).get("trades_count", 0),
        "trades_30d": stats.get("30d", {}).get("trades_count", 0),
        "win_rate_24h": stats.get("24h", {}).get("win_rate", 0),
        "win_rate_7d": stats.get("7d", {}).get("win_rate", 0),
        "win_rate_30d": stats.get("30d", {}).get("win_rate", 0),
        "timestamp": time.time()
    }


@app.get("/api/trades")
async def get_trades_list(account_id: Optional[int] = None, limit: int = 100):
    """
    Get list of trades with PnL and volume.
    Returns: market, side, position_size, entry_price, exit_price, realized_pnl, volume, timestamp
    """
    if not supabase_client.is_initialized:
        raise HTTPException(status_code=503, detail="Supabase persistence not enabled")
    
    trades = await supabase_client.get_trades_list(limit=limit, account_index=account_id)
    return {
        "account_id": account_id,
        "trades": trades,
        "count": len(trades),
        "timestamp": time.time()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
