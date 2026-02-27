from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import aiohttp
import asyncio
import os
from typing import Dict, Any, Set, List, Optional
import json
import time
from datetime import datetime
from dataclasses import dataclass, field
from supabase_client import supabase_client
from margin_alerts import alert_manager, MARGIN_THRESHOLDS
import trade_history
from reya_client import (
    load_reya_accounts, fetch_reya_api, normalize_reya_positions,
    normalize_reya_balance, normalize_reya_orders, fetch_reya_market_prices,
    ReyaAccountConfig, ReyaAccountCache,
)
from edgex_client import (
    load_edgex_accounts, fetch_edgex_api, normalize_edgex_positions,
    normalize_edgex_balance, normalize_edgex_orders, fetch_edgex_ticker_prices,
    EdgeXAccountConfig, EdgeXAccountCache,
)
from hibachi_client import (
    load_hibachi_accounts, poll_hibachi_account,
    HibachiAccountConfig, HibachiAccountCache,
)
from grvt_client import (
    load_grvt_accounts, poll_grvt_account,
    GrvtAccountConfig, GrvtAccountCache,
)
from zero_one_client import (
    load_01_accounts, poll_01_account, resolve_all_account_ids,
    ZeroOneAccountConfig, ZeroOneAccountCache,
)

app = FastAPI(title="Extended API Multi-Account Broadcaster")

# ============= BROADCASTER MODE CONFIGURATION =============
BROADCASTER_MODE = os.getenv("BROADCASTER_MODE", "COLLECTOR")
REMOTE_API_BASE = os.getenv("REMOTE_API_BASE", "").rstrip("/")
IS_FRONTEND_ONLY = BROADCASTER_MODE == "FRONTEND_ONLY"

if IS_FRONTEND_ONLY:
    print(f"🌐 Running in FRONTEND_ONLY mode")
    print(f"📡 Proxying API requests to: {REMOTE_API_BASE}")
else:
    print(f"🔄 Running in COLLECTOR mode - polling Extended API directly")

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
    proxy_url: Optional[str] = None  # Optional proxy URL per account

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
def parse_proxy_url(raw_proxy: str, use_staticresidential: bool = False, account_num: int = 0) -> Optional[str]:
    """Parse proxy URL from various formats into a standard http:// URL."""
    if not raw_proxy:
        return None
    raw_proxy = raw_proxy.strip()
    if raw_proxy.startswith("http://") or raw_proxy.startswith("https://"):
        try:
            at_idx = raw_proxy.find('@')
            if at_idx > 0:
                host_part = raw_proxy[at_idx+1:].rstrip('/')
                print(f"✅ Account {account_num} proxy: {host_part}")
            else:
                print(f"✅ Account {account_num} proxy: configured (full URL)")
        except:
            print(f"✅ Account {account_num} proxy: configured (full URL)")
        return raw_proxy
    else:
        parts = raw_proxy.split(':')
        if len(parts) == 4:
            ip, port, username, password = parts
            if use_staticresidential and not username.endswith('-staticresidential'):
                username = f"{username}-staticresidential"
            proxy_url = f"http://{username}:{password}@{ip}:{port}"
            print(f"✅ Account {account_num} proxy: {ip}:{port} (user: {username})")
            return proxy_url
        else:
            print(f"⚠️ Account {account_num} proxy invalid: expected IP:PORT:User:Pass or full URL, got: {raw_proxy[:30]}...")
            return None

def load_accounts() -> List[AccountConfig]:
    import re
    import json as json_lib
    accounts = []
    json_accounts = {}
    legacy_accounts = {}
    
    # === Phase 1: Detect JSON format accounts (Extended_N = {...}) ===
    json_pattern = re.compile(r'^Extended_(\d+)$')
    for env_var in os.environ:
        match = json_pattern.match(env_var)
        if match:
            account_num = int(match.group(1))
            raw_value = os.getenv(env_var, '').strip()
            if raw_value.startswith('{'):
                try:
                    data = json_lib.loads(raw_value)
                    if 'api_key' in data:
                        json_accounts[account_num] = data
                except json_lib.JSONDecodeError:
                    print(f"⚠️ Extended_{account_num}: invalid JSON format")
    
    # === Phase 2: Detect legacy format accounts (Extended_N_CODE_API_KEY) ===
    api_key_pattern = re.compile(r'^Extended_(\d+)_([A-Za-z0-9]+)_API_KEY$')
    for env_var in os.environ:
        match = api_key_pattern.match(env_var)
        if match:
            account_num = int(match.group(1))
            if account_num not in json_accounts:
                account_code = match.group(2)
                api_key = os.getenv(env_var)
                if api_key:
                    legacy_accounts[account_num] = {
                        'code': account_code,
                        'api_key': api_key
                    }
    
    print(f"🔍 Detected {len(json_accounts)} JSON accounts + {len(legacy_accounts)} legacy accounts = {len(json_accounts) + len(legacy_accounts)} total")
    
    # === Process JSON accounts ===
    for i in sorted(json_accounts.keys()):
        data = json_accounts[i]
        code = data.get('code', f'acc{i}')
        api_key = data['api_key']
        raw_proxy = data.get('proxy_url', '')
        proxy_url = parse_proxy_url(raw_proxy, use_staticresidential=False, account_num=i) if raw_proxy else None
        
        if not proxy_url:
            print(f"⚠️ Account {i}: no proxy in JSON config")
        
        accounts.append(AccountConfig(
            id=f"account_{i}",
            name=f"Extended {i} ({code})",
            api_key=api_key,
            base_url="https://api.starknet.extended.exchange/api/v1",
            proxy_url=proxy_url
        ))
        proxy_info = f" (via proxy)" if proxy_url else " (no proxy)"
        print(f"✅ Loaded Account {i}: Extended_{i}_{code}{proxy_info} [JSON]")
    
    # === Process legacy accounts ===
    for i in sorted(legacy_accounts.keys()):
        code = legacy_accounts[i]['code']
        api_key = legacy_accounts[i]['api_key']
        
        proxy_var_new = f"Extended_{i}_{code}_Proxy"
        proxy_var_old = f"Extended_{i}_PROXY_{i}_URL"
        proxy_var_simple = f"Extended_{i}_PROXY"
        
        raw_proxy_new = os.getenv(proxy_var_new)
        raw_proxy_old = os.getenv(proxy_var_old)
        raw_proxy_simple = os.getenv(proxy_var_simple)
        
        use_staticresidential = False
        if raw_proxy_new:
            raw_proxy = raw_proxy_new
            use_staticresidential = False
        elif raw_proxy_simple:
            raw_proxy = raw_proxy_simple
            use_staticresidential = False
        elif raw_proxy_old:
            raw_proxy = raw_proxy_old
            use_staticresidential = True
        else:
            raw_proxy = None
        
        proxy_url = parse_proxy_url(raw_proxy, use_staticresidential, i) if raw_proxy else None
        if not proxy_url and not raw_proxy:
            print(f"⚠️ Account {i}: no proxy ({proxy_var_new} or {proxy_var_old} not set)")
        
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

# Load accounts only in COLLECTOR mode
if not IS_FRONTEND_ONLY:
    ACCOUNTS = load_accounts()
    if not ACCOUNTS:
        raise ValueError("No account API keys configured! Set ACCOUNT_1_API_KEY or EXTENDED_API_KEY")
    print(f"🎯 Total Extended accounts configured: {len(ACCOUNTS)}")

    REYA_ACCOUNTS = load_reya_accounts()
    print(f"🎯 Total Reya accounts configured: {len(REYA_ACCOUNTS)}")
else:
    ACCOUNTS = []
    REYA_ACCOUNTS = load_reya_accounts()
    print(f"🎯 Total Reya accounts configured: {len(REYA_ACCOUNTS)}")
    print("🌐 FRONTEND_ONLY mode - Extended proxied from remote, Reya polled locally")

EDGEX_ACCOUNTS = load_edgex_accounts()
print(f"🎯 Total EdgeX accounts configured: {len(EDGEX_ACCOUNTS)}")

HIBACHI_ACCOUNTS = load_hibachi_accounts()
print(f"🎯 Total Hibachi accounts configured: {len(HIBACHI_ACCOUNTS)}")

GRVT_ACCOUNTS = load_grvt_accounts()
print(f"🎯 Total GRVT accounts configured: {len(GRVT_ACCOUNTS)}")

ZERO_ONE_ACCOUNTS = load_01_accounts()
print(f"🎯 Total 01 Exchange accounts configured: {len(ZERO_ONE_ACCOUNTS)}")

# ============= BROADCASTER GLOBAL STATE =============
# Cache for each account - keyed by account ID
BROADCASTER_CACHES: Dict[str, AccountCache] = {
    account.id: AccountCache() for account in ACCOUNTS
}
REYA_CACHES: Dict[str, ReyaAccountCache] = {
    account.id: ReyaAccountCache() for account in REYA_ACCOUNTS
}
EDGEX_CACHES: Dict[str, EdgeXAccountCache] = {
    account.id: EdgeXAccountCache() for account in EDGEX_ACCOUNTS
}
HIBACHI_CACHES: Dict[str, HibachiAccountCache] = {
    account.id: HibachiAccountCache() for account in HIBACHI_ACCOUNTS
}
GRVT_CACHES: Dict[str, GrvtAccountCache] = {
    account.id: GrvtAccountCache() for account in GRVT_ACCOUNTS
}
ZERO_ONE_CACHES: Dict[str, ZeroOneAccountCache] = {
    account.id: ZeroOneAccountCache() for account in ZERO_ONE_ACCOUNTS
}

# Set of connected WebSocket clients
BROADCAST_CLIENTS: Set[WebSocket] = set()

# Poller state tracking
TRADES_POLL_COUNTER = 0

# ============= ORDER BOOK STREAM STATE =============
ORDERBOOK_CACHE: Dict[str, Any] = {}
ORDERBOOK_LAST_UPDATE: float = 0
ORDERBOOK_WS_CONNECTED: bool = False
ORDERBOOK_MARKETS = ["ETH-PERP", "BTC-PERP", "SOL-PERP", "DOGE-PERP", "XRP-PERP", "ADA-PERP", "AVAX-PERP", "LINK-PERP", "DOT-PERP", "MATIC-PERP"]
EXTENDED_STREAM_URL = "wss://api.starknet.extended.exchange/stream.extended.exchange/v1"
ORDERBOOK_PROXY_URL = os.getenv("ORDERBOOK_PROXY_URL")
ORDERBOOK_DEPTH = 20

# ============= EARNED POINTS STATE =============
# Cache for earned points per account - fetched every 10 minutes
# Format: {account_id: {"points": float, "last_update": float, "raw_data": dict}}
POINTS_CACHE: Dict[str, Dict[str, Any]] = {}
POINTS_LAST_UPDATE: float = 0
POINTS_POLL_INTERVAL = 600  # 10 minutes in seconds


# ============= PROXY FUNCTION FOR FRONTEND_ONLY MODE =============
async def proxy_to_remote(endpoint: str, method: str = "GET") -> Dict[str, Any]:
    """Proxy request to remote backend in FRONTEND_ONLY mode."""
    if not REMOTE_API_BASE:
        raise HTTPException(status_code=503, detail="REMOTE_API_BASE not configured")
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{REMOTE_API_BASE}{endpoint}"
            if method == "POST":
                async with session.post(url, timeout=aiohttp.ClientTimeout(total=30.0)) as resp:
                    if resp.status in [200, 201]:
                        return await resp.json()
                    else:
                        raise HTTPException(status_code=resp.status, detail=f"Remote API error: {resp.status}")
            else:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30.0)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        raise HTTPException(status_code=resp.status, detail=f"Remote API error: {resp.status}")
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=503, detail=f"Remote API connection error: {str(e)}")


# ============= UTILITY FUNCTIONS =============
def data_changed(old_data: Any, new_data: Any) -> bool:
    """Compare two data structures to detect changes."""
    if old_data is None and new_data is not None:
        return True
    if old_data is not None and new_data is None:
        return True
    return json.dumps(old_data, sort_keys=True) != json.dumps(new_data, sort_keys=True)


async def fetch_account_api(account: AccountConfig, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any] | None:
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
            
            if account.proxy_url:
                request_kwargs["proxy"] = account.proxy_url

            if params:
                request_kwargs["params"] = params
            
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
        error_type = type(e).__name__
        error_msg = str(e) if str(e) else "No error message"
        print(f"❌ [{account.name}][{endpoint}]{proxy_info} {error_type}: {error_msg}")
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
    new_trades = await fetch_account_api(account, "/user/positions/history")
    
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


# ============= EARNED POINTS POLLING =============
def find_last_week_points(data: list) -> float:
    """Find points from the most recent completed epoch (last week)."""
    from datetime import datetime, date, timedelta
    today = date.today()
    last_week_points = 0.0
    latest_end_date = None
    
    for season in data:
        if not isinstance(season, dict):
            continue
        for epoch in season.get('epochRewards', []):
            if not isinstance(epoch, dict):
                continue
            try:
                end_date = datetime.strptime(epoch.get('endDate', ''), '%Y-%m-%d').date()
                if end_date <= today:
                    if latest_end_date is None or end_date > latest_end_date:
                        latest_end_date = end_date
                        last_week_points = float(epoch.get('pointsReward', 0))
            except (ValueError, TypeError):
                continue
    
    return last_week_points


async def fetch_account_points(account: AccountConfig) -> Dict[str, Any] | None:
    """Fetch earned points from Extended Exchange API for a specific account."""
    global POINTS_CACHE, POINTS_LAST_UPDATE
    
    try:
        result = await fetch_account_api(account, "/user/rewards/earned")
        
        if result is not None:
            data = result.get('data', []) if isinstance(result, dict) else []
            total_points = 0.0
            season_points = {}
            
            if isinstance(data, list):
                for season in data:
                    if isinstance(season, dict):
                        season_id = season.get('seasonId', 0)
                        epoch_rewards = season.get('epochRewards', [])
                        season_total = 0.0
                        for epoch in epoch_rewards:
                            if isinstance(epoch, dict):
                                reward = float(epoch.get('pointsReward', 0))
                                season_total += reward
                        season_points[f"season_{season_id}"] = season_total
                        total_points += season_total
            
            last_week = find_last_week_points(data) if isinstance(data, list) else 0.0
            
            POINTS_CACHE[account.id] = {
                "points": total_points,
                "last_week_points": last_week,
                "season_points": season_points,
                "last_update": time.time(),
                "raw_data": result,
                "account_name": account.name
            }
            POINTS_LAST_UPDATE = time.time()
            
            return POINTS_CACHE[account.id]
    except Exception as e:
        print(f"❌ [{account.name}] Points fetch error: {e}")
    
    return None


async def poll_all_accounts_points():
    """Fetch earned points for all accounts in parallel."""
    results = await asyncio.gather(*[
        fetch_account_points(account) for account in ACCOUNTS
    ], return_exceptions=True)
    
    # Count successful fetches
    success_count = sum(1 for r in results if r is not None and not isinstance(r, Exception))
    total_points = sum(
        POINTS_CACHE.get(acc.id, {}).get('points', 0) 
        for acc in ACCOUNTS
    )
    
    print(f"💎 [Points] Updated {success_count}/{len(ACCOUNTS)} accounts | Total: {total_points:,.2f} points")
    
    # Broadcast points update to clients
    await broadcast_to_clients({
        "type": "points_update",
        "accounts": {
            acc.id: POINTS_CACHE.get(acc.id, {"points": 0, "account_name": acc.name})
            for acc in ACCOUNTS
        },
        "total_points": total_points,
        "timestamp": time.time()
    })


async def points_background_poller():
    """
    Background task that polls earned points every 10 minutes.
    Runs independently from the main fast poller.
    """
    print(f"💎 [Points] Background poller started (interval: {POINTS_POLL_INTERVAL}s = 10 min)")
    
    # Initial fetch after 5 seconds
    await asyncio.sleep(5)
    await poll_all_accounts_points()
    
    while True:
        try:
            await asyncio.sleep(POINTS_POLL_INTERVAL)
            await poll_all_accounts_points()
        except Exception as e:
            print(f"❌ [Points] Poller error: {e}")
            await asyncio.sleep(60)  # Wait 1 minute on error


# ============= ORDER BOOK WEBSOCKET CLIENT =============
async def orderbook_websocket_client():
    """
    Connect to Extended Exchange Order Book stream via WebSocket.
    Subscribes to orderbook channel for all configured markets.
    
    Supports optional proxy via ORDERBOOK_PROXY_URL environment variable.
    If proxy is configured, uses aiohttp with SOCKS/HTTP proxy support.
    """
    global ORDERBOOK_CACHE, ORDERBOOK_LAST_UPDATE, ORDERBOOK_WS_CONNECTED
    
    import random
    
    retry_count = 0
    base_delay = 5
    max_delay = 300
    
    proxy_info = f" via proxy" if ORDERBOOK_PROXY_URL else ""
    print(f"📖 [OrderBook] Will connect to {EXTENDED_STREAM_URL}{proxy_info}")
    
    while True:
        connection_was_successful = False
        
        try:
            print(f"📖 [OrderBook] Connecting (attempt {retry_count + 1})...")
            
            if ORDERBOOK_PROXY_URL:
                from aiohttp_socks import ProxyConnector
                connector = ProxyConnector.from_url(ORDERBOOK_PROXY_URL)
                session = aiohttp.ClientSession(connector=connector)
            else:
                session = aiohttp.ClientSession()
            
            try:
                async with session.ws_connect(
                    EXTENDED_STREAM_URL,
                    heartbeat=30,
                    receive_timeout=60
                ) as ws:
                    ORDERBOOK_WS_CONNECTED = True
                    connection_was_successful = True
                    retry_count = 0
                    print(f"✅ [OrderBook] Connected! Subscribing to {len(ORDERBOOK_MARKETS)} markets...")
                    
                    subscribe_msg = {
                        "type": "subscribe",
                        "channel": "orderbook",
                        "markets": ORDERBOOK_MARKETS
                    }
                    await ws.send_str(json.dumps(subscribe_msg))
                    print(f"📨 [OrderBook] Subscribed to: {', '.join(ORDERBOOK_MARKETS)}")
                    
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                
                                if data.get("type") == "orderbook" or data.get("channel") == "orderbook":
                                    market = data.get("market") or data.get("symbol")
                                    if market:
                                        bids = data.get("bids", [])[:ORDERBOOK_DEPTH]
                                        asks = data.get("asks", [])[:ORDERBOOK_DEPTH]
                                        
                                        ORDERBOOK_CACHE[market] = {
                                            "bids": bids,
                                            "asks": asks,
                                            "timestamp": data.get("timestamp") or time.time(),
                                            "sequence": data.get("sequence")
                                        }
                                        ORDERBOOK_LAST_UPDATE = time.time()
                                        
                                        await broadcast_to_clients({
                                            "type": "orderbook_update",
                                            "market": market,
                                            "bids": bids,
                                            "asks": asks,
                                            "timestamp": time.time()
                                        })
                                
                                elif data.get("type") == "subscribed":
                                    print(f"✅ [OrderBook] Subscription confirmed: {data.get('channel')}")
                                
                                elif data.get("type") == "error":
                                    print(f"⚠️ [OrderBook] Stream error: {data.get('message')}")
                                    
                            except json.JSONDecodeError as e:
                                print(f"⚠️ [OrderBook] Invalid JSON: {e}")
                        
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print(f"⚠️ [OrderBook] WebSocket error: {ws.exception()}")
                            break
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            print(f"⚠️ [OrderBook] WebSocket closed by server")
                            break
            finally:
                ORDERBOOK_WS_CONNECTED = False
                await session.close()
                        
        except Exception as e:
            print(f"❌ [OrderBook] WebSocket error: {e}")
        
        ORDERBOOK_WS_CONNECTED = False
        retry_count += 1
        delay = min(base_delay * (2 ** min(retry_count - 1, 6)), max_delay)
        jitter = random.uniform(0.5, 1.5)
        sleep_time = delay * jitter
        print(f"🔄 [OrderBook] Reconnecting in {sleep_time:.1f}s (attempt {retry_count})...")
        await asyncio.sleep(sleep_time)


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


# ============= REYA POLLING =============
async def poll_reya_account_data(account: ReyaAccountConfig):
    cache = REYA_CACHES[account.id]

    positions_task = fetch_reya_api(account, "/positions")
    balance_task = fetch_reya_api(account, "/accountBalances")
    orders_task = fetch_reya_api(account, "/openOrders")
    accounts_task = fetch_reya_api(account, "/accounts")

    raw_positions, raw_balances, raw_orders, raw_accounts = await asyncio.gather(
        positions_task, balance_task, orders_task, accounts_task,
        return_exceptions=True
    )

    changes = []

    if not isinstance(raw_positions, Exception) and raw_positions is not None:
        normalized = normalize_reya_positions(raw_positions)
        cache.positions = normalized
        cache.last_update["positions"] = time.time()
        changes.append("positions")

    if not isinstance(raw_balances, Exception) and raw_balances is not None:
        normalized_balance = normalize_reya_balance(
            raw_balances,
            raw_accounts if not isinstance(raw_accounts, Exception) else None,
            positions=cache.positions
        )
        cache.balance = normalized_balance
        cache.last_update["balance"] = time.time()
        changes.append("balance")

    if not isinstance(raw_orders, Exception) and raw_orders is not None:
        normalized_orders = normalize_reya_orders(raw_orders)
        if data_changed(cache.orders, normalized_orders):
            cache.orders = normalized_orders
            cache.last_update["orders"] = time.time()
            changes.append("orders")

    if not isinstance(raw_accounts, Exception) and raw_accounts is not None:
        cache.accounts = raw_accounts
        cache.last_update["accounts"] = time.time()

    if changes:
        print(f"📊 [{account.name}] Reya changes: {', '.join(changes)}")
        await broadcast_to_clients({
            "type": "account_update",
            "account_id": account.id,
            "account_name": account.name,
            "exchange": "reya",
            "positions": cache.positions if "positions" in changes else None,
            "balance": cache.balance if "balance" in changes else None,
            "orders": cache.orders if "orders" in changes else None,
            "timestamp": time.time()
        })


async def poll_all_reya_accounts():
    if not REYA_ACCOUNTS:
        return
    await fetch_reya_market_prices()
    results = await asyncio.gather(*[
        poll_reya_account_data(account) for account in REYA_ACCOUNTS
    ], return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"❌ [Reya {REYA_ACCOUNTS[i].name}] poll error: {r}")


REYA_POLL_COUNTER = 0
EDGEX_POLL_COUNTER = 0
HIBACHI_POLL_COUNTER = 0
GRVT_POLL_COUNTER = 0
ZERO_ONE_POLL_COUNTER = 0

MARGIN_CHECK_COUNTER = 0  # Check margins every 20 cycles (5 seconds)


# ============= EDGEX POLLING =============
async def poll_edgex_account_data(account: EdgeXAccountConfig):
    cache = EDGEX_CACHES[account.id]

    account_info_task = fetch_edgex_api(
        account, "/api/v1/private/account/getAccountById",
        params={"accountId": account.account_id}
    )
    positions_task = fetch_edgex_api(
        account, "/api/v1/private/account/getPositionByContractId",
        params={"accountId": account.account_id}
    )
    orders_task = fetch_edgex_api(
        account, "/api/v1/private/order/getOrderPage",
        params={"accountId": account.account_id, "size": "50", "status": "OPEN"}
    )

    raw_account_info, raw_positions, raw_orders = await asyncio.gather(
        account_info_task, positions_task, orders_task,
        return_exceptions=True
    )

    changes = []

    if not isinstance(raw_positions, Exception) and raw_positions is not None:
        pos_list = raw_positions if isinstance(raw_positions, list) else []
        normalized = normalize_edgex_positions(pos_list)
        cache.positions = normalized
        cache.last_update["positions"] = time.time()
        changes.append("positions")

    if not isinstance(raw_account_info, Exception) and raw_account_info is not None:
        cache.account_info = raw_account_info
        cache.last_update["account_info"] = time.time()
        normalized_balance = normalize_edgex_balance(raw_account_info, positions=cache.positions)
        cache.balance = normalized_balance
        cache.last_update["balance"] = time.time()
        changes.append("balance")

    if not isinstance(raw_orders, Exception) and raw_orders is not None:
        order_list = raw_orders.get("dataList", []) if isinstance(raw_orders, dict) else (raw_orders if isinstance(raw_orders, list) else [])
        normalized_orders = normalize_edgex_orders(order_list)
        if data_changed(cache.orders, normalized_orders):
            cache.orders = normalized_orders
            cache.last_update["orders"] = time.time()
            changes.append("orders")

    if changes:
        print(f"📊 [{account.name}] EdgeX changes: {', '.join(changes)}")
        await broadcast_to_clients({
            "type": "account_update",
            "account_id": account.id,
            "account_name": account.name,
            "exchange": "edgex",
            "positions": cache.positions if "positions" in changes else None,
            "balance": cache.balance if "balance" in changes else None,
            "orders": cache.orders if "orders" in changes else None,
            "timestamp": time.time()
        })


async def poll_all_edgex_accounts():
    if not EDGEX_ACCOUNTS:
        return
    await fetch_edgex_ticker_prices()
    results = await asyncio.gather(*[
        poll_edgex_account_data(account) for account in EDGEX_ACCOUNTS
    ], return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"❌ [EdgeX {EDGEX_ACCOUNTS[i].name}] poll error: {r}")


# ============= HIBACHI POLLING =============
async def poll_hibachi_account_data(account: HibachiAccountConfig):
    cache = HIBACHI_CACHES[account.id]
    changed = await poll_hibachi_account(account, cache)
    if changed:
        print(f"📊 [{account.name}] Hibachi changes detected")
        await broadcast_to_clients({
            "type": "account_update",
            "account_id": account.id,
            "account_name": account.name,
            "exchange": "hibachi",
            "positions": cache.positions,
            "balance": cache.balance,
            "orders": cache.orders,
            "timestamp": time.time()
        })


async def poll_all_hibachi_accounts():
    if not HIBACHI_ACCOUNTS:
        return
    results = await asyncio.gather(*[
        poll_hibachi_account_data(account) for account in HIBACHI_ACCOUNTS
    ], return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"❌ [Hibachi {HIBACHI_ACCOUNTS[i].name}] poll error: {r}")


async def poll_grvt_account_data(account: GrvtAccountConfig):
    cache = GRVT_CACHES[account.id]
    changed = await poll_grvt_account(account, cache)
    if changed:
        print(f"📊 [{account.name}] GRVT changes detected")
        await broadcast_to_clients({
            "type": "account_update",
            "account_id": account.id,
            "account_name": account.name,
            "exchange": "grvt",
            "positions": cache.positions,
            "balance": cache.balance,
            "orders": cache.orders,
            "timestamp": time.time()
        })


async def poll_all_grvt_accounts():
    if not GRVT_ACCOUNTS:
        return
    results = await asyncio.gather(*[
        poll_grvt_account_data(account) for account in GRVT_ACCOUNTS
    ], return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"❌ [GRVT {GRVT_ACCOUNTS[i].name}] poll error: {r}")


async def poll_01_account_data(account: ZeroOneAccountConfig):
    cache = ZERO_ONE_CACHES[account.id]
    changed = await poll_01_account(account, cache)
    if changed:
        print(f"📊 [{account.name}] 01 Exchange changes detected")
        await broadcast_to_clients({
            "type": "account_update",
            "account_id": account.id,
            "account_name": account.name,
            "exchange": "01exchange",
            "positions": cache.positions,
            "balance": cache.balance,
            "orders": cache.orders,
            "timestamp": time.time()
        })


async def poll_all_01_accounts():
    if not ZERO_ONE_ACCOUNTS:
        return
    results = await asyncio.gather(*[
        poll_01_account_data(account) for account in ZERO_ONE_ACCOUNTS
    ], return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"❌ [01 Exchange {ZERO_ONE_ACCOUNTS[i].name}] poll error: {r}")


async def local_exchange_poller():
    print(f"🚀 [LocalPoller] Started for {len(REYA_ACCOUNTS)} Reya + {len(EDGEX_ACCOUNTS)} EdgeX + {len(HIBACHI_ACCOUNTS)} Hibachi + {len(GRVT_ACCOUNTS)} GRVT + {len(ZERO_ONE_ACCOUNTS)} 01 Exchange accounts")
    if ZERO_ONE_ACCOUNTS:
        await resolve_all_account_ids(ZERO_ONE_ACCOUNTS)
    while True:
        try:
            if REYA_ACCOUNTS:
                await poll_all_reya_accounts()
            if EDGEX_ACCOUNTS:
                await poll_all_edgex_accounts()
            if HIBACHI_ACCOUNTS:
                await poll_all_hibachi_accounts()
            if GRVT_ACCOUNTS:
                await poll_all_grvt_accounts()
            if ZERO_ONE_ACCOUNTS:
                await poll_all_01_accounts()
            await asyncio.sleep(2.0)
        except Exception as e:
            print(f"❌ [LocalPoller] Error: {e}")
            await asyncio.sleep(1.0)


async def background_poller():
    """
    Main background task that continuously polls Extended + Reya API for all accounts.
    
    With proxies per account, rate limiting is avoided.
    - Main loop (2s): positions + balance + orders + trades for all accounts
    - Margin check (6s): check margins and send alerts
    """
    global TRADES_POLL_COUNTER, MARGIN_CHECK_COUNTER, REYA_POLL_COUNTER, EDGEX_POLL_COUNTER, HIBACHI_POLL_COUNTER, GRVT_POLL_COUNTER, ZERO_ONE_POLL_COUNTER
    
    # Count accounts with proxies
    proxied_accounts = sum(1 for a in ACCOUNTS if a.proxy_url)
    print(f"🚀 [Broadcaster] Background poller started for {len(ACCOUNTS)} Extended + {len(REYA_ACCOUNTS)} Reya + {len(EDGEX_ACCOUNTS)} EdgeX + {len(HIBACHI_ACCOUNTS)} Hibachi + {len(GRVT_ACCOUNTS)} GRVT + {len(ZERO_ONE_ACCOUNTS)} 01 Exchange accounts")
    print(f"🔒 Accounts with proxy: {proxied_accounts}/{len(ACCOUNTS)}")
    print(f"⚡ Polling rates: all data 1x/2s, margin check 1x/6s")
    
    if ZERO_ONE_ACCOUNTS:
        await resolve_all_account_ids(ZERO_ONE_ACCOUNTS)
    
    while True:
        try:
            await poll_all_accounts_fast()
            await poll_all_accounts_orders()
            
            REYA_POLL_COUNTER += 1
            if REYA_POLL_COUNTER >= 1:
                await poll_all_reya_accounts()
                REYA_POLL_COUNTER = 0

            EDGEX_POLL_COUNTER += 1
            if EDGEX_POLL_COUNTER >= 1:
                await poll_all_edgex_accounts()
                EDGEX_POLL_COUNTER = 0

            HIBACHI_POLL_COUNTER += 1
            if HIBACHI_POLL_COUNTER >= 1:
                await poll_all_hibachi_accounts()
                HIBACHI_POLL_COUNTER = 0

            GRVT_POLL_COUNTER += 1
            if GRVT_POLL_COUNTER >= 1:
                await poll_all_grvt_accounts()
                GRVT_POLL_COUNTER = 0

            ZERO_ONE_POLL_COUNTER += 1
            if ZERO_ONE_POLL_COUNTER >= 1:
                await poll_all_01_accounts()
                ZERO_ONE_POLL_COUNTER = 0
            
            TRADES_POLL_COUNTER += 1
            if TRADES_POLL_COUNTER >= 1:
                await poll_all_accounts_trades()
                TRADES_POLL_COUNTER = 0
            
            MARGIN_CHECK_COUNTER += 1
            if MARGIN_CHECK_COUNTER >= 3:
                await check_margins_and_alert()
                MARGIN_CHECK_COUNTER = 0
            
            await asyncio.sleep(2.0)
            
        except Exception as e:
            print(f"❌ [Broadcaster] Poller error: {e}")
            await asyncio.sleep(0.5)


async def startup_alert_test():
    """Wysyła testowy alert przy starcie serwera"""
    await asyncio.sleep(5)  # Poczekaj 5 sekund aż serwer się w pełni uruchomi
    try:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        test_message = f"🚀 SERWER URUCHOMIONY 🚀\nBackend Extended Broadcaster\nStart: {timestamp}\nAlertymarginowe: AKTYWNE"
        
        # Wyślij tylko na Telegram (wystarczy do potwierdzenia)
        result = await alert_manager.send_telegram(test_message)
        if result:
            print("✅ [Startup] Testowy alert wysłany na Telegram")
        else:
            print("⚠️ [Startup] Nie udało się wysłać testowego alertu na Telegram")
    except Exception as e:
        print(f"❌ [Startup] Błąd testu alertów: {e}")


# ============= STARTUP EVENT =============
@app.on_event("startup")
async def startup_broadcaster():
    if IS_FRONTEND_ONLY:
        print(f"🌐 [Startup] FRONTEND_ONLY mode - proxying Extended to {REMOTE_API_BASE}")
        if REYA_ACCOUNTS or EDGEX_ACCOUNTS or HIBACHI_ACCOUNTS or GRVT_ACCOUNTS:
            asyncio.create_task(local_exchange_poller())
            print(f"✅ [Startup] Local poller started for {len(REYA_ACCOUNTS)} Reya + {len(EDGEX_ACCOUNTS)} EdgeX + {len(HIBACHI_ACCOUNTS)} Hibachi + {len(GRVT_ACCOUNTS)} GRVT accounts")
        print("✅ [Startup] Frontend-only broadcaster initialized")
        return
    
    print(f"⚡ [Startup] Initializing multi-account broadcaster for {len(ACCOUNTS)} accounts...")
    
    # Initialize Supabase persistence
    if supabase_client.initialize():
        print("✅ [Startup] Supabase persistence enabled")
    else:
        print("⚠️ [Startup] Supabase persistence disabled (no credentials)")
    
    asyncio.create_task(background_poller())
    asyncio.create_task(orderbook_websocket_client())
    asyncio.create_task(points_background_poller())
    asyncio.create_task(trade_history_background_poller())
    print("✅ [Startup] Broadcaster initialized with Order Book stream + Points tracking + Trade History")
    
    # Automatyczny test alertów przy starcie - wyśle testowy alert na Telegram
    asyncio.create_task(startup_alert_test())


# ============= REST API ENDPOINTS =============
@app.get("/health")
async def health_check():
    if IS_FRONTEND_ONLY:
        return {
            "status": "ok",
            "service": "extended-multi-account-broadcaster",
            "mode": "FRONTEND_ONLY",
            "remote_api": REMOTE_API_BASE
        }
    
    return {
        "status": "ok",
        "service": "extended-multi-account-broadcaster",
        "mode": "COLLECTOR",
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
    if IS_FRONTEND_ONLY:
        remote_data = await proxy_to_remote("/api/cached-accounts")
        if (REYA_ACCOUNTS or EDGEX_ACCOUNTS or HIBACHI_ACCOUNTS or GRVT_ACCOUNTS) and isinstance(remote_data, dict):
            current_time = time.time()
            accounts = remote_data.get("accounts", {})
            for account in REYA_ACCOUNTS:
                cache = REYA_CACHES[account.id]
                accounts[account.id] = {
                    "id": account.id,
                    "name": account.name,
                    "exchange": "reya",
                    "positions": cache.positions,
                    "balance": cache.balance,
                    "trades": [],
                    "orders": cache.orders,
                    "cache_age_ms": {
                        "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
                        "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
                        "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
                    },
                    "last_update": cache.last_update.copy()
                }
            for account in EDGEX_ACCOUNTS:
                cache = EDGEX_CACHES[account.id]
                accounts[account.id] = {
                    "id": account.id,
                    "name": account.name,
                    "exchange": "edgex",
                    "positions": cache.positions,
                    "balance": cache.balance,
                    "trades": [],
                    "orders": cache.orders,
                    "cache_age_ms": {
                        "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
                        "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
                        "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
                    },
                    "last_update": cache.last_update.copy()
                }
            for account in HIBACHI_ACCOUNTS:
                cache = HIBACHI_CACHES[account.id]
                accounts[account.id] = {
                    "id": account.id,
                    "name": account.name,
                    "exchange": "hibachi",
                    "positions": cache.positions,
                    "balance": cache.balance,
                    "trades": [],
                    "orders": cache.orders,
                    "cache_age_ms": {
                        "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
                        "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
                        "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
                    },
                    "last_update": cache.last_update.copy()
                }
            for account in GRVT_ACCOUNTS:
                cache = GRVT_CACHES[account.id]
                accounts[account.id] = {
                    "id": account.id,
                    "name": account.name,
                    "exchange": "grvt",
                    "positions": cache.positions,
                    "balance": cache.balance,
                    "trades": [],
                    "orders": cache.orders,
                    "cache_age_ms": {
                        "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
                        "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
                        "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
                    },
                    "last_update": cache.last_update.copy()
                }
            for account in ZERO_ONE_ACCOUNTS:
                cache = ZERO_ONE_CACHES[account.id]
                accounts[account.id] = {
                    "id": account.id,
                    "name": account.name,
                    "exchange": "01exchange",
                    "positions": cache.positions,
                    "balance": cache.balance,
                    "trades": [],
                    "orders": cache.orders,
                    "cache_age_ms": {
                        "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
                        "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
                        "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
                    },
                    "last_update": cache.last_update.copy()
                }
            remote_data["accounts"] = accounts
            remote_data["total_accounts"] = len(accounts)
        return remote_data
    
    current_time = time.time()
    
    accounts_data = {}
    for account in ACCOUNTS:
        cache = BROADCASTER_CACHES[account.id]
        accounts_data[account.id] = {
            "id": account.id,
            "name": account.name,
            "exchange": "extended",
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

    for account in REYA_ACCOUNTS:
        cache = REYA_CACHES[account.id]
        accounts_data[account.id] = {
            "id": account.id,
            "name": account.name,
            "exchange": "reya",
            "positions": cache.positions,
            "balance": cache.balance,
            "trades": [],
            "orders": cache.orders,
            "cache_age_ms": {
                "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
                "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
                "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
            },
            "last_update": cache.last_update.copy()
        }

    for account in EDGEX_ACCOUNTS:
        cache = EDGEX_CACHES[account.id]
        accounts_data[account.id] = {
            "id": account.id,
            "name": account.name,
            "exchange": "edgex",
            "positions": cache.positions,
            "balance": cache.balance,
            "trades": [],
            "orders": cache.orders,
            "cache_age_ms": {
                "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
                "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
                "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
            },
            "last_update": cache.last_update.copy()
        }

    for account in HIBACHI_ACCOUNTS:
        cache = HIBACHI_CACHES[account.id]
        accounts_data[account.id] = {
            "id": account.id,
            "name": account.name,
            "exchange": "hibachi",
            "positions": cache.positions,
            "balance": cache.balance,
            "trades": [],
            "orders": cache.orders,
            "cache_age_ms": {
                "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
                "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
                "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
            },
            "last_update": cache.last_update.copy()
        }

    for account in GRVT_ACCOUNTS:
        cache = GRVT_CACHES[account.id]
        accounts_data[account.id] = {
            "id": account.id,
            "name": account.name,
            "exchange": "grvt",
            "positions": cache.positions,
            "balance": cache.balance,
            "trades": [],
            "orders": cache.orders,
            "cache_age_ms": {
                "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
                "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
                "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
            },
            "last_update": cache.last_update.copy()
        }

    for account in ZERO_ONE_ACCOUNTS:
        cache = ZERO_ONE_CACHES[account.id]
        accounts_data[account.id] = {
            "id": account.id,
            "name": account.name,
            "exchange": "01exchange",
            "positions": cache.positions,
            "balance": cache.balance,
            "trades": [],
            "orders": cache.orders,
            "cache_age_ms": {
                "positions": int((current_time - cache.last_update["positions"]) * 1000) if cache.last_update["positions"] > 0 else None,
                "balance": int((current_time - cache.last_update["balance"]) * 1000) if cache.last_update["balance"] > 0 else None,
                "orders": int((current_time - cache.last_update["orders"]) * 1000) if cache.last_update["orders"] > 0 else None,
            },
            "last_update": cache.last_update.copy()
        }

    return {
        "accounts": accounts_data,
        "total_accounts": len(ACCOUNTS) + len(REYA_ACCOUNTS) + len(EDGEX_ACCOUNTS) + len(HIBACHI_ACCOUNTS) + len(GRVT_ACCOUNTS) + len(ZERO_ONE_ACCOUNTS),
        "timestamp": current_time
    }


@app.get("/api/cached-account")
async def get_cached_account():
    """
    Return cached data for the first/primary account (backward compatibility).
    """
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/cached-account")
    
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
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote(f"/api/cached-account/{account_id}")
    
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
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/broadcaster/stats")
    
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
                "exchange": "extended",
                "positions": cache.positions,
                "balance": cache.balance,
                "trades": cache.trades,
                "orders": cache.orders,
            }

        for account in REYA_ACCOUNTS:
            cache = REYA_CACHES[account.id]
            accounts_snapshot[account.id] = {
                "id": account.id,
                "name": account.name,
                "exchange": "reya",
                "positions": cache.positions,
                "balance": cache.balance,
                "trades": [],
                "orders": cache.orders,
            }

        for account in EDGEX_ACCOUNTS:
            cache = EDGEX_CACHES[account.id]
            accounts_snapshot[account.id] = {
                "id": account.id,
                "name": account.name,
                "exchange": "edgex",
                "positions": cache.positions,
                "balance": cache.balance,
                "trades": [],
                "orders": cache.orders,
            }

        for account in HIBACHI_ACCOUNTS:
            cache = HIBACHI_CACHES[account.id]
            accounts_snapshot[account.id] = {
                "id": account.id,
                "name": account.name,
                "exchange": "hibachi",
                "positions": cache.positions,
                "balance": cache.balance,
                "trades": [],
                "orders": cache.orders,
            }

        for account in GRVT_ACCOUNTS:
            cache = GRVT_CACHES[account.id]
            accounts_snapshot[account.id] = {
                "id": account.id,
                "name": account.name,
                "exchange": "grvt",
                "positions": cache.positions,
                "balance": cache.balance,
                "trades": [],
                "orders": cache.orders,
            }

        for account in ZERO_ONE_ACCOUNTS:
            cache = ZERO_ONE_CACHES[account.id]
            accounts_snapshot[account.id] = {
                "id": account.id,
                "name": account.name,
                "exchange": "01exchange",
                "positions": cache.positions,
                "balance": cache.balance,
                "trades": [],
                "orders": cache.orders,
            }

        snapshot = {
            "type": "snapshot",
            "accounts": accounts_snapshot,
            "total_accounts": len(ACCOUNTS) + len(REYA_ACCOUNTS) + len(EDGEX_ACCOUNTS) + len(HIBACHI_ACCOUNTS) + len(GRVT_ACCOUNTS) + len(ZERO_ONE_ACCOUNTS),
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
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote(f"/api/account/{account_id}/history?limit={limit}")
    
    if not supabase_client.is_initialized:
        raise HTTPException(status_code=503, detail="Supabase persistence not enabled")
    
    history = await supabase_client.get_account_history(account_id, limit, exchange="extended")
    return {"account_id": account_id, "history": history, "count": len(history)}


@app.get("/api/trades/recent")
async def get_recent_trades(account_id: Optional[int] = None, limit: int = 100):
    """Get recent trades from Supabase."""
    if IS_FRONTEND_ONLY:
        query = f"/api/trades/recent?limit={limit}"
        if account_id is not None:
            query += f"&account_id={account_id}"
        return await proxy_to_remote(query)
    
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
    if IS_FRONTEND_ONLY:
        query = "/api/stats/periods"
        if account_id is not None:
            query += f"?account_id={account_id}"
        return await proxy_to_remote(query)
    
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
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/stats/summary")
    
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
    if IS_FRONTEND_ONLY:
        query = f"/api/trades?limit={limit}"
        if account_id is not None:
            query += f"&account_id={account_id}"
        return await proxy_to_remote(query)
    
    if not supabase_client.is_initialized:
        raise HTTPException(status_code=503, detail="Supabase persistence not enabled")
    
    trades = await supabase_client.get_trades_list(limit=limit, account_index=account_id)
    return {
        "account_id": account_id,
        "trades": trades,
        "count": len(trades),
        "timestamp": time.time()
    }


# ============= ORDER BOOK ENDPOINTS =============
@app.get("/api/orderbook")
async def get_orderbook():
    """
    Get cached order book data for all markets.
    Real-time data from Extended Exchange WebSocket stream.
    """
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/orderbook")
    
    return {
        "markets": ORDERBOOK_CACHE,
        "connected": ORDERBOOK_WS_CONNECTED,
        "last_update": ORDERBOOK_LAST_UPDATE,
        "cache_age_ms": int((time.time() - ORDERBOOK_LAST_UPDATE) * 1000) if ORDERBOOK_LAST_UPDATE > 0 else None,
        "subscribed_markets": ORDERBOOK_MARKETS,
        "timestamp": time.time()
    }


@app.get("/api/orderbook/{market}")
async def get_orderbook_market(market: str):
    """
    Get cached order book data for a specific market.
    Example: /api/orderbook/ETH-PERP
    """
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote(f"/api/orderbook/{market}")
    
    market_upper = market.upper()
    
    if market_upper not in ORDERBOOK_CACHE:
        available = list(ORDERBOOK_CACHE.keys()) if ORDERBOOK_CACHE else ORDERBOOK_MARKETS
        raise HTTPException(
            status_code=404, 
            detail=f"Market {market_upper} not found. Available: {', '.join(available)}"
        )
    
    book = ORDERBOOK_CACHE[market_upper]
    return {
        "market": market_upper,
        "bids": book.get("bids", []),
        "asks": book.get("asks", []),
        "sequence": book.get("sequence"),
        "last_update": book.get("timestamp"),
        "connected": ORDERBOOK_WS_CONNECTED,
        "timestamp": time.time()
    }


@app.get("/api/orderbook-status")
async def get_orderbook_status():
    """Get order book WebSocket connection status."""
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/orderbook-status")
    
    return {
        "connected": ORDERBOOK_WS_CONNECTED,
        "stream_url": EXTENDED_STREAM_URL,
        "subscribed_markets": ORDERBOOK_MARKETS,
        "cached_markets": list(ORDERBOOK_CACHE.keys()),
        "last_update": ORDERBOOK_LAST_UPDATE,
        "cache_age_ms": int((time.time() - ORDERBOOK_LAST_UPDATE) * 1000) if ORDERBOOK_LAST_UPDATE > 0 else None,
        "timestamp": time.time()
    }


# ============= EARNED POINTS ENDPOINTS =============
@app.get("/api/points")
async def get_earned_points():
    """
    Get earned points for all accounts.
    Points are fetched from Extended Exchange API every 10 minutes.
    
    Returns:
        - accounts: Dict of account_id -> {points, account_name, last_update}
        - total_points: Sum of all points across accounts
        - last_update: Timestamp of last successful fetch
    """
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/points")
    
    total_points = sum(
        data.get('points', 0) 
        for data in POINTS_CACHE.values()
    )
    total_last_week = sum(
        data.get('last_week_points', 0)
        for data in POINTS_CACHE.values()
    )
    
    return {
        "accounts": {
            acc.id: {
                "account_name": acc.name,
                "points": POINTS_CACHE.get(acc.id, {}).get('points', 0),
                "last_week_points": POINTS_CACHE.get(acc.id, {}).get('last_week_points', 0),
                "last_update": POINTS_CACHE.get(acc.id, {}).get('last_update', 0)
            }
            for acc in ACCOUNTS
        },
        "total_points": total_points,
        "total_last_week_points": total_last_week,
        "last_update": POINTS_LAST_UPDATE,
        "cache_age_seconds": int(time.time() - POINTS_LAST_UPDATE) if POINTS_LAST_UPDATE > 0 else None,
        "poll_interval_seconds": POINTS_POLL_INTERVAL,
        "timestamp": time.time()
    }


@app.get("/api/points/{account_index}")
async def get_account_points(account_index: int):
    """Get earned points for a specific account by index."""
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote(f"/api/points/{account_index}")
    
    account_id = f"account_{account_index}"
    
    if account_id not in POINTS_CACHE:
        # Try to find account and return 0 if exists but not yet fetched
        account = next((a for a in ACCOUNTS if a.id == account_id), None)
        if account:
            return {
                "account_id": account_id,
                "account_name": account.name,
                "points": 0,
                "last_update": 0,
                "message": "Points not yet fetched"
            }
        raise HTTPException(status_code=404, detail=f"Account {account_index} not found")
    
    data = POINTS_CACHE[account_id]
    return {
        "account_id": account_id,
        "account_name": data.get('account_name', f'Account {account_index}'),
        "points": data.get('points', 0),
        "last_update": data.get('last_update', 0),
        "raw_data": data.get('raw_data')
    }


@app.post("/api/points/refresh")
async def refresh_points():
    """Force refresh of earned points for all accounts."""
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/points/refresh", method="POST")
    
    await poll_all_accounts_points()
    
    total_points = sum(
        data.get('points', 0) 
        for data in POINTS_CACHE.values()
    )
    
    return {
        "success": True,
        "message": "Points refreshed for all accounts",
        "total_points": total_points,
        "accounts_updated": len(POINTS_CACHE),
        "timestamp": time.time()
    }


# ============= MARGIN ALERTS ENDPOINTS =============
@app.get("/api/alerts/status")
async def get_alerts_status():
    """Get margin alert system status and configuration."""
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/alerts/status")
    
    return {
        "enabled": True,
        "thresholds": MARGIN_THRESHOLDS,
        "channels": {
            "telegram": bool(alert_manager.config.telegram_bot_token and alert_manager.config.telegram_chat_id),
            "pushover": bool(alert_manager.config.pushover_app_token and alert_manager.config.pushover_user_key),
            "sms": bool(alert_manager.config.twilio_account_sid and alert_manager.config.twilio_api_key_sid),
            "phone": bool(alert_manager.config.phone_number)
        },
        "cooldown_minutes": alert_manager.state.cooldown_minutes,
        "active_alerts": len(alert_manager.state.sent_alerts),
        "timestamp": time.time()
    }


@app.get("/api/alerts/config")
async def get_alerts_config():
    """Get detailed configuration status for all alert channels."""
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/alerts/config")
    
    config_status = alert_manager.get_config_status()
    print(f"📋 [Alerts] Config status requested: {config_status}")
    return {
        "config": config_status,
        "timestamp": time.time()
    }


@app.post("/api/alerts/test")
async def test_alerts():
    """Test all notification channels."""
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/alerts/test", method="POST")
    
    print("🧪 [Alerts] Starting test of all channels...")
    print(f"📋 [Alerts] Config: {alert_manager.get_config_status()}")
    
    results = await alert_manager.test_all_channels()
    
    print(f"📊 [Alerts] Test results: telegram={results['telegram']}, pushover={results['pushover']}, sms={results['sms']}, phone={results['phone_call']}")
    
    return {
        "success": any([results["telegram"], results["pushover"], results["sms"], results["phone_call"]]),
        "results": results,
        "config": alert_manager.get_config_status(),
        "timestamp": time.time()
    }


@app.post("/api/alerts/test-telegram")
async def test_telegram_only():
    """Test only Telegram channel with detailed logs."""
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/alerts/test-telegram", method="POST")
    
    print("🧪 [Alerts] Testing Telegram only...")
    result = await alert_manager.test_telegram_only()
    print(f"📊 [Alerts] Telegram test result: {result}")
    
    return {
        **result,
        "timestamp": time.time()
    }


@app.get("/api/alerts/margins")
async def get_current_margins():
    """Get current margin ratios for all accounts."""
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/alerts/margins")
    
    margins = []
    for account in ACCOUNTS:
        cache = BROADCASTER_CACHES.get(account.id)
        if cache and cache.balance:
            balance_data = cache.balance.get("data", {}) if isinstance(cache.balance, dict) else {}
            margin_ratio = float(balance_data.get("marginRatio", 0))
            equity = float(balance_data.get("equity", 0))
            margins.append({
                "account_id": account.id,
                "account_name": account.name,
                "margin_ratio": margin_ratio,
                "margin_percent": round(margin_ratio * 100, 2),
                "equity": round(equity, 2),
                "threshold_triggered": alert_manager.get_threshold_level(margin_ratio)
            })
    
    return {
        "accounts": margins,
        "thresholds": MARGIN_THRESHOLDS,
        "timestamp": time.time()
    }


async def check_margins_and_alert():
    """Check all account margins and send alerts if needed."""
    for account in ACCOUNTS:
        cache = BROADCASTER_CACHES.get(account.id)
        if cache and cache.balance:
            balance_data = cache.balance.get("data", {}) if isinstance(cache.balance, dict) else {}
            margin_ratio = float(balance_data.get("marginRatio", 0))
            equity = float(balance_data.get("equity", 0))
            
            has_positions = False
            if cache.positions:
                if isinstance(cache.positions, dict):
                    pd = cache.positions.get("data", [])
                    if isinstance(pd, list):
                        has_positions = len(pd) > 0
                elif isinstance(cache.positions, list):
                    has_positions = len(cache.positions) > 0
            
            if margin_ratio > 0 or not has_positions:
                try:
                    result = await alert_manager.check_and_alert(
                        account.id, 
                        account.name, 
                        margin_ratio, 
                        equity,
                        has_positions=has_positions
                    )
                    if result.get("alerts_sent"):
                        print(f"🚨 Alert sent for {account.name}: margin={margin_ratio:.4f} has_pos={has_positions} channels={result['alerts_sent']}")
                except Exception as e:
                    print(f"❌ Error checking margin for {account.name}: {e}")


# ============= TRADE HISTORY ENDPOINTS =============
TRADE_HISTORY_POLL_INTERVAL = 600  # 10 minutes
TRADE_HISTORY_LAST_UPDATE = 0

async def trade_history_background_poller():
    global TRADE_HISTORY_LAST_UPDATE
    await asyncio.sleep(10)
    print("📊 [TradeHistory] Background poller started (every 10 minutes)")
    while True:
        try:
            saved_pos = await trade_history.fetch_and_store_all_trades(ACCOUNTS, fetch_account_api)
            saved_ord = await trade_history.fetch_and_store_all_orders(ACCOUNTS, fetch_account_api)
            TRADE_HISTORY_LAST_UPDATE = time.time()
            print(f"📊 [TradeHistory] Cycle complete, {saved_pos} positions + {saved_ord} orders saved")
        except Exception as e:
            print(f"❌ [TradeHistory] Error: {e}")
        await asyncio.sleep(TRADE_HISTORY_POLL_INTERVAL)


@app.get("/api/trade-history/epochs")
async def get_trade_history_epochs():
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/trade-history/epochs")
    try:
        epochs = await trade_history.get_available_epochs()
        return {"epochs": epochs, "last_update": TRADE_HISTORY_LAST_UPDATE}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trade-history/epoch/{epoch_number}")
async def get_trade_history_epoch(epoch_number: int):
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote(f"/api/trade-history/epoch/{epoch_number}")
    try:
        current_epoch = trade_history.get_epoch_number(datetime.utcnow())
        points_data = {
            "accounts": {
                acc.id: {
                    "account_name": acc.name,
                    "points": POINTS_CACHE.get(acc.id, {}).get('points', 0),
                    "last_week_points": POINTS_CACHE.get(acc.id, {}).get('last_week_points', 0),
                }
                for acc in ACCOUNTS
            },
            "total_last_week_points": sum(d.get('last_week_points', 0) for d in POINTS_CACHE.values()),
        }
        stats = await trade_history.get_epoch_stats(epoch_number, points_data, current_epoch=current_epoch)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trade-history/account/{epoch_number}/{account_index}")
async def get_trade_history_account(epoch_number: int, account_index: int):
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote(f"/api/trade-history/account/{epoch_number}/{account_index}")
    try:
        trades = await trade_history.get_account_trades(epoch_number, account_index)
        return {"trades": trades, "count": len(trades)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trade-history/stats")
async def get_trade_history_db_stats():
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/trade-history/stats")
    try:
        stats = await trade_history.get_db_stats()
        stats["last_poll"] = TRADE_HISTORY_LAST_UPDATE
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trade-history/regression")
async def get_regression():
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/trade-history/regression")
    try:
        current_epoch = trade_history.get_epoch_number(datetime.utcnow())
        points_data = {
            "accounts": {
                acc.id: {
                    "account_name": acc.name,
                    "points": POINTS_CACHE.get(acc.id, {}).get('points', 0),
                    "last_week_points": POINTS_CACHE.get(acc.id, {}).get('last_week_points', 0),
                }
                for acc in ACCOUNTS
            },
            "total_last_week_points": sum(d.get('last_week_points', 0) for d in POINTS_CACHE.values()),
        }
        result = await trade_history.get_regression_analysis(points_data, current_epoch)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trade-history/debug/{account_index}")
async def debug_trade_data(account_index: int):
    acc = next((a for a in ACCOUNTS if int(a.id.split('_')[1]) == account_index), None)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    
    positions = await fetch_account_api(acc, '/user/positions/history', params={"limit": 1000, "offset": 0})
    orders = await fetch_account_api(acc, '/user/orders/history', params={"limit": 100, "offset": 0})
    
    pos_data = positions.get('data', []) if positions else []
    ord_data = orders.get('data', []) if orders else []
    
    total_vol_size = sum(abs(float(p.get('size', 0)) * float(p.get('openPrice', 0))) for p in pos_data)
    total_vol_max = sum(abs(float(p.get('maxPositionSize', 0)) * float(p.get('openPrice', 0))) for p in pos_data)
    total_vol_max_close = sum(
        abs(float(p.get('maxPositionSize', 0)) * float(p.get('exitPrice', 0))) 
        for p in pos_data if p.get('exitPrice')
    )
    
    ord_volume = 0
    for o in ord_data:
        filled = float(o.get('filledSize', 0) or 0)
        price = float(o.get('avgFillPrice', 0) or o.get('price', 0) or 0)
        ord_volume += abs(filled * price)
    
    return {
        "account_index": account_index,
        "positions_count": len(pos_data),
        "orders_count": len(ord_data),
        "volume_size_x_price": round(total_vol_size, 2),
        "volume_maxpos_x_openprice": round(total_vol_max, 2),
        "volume_maxpos_x_exitprice": round(total_vol_max_close, 2),
        "volume_open_plus_close": round(total_vol_max + total_vol_max_close, 2),
        "orders_volume": round(ord_volume, 2),
        "sample_positions": pos_data[:2],
        "sample_orders": ord_data[:2],
    }


@app.post("/api/trade-history/refresh")
async def refresh_trade_history(full: bool = False):
    if IS_FRONTEND_ONLY:
        return await proxy_to_remote("/api/trade-history/refresh", method="POST")
    try:
        if full:
            pool = await trade_history.get_db_pool()
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM trade_positions")
                await conn.execute("DELETE FROM trade_orders")
                print(f"🗑️ [TradeHistory] Cleared all data for full refresh")
        saved_pos = await trade_history.fetch_and_store_all_trades(ACCOUNTS, fetch_account_api)
        saved_ord = await trade_history.fetch_and_store_all_orders(ACCOUNTS, fetch_account_api)
        global TRADE_HISTORY_LAST_UPDATE
        TRADE_HISTORY_LAST_UPDATE = time.time()
        return {
            "success": True,
            "positions_saved": saved_pos,
            "orders_saved": saved_ord,
            "full_refresh": full,
            "timestamp": time.time(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= STATIC FILES FOR PRODUCTION =============
# Serve frontend static files in production
DIST_DIR = Path(__file__).parent.parent / "dist"
if DIST_DIR.exists():
    print(f"📁 Serving static files from: {DIST_DIR}")
    # Mount static assets (js, css, images)
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")
    
    # Catch-all route for SPA - must be after all API routes
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        """Serve the frontend SPA for non-API routes"""
        # Don't intercept API, WebSocket, or asset routes
        if full_path.startswith(("api/", "ws/", "assets/")):
            raise HTTPException(status_code=404)
        
        index_file = DIST_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Frontend not built")
else:
    print(f"⚠️ Static files directory not found: {DIST_DIR}")
    print("   Frontend will not be served. Run 'npm run build' in MergedApp/")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
